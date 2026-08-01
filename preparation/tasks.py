import logging

from django.conf import settings
from django.utils import timezone
from django_tasks import task

from actions.reddit_actions import TRANSIENT_EXCEPTIONS, retry_delay_seconds
from ingest.models import RawItem
from preparation.context import build_context

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 5  # 1 initial attempt + 4 retries


@task(queue_name=settings.TASK_QUEUE_REDDIT)
def prepare_item(raw_id: int, attempt: int = 0) -> None:
    """Assemble ancestor context for a RawItem, then hand off to
    evaluate_item. Runs on the shared reddit queue because assembling
    context may require a live PRAW fetch for ancestors that fell out of
    RawItem's retention window."""
    from evaluate.tasks import evaluate_item

    try:
        raw = RawItem.objects.get(id=raw_id)
    except RawItem.DoesNotExist:
        return

    try:
        context = build_context(raw, best_effort=attempt + 1 >= MAX_RETRY_ATTEMPTS)
    except TRANSIENT_EXCEPTIONS as e:
        delay = retry_delay_seconds(e, attempt)
        logger.warning(
            "Transient error preparing context for raw_id=%s (attempt %s/%s), "
            "retrying in %.0fs: %s",
            raw_id,
            attempt + 1,
            MAX_RETRY_ATTEMPTS,
            delay,
            e,
        )
        prepare_item.using(
            run_after=timezone.now() + timezone.timedelta(seconds=delay)
        ).enqueue(raw_id, attempt=attempt + 1)
        return

    evaluate_item.enqueue(raw_id, context=context)
