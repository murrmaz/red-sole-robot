from datetime import datetime, timezone
from unittest.mock import Mock, patch

import prawcore
from django.conf import settings
from django.test import TestCase

from actions.models import ActionRecord, ActionStatus
from actions.tasks import MAX_RETRY_ATTEMPTS, handle_flagged
from evaluate.models import EvaluationRecord, ItemType, Verdict
from evaluate.tasks import evaluate_item


def make_evaluation_record(**overrides):
    defaults = dict(
        item_type=ItemType.COMMENT,
        reddit_fullname="t1_abc123",
        subreddit="LouboutinLife",
        author="someuser",
        permalink="/r/LouboutinLife/comments/abc/xyz/",
        content_created_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        verdict=Verdict.FLAGGED,
        category="spam",
        confidence=0.9,
        rationale="looks like spam",
        model_name="test-model",
    )
    defaults.update(overrides)
    return EvaluationRecord.objects.create(**defaults)


class HandleFlaggedTests(TestCase):
    @patch("actions.tasks.submit_report")
    def test_successful_report_marks_submitted(self, mock_submit_report):
        record = make_evaluation_record()

        handle_flagged.call(record.id)

        action = ActionRecord.objects.get(evaluation_record=record)
        self.assertEqual(action.status, ActionStatus.SUBMITTED)
        self.assertIsNotNone(action.submitted_at)
        mock_submit_report.assert_called_once_with("comment", "abc123", "spam")

    @patch("actions.tasks.submit_report")
    def test_report_failure_is_recorded(self, mock_submit_report):
        mock_submit_report.side_effect = Exception("reddit API down")
        record = make_evaluation_record()

        handle_flagged.call(record.id)

        action = ActionRecord.objects.get(evaluation_record=record)
        self.assertEqual(action.status, ActionStatus.FAILED)
        self.assertIn("reddit API down", action.error)

    def _make_too_many_requests(self, retry_after=None):
        response = Mock(status_code=429, text="")
        response.headers.get.return_value = retry_after
        return prawcore.exceptions.TooManyRequests(response)

    @patch("actions.tasks.submit_report")
    def test_transient_error_requeues_and_stays_pending(self, mock_submit_report):
        mock_submit_report.side_effect = self._make_too_many_requests(retry_after="30")
        record = make_evaluation_record()

        with patch("django_tasks.base.Task.using") as mock_using:
            handle_flagged.call(record.id, attempt=0)

        action = ActionRecord.objects.get(evaluation_record=record)
        self.assertEqual(action.status, ActionStatus.PENDING)
        mock_using.assert_called_once()
        self.assertIn("run_after", mock_using.call_args.kwargs)
        mock_using.return_value.enqueue.assert_called_once_with(record.id, attempt=1)

    @patch("actions.tasks.submit_report")
    def test_transient_error_exhausts_retries_and_marks_failed(self, mock_submit_report):
        mock_submit_report.side_effect = self._make_too_many_requests()

        record = make_evaluation_record()

        handle_flagged.call(record.id, attempt=MAX_RETRY_ATTEMPTS - 1)

        action = ActionRecord.objects.get(evaluation_record=record)
        self.assertEqual(action.status, ActionStatus.FAILED)
        self.assertIn("Exhausted retries", action.error)

    @patch("actions.tasks.submit_report")
    def test_retry_reuses_existing_action_record(self, mock_submit_report):
        record = make_evaluation_record()

        mock_submit_report.side_effect = self._make_too_many_requests()
        with patch("django_tasks.base.Task.using"):
            handle_flagged.call(record.id, attempt=0)

        mock_submit_report.side_effect = None
        handle_flagged.call(record.id, attempt=1)

        self.assertEqual(ActionRecord.objects.filter(evaluation_record=record).count(), 1)
        action = ActionRecord.objects.get(evaluation_record=record)
        self.assertEqual(action.status, ActionStatus.SUBMITTED)


class TaskQueueAssignmentTests(TestCase):
    def test_evaluate_item_uses_evaluation_queue(self):
        self.assertEqual(evaluate_item.queue_name, settings.TASK_QUEUE_EVALUATION)

    def test_handle_flagged_uses_actions_queue(self):
        self.assertEqual(handle_flagged.queue_name, settings.TASK_QUEUE_ACTIONS)
