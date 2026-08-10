from datetime import datetime

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncHour
from django.utils.text import slugify
from django_tasks import task

from actions.models import ActionRecord
from dashboard.models import Granularity, MetricBucket
from evaluate.models import EvaluationRecord, Verdict
from ingest.models import IngestLogEntry

_TRUNC = {Granularity.HOUR: TruncHour, Granularity.DAY: TruncDay}


def _snap(since, granularity):
    """Floor `since` to the start of its bucket, so an incremental rollup always
    re-covers the entire bucket `since` falls in rather than a partial one --
    otherwise `_upsert` overwrites a previously complete bucket with a fragment."""
    if since is None:
        return None
    if granularity == Granularity.HOUR:
        return since.replace(minute=0, second=0, microsecond=0)
    return since.replace(hour=0, minute=0, second=0, microsecond=0)


def _upsert(rows):
    if rows:
        MetricBucket.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["granularity", "bucket_start", "metric_key"],
            update_fields=["count"],
        )


def _rollup_evaluations(granularity, since):
    trunc = _TRUNC[granularity]
    since = _snap(since, granularity)
    qs = EvaluationRecord.objects.all()
    if since is not None:
        qs = qs.filter(processed_at__gte=since)
    qs = qs.annotate(bucket=trunc("processed_at"))

    rows = []
    for entry in qs.values("bucket").annotate(n=Count("id")):
        rows.append(MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                                  metric_key="processed.total", count=entry["n"]))
    for entry in qs.values("bucket", "item_type").annotate(n=Count("id")):
        rows.append(MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                                  metric_key=f"processed.{entry['item_type']}", count=entry["n"]))
    for entry in qs.values("bucket", "verdict").annotate(n=Count("id")):
        rows.append(MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                                  metric_key=f"verdict.{entry['verdict']}", count=entry["n"]))

    flagged_qs = qs.filter(verdict=Verdict.FLAGGED)
    for entry in flagged_qs.values("bucket", "item_type").annotate(n=Count("id")):
        rows.append(MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                                  metric_key=f"flagged.{entry['item_type']}", count=entry["n"]))

    cat_qs = qs.filter(verdict=Verdict.FLAGGED).exclude(category="")
    for entry in cat_qs.values("bucket", "category").annotate(n=Count("id")):
        rows.append(MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                                  metric_key=f"category.{slugify(entry['category']) or 'uncategorized'}",
                                  count=entry["n"]))
    _upsert(rows)


def _rollup_ingested(granularity, since):
    trunc = _TRUNC[granularity]
    since = _snap(since, granularity)
    qs = IngestLogEntry.objects.all()
    if since is not None:
        qs = qs.filter(fetched_at__gte=since)
    qs = qs.annotate(bucket=trunc("fetched_at"))

    rows = [
        MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                      metric_key=f"ingested.{entry['item_type']}", count=entry["n"])
        for entry in qs.values("bucket", "item_type").annotate(n=Count("id"))
    ]
    _upsert(rows)


def _rollup_actions(granularity, since):
    trunc = _TRUNC[granularity]
    since = _snap(since, granularity)
    qs = ActionRecord.objects.all()
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    qs = qs.annotate(bucket=trunc("created_at"))

    rows = [
        MetricBucket(granularity=granularity, bucket_start=entry["bucket"],
                      metric_key=f"action.{entry['status']}", count=entry["n"])
        for entry in qs.values("bucket", "status").annotate(n=Count("id"))
    ]
    _upsert(rows)


def run_rollup(since: datetime | None = None) -> None:
    """Recompute hourly and daily MetricBucket rows. Idempotent (upserts on
    (granularity, bucket_start, metric_key)); since=None recomputes all
    history (one-time backfill), a cutoff makes incremental runs cheap."""
    for granularity in (Granularity.HOUR, Granularity.DAY):
        _rollup_ingested(granularity, since)
        _rollup_evaluations(granularity, since)
        _rollup_actions(granularity, since)


@task(queue_name=settings.TASK_QUEUE_DASHBOARD)
def rollup_metrics_task(since_iso: str | None = None) -> None:
    run_rollup(datetime.fromisoformat(since_iso) if since_iso else None)
