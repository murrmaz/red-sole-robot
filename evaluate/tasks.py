import logging

from django_tasks import task

from evaluate.backends import get_inference_backend
from evaluate.models import EvaluationRecord, ItemType, Verdict
from ingest.models import RawComment, RawPost

logger = logging.getLogger(__name__)

_RAW_MODELS = {
    ItemType.COMMENT: (RawComment, "t1"),
    ItemType.POST: (RawPost, "t3"),
}


@task()
def evaluate_item(item_type: str, raw_id: int) -> None:
    """Run evaluation on one queued raw item and record the verdict, then
    delete the raw content regardless of outcome, since it must not be
    retained once evaluation has seen it. If the verdict is flagged, hands
    off to `actions.tasks.handle_flagged` — evaluation itself has no
    knowledge of what happens as a result of a verdict.

    On a failed/malformed evaluation response, the raw row is left in place
    so a later run retries it; it stays bounded by the queue cap either way.
    """
    from actions.tasks import handle_flagged

    raw_model, fullname_prefix = _RAW_MODELS[item_type]
    try:
        raw = raw_model.objects.get(id=raw_id)
    except raw_model.DoesNotExist:
        return

    text = raw.body if item_type == ItemType.COMMENT else f"{raw.title}\n\n{raw.selftext}"

    backend = get_inference_backend()
    try:
        result = backend.classify(text)
    except Exception:
        logger.exception("Evaluation failed for %s raw_id=%s", item_type, raw_id)
        return

    record = EvaluationRecord.objects.create(
        item_type=item_type,
        reddit_fullname=f"{fullname_prefix}_{raw.reddit_id}",
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

    raw.delete()
