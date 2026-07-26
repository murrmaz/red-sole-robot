from django.db import models


class RawComment(models.Model):
    """A comment awaiting AI inference.

    Presence of a row here *is* its "pending" state — once inference
    processes a row it is deleted, so raw comment bodies are never retained
    long-term. Only bounded by QUEUE_COMMENT_CAP (trimmed by `reconcile`).
    """

    reddit_id = models.CharField(max_length=20, unique=True, db_index=True)
    subreddit = models.CharField(max_length=100)
    author = models.CharField(max_length=100, blank=True)
    body = models.TextField()
    permalink = models.CharField(max_length=500)
    link_id = models.CharField(max_length=20)
    parent_id = models.CharField(max_length=20)
    created_utc = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_utc"]

    def __str__(self):
        return f"RawComment({self.reddit_id})"


class RawPost(models.Model):
    """A post awaiting AI inference. See RawComment for retention rationale."""

    reddit_id = models.CharField(max_length=20, unique=True, db_index=True)
    subreddit = models.CharField(max_length=100)
    author = models.CharField(max_length=100, blank=True)
    title = models.TextField()
    selftext = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True)
    permalink = models.CharField(max_length=500)
    created_utc = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_utc"]

    def __str__(self):
        return f"RawPost({self.reddit_id})"
