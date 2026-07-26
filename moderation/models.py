from django.conf import settings
from django.db import models


class ItemType(models.TextChoices):
    POST = "post", "Post"
    COMMENT = "comment", "Comment"


class Verdict(models.TextChoices):
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"


class ReviewStatus(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    ACTIONED = "actioned", "Actioned"
    DISMISSED = "dismissed", "Dismissed"


class ModerationRecord(models.Model):
    """The permanent record of an AI inference pass over one Reddit item.

    Deliberately holds only metadata (author, permalink, ids, timestamps) and
    data we generated ourselves (verdict, category, confidence, rationale,
    review state) — never the original comment/post body, which must not be
    retained once scored.
    """

    item_type = models.CharField(max_length=10, choices=ItemType.choices)
    reddit_fullname = models.CharField(max_length=20, unique=True, db_index=True)
    subreddit = models.CharField(max_length=100)
    author = models.CharField(max_length=100, blank=True)
    permalink = models.CharField(max_length=500)
    content_created_utc = models.DateTimeField()
    processed_at = models.DateTimeField(auto_now_add=True)

    verdict = models.CharField(max_length=10, choices=Verdict.choices)
    category = models.CharField(max_length=100, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    rationale = models.TextField(blank=True)
    model_name = models.CharField(max_length=200, blank=True)

    reddit_report_submitted = models.BooleanField(default=False)
    reddit_report_submitted_at = models.DateTimeField(null=True, blank=True)
    reddit_report_error = models.CharField(max_length=500, blank=True)

    review_status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.UNREVIEWED
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-processed_at"]

    def __str__(self):
        return f"ModerationRecord({self.reddit_fullname}, {self.verdict})"
