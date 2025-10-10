from __future__ import annotations

from typing import Optional

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from memory.models import MemoryCondensationJob
from memory.services.condensation import generate_summary


class Command(BaseCommand):
    help = "Process pending memory condensation jobs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=None,
            help="Maximum number of jobs to process in this run.",
        )

    def handle(self, *args, **options):
        max_jobs: Optional[int] = options.get("max_jobs")
        processed = self._process_jobs(max_jobs=max_jobs)
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} condensation jobs."))

    def _process_jobs(self, *, max_jobs: Optional[int]) -> int:
        processed = 0
        while max_jobs is None or processed < max_jobs:
            job = self._acquire_next_job()
            if job is None:
                break
            try:
                summary = generate_summary(job.memory_entry)
                job.complete(summary)
            except Exception as exc:  # pragma: no cover - unexpected failure paths
                job.fail(str(exc))
            processed += 1
        return processed

    def _acquire_next_job(self) -> Optional[MemoryCondensationJob]:
        with transaction.atomic():
            job = (
                MemoryCondensationJob.objects.select_for_update(skip_locked=True)
                .due()
                .first()
            )
            if not job:
                return None
            job.start()
            return job
