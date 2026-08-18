"""Load testing for Praviar API using Locust.

Run with:
    pip install locust
    cd api
    locust -f load_tests/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 in your browser to configure and start the test.

Typical test profile:
    - 10 users, 1 user/sec ramp-up → baseline
    - 50 users, 5 users/sec → moderate load
    - 100 users, 10 users/sec → stress test
"""

from __future__ import annotations

import json
import random
import uuid

from locust import HttpUser, between, task

# Dev token for local testing (matches api/src/api/deps.py dev bypass)
DEV_TOKEN = "dev-token"
HEADERS = {
    "Authorization": f"Bearer {DEV_TOKEN}",
    "Content-Type": "application/json",
}


class FTOAnalysisUser(HttpUser):
    """Simulates a scientist using the FTO analysis platform."""

    wait_time = between(2, 5)

    def on_start(self) -> None:
        """Fetch initial data on user start."""
        self._analysis_ids: list[str] = []
        self._completed_ids: list[str] = []

        # Warm up by fetching existing analyses
        with self.client.get(
            "/api/v1/analyses",
            headers=HEADERS,
            catch_response=True,
            name="/api/v1/analyses [list]",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    self._analysis_ids.append(item["id"])
                    if item.get("status") == "completed":
                        self._completed_ids.append(item["id"])

    @task(5)
    def list_analyses(self) -> None:
        """Most common action: browse the analysis library."""
        self.client.get(
            "/api/v1/analyses",
            headers=HEADERS,
            name="/api/v1/analyses [list]",
        )

    @task(3)
    def get_analysis_detail(self) -> None:
        """View a specific analysis."""
        if not self._analysis_ids:
            return
        aid = random.choice(self._analysis_ids)
        self.client.get(
            f"/api/v1/analyses/{aid}",
            headers=HEADERS,
            name="/api/v1/analyses/:id [detail]",
        )

    @task(3)
    def get_report(self) -> None:
        """View a completed report (heaviest response — full JSONB)."""
        if not self._completed_ids:
            return
        aid = random.choice(self._completed_ids)
        self.client.get(
            f"/api/v1/reports/{aid}",
            headers=HEADERS,
            name="/api/v1/reports/:id [full report]",
        )

    @task(2)
    def get_report_summary(self) -> None:
        """View report summary (lightweight)."""
        if not self._completed_ids:
            return
        aid = random.choice(self._completed_ids)
        self.client.get(
            f"/api/v1/reports/{aid}/summary",
            headers=HEADERS,
            name="/api/v1/reports/:id/summary",
        )

    @task(2)
    def list_comments(self) -> None:
        """Fetch comments for an analysis."""
        if not self._analysis_ids:
            return
        aid = random.choice(self._analysis_ids)
        self.client.get(
            f"/api/v1/comments?analysis_id={aid}",
            headers=HEADERS,
            name="/api/v1/comments [list]",
        )

    @task(1)
    def post_comment(self) -> None:
        """Add a comment (write operation)."""
        if not self._analysis_ids:
            return
        aid = random.choice(self._analysis_ids)
        self.client.post(
            "/api/v1/comments",
            headers=HEADERS,
            data=json.dumps(
                {
                    "analysis_id": aid,
                    "body": f"Load test comment {uuid.uuid4().hex[:8]}",
                    "target_type": "analysis",
                    "target_id": aid,
                }
            ),
            name="/api/v1/comments [create]",
        )

    @task(1)
    def get_config_presets(self) -> None:
        """Fetch pipeline configuration presets."""
        self.client.get(
            "/api/v1/configs/presets",
            headers=HEADERS,
            name="/api/v1/configs/presets",
        )

    @task(1)
    def health_check(self) -> None:
        """Health endpoint (no auth)."""
        self.client.get("/api/health", name="/api/health")

    @task(1)
    def readiness_check(self) -> None:
        """Readiness endpoint (verifies DB + Redis)."""
        self.client.get("/api/health/ready", name="/api/health/ready")


class QuickCheckUser(HttpUser):
    """Simulates a user doing quick compound checks (lighter load profile)."""

    wait_time = between(5, 15)
    weight = 1  # Lower weight than FTOAnalysisUser

    @task(3)
    def list_analyses(self) -> None:
        self.client.get(
            "/api/v1/analyses",
            headers=HEADERS,
            name="/api/v1/analyses [list]",
        )

    @task(1)
    def create_analysis(self) -> None:
        """Submit a new analysis (triggers Celery task)."""
        compounds = [
            "aspirin",
            "ibuprofen",
            "caffeine",
            "benzene",
            "ethanol",
        ]
        self.client.post(
            "/api/v1/analyses",
            headers=HEADERS,
            data=json.dumps(
                {
                    "compound_input": random.choice(compounds),
                    "config": {
                        "search_max_ranked_results": 50,
                        "max_analysis_patents": 5,
                    },
                }
            ),
            name="/api/v1/analyses [create]",
        )
