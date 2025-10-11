from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.utils import timezone
import pytest

from audit import signals as audit_signals
from memory.models import MemoryCondensationJob, MemoryEntry


@pytest.fixture(autouse=True)
def disable_audit_signals():
    post_save.disconnect(audit_signals.audit_post_save)
    post_delete.disconnect(audit_signals.audit_post_delete)
    yield
    post_save.connect(audit_signals.audit_post_save, weak=False)
    post_delete.connect(audit_signals.audit_post_delete, weak=False)


@pytest.mark.django_db
class TestMemoryModels:
    def setup_method(self) -> None:
        self.entry = MemoryEntry.objects.create(
            title="Initial",
            content="Some content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )

    def test_increment_version_optimistic_locking(self):
        original_version = self.entry.version
        self.entry.increment_version()
        self.entry.refresh_from_db()
        assert self.entry.version == original_version + 1

    def test_condensation_job_transitions(self):
        job = MemoryCondensationJob.objects.create(memory_entry=self.entry)

        job.start()
        assert job.status == MemoryCondensationJob.STATUS_PROCESSING
        assert job.started_at is not None
        assert job.attempts == 1

        with pytest.raises(ValueError):
            job.start()

        job.complete("summary")
        assert job.status == MemoryCondensationJob.STATUS_COMPLETED
        assert job.summary == "summary"
        assert job.completed_at is not None

        with pytest.raises(ValueError):
            job.fail("error")

        job.status = MemoryCondensationJob.STATUS_FAILED
        job.save(update_fields=["status"])

        job.reschedule(when=timezone.now())
        assert job.status == MemoryCondensationJob.STATUS_PENDING
        assert job.started_at is None
        assert job.completed_at is None

        job.start()
        job.fail("boom")
        assert job.status == MemoryCondensationJob.STATUS_FAILED
        assert job.error_message == "boom"

        job.reschedule()
        assert job.status == MemoryCondensationJob.STATUS_PENDING
