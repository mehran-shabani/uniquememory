from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Tuple

from django.http import (HttpRequest, HttpResponseBadRequest, JsonResponse,
                         QueryDict)
from django.views import View

from graph.models import GraphEdge, GraphNode


class GraphRelatedView(View):
    """Return nodes related to a given anchor node ranked by graph proximity."""

    http_method_names = ["get"]
    max_depth: int = 4

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        node_type = request.GET.get("node_type")
        reference_id = request.GET.get("reference_id")
        if not node_type or not reference_id:
            return HttpResponseBadRequest("node_type and reference_id are required.")

        candidate_type = request.GET.get("candidate_type", "memory_entry")
        try:
            limit = self._parse_limit(request.GET)
        except ValueError:
            return HttpResponseBadRequest("limit must be a positive integer.")

        candidate_references = self._parse_candidates(request.GET)
        if not candidate_references:
            return HttpResponseBadRequest("At least one candidate reference must be provided.")

        anchor = GraphNode.objects.filter(
            node_type=node_type,
            reference_id=reference_id,
        ).first()
        if not anchor:
            return JsonResponse({"count": 0, "results": []}, status=200)

        candidates = list(
            GraphNode.objects.filter(
                node_type=candidate_type,
                reference_id__in=candidate_references,
            )
        )
        if not candidates:
            return JsonResponse({"count": 0, "results": []}, status=200)

        adjacency = self._build_adjacency()
        ranked = self._rank_candidates(anchor, candidates, adjacency)
        payload = {
            "node": {
                "id": anchor.id,
                "type": anchor.node_type,
                "reference_id": anchor.reference_id,
            },
            "count": min(limit, len(ranked)),
            "results": ranked[:limit],
        }
        return JsonResponse(payload)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _parse_limit(self, params: QueryDict) -> int:
        limit_param = params.get("limit")
        if limit_param is None:
            return 5
        limit = int(limit_param)
        if limit <= 0:
            raise ValueError
        return min(limit, 100)

    def _parse_candidates(self, params: QueryDict) -> List[str]:
        values: List[str] = []
        if "candidate" in params:
            values.extend(params.getlist("candidate"))
        candidates_param = params.get("candidates")
        if candidates_param:
            values.extend(part.strip() for part in candidates_param.split(","))

        seen = set()
        deduped: list[str] = []
        for value in (value.strip() for value in values):
            if value and value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped
    # ------------------------------------------------------------------
    # Ranking helpers
    # ------------------------------------------------------------------
    def _build_adjacency(self) -> Dict[int, List[Tuple[int, float]]]:
        adjacency: Dict[int, List[Tuple[int, float]]] = defaultdict(list)
        edges = GraphEdge.objects.all().values_list("source_id", "target_id", "weight")
        for source_id, target_id, weight in edges:
            adjacency[source_id].append((target_id, float(weight)))
            adjacency[target_id].append((source_id, float(weight)))
        return adjacency

    def _rank_candidates(
        self,
        anchor: GraphNode,
        candidates: Iterable[GraphNode],
        adjacency: Dict[int, List[Tuple[int, float]]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for candidate in candidates:
            score = self._compute_closeness(anchor_id=anchor.id, candidate_id=candidate.id, adjacency=adjacency)
            results.append(
                {
                    "node_id": candidate.id,
                    "reference_id": candidate.reference_id,
                    "node_type": candidate.node_type,
                    "score": round(score, 6),
                    "metadata": candidate.metadata,
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def _compute_closeness(
        self,
        *,
        anchor_id: int,
        candidate_id: int,
        adjacency: Dict[int, List[Tuple[int, float]]],
    ) -> float:
        if anchor_id == candidate_id:
            return 1.0
        visited = {anchor_id}
        queue: deque[Tuple[int, int, float]] = deque([(anchor_id, 0, 1.0)])
        best_score = 0.0
        while queue:
            node_id, depth, weight_product = queue.popleft()
            if depth >= self.max_depth:
                continue
            for neighbor_id, edge_weight in adjacency.get(node_id, []):
                next_depth = depth + 1
                next_weight = weight_product * edge_weight
                if neighbor_id == candidate_id:
                    distance_score = 1.0 / (next_depth + 1)
                    best_score = max(best_score, distance_score * next_weight)
                    continue
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, next_depth, next_weight))
        return best_score


__all__ = ["GraphRelatedView"]
