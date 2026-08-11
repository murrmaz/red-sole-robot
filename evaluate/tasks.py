import logging

import requests
from django.conf import settings
from django.utils import timezone
from django_tasks import task

from actions.reddit_actions import retry_delay_seconds
from evaluate.backends import get_inference_backend
from evaluate.models import EvaluationRecord, ItemType, Verdict
from ingest.models import RawItem
from preparation.context import build_context

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 5  # 1 initial attempt + 4 retries

# requests errors cover model-server outages/timeouts; ValueError covers a
# malformed inference response (evaluate/backends/openai_compatible.py) --
# both are worth retrying since a flaky server or a flaky response may
# succeed on a later attempt. Not shared with actions/reddit_actions.py's
# TRANSIENT_EXCEPTIONS, which is PRAW/prawcore-specific.
EVALUATION_TRANSIENT_EXCEPTIONS = (requests.exceptions.RequestException, ValueError)


@task(queue_name=settings.TASK_QUEUE_EVALUATION)
def evaluate_item(raw_id: int, attempt: int = 0) -> None:
    """Run evaluation on one queued raw item and record the verdict. If the
    verdict is flagged, hands off to `actions.tasks.handle_flagged` —
    evaluation itself has no knowledge of what happens as a result of a
    verdict.

    The conversational context (parent comments) is rebuilt here, read-only,
    from RawItem via `build_context(allow_fetch=False, protect=False)` --
    not received as a task argument -- so raw content never ends up in
    django_tasks_db's DBTaskResult.args_kwargs (which is persisted
    indefinitely). `preparation.tasks.prepare_item` already fetched and
    protected any ancestors that needed it before enqueueing this task; this
    call is a pure DB read with no PRAW fetch and no protect_until bump,
    since evaluation is the final consumer with nothing left to wait for.

    The raw row is left in place either way (it's no longer deleted here) —
    RawItem now persists as a rolling retention window, trimmed by
    `ingest_batch`, rather than being deleted at evaluation time.

    Writing the record via get_or_create on reddit_fullname (rather than
    create) guards against a duplicate evaluation of an already-scored item
    -- e.g. an ancestor that aged out of RawItem's retention window and was
    re-fetched for context. If one is already recorded, this is a no-op
    rather than an IntegrityError, and no second handle_flagged is enqueued.

    Transient inference failures (server outage, malformed response) are
    retried with backoff, same as prepare_item/handle_flagged. Once retries
    are exhausted, or on a non-transient error, the failure is logged and the
    item is permanently dropped -- no EvaluationRecord is written.
    """
    from actions.tasks import handle_flagged

    try:
        raw = RawItem.objects.get(id=raw_id)
    except RawItem.DoesNotExist:
        return

    context = build_context(raw, allow_fetch=False, protect=False)
    text = raw.body if raw.item_type == ItemType.COMMENT else f"{raw.title}\n\n{raw.selftext}"

    backend = get_inference_backend()
    try:
        result = backend.classify(text, context=context)
    except EVALUATION_TRANSIENT_EXCEPTIONS as e:
        if attempt + 1 < MAX_RETRY_ATTEMPTS:
            delay = retry_delay_seconds(e, attempt)
            logger.warning(
                "Transient error evaluating raw_id=%s (attempt %s/%s), retrying in %.0fs: %s",
                raw_id,
                attempt + 1,
                MAX_RETRY_ATTEMPTS,
                delay,
                e,
            )
            evaluate_item.using(
                run_after=timezone.now() + timezone.timedelta(seconds=delay)
            ).enqueue(raw_id, attempt=attempt + 1)
            return
        logger.error(
            "Evaluation permanently failed for raw_id=%s after %s attempts: %s",
            raw_id,
            MAX_RETRY_ATTEMPTS,
            e,
        )
        return
    except Exception:
        logger.exception("Non-retryable evaluation error for raw_id=%s", raw_id)
        return

    record, created = EvaluationRecord.objects.get_or_create(
        reddit_fullname=raw.fullname,
        defaults=dict(
            item_type=raw.item_type,
            subreddit=raw.subreddit,
            author=raw.author,
            permalink=raw.permalink,
            content_created_utc=raw.created_utc,
            verdict=Verdict.FLAGGED if result.flagged else Verdict.CLEAR,
            category=result.category,
            confidence=result.confidence,
            rationale=result.rationale,
            model_name=backend.model_name,
        ),
    )

    if created and result.flagged:
        handle_flagged.enqueue(record.id)
