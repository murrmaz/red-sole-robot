"""Shared logic for turning PRAW objects into RawItem/IngestLogEntry rows.

Used by both `ingest_batch` and preparation's ancestor-fetch fallback, so
ingestion behavior (dedup, field mapping, enqueueing preparation) stays in
one place.
"""

from datetime import datetime, timezone

from ingest.models import IngestLogEntry, ItemType, RawItem
from preparation.tasks import prepare_item


def _created_utc(reddit_obj):
    return datetime.fromtimestamp(reddit_obj.created_utc, tz=timezone.utc)


def save_comment(comment, enqueue_prepare=True):
    """Get-or-create a RawItem for a PRAW comment, enqueueing context
    preparation on first insert (unless enqueue_prepare=False, for callers
    fetching it purely as context for something else's preparation, not as
    a new unit of work). Returns the row (whether newly created or not)."""
    raw, created = RawItem.objects.get_or_create(
        fullname=comment.fullname,
        defaults={
            "item_type": ItemType.COMMENT,
            "reddit_id": comment.id,
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
        IngestLogEntry.objects.create(
            item_type=ItemType.COMMENT,
            fullname=raw.fullname,
            subreddit=raw.subreddit,
            permalink=raw.permalink,
        )
        if enqueue_prepare:
            prepare_item.enqueue(raw.id)
    return raw, created


def save_post(submission, enqueue_prepare=True):
    """Get-or-create a RawItem for a PRAW submission, enqueueing context
    preparation on first insert (unless enqueue_prepare=False, for callers
    fetching it purely as context for something else's preparation, not as
    a new unit of work). Returns the row (whether newly created or not)."""
    raw, created = RawItem.objects.get_or_create(
        fullname=submission.fullname,
        defaults={
            "item_type": ItemType.POST,
            "reddit_id": submission.id,
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
        IngestLogEntry.objects.create(
            item_type=ItemType.POST,
            fullname=raw.fullname,
            subreddit=raw.subreddit,
            permalink=raw.permalink,
        )
        if enqueue_prepare:
            prepare_item.enqueue(raw.id)
    return raw, created
