from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from actions.models import ActionRecord
from dashboard.models import MetricBucket
from dashboard.tasks import rollup_metrics_task, run_rollup
from evaluate.models import EvaluationRecord, ItemType, Verdict
from ingest.models import IngestLogEntry


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


def make_ingest_log_entry(**overrides):
    defaults = dict(
        item_type=ItemType.COMMENT,
        fullname="t1_abc123",
        subreddit="LouboutinLife",
        permalink="/r/LouboutinLife/comments/abc/xyz/",
    )
    defaults.update(overrides)
    return IngestLogEntry.objects.create(**defaults)


class HomeViewTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_staff_user_sees_dashboard(self):
        user = User.objects.create_user(
            username="mod", password="pw", is_staff=True
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reddit Posts")
        self.assertContains(response, "Reddit Comments")


class MetricsDataViewTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("metrics_data"), {"item_type": "comment"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_missing_item_type_is_bad_request(self):
        user = User.objects.create_user(username="mod", password="pw", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("metrics_data"))

        self.assertEqual(response.status_code, 400)

    def test_staff_user_gets_bucketed_data(self):
        make_evaluation_record()
        make_ingest_log_entry()
        run_rollup()

        user = User.objects.create_user(username="mod", password="pw", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(
            reverse("metrics_data"), {"granularity": "hour", "item_type": "comment"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["granularity"], "hour")
        self.assertIn("labels", data)
        self.assertIn("datasets", data)
        flagged = next(ds for ds in data["datasets"] if ds["label"] == "Flagged")
        self.assertEqual(sum(flagged["data"]), 1)
        ingested = next(ds for ds in data["datasets"] if ds["label"] == "Ingested")
        self.assertEqual(sum(ingested["data"]), 1)


class BucketItemsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mod", password="pw", is_staff=True)
        self.client.force_login(self.user)

    def test_flagged_bucket_lists_matching_records(self):
        record = make_evaluation_record()
        bucket_start = record.processed_at.replace(minute=0, second=0, microsecond=0)

        response = self.client.get(reverse("bucket_items"), {
            "item_type": "comment",
            "metric": "flagged",
            "granularity": "hour",
            "bucket_start": bucket_start.isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "spam")

    def test_missing_params_is_bad_request(self):
        response = self.client.get(reverse("bucket_items"))
        self.assertEqual(response.status_code, 400)


class RunRollupTests(TestCase):
    def test_rollup_counts_processed_and_flagged(self):
        make_evaluation_record(reddit_fullname="t1_a", verdict=Verdict.FLAGGED)
        make_evaluation_record(reddit_fullname="t1_b", verdict=Verdict.CLEAR)

        run_rollup()

        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="processed.total").count, 2
        )
        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="verdict.flagged").count, 1
        )
        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="verdict.clear").count, 1
        )
        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="flagged.comment").count, 1
        )


class TaskQueueAssignmentTests(TestCase):
    def test_rollup_metrics_task_uses_dashboard_queue(self):
        self.assertEqual(rollup_metrics_task.queue_name, settings.TASK_QUEUE_DASHBOARD)

    def test_rollup_counts_ingested(self):
        make_ingest_log_entry(fullname="t1_a")
        make_ingest_log_entry(fullname="t1_b")

        run_rollup()

        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="ingested.comment").count, 2
        )

    def test_rollup_is_idempotent(self):
        make_evaluation_record()

        run_rollup()
        run_rollup()

        self.assertEqual(MetricBucket.objects.filter(metric_key="processed.total").count(), 2)
        bucket = MetricBucket.objects.get(granularity="day", metric_key="processed.total")
        self.assertEqual(bucket.count, 1)

    def test_rollup_includes_action_records(self):
        record = make_evaluation_record()
        ActionRecord.objects.create(evaluation_record=record)

        run_rollup()

        self.assertEqual(
            MetricBucket.objects.get(granularity="day", metric_key="action.pending").count, 1
        )
