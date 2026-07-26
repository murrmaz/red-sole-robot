import logging

from django.utils import timezone
from django_tasks import task

from actions.models import ActionRecord, ActionStatus
from actions.reddit_actions import submit_report
from evaluate.models import EvaluationRecord

logger = logging.getLogger(__name__)


@task()
def handle_flagged(evaluation_record_id: int) -> None:
    """React to a flagged EvaluationRecord. Currently the only action is a
    native Reddit report; future action types (removing content, banning
    users) get added here without touching evaluation logic."""
    try:
        record = EvaluationRecord.objects.get(id=evaluation_record_id)
    except EvaluationRecord.DoesNotExist:
        return

    reddit_id = record.reddit_fullname.split("_", 1)[1]
    action = ActionRecord.objects.create(evaluation_record=record)

    try:
        submit_report(record.item_type, reddit_id, record.category or "AI-flagged")
    except Exception as e:
        action.status = ActionStatus.FAILED
        action.error = str(e)[:500]
        logger.exception("Reddit report submission failed for %s", reddit_id)
    else:
        action.status = ActionStatus.SUBMITTED
        action.submitted_at = timezone.now()

    action.save(update_fields=["status", "submitted_at", "error"])
