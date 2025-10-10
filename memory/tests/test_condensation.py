from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from memory.models import MemoryCondensationJob, MemoryEntry


class CondensationCommandTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.entry = MemoryEntry.objects.create(
            title="Daily log",
            content="Today we explored the bazaar. It was vibrant. Learned new recipes.",
        )

    def test_processes_pending_job_and_creates_summary(self) -> None:
        job = MemoryCondensationJob.objects.create(memory_entry=self.entry)

        call_command("run_condensation")

        job.refresh_from_db()
        self.assertEqual(job.status, MemoryCondensationJob.STATUS_COMPLETED, job.error_message)
        self.assertTrue(job.summary.startswith("Today we explored"))
        self.assertGreater(job.attempts, 0)

    def test_failures_mark_job_and_allow_retry(self) -> None:
        job = MemoryCondensationJob.objects.create(memory_entry=self.entry)

        with mock.patch("memory.management.commands.run_condensation.generate_summary", side_effect=RuntimeError("oops")):
            call_command("run_condensation")

        job.refresh_from_db()
        self.assertEqual(job.status, MemoryCondensationJob.STATUS_FAILED)
        self.assertIn("oops", job.error_message)

        scheduled_time = timezone.now() + timedelta(minutes=5)
        job.reschedule(when=scheduled_time)
        self.assertEqual(job.status, MemoryCondensationJob.STATUS_PENDING)
        self.assertEqual(job.scheduled_for.replace(microsecond=0), scheduled_time.replace(microsecond=0))
