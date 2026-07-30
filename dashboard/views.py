from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from actions.models import ActionRecord, ReviewStatus
from dashboard.models import Granularity, MetricBucket
from evaluate.models import EvaluationRecord, Verdict
from ingest.models import RawComment, RawPost

METRIC_LABELS = {
    "processed.total": "Processed",
    "processed.comment": "Comments",
    "processed.post": "Posts",
    "verdict.flagged": "Flagged",
    "action.submitted": "Reports submitted",
    "action.failed": "Report failures",
}


@login_required
@staff_member_required
def home(request):
    since = timezone.now() - timedelta(days=1)
    recent = EvaluationRecord.objects.filter(processed_at__gte=since)

    context = {
        "raw_comment_count": RawComment.objects.count(),
        "raw_comment_cap": settings.QUEUE_COMMENT_CAP,
        "raw_post_count": RawPost.objects.count(),
        "raw_post_cap": settings.QUEUE_POST_CAP,
        "total_processed": EvaluationRecord.objects.count(),
        "processed_last_24h": recent.count(),
        "flagged_last_24h": recent.filter(verdict=Verdict.FLAGGED).count(),
        "unreviewed_flagged": ActionRecord.objects.filter(
            review_status=ReviewStatus.UNREVIEWED,
            evaluation_record__verdict=Verdict.FLAGGED,
        ).count(),
    }
    return render(request, "dashboard/home.html", context)


@login_required
@staff_member_required
def metrics_data(request):
    granularity = request.GET.get("granularity", Granularity.HOUR)
    if granularity not in Granularity.values:
        granularity = Granularity.HOUR
    days = int(request.GET.get("days", 7 if granularity == Granularity.HOUR else 30))
    since = timezone.now() - timedelta(days=days)

    rows = MetricBucket.objects.filter(
        granularity=granularity, bucket_start__gte=since, metric_key__in=METRIC_LABELS,
    ).order_by("bucket_start")

    series = {k: {} for k in METRIC_LABELS}
    for row in rows:
        series[row.metric_key][row.bucket_start.isoformat()] = row.count
    labels = sorted({b for s in series.values() for b in s})
    datasets = [
        {"label": label, "data": [series[key].get(b, 0) for b in labels]}
        for key, label in METRIC_LABELS.items()
    ]
    return JsonResponse({"labels": labels, "datasets": datasets, "granularity": granularity})
