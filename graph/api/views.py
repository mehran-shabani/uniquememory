from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from heapq import heappop, heappush
from typing import Any, ClassVar

from django.http import (HttpRequest, HttpResponseBadRequest, JsonResponse,
                         QueryDict)
from django.db.models import Q
from django.views import View

from graph.models import GraphEdge, GraphNode


class GraphRelatedView(View):
    """Return nodes related to a given anchor node ranked by graph proximity."""

    http_method_names = ["get"]
    max_depth: ClassVar[int] = 4

    def get(self, request: HttpRequest, *_: Any, **__: Any) -> JsonResponse:
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

        adjacency = self._build_adjacency(anchor, candidates)
        ranked = self._rank_candidates(anchor, candidates, adjacency)
        payload = {
            "node": {
                "id": anchor.id,
                "node_type": anchor.node_type,
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

    def _parse_candidates(self, params: QueryDict) -> list[str]:
        values: list[str] = []
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
    def _build_adjacency(
        self, anchor: GraphNode, _candidates: Iterable[GraphNode]
    ) -> dict[int, list[tuple[int, float]]]:
        adjacency: dict[int, list[tuple[int, float]]] = defaultdict(list)
        frontier: set[int] = {anchor.id}
        visited: set[int] = set()
        seen_edges: set[tuple[int, int]] = set()

        depth = 0
        while frontier and depth < self.max_depth:
            edges = GraphEdge.objects.filter(
                Q(source_id__in=frontier) | Q(target_id__in=frontier)
            ).values_list("source_id", "target_id", "weight")

            next_frontier: set[int] = set()
            for source_id, target_id, weight in edges:
                weight_value = float(weight)
                if (source_id, target_id) not in seen_edges:
                    adjacency[source_id].append((target_id, weight_value))
                    seen_edges.add((source_id, target_id))
                if (target_id, source_id) not in seen_edges:
                    adjacency[target_id].append((source_id, weight_value))
                    seen_edges.add((target_id, source_id))

                if target_id not in visited and target_id not in frontier:
                    next_frontier.add(target_id)
                if source_id not in visited and source_id not in frontier:
                    next_frontier.add(source_id)

            visited.update(frontier)
            depth += 1
            frontier = next_frontier - visited

        return adjacency

    def _rank_candidates(
        self,
        anchor: GraphNode,
        candidates: Iterable[GraphNode],
        adjacency: Dict[int, List[Tuple[int, float]]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for candidate in candidates:
            score = self._compute_closeness(anchor_id=anchor.id, candidate_id=candidate.id, adjacency=adjacency)
            results.append(
                {
                    "id": candidate.id,
                    "reference_id": candidate.reference_id,
                    "node_type": candidate.node_type,
                    "score": round(score, 6),
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def _compute_closeness(
        self,
        *,
        anchor_id: int,
        candidate_id: int,
        adjacency: dict[int, list[tuple[int, float]]],
    ) -> float:
        if anchor_id == candidate_id:
            return 1.0
        best_paths: dict[int, float] = {anchor_id: 1.0}
        heap: list[tuple[float, int, int]] = [(-1.0, anchor_id, 0)]
        best_score = 0.0

        while heap:
            neg_weight, node_id, depth = heappop(heap)
            weight_product = -neg_weight
            if depth >= self.max_depth:
                continue

            for neighbor_id, edge_weight in adjacency.get(node_id, []):
                next_depth = depth + 1
                if next_depth > self.max_depth:
                    continue

                next_weight = weight_product * edge_weight
                if neighbor_id == candidate_id:
                    distance_score = 1.0 / (next_depth + 1)
                    best_score = max(best_score, distance_score * next_weight)

                if next_weight <= best_paths.get(neighbor_id, 0.0):
                    continue

                best_paths[neighbor_id] = next_weight
                heappush(heap, (-next_weight, neighbor_id, next_depth))

        return best_score


__all__ = ["GraphRelatedView"]
