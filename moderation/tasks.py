import logging

from django.utils import timezone
from django_tasks import task

from ingest.models import RawComment, RawPost
from moderation.inference import get_inference_backend
from moderation.models import ItemType, ModerationRecord, Verdict
from moderation.reddit_reports import submit_report

logger = logging.getLogger(__name__)

_RAW_MODELS = {
    ItemType.COMMENT: (RawComment, "t1"),
    ItemType.POST: (RawPost, "t3"),
}


@task()
def classify_item(item_type: str, raw_id: int) -> None:
    """Run inference on one queued raw item, record the verdict, and (if
    flagged) file a Reddit report — then delete the raw content regardless
    of outcome, since it must not be retained once inference has seen it.

    On a failed/malformed inference response, the raw row is left in place
    so a later run retries it; it stays bounded by the queue cap either way.
    """
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
        logger.exception("Inference failed for %s raw_id=%s", item_type, raw_id)
        return

    record = ModerationRecord.objects.create(
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
        try:
            submit_report(item_type, raw.reddit_id, result.category or "AI-flagged")
        except Exception as e:
            record.reddit_report_error = str(e)[:500]
            logger.exception("Reddit report submission failed for %s", raw.reddit_id)
        else:
            record.reddit_report_submitted = True
            record.reddit_report_submitted_at = timezone.now()
        record.save(
            update_fields=[
                "reddit_report_submitted",
                "reddit_report_submitted_at",
                "reddit_report_error",
            ]
        )

    raw.delete()
