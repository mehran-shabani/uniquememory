from __future__ import annotations

from django.core.cache import cache
import pytest

from memory.models import MemoryEntry
from memory.services.query import HybridQueryService


@pytest.mark.django_db
class TestHybridQueryService:
    def setup_method(self) -> None:
        cache.clear()
        self.entry_alpha = MemoryEntry.objects.create(
            title="Alpha",
            content="Alpha content",
            sensitivity=MemoryEntry.SENSITIVITY_PUBLIC,
            entry_type=MemoryEntry.TYPE_NOTE,
        )
        self.entry_beta = MemoryEntry.objects.create(
            title="Beta",
            content="Beta content",
            sensitivity=MemoryEntry.SENSITIVITY_CONFIDENTIAL,
            entry_type=MemoryEntry.TYPE_EVENT,
        )
        self.service = HybridQueryService()

    def test_combine_scores_prefers_highest_weight(self):
        text_scores = {self.entry_alpha.id: 0.6, self.entry_beta.id: 0.1}
        vector_scores = {self.entry_alpha.id: 0.2, self.entry_beta.id: 0.9}

        results = self.service._combine_scores(text_scores, vector_scores, limit=2)
        assert [result.entry_id for result in results] == [self.entry_alpha.id, self.entry_beta.id]
        alpha = results[0]
        assert alpha.combined_score == pytest.approx(
            (0.6 * self.service.text_weight) + (0.2 * self.service.vector_weight)
        )

    def test_combine_scores_ignores_missing_entries(self):
        text_scores = {999: 1.0}
        results = self.service._combine_scores(text_scores, {}, limit=5)
        assert results == []

    def test_blank_query_returns_empty_results(self):
        assert self.service.search(user_id="1", query="   ") == []
