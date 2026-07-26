from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase

from actions.models import ActionRecord, ActionStatus
from actions.tasks import handle_flagged
from evaluate.models import EvaluationRecord, ItemType, Verdict


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
