"""Model Lifecycle Auto-Adoption scanner (S35).

Scans /v1/models on configured local endpoints.
Implements the model lifecycle state machine:
DISCOVERED -> QUARANTINED -> (adversarial probe) -> QUALIFIED (on pass) or COOLDOWN (on fail) -> ACTIVE.
Zero-trust, fail-closed, real database persistence via FoundationDB.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from scp.contracts.time import now_utc_iso
from scp.llm_gateway.prober import ContractProber
from scp.persistence import FoundationDB

logger = logging.getLogger("scp.llm_gateway.discovery")


class ModelLifecycleState(str, Enum):
    """Lifecycle states for auto-discovered models."""

    DISCOVERED = "DISCOVERED"
    QUARANTINED = "QUARANTINED"
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    COOLDOWN = "COOLDOWN"


_DISCOVERY_MIGRATIONS = [
    (
        "0001_discovery_state",
        [
            """CREATE TABLE IF NOT EXISTS model_lifecycle (
                   endpoint TEXT NOT NULL,
                   model_id TEXT NOT NULL,
                   state TEXT NOT NULL,
                   discovered_at TEXT NOT NULL,
                   updated_at TEXT NOT NULL,
                   PRIMARY KEY (endpoint, model_id)
            )"""
        ],
    ),
]


class ModelDiscoveryStore:
    """Persistent storage for model lifecycle state backed by FoundationDB (SQLite)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db = FoundationDB(db_path, _DISCOVERY_MIGRATIONS)

    def upsert_model(
        self, endpoint: str, model_id: str, state: ModelLifecycleState
    ) -> None:
        """Insert or update the lifecycle state of a model."""
        now = now_utc_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO model_lifecycle (endpoint, model_id, state, discovered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(endpoint, model_id) DO UPDATE SET
                   state = excluded.state,
                   updated_at = excluded.updated_at""",
                (endpoint, model_id, state.value, now, now),
            )

    def get_model_state(
        self, endpoint: str, model_id: str
    ) -> ModelLifecycleState | None:
        """Retrieve current lifecycle state for an endpoint + model_id."""
        rows = self.db.query(
            "SELECT state FROM model_lifecycle WHERE endpoint = ? AND model_id = ?",
            (endpoint, model_id),
        )
        if rows:
            return ModelLifecycleState(rows[0]["state"])
        return None

    def list_models(self) -> list[dict[str, Any]]:
        """List all models currently tracked in the discovery store."""
        return [
            dict(r)
            for r in self.db.query(
                "SELECT endpoint, model_id, state, discovered_at, updated_at "
                "FROM model_lifecycle ORDER BY endpoint, model_id"
            )
        ]

    def get_models_by_state(
        self, state: ModelLifecycleState
    ) -> list[dict[str, Any]]:
        """Retrieve all models in a specific lifecycle state."""
        return [
            dict(r)
            for r in self.db.query(
                "SELECT endpoint, model_id, state, discovered_at, updated_at "
                "FROM model_lifecycle WHERE state = ? ORDER BY endpoint, model_id",
                (state.value,),
            )
        ]

    def close(self) -> None:
        """Close the underlying database connection."""
        self.db.close()


class LocalEndpointScanner:
    """Scans endpoints for models, executes adversarial probing, and advances lifecycle state."""

    def __init__(
        self,
        store: ModelDiscoveryStore,
        endpoints: list[str] | None = None,
        timeout: float = 10.0,
        prober_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.store = store
        self.timeout = timeout
        self.prober_factory = prober_factory

        if endpoints is None:
            endpoints_env = os.environ.get("SCP_LOCAL_ENDPOINTS", "")
            self.endpoints = [e.strip() for e in endpoints_env.split(",") if e.strip()]
        else:
            self.endpoints = endpoints

    async def run_discovery(self) -> None:
        """Scan all endpoints for /v1/models and mark newly found models as DISCOVERED."""
        if not self.endpoints:
            return

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [self._scan_single(client, ep) for ep in self.endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ep, result in zip(self.endpoints, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning("Failed to scan endpoint %s: %s", ep, result)
                else:
                    for model_id in result:
                        current_state = self.store.get_model_state(ep, model_id)
                        if current_state is None:
                            self.store.upsert_model(
                                ep, model_id, ModelLifecycleState.DISCOVERED
                            )

    async def _scan_single(self, client: httpx.AsyncClient, endpoint: str) -> list[str]:
        base_url = endpoint.rstrip("/")
        url = f"{base_url}/v1/models"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return []
        models = data.get("data", [])
        if not isinstance(models, list):
            return []
        return [m.get("id") for m in models if isinstance(m, dict) and "id" in m]

    async def run_lifecycle(self) -> None:
        """Transition models through their lifecycle:

        DISCOVERED -> QUARANTINED
        QUARANTINED -> probe -> QUALIFIED (on pass) or COOLDOWN (on fail)
        QUALIFIED -> ACTIVE
        """
        models = self.store.list_models()
        for model in models:
            ep = model["endpoint"]
            model_id = model["model_id"]
            state = ModelLifecycleState(model["state"])

            if state == ModelLifecycleState.DISCOVERED:
                self.store.upsert_model(ep, model_id, ModelLifecycleState.QUARANTINED)
                state = ModelLifecycleState.QUARANTINED

            if state == ModelLifecycleState.QUARANTINED:
                passed = await self._probe_model(ep, model_id)
                new_state = (
                    ModelLifecycleState.QUALIFIED
                    if passed
                    else ModelLifecycleState.COOLDOWN
                )
                self.store.upsert_model(ep, model_id, new_state)
                state = new_state

            if state == ModelLifecycleState.QUALIFIED:
                self.store.upsert_model(ep, model_id, ModelLifecycleState.ACTIVE)

    async def _probe_model(self, endpoint: str, model_id: str) -> bool:
        """Execute adversarial probe against endpoint + model_id."""
        base_url = endpoint.rstrip("/")
        url = f"{base_url}/v1/chat/completions"
        try:
            if self.prober_factory is not None:
                try:
                    prober = self.prober_factory(
                        endpoint_url=url, model=model_id, timeout=self.timeout
                    )
                except TypeError:
                    prober = self.prober_factory(url, model_id)
            else:
                prober = ContractProber(
                    endpoint_url=url, model=model_id, timeout=self.timeout
                )
            return await prober.probe_async()
        except Exception as e:
            logger.warning(
                "Probe execution failed for %s at %s: %s. Fail-closed to False.",
                model_id,
                endpoint,
                e,
            )
            return False
