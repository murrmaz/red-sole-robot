from django.db import models


class ItemType(models.TextChoices):
    POST = "post", "Post"
    COMMENT = "comment", "Comment"


class RawItem(models.Model):
    """A post or comment's raw content, retained as a rolling window (most
    recent RETAINED_COMMENT_CAP comments / RETAINED_POST_CAP posts, trimmed
    by `ingest_batch`) rather than deleted at evaluation time -- so recent
    sibling/parent items remain available as context. Identified by
    `fullname` (PRAW's own t1_/t3_-prefixed id), matching
    evaluate.EvaluationRecord.reddit_fullname.
    """

    item_type = models.CharField(max_length=10, choices=ItemType.choices)
    fullname = models.CharField(max_length=24, unique=True, db_index=True)
    reddit_id = models.CharField(max_length=20)
    subreddit = models.CharField(max_length=100)
    author = models.CharField(max_length=100, blank=True)
    permalink = models.CharField(max_length=500)
    created_utc = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    protect_until = models.DateTimeField(null=True, blank=True, db_index=True)

    # comment-only
    body = models.TextField(blank=True)
    link_id = models.CharField(max_length=20, blank=True)
    parent_id = models.CharField(max_length=20, blank=True)

    # post-only
    title = models.TextField(blank=True)
    selftext = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_utc"]

    def __str__(self):
        return f"RawItem({self.fullname})"


class IngestLogEntry(models.Model):
    """Permanent, content-free record that an item was ingested -- drives
    the dashboard's 'ingested' metric and drill-down once the item has
    aged out of RawItem's retention window.
    """

    item_type = models.CharField(max_length=10, choices=ItemType.choices)
    fullname = models.CharField(max_length=24)
    subreddit = models.CharField(max_length=100)
    permalink = models.CharField(max_length=500)
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"IngestLogEntry({self.fullname})"
