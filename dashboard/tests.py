from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from actions.models import ActionRecord
from dashboard.models import MetricBucket
from dashboard.tasks import run_rollup
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
        for key in (
            "raw_comment_count",
            "raw_comment_cap",
            "raw_post_count",
            "raw_post_cap",
            "total_processed",
            "processed_last_24h",
            "flagged_last_24h",
            "unreviewed_flagged",
        ):
            self.assertIn(key, response.context)


class MetricsDataViewTests(TestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("metrics_data"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_staff_user_gets_bucketed_data(self):
        make_evaluation_record()
        run_rollup()

        user = User.objects.create_user(username="mod", password="pw", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("metrics_data"), {"granularity": "hour"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["granularity"], "hour")
        self.assertIn("labels", data)
        self.assertIn("datasets", data)
        flagged = next(ds for ds in data["datasets"] if ds["label"] == "Flagged")
        self.assertEqual(sum(flagged["data"]), 1)


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
