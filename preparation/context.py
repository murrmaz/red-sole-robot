"""Ancestor-walking logic for the preparation stage: assembling
conversational context for a comment before it goes to inference.

`_fetch_ancestor` imports `ingest.ingestion` lazily (inside the function,
not at module level) to avoid a circular import -- `ingest.ingestion`
imports `preparation.tasks`, which imports this module.
"""

from datetime import timedelta

import prawcore
from django.conf import settings
from django.utils import timezone

from actions.reddit_actions import TRANSIENT_EXCEPTIONS
from ingest.models import ItemType, RawItem
from ingest.reddit_client import get_reddit_client

NOT_FOUND_EXCEPTIONS = (prawcore.exceptions.NotFound, prawcore.exceptions.Forbidden)


def _text_for(raw: RawItem) -> str:
    if raw.item_type == ItemType.COMMENT:
        return raw.body
    return f"{raw.title}\n\n{raw.selftext}"


def _fetch_ancestor(fullname: str) -> RawItem:
    """Fetch a single ancestor live from Reddit and persist it through the
    existing save_comment/save_post dedup path, so it's cached in RawItem
    for any sibling item's future preparation pass."""
    from ingest.ingestion import save_comment, save_post

    reddit = get_reddit_client()
    kind, reddit_id = fullname.split("_", 1)
    if kind == "t1":
        raw, _ = save_comment(reddit.comment(reddit_id))
    else:
        raw, _ = save_post(reddit.submission(reddit_id))
    return raw


def build_context(raw: RawItem, best_effort: bool = False) -> str:
    """Walk a comment's parent_id chain to assemble conversational context,
    preferring already-retained RawItem rows and falling back to a live
    PRAW fetch (persisted back into RawItem for reuse) for ancestors that
    aged out of retention. Posts have no parent chain, so this returns ""
    for them without any PRAW call.

    Stops early (without error) once an ancestor is deleted/removed
    (NotFound/Forbidden) -- there's nothing further to retrieve. On a
    transient PRAW error, raises unless best_effort=True, in which case the
    walk stops there and whatever context was assembled so far is returned.

    Every ancestor consulted has its `protect_until` bumped so trimming
    won't evict it while it's still needed by a pending/retrying
    evaluation.
    """
    if raw.item_type != ItemType.COMMENT:
        return ""

    ancestors = []
    parent_fullname = raw.parent_id
    depth = 0

    while parent_fullname and depth < settings.PREPARATION_MAX_ANCESTOR_DEPTH:
        parent = RawItem.objects.filter(fullname=parent_fullname).first()
        if parent is None:
            try:
                parent = _fetch_ancestor(parent_fullname)
            except NOT_FOUND_EXCEPTIONS:
                break
            except TRANSIENT_EXCEPTIONS:
                if best_effort:
                    break
                raise

        parent.protect_until = timezone.now() + timedelta(
            seconds=settings.RAW_ITEM_PROTECTION_TTL_SECONDS
        )
        parent.save(update_fields=["protect_until"])

        ancestors.append(_text_for(parent))

        if parent.item_type != ItemType.COMMENT:
            break  # reached the post root
        parent_fullname = parent.parent_id
        depth += 1

    return "\n---\n".join(reversed(ancestors))
