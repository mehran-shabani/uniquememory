from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from companies.models import Company
from webhooks.models import WebhookSubscription


class WebhookSubscriptionModelTests(TestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.subscription = WebhookSubscription.objects.create(
            company=self.company,
            target_url="https://example.com/webhook",
            events=["memory.entry.created", "consent.created"],
            secret="secret",
        )

    def test_querysets_filter_by_event_and_status(self) -> None:
        other = WebhookSubscription.objects.create(
            company=self.company,
            target_url="https://example.com/other",
            events=["consent.revoked"],
            secret="secret2",
            status=WebhookSubscription.STATUS_ERROR,
        )

        active = list(WebhookSubscription.objects.active())
        self.assertIn(self.subscription, active)
        self.assertNotIn(other, active)

        created = list(WebhookSubscription.objects.for_event("memory.entry.created"))
        self.assertIn(self.subscription, created)
        self.assertNotIn(other, created)

    def test_status_transitions_and_counters(self) -> None:
        self.subscription.activate()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ACTIVE)
        self.assertEqual(self.subscription.failure_count, 0)

        self.subscription.pause()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_PAUSED)

        self.subscription.mark_success()
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ACTIVE)
        self.assertIsNotNone(self.subscription.last_success_at)
        self.assertEqual(self.subscription.last_error, "")

        now = timezone.now()
        with self.subTest("failure progression"):
            self.subscription.mark_failure("boom")
            self.subscription.refresh_from_db()
            self.assertEqual(self.subscription.failure_count, 1)
            self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ACTIVE)
            self.assertGreaterEqual(self.subscription.last_failure_at, now)
            self.assertEqual(self.subscription.last_error, "boom")

            self.subscription.mark_failure("boom")
            self.subscription.mark_failure("boom")
            self.subscription.refresh_from_db()
            self.assertEqual(self.subscription.failure_count, 3)
            self.assertEqual(self.subscription.status, WebhookSubscription.STATUS_ERROR)

    def test_set_events_normalizes_values(self) -> None:
        self.subscription.set_events(["consent.created", "memory.entry.created", "consent.created"])
        self.subscription.refresh_from_db()
        self.assertEqual(
            self.subscription.events,
            ["consent.created", "memory.entry.created"],
        )
