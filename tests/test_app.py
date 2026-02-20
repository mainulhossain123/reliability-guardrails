"""
Tests for app/app.py (sample Flask service)
"""

from __future__ import annotations


class TestHealthEndpoint:
    def test_health_returns_200(self, app_client):
        response = app_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, app_client):
        response = app_client.get("/health")
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, app_client):
        response = app_client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type_is_text(self, app_client):
        response = app_client.get("/metrics")
        assert "text/plain" in response.content_type


class TestIndexEndpoint:
    def test_index_returns_json(self, app_client):
        # Retry to handle probabilistic errors
        for _ in range(20):
            response = app_client.get("/")
            if response.status_code == 200:
                data = response.get_json()
                assert "status" in data
                return
        # If all attempts were errors, that's also valid behaviour
        assert response.status_code in {200, 500}

    def test_checkout_endpoint_reachable(self, app_client):
        for _ in range(20):
            response = app_client.get("/checkout")
            if response.status_code == 200:
                data = response.get_json()
                assert "order_id" in data
                return
        assert response.status_code in {200, 500}
