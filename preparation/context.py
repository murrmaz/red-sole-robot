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


def protect_item(raw: RawItem) -> None:
    """Bump `protect_until` so `ingest.trimming.trim_to_cap` won't evict this
    row while it's still needed by a pending/retrying prepare or evaluate
    task."""
    raw.protect_until = timezone.now() + timedelta(
        seconds=settings.RAW_ITEM_PROTECTION_TTL_SECONDS
    )
    raw.save(update_fields=["protect_until"])


def _fetch_ancestor(fullname: str) -> RawItem:
    """Fetch a single ancestor live from Reddit and persist it through the
    existing save_comment/save_post dedup path, so it's cached in RawItem
    for any sibling item's future preparation pass. Fetched purely as
    context for the item already being prepared, not as a new unit of work,
    so preparation is not enqueued for it."""
    from ingest.ingestion import save_comment, save_post

    reddit = get_reddit_client()
    kind, reddit_id = fullname.split("_", 1)
    if kind == "t1":
        raw, _ = save_comment(reddit.comment(reddit_id), enqueue_prepare=False)
    else:
        raw, _ = save_post(reddit.submission(reddit_id), enqueue_prepare=False)
    return raw


def build_context(
    raw: RawItem,
    best_effort: bool = False,
    allow_fetch: bool = True,
    protect: bool = True,
) -> str:
    """Walk a comment's parent_id chain to assemble conversational context,
    preferring already-retained RawItem rows and falling back (when
    allow_fetch=True) to a live PRAW fetch, persisted back into RawItem for
    reuse, for ancestors that aged out of retention. Posts have no parent
    chain, so this returns "" for them without any PRAW call.

    With allow_fetch=False, the walk never touches PRAW: it stops as soon as
    the next ancestor isn't already in RawItem, same as hitting a
    deleted/removed one. This is for callers that must not risk running a
    PRAW call outside the single-process `reddit` queue.

    Stops early (without error) once an ancestor is deleted/removed
    (NotFound/Forbidden) -- there's nothing further to retrieve. On a
    transient PRAW error, raises unless best_effort=True, in which case the
    walk stops there and whatever context was assembled so far is returned.

    With protect=True (the default), every ancestor consulted has its
    `protect_until` bumped so trimming won't evict it while it's still
    needed by a pending/retrying evaluation. Callers doing a final,
    immediate read (nothing left to wait for) should pass protect=False so
    they don't re-arm that TTL for no reason.
    """
    if raw.item_type != ItemType.COMMENT:
        return ""

    ancestors = []
    parent_fullname = raw.parent_id
    depth = 0

    while parent_fullname and depth < settings.PREPARATION_MAX_ANCESTOR_DEPTH:
        parent = RawItem.objects.filter(fullname=parent_fullname).first()
        if parent is None:
            if not allow_fetch:
                break
            try:
                parent = _fetch_ancestor(parent_fullname)
            except NOT_FOUND_EXCEPTIONS:
                break
            except TRANSIENT_EXCEPTIONS:
                if best_effort:
                    break
                raise

        if protect:
            protect_item(parent)

        ancestors.append(_text_for(parent))

        if parent.item_type != ItemType.COMMENT:
            break  # reached the post root
        parent_fullname = parent.parent_id
        depth += 1

    return "\n---\n".join(reversed(ancestors))
