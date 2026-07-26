from django.conf import settings
from django.db import models

from evaluate.models import EvaluationRecord


class ActionType(models.TextChoices):
    REPORT = "report", "Report"


class ActionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUBMITTED = "submitted", "Submitted"
    FAILED = "failed", "Failed"


class ReviewStatus(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    ACTIONED = "actioned", "Actioned"
    DISMISSED = "dismissed", "Dismissed"


class ActionRecord(models.Model):
    """What was (or should be) done in response to a flagged EvaluationRecord.

    Kept separate from EvaluationRecord so that new action types (removing
    content, banning users) can be added here without touching evaluation
    logic at all.
    """

    evaluation_record = models.OneToOneField(EvaluationRecord, on_delete=models.CASCADE)

    action_type = models.CharField(
        max_length=20, choices=ActionType.choices, default=ActionType.REPORT
    )
    status = models.CharField(
        max_length=10, choices=ActionStatus.choices, default=ActionStatus.PENDING
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)

    review_status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.UNREVIEWED
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ActionRecord({self.evaluation_record.reddit_fullname}, {self.action_type}, {self.status})"
