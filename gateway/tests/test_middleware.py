from __future__ import annotations

import json

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from companies.models import ApiKey, Company
from gateway.middleware import ApiGatewayMiddleware


class ApiGatewayMiddlewareTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.factory = RequestFactory()
        self.company = Company.objects.create(name="Acme", slug="acme")
        self.api_key = ApiKey.objects.create(
            company=self.company,
            name="Primary",
            rate_limit=2,
            rate_limit_window=60,
        )
        self.middleware = ApiGatewayMiddleware(lambda request: None)

    def test_skips_non_api_paths(self):
        request = self.factory.get("/healthz")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)

    def test_requires_api_key_for_protected_paths(self):
        request = self.factory.get("/api/memory/")
        response = self.middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["detail"], "API key required.")

    def test_rejects_invalid_api_key(self):
        request = self.factory.get("/api/memory/", HTTP_X_API_KEY="invalid")
        response = self.middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["detail"], "Invalid API key.")

    def test_allows_valid_key_and_updates_usage(self):
        request = self.factory.get("/api/memory/", HTTP_X_API_KEY=self.api_key.key)
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        refreshed = ApiKey.objects.get(pk=self.api_key.pk)
        self.assertIsNotNone(refreshed.last_used_at)

    def test_rate_limit_enforced(self):
        request = self.factory.get("/api/memory/", HTTP_X_API_KEY=self.api_key.key)
        self.assertIsNone(self.middleware.process_request(request))
        self.assertIsNone(self.middleware.process_request(request))
        throttled = self.middleware.process_request(request)
        self.assertIsNotNone(throttled)
        self.assertEqual(throttled.status_code, 429)
        self.assertIn("Retry-After", throttled)
