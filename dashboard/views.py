from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from actions.models import ActionRecord, ReviewStatus
from evaluate.models import EvaluationRecord, Verdict
from ingest.models import RawComment, RawPost


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
