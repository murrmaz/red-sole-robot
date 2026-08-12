from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from evaluate.models import EvaluationRecord, Verdict

from .models import ActionRecord


@login_required
@staff_member_required
def stats(request):
    since = timezone.now() - timedelta(days=7)
    recent = EvaluationRecord.objects.filter(processed_at__gte=since)
    recent_actions = ActionRecord.objects.filter(evaluation_record__processed_at__gte=since)

    context = {
        "total_processed": recent.count(),
        "total_flagged": recent.filter(verdict=Verdict.FLAGGED).count(),
        "report_failures": recent_actions.exclude(error="").count(),
    }
    return render(request, "actions/stats.html", context)
