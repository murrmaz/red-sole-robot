from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import ModerationRecord, ReviewStatus, Verdict


@login_required
@staff_member_required
def queue_list(request):
    records = ModerationRecord.objects.all()

    verdict = request.GET.get("verdict", Verdict.FLAGGED)
    if verdict:
        records = records.filter(verdict=verdict)

    review_status = request.GET.get("review_status", ReviewStatus.UNREVIEWED)
    if review_status:
        records = records.filter(review_status=review_status)

    category = request.GET.get("category")
    if category:
        records = records.filter(category=category)

    paginator = Paginator(records, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "moderation/queue_list.html",
        {
            "page_obj": page_obj,
            "verdict": verdict,
            "review_status": review_status,
            "category": category,
            "verdict_choices": Verdict.choices,
            "review_status_choices": ReviewStatus.choices,
        },
    )


@login_required
@staff_member_required
def record_detail(request, pk):
    record = get_object_or_404(ModerationRecord, pk=pk)
    return render(request, "moderation/record_detail.html", {"record": record})


@login_required
@staff_member_required
def review_record(request, pk):
    record = get_object_or_404(ModerationRecord, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action in (ReviewStatus.ACTIONED, ReviewStatus.DISMISSED):
            record.review_status = action
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])
    return redirect("moderation:record_detail", pk=pk)


@login_required
@staff_member_required
def stats(request):
    since = timezone.now() - timedelta(days=7)
    recent = ModerationRecord.objects.filter(processed_at__gte=since)

    context = {
        "total_processed": recent.count(),
        "total_flagged": recent.filter(verdict=Verdict.FLAGGED).count(),
        "total_unreviewed": recent.filter(
            verdict=Verdict.FLAGGED, review_status=ReviewStatus.UNREVIEWED
        ).count(),
        "report_failures": recent.exclude(reddit_report_error="").count(),
    }
    return render(request, "moderation/stats.html", context)
