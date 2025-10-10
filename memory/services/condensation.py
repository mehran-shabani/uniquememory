from __future__ import annotations

import re
from typing import Iterable

from memory.models import MemoryEntry


def _split_sentences(text: str) -> Iterable[str]:
    normalized = text.replace("\n", " ").strip()
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def generate_summary(entry: MemoryEntry, *, max_sentences: int = 3) -> str:
    """Produce a lightweight extractive summary for the entry."""

    sentences = list(_split_sentences(entry.content))
    if not sentences:
        return entry.content.strip()[:256]
    summary = " ".join(sentences[:max_sentences])
    return summary[:1024]
