import logging

from django.conf import settings
from django.utils import timezone
from django_tasks import task

from actions.models import ActionRecord, ActionStatus
from actions.reddit_actions import TRANSIENT_EXCEPTIONS, retry_delay_seconds, submit_report
from evaluate.models import EvaluationRecord

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 5  # 1 initial attempt + 4 retries


@task(queue_name=settings.TASK_QUEUE_ACTIONS)
def handle_flagged(evaluation_record_id: int, attempt: int = 0) -> None:
    """React to a flagged EvaluationRecord. Currently the only action is a
    native Reddit report; future action types (removing content, banning
    users) get added here without touching evaluation logic."""
    try:
        record = EvaluationRecord.objects.get(id=evaluation_record_id)
    except EvaluationRecord.DoesNotExist:
        return

    reddit_id = record.reddit_fullname.split("_", 1)[1]
    # get_or_create, not create: evaluation_record is a OneToOneField, and
    # retries re-enter this task for the same EvaluationRecord.
    action, _ = ActionRecord.objects.get_or_create(evaluation_record=record)

    try:
        submit_report(record.item_type, reddit_id, record.category or "AI-flagged")
    except TRANSIENT_EXCEPTIONS as e:
        if attempt + 1 < MAX_RETRY_ATTEMPTS:
            delay = retry_delay_seconds(e, attempt)
            logger.warning(
                "Transient error submitting report for %s (attempt %s/%s), retrying in %.0fs: %s",
                reddit_id,
                attempt + 1,
                MAX_RETRY_ATTEMPTS,
                delay,
                e,
            )
            handle_flagged.using(
                run_after=timezone.now() + timezone.timedelta(seconds=delay)
            ).enqueue(evaluation_record_id, attempt=attempt + 1)
            # Leave the ActionRecord PENDING; this DBTaskResult completes
            # normally, and the retry is tracked by the new DBTaskResult
            # just enqueued (django_tasks_db has no native retry concept).
            return
        logger.exception(
            "Exhausted retries (%s) submitting report for %s", MAX_RETRY_ATTEMPTS, reddit_id
        )
        action.status = ActionStatus.FAILED
        action.error = f"Exhausted retries after transient error: {e}"[:500]
        action.save(update_fields=["status", "error"])
        return
    except Exception as e:
        action.status = ActionStatus.FAILED
        action.error = str(e)[:500]
        logger.exception("Reddit report submission failed for %s", reddit_id)
        action.save(update_fields=["status", "error"])
        return

    action.status = ActionStatus.SUBMITTED
    action.submitted_at = timezone.now()
    action.save(update_fields=["status", "submitted_at"])
