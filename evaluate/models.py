from django.db import models


class ItemType(models.TextChoices):
    POST = "post", "Post"
    COMMENT = "comment", "Comment"


class Verdict(models.TextChoices):
    CLEAR = "clear", "Clear"
    FLAGGED = "flagged", "Flagged"


class EvaluationRecord(models.Model):
    """The permanent record of one evaluation pass over a Reddit item.

    Deliberately holds only metadata (author, permalink, ids, timestamps) and
    data we generated ourselves (verdict, category, confidence, rationale) —
    never the original comment/post body, which must not be retained once
    scored. Says nothing about what happens as a *result* of the verdict —
    that's the `actions` app's concern.
    """

    item_type = models.CharField(max_length=10, choices=ItemType.choices)
    reddit_fullname = models.CharField(max_length=24, unique=True, db_index=True)
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

    class Meta:
        ordering = ["-processed_at"]

    def __str__(self):
        return f"EvaluationRecord({self.reddit_fullname}, {self.verdict})"
