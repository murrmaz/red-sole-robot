from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
