from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.db.models import Max
from django.utils.functional import cached_property

from embeddings.models import Embedding
from memory.models import MemoryEntry

try:  # pragma: no cover - optional dependency for production environments
    from sentence_transformers import SentenceTransformer  # type: ignore[import]
except ImportError:  # pragma: no cover - dependency guard
    SentenceTransformer = None  # type: ignore[assignment]

CACHE_NAMESPACE = "memory-hybrid-query"


@dataclass
class HybridSearchResult:
    entry_id: int
    title: str
    snippet: str
    combined_score: float
    text_score: float
    vector_score: float
    sensitivity: str
    entry_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.entry_id,
            "title": self.title,
            "snippet": self.snippet,
            "combined_score": self.combined_score,
            "scores": {
                "text": self.text_score,
                "vector": self.vector_score,
            },
            "sensitivity": self.sensitivity,
            "entry_type": self.entry_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "HybridSearchResult":
        return cls(
            entry_id=data["id"],
            title=data["title"],
            snippet=data.get("snippet", ""),
            combined_score=float(data.get("combined_score", 0.0)),
            text_score=float(data.get("scores", {}).get("text", 0.0)),
            vector_score=float(data.get("scores", {}).get("vector", 0.0)),
            sensitivity=data.get("sensitivity", MemoryEntry.SENSITIVITY_PUBLIC),
            entry_type=data.get("entry_type", MemoryEntry.TYPE_NOTE),
        )


class HybridQueryService:
    """Execute hybrid (text + vector) retrieval against memory entries."""

    text_weight: float = 0.6
    vector_weight: float = 0.4
    cache_timeout: int = 120
    fts_table: str = "memory_memoryentry_fts"

    def search(self, *, user_id: str, query: str, limit: int = 10) -> list[HybridSearchResult]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return []

        cache_key = self._cache_key(user_id=user_id, query=normalized_query, limit=limit)
        cached = cache.get(cache_key)
        if cached is not None:
            return [HybridSearchResult.from_dict(item) for item in cached]

        self._ensure_fts_index()
        text_scores = self._text_search(normalized_query, limit=limit)
        query_vector = self._encode_query(normalized_query)
        vector_scores = self._vector_search(query_vector, limit=limit * 3)

        results = self._combine_scores(text_scores, vector_scores, limit)
        cache.set(cache_key, [result.to_dict() for result in results], timeout=self.cache_timeout)
        return results

    def _cache_key(self, *, user_id: str, query: str, limit: int) -> str:
        return f"{CACHE_NAMESPACE}:{user_id}:{limit}:{hash(query)}"

    def _ensure_fts_index(self) -> None:
        if not MemoryEntry.objects.exists():
            return

        with connections["default"].cursor() as cursor:
            cursor.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {self.fts_table} USING fts5(title, content)"
            )
            latest_update = MemoryEntry.objects.aggregate(max_updated=Max("updated_at"))["max_updated"]
            marker_key = f"{CACHE_NAMESPACE}:fts-version"
            marker = cache.get(marker_key)
            if marker != latest_update:
                cursor.execute(f"DELETE FROM {self.fts_table}")
                values = MemoryEntry.objects.values_list("id", "title", "content")
                rows = [
                    (
                        entry_id,
                        title or "",
                        content or "",
                    )
                    for entry_id, title, content in values
                ]
                if rows:
                    cursor.executemany(
                        f"INSERT INTO {self.fts_table}(rowid, title, content) VALUES (?, ?, ?)",
                        rows,
                    )
                cache.set(marker_key, latest_update, timeout=self.cache_timeout)

    def _prepare_fts_query(self, query: str) -> str:
        terms = [term.strip() for term in query.split() if term.strip()]
        if not terms:
            return query
        return " ".join(f"{term}*" for term in terms)

    def _text_search(self, query: str, *, limit: int) -> dict[int, float]:
        scores: dict[int, float] = {}
        if not query:
            return scores
        fts_query = self._prepare_fts_query(query)
        with connections["default"].cursor() as cursor:
            cursor.execute(
                f"SELECT rowid, bm25({self.fts_table}) AS rank "
                f"FROM {self.fts_table} WHERE {self.fts_table} MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, limit),
            )
            for rowid, rank in cursor.fetchall():
                rank_value = float(rank)
                if rank_value < 0:
                    rank_value = 0.0
                normalized = 1.0 / (1.0 + rank_value)
                scores[int(rowid)] = normalized
        return scores

    def _vector_search(self, query_vector: Iterable[float], *, limit: int) -> dict[int, float]:
        results: dict[int, float] = {}
        vectors = list(query_vector)
        if not vectors:
            return results
        norm_query = self._vector_norm(vectors)
        if norm_query == 0.0:
            return results
        embeddings = Embedding.objects.select_related("memory_entry").all()
        scores: list[tuple[int, float]] = []
        for embedding in embeddings:
            candidate_vector = embedding.as_vector()
            score = self._cosine_similarity(vectors, candidate_vector, norm_query)
            if score > 0:
                scores.append((embedding.memory_entry_id, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        for entry_id, score in scores[:limit]:
            results[entry_id] = score
        return results

    def _combine_scores(
        self,
        text_scores: dict[int, float],
        vector_scores: dict[int, float],
        limit: int,
    ) -> list[HybridSearchResult]:
        entry_ids = set(text_scores) | set(vector_scores)
        if not entry_ids:
            return []

        combined: list[tuple[int, float, float, float]] = []
        for entry_id in entry_ids:
            text_score = text_scores.get(entry_id, 0.0)
            vector_score = vector_scores.get(entry_id, 0.0)
            combined_score = (text_score * self.text_weight) + (vector_score * self.vector_weight)
            combined.append((entry_id, combined_score, text_score, vector_score))

        combined.sort(key=lambda item: (item[1], item[2], item[3]), reverse=True)
        selected_ids = [entry_id for entry_id, *_ in combined[:limit]]
        entries = {entry.id: entry for entry in MemoryEntry.objects.filter(id__in=selected_ids)}

        results: list[HybridSearchResult] = []
        for entry_id, combined_score, text_score, vector_score in combined:
            if entry_id not in entries:
                continue
            entry = entries[entry_id]
            snippet = (entry.content or "")[:200]
            results.append(
                HybridSearchResult(
                    entry_id=entry.id,
                    title=entry.title,
                    snippet=snippet,
                    combined_score=combined_score,
                    text_score=text_score,
                    vector_score=vector_score,
                    sensitivity=entry.sensitivity,
                    entry_type=entry.entry_type,
                )
            )
            if len(results) >= limit:
                break
        return results

    def _encode_query(self, query: str) -> list[float]:
        backend = self._embedding_backend
        encoded = backend.encode([query], batch_size=1, convert_to_numpy=False)
        if isinstance(encoded, list):
            vector: Any = encoded[0]
        else:  # numpy array like
            vector = encoded[0]
        if hasattr(vector, "tolist"):
            values = vector.tolist()
        elif isinstance(vector, (list, tuple)):
            values = vector
        else:
            try:
                values = list(vector)
            except TypeError:
                values = [vector]
        return [float(value) for value in values]

    @cached_property
    def _embedding_backend(self):
        backend_path = getattr(settings, "EMBEDDINGS_BACKEND", None)
        if backend_path:
            from django.utils.module_loading import import_string

            backend_factory = import_string(backend_path)
            return backend_factory()
        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers package is required for embedding queries."
            )
        model_name = getattr(settings, "EMBEDDINGS_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformer(model_name)

    @staticmethod
    def _vector_norm(vector: Iterable[float]) -> float:
        return math.sqrt(sum(value * value for value in vector))

    @staticmethod
    def _cosine_similarity(
        vector_a: Iterable[float],
        vector_b: Iterable[float],
        norm_a: float,
    ) -> float:
        values_b = list(vector_b)
        if not values_b:
            return 0.0
        norm_b = HybridQueryService._vector_norm(values_b)
        if norm_b == 0.0:
            return 0.0
        dot = sum(a * b for a, b in zip(vector_a, values_b))
        return dot / (norm_a * norm_b)
