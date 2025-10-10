from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from embeddings.models import Embedding
from memory.models import MemoryEntry

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate dense vector embeddings for MemoryEntry records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            default=getattr(settings, "EMBEDDINGS_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
            help="SentenceTransformers model to use for encoding.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=32,
            help="Number of entries to encode per batch.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional limit on the number of entries to process.",
        )

    def handle(self, *args, **options):
        model_name: str = options["model"]
        batch_size: int = options["batch_size"]
        limit: int | None = options["limit"]

        embedder = self._load_model(model_name)

        queryset = MemoryEntry.objects.order_by("id")
        if limit:
            queryset = queryset[:limit]
        entries = list(queryset)
        if not entries:
            self.stdout.write("No memory entries found to embed.")
            return

        texts = [self._compose_text(entry) for entry in entries]
        vectors = self._encode_batches(embedder, texts, batch_size=batch_size)

        processed = 0
        for entry, vector in zip(entries, vectors, strict=False):
            vector_list = [float(value) for value in vector]
            defaults = {
                "vector": vector_list,
                "dimension": len(vector_list),
                "model_name": model_name,
            }
            Embedding.objects.update_or_create(memory_entry=entry, defaults=defaults)
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"Stored embeddings for {processed} memory entries."))

    def _load_model(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise CommandError(
                "sentence-transformers package is required to build embeddings."
            ) from exc

        self.stdout.write(f"Loading embedding model '{model_name}'...")
        return SentenceTransformer(model_name)

    def _encode_batches(self, model, texts: Iterable[str], *, batch_size: int):
        try:
            return model.encode(list(texts), batch_size=batch_size, convert_to_numpy=False)
        except Exception as exc:  # pragma: no cover - runtime errors should surface
            logger.exception("Failed to encode texts", exc_info=exc)
            raise CommandError("Failed to encode memory entries") from exc

    @staticmethod
    def _compose_text(entry: MemoryEntry) -> str:
        return f"{entry.title}\n\n{entry.content}"
