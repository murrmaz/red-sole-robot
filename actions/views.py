from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from evaluate.models import EvaluationRecord, Verdict

from .models import ActionRecord, ReviewStatus


@login_required
@staff_member_required
def queue_list(request):
    records = ActionRecord.objects.select_related("evaluation_record").order_by(
        "-evaluation_record__processed_at"
    )

    verdict = request.GET.get("verdict", Verdict.FLAGGED)
    if verdict:
        records = records.filter(evaluation_record__verdict=verdict)

    review_status = request.GET.get("review_status", ReviewStatus.UNREVIEWED)
    if review_status:
        records = records.filter(review_status=review_status)

    category = request.GET.get("category")
    if category:
        records = records.filter(evaluation_record__category=category)

    paginator = Paginator(records, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "actions/queue_list.html",
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
    record = get_object_or_404(
        ActionRecord.objects.select_related("evaluation_record"), pk=pk
    )
    return render(request, "actions/record_detail.html", {"record": record})


@login_required
@staff_member_required
def review_record(request, pk):
    record = get_object_or_404(ActionRecord, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action in (ReviewStatus.ACTIONED, ReviewStatus.DISMISSED):
            record.review_status = action
            record.reviewed_by = request.user
            record.reviewed_at = timezone.now()
            record.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])
    return redirect("actions:record_detail", pk=pk)


@login_required
@staff_member_required
def stats(request):
    since = timezone.now() - timedelta(days=7)
    recent = EvaluationRecord.objects.filter(processed_at__gte=since)
    recent_actions = ActionRecord.objects.filter(evaluation_record__processed_at__gte=since)

    context = {
        "total_processed": recent.count(),
        "total_flagged": recent.filter(verdict=Verdict.FLAGGED).count(),
        "total_unreviewed": recent_actions.filter(
            review_status=ReviewStatus.UNREVIEWED
        ).count(),
        "report_failures": recent_actions.exclude(error="").count(),
    }
    return render(request, "actions/stats.html", context)
