import logging

from django.conf import settings
from django_tasks import task

from evaluate.backends import get_inference_backend
from evaluate.models import EvaluationRecord, ItemType, Verdict
from ingest.models import RawItem

logger = logging.getLogger(__name__)


@task(queue_name=settings.TASK_QUEUE_EVALUATION)
def evaluate_item(raw_id: int) -> None:
    """Run evaluation on one queued raw item and record the verdict. If the
    verdict is flagged, hands off to `actions.tasks.handle_flagged` —
    evaluation itself has no knowledge of what happens as a result of a
    verdict.

    The raw row is left in place either way (it's no longer deleted here) —
    RawItem now persists as a rolling retention window, trimmed by
    `reconcile`, rather than being deleted at evaluation time.
    """
    from actions.tasks import handle_flagged

    try:
        raw = RawItem.objects.get(id=raw_id)
    except RawItem.DoesNotExist:
        return

    text = raw.body if raw.item_type == ItemType.COMMENT else f"{raw.title}\n\n{raw.selftext}"

    backend = get_inference_backend()
    try:
        result = backend.classify(text)
    except Exception:
        logger.exception("Evaluation failed for raw_id=%s", raw_id)
        return

    record = EvaluationRecord.objects.create(
        item_type=raw.item_type,
        reddit_fullname=raw.fullname,
        subreddit=raw.subreddit,
        author=raw.author,
        permalink=raw.permalink,
        content_created_utc=raw.created_utc,
        verdict=Verdict.FLAGGED if result.flagged else Verdict.CLEAR,
        category=result.category,
        confidence=result.confidence,
        rationale=result.rationale,
        model_name=backend.model_name,
    )

    if result.flagged:
        handle_flagged.enqueue(record.id)
