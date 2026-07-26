"""Shared logic for turning PRAW objects into RawComment/RawPost rows.

Used by both the `stream` and `reconcile` management commands so ingestion
behavior (dedup, field mapping, enqueueing inference) stays in one place.
"""

from datetime import datetime, timezone

from ingest.models import RawComment, RawPost
from moderation.tasks import classify_item


def _created_utc(reddit_obj):
    return datetime.fromtimestamp(reddit_obj.created_utc, tz=timezone.utc)


def save_comment(comment):
    """Get-or-create a RawComment for a PRAW comment, enqueueing inference
    on first insert. Returns the row (whether newly created or not)."""
    raw, created = RawComment.objects.get_or_create(
        reddit_id=comment.id,
        defaults={
            "subreddit": str(comment.subreddit),
            "author": str(comment.author) if comment.author else "",
            "body": comment.body,
            "permalink": comment.permalink,
            "link_id": comment.link_id,
            "parent_id": comment.parent_id,
            "created_utc": _created_utc(comment),
        },
    )
    if created:
        classify_item.enqueue("comment", raw.id)
    return raw, created


def save_post(submission):
    """Get-or-create a RawPost for a PRAW submission, enqueueing inference
    on first insert. Returns the row (whether newly created or not)."""
    raw, created = RawPost.objects.get_or_create(
        reddit_id=submission.id,
        defaults={
            "subreddit": str(submission.subreddit),
            "author": str(submission.author) if submission.author else "",
            "title": submission.title,
            "selftext": submission.selftext,
            "url": submission.url or "",
            "permalink": submission.permalink,
            "created_utc": _created_utc(submission),
        },
    )
    if created:
        classify_item.enqueue("post", raw.id)
    return raw, created
