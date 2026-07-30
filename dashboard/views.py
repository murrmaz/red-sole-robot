from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from dashboard.models import Granularity, MetricBucket
from evaluate.models import EvaluationRecord, ItemType, Verdict
from ingest.models import IngestLogEntry, RawItem

METRIC_LABELS = {
    "post": {
        "ingested.post": "Ingested",
        "processed.post": "Evaluated",
        "flagged.post": "Flagged",
    },
    "comment": {
        "ingested.comment": "Ingested",
        "processed.comment": "Evaluated",
        "flagged.comment": "Flagged",
    },
}


@login_required
@staff_member_required
def home(request):
    return render(request, "dashboard/home.html")


@login_required
@staff_member_required
def metrics_data(request):
    item_type = request.GET.get("item_type")
    if item_type not in METRIC_LABELS:
        return HttpResponseBadRequest("item_type must be 'post' or 'comment'")
    labels = METRIC_LABELS[item_type]

    granularity = request.GET.get("granularity", Granularity.HOUR)
    if granularity not in Granularity.values:
        granularity = Granularity.HOUR
    days = int(request.GET.get("days", 7 if granularity == Granularity.HOUR else 30))
    since = timezone.now() - timedelta(days=days)

    rows = MetricBucket.objects.filter(
        granularity=granularity, bucket_start__gte=since, metric_key__in=labels,
    ).order_by("bucket_start")

    series = {k: {} for k in labels}
    for row in rows:
        series[row.metric_key][row.bucket_start.isoformat()] = row.count
    bucket_labels = sorted({b for s in series.values() for b in s})
    datasets = [
        {"label": label, "metric": key, "data": [series[key].get(b, 0) for b in bucket_labels]}
        for key, label in labels.items()
    ]
    return JsonResponse({"labels": bucket_labels, "datasets": datasets, "granularity": granularity})


@login_required
@staff_member_required
def bucket_items(request):
    item_type = request.GET.get("item_type")
    if item_type not in ItemType.values:
        return HttpResponseBadRequest("item_type must be 'post' or 'comment'")

    metric = request.GET.get("metric")
    if metric not in ("ingested", "processed", "flagged"):
        return HttpResponseBadRequest("metric must be 'ingested', 'processed', or 'flagged'")

    granularity = request.GET.get("granularity")
    if granularity not in Granularity.values:
        return HttpResponseBadRequest("granularity must be 'hour' or 'day'")

    bucket_start = parse_datetime(request.GET.get("bucket_start", ""))
    if bucket_start is None:
        return HttpResponseBadRequest("bucket_start must be an ISO datetime")
    bucket_end = bucket_start + (timedelta(hours=1) if granularity == Granularity.HOUR else timedelta(days=1))

    if metric == "ingested":
        records = IngestLogEntry.objects.filter(
            item_type=item_type, fetched_at__gte=bucket_start, fetched_at__lt=bucket_end,
        ).order_by("-fetched_at")
    else:
        records = EvaluationRecord.objects.filter(
            item_type=item_type, processed_at__gte=bucket_start, processed_at__lt=bucket_end,
        ).order_by("-processed_at")
        if metric == "flagged":
            records = records.filter(verdict=Verdict.FLAGGED)

    paginator = Paginator(records, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    fullnames = [r.fullname if metric == "ingested" else r.reddit_fullname for r in page_obj]
    raw_by_fullname = {r.fullname: r for r in RawItem.objects.filter(fullname__in=fullnames)}
    rows = [(record, raw_by_fullname.get(
        record.fullname if metric == "ingested" else record.reddit_fullname)) for record in page_obj]

    context = {
        "item_type": item_type,
        "metric": metric,
        "granularity": granularity,
        "bucket_start": bucket_start,
        "page_obj": page_obj,
        "rows": rows,
    }
    return render(request, "dashboard/bucket_items.html", context)
