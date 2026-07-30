from django.db import models


class Granularity(models.TextChoices):
    HOUR = "hour", "Hourly"
    DAY = "day", "Daily"


class MetricBucket(models.Model):
    """One precomputed count for one (granularity, time bucket, metric).

    Holds only an integer count keyed by time bucket and a short metric
    name -- never body text or usernames, per the app's retention constraint.
    """

    granularity = models.CharField(max_length=5, choices=Granularity.choices)
    bucket_start = models.DateTimeField()
    metric_key = models.CharField(max_length=100)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["granularity", "bucket_start", "metric_key"],
                name="unique_metric_bucket",
            )
        ]
        indexes = [
            models.Index(fields=["metric_key", "granularity", "bucket_start"]),
        ]

    def __str__(self):
        return f"MetricBucket({self.granularity}, {self.bucket_start}, {self.metric_key}={self.count})"
