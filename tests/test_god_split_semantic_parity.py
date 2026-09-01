from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

# The GOD split must remain importable in the same fail-closed CI profile used
# by SCP tests. These values are test-only and deliberately non-production.
os.environ.setdefault("SCP_JWT_SECRET", "god-split-parity-test-secret-32bytes")
os.environ.setdefault("SCP_PRODUCTION_MODE", "0")
os.environ.setdefault("SCP_SKIP_STARTUP_GATE", "0")
os.environ.setdefault("SCP_EGRESS_MODE", "deny")


TARGET_MODULES = (
    "scp.api_server",
    "scp.autofix.engine",
    "scp.autofix.llm_fix",
    "scp.autofix.scanners.cross_func_taint_scanner",
    "scp.benchmark.run_benchmark_v2",
    "scp.core.db_manager",
    "scp.core.fast_learning_engine",
    "scp.data_sources.domain_registry",
    "scp.knowledge.antibody_system",
    "scp.meta.why_engine",
    "scp.runtime.judge_parts.judgecore_mixin",
    "scp.task_kernel",
)


@pytest.mark.parametrize("module_name", TARGET_MODULES)
def test_split_target_imports(module_name: str) -> None:
    """A semantic split may not turn an importable production module into a syntax/import failure."""
    importlib.import_module(module_name)


def test_domain_registry_keeps_parent_registry_binding() -> None:
    from scp.data_sources.domain_registry import search_domains_by_keyword

    assert "geography" in search_domains_by_keyword("What is the capital of France?")


def test_benchmark_helpers_keep_normalization_dependencies() -> None:
    from scp.benchmark.run_benchmark_v2 import check_factual_correctness

    ok, method = check_factual_correctness("4", "4", "numeric")
    assert ok is True
    assert method.startswith("numeric_match")


def test_db_manager_parts_share_runtime_state(tmp_path: Path) -> None:
    from scp.core.db_manager import db_query_one

    row = db_query_one("SELECT 1 AS x", db_path=str(tmp_path / "parity.db"))
    assert row == {"x": 1}


def test_fast_learning_engine_keeps_constants_and_schema(tmp_path: Path) -> None:
    from scp.core.fast_learning_engine import FastLearningEngine, get_country_domain_matrix

    engine = FastLearningEngine(
        scp_db_path=str(tmp_path / "learning.db"),
        data_dir=str(tmp_path / "data"),
    )
    assert engine is not None
    matrix = get_country_domain_matrix()
    assert "Việt Nam" in matrix
    assert "geography" in matrix["Việt Nam"]


def test_antibody_split_preserves_behavior() -> None:
    from scp.knowledge.antibody_system import DomainAntibodySystem

    system = DomainAntibodySystem()
    assert system.should_run(
        "dosage_validator",
        "What dosage should be used?",
        "medical",
        "paracetamol 500mg",
    ) is True


def test_why_engine_split_preserves_helper_wiring() -> None:
    from scp.meta.why_engine import WhyEngine

    engine = WhyEngine.__new__(WhyEngine)
    target, target_type, evidence_type = engine.identify_target("capital of France?")
    assert target
    assert target_type == "entity"
    assert evidence_type == "geographic_database"


def test_llm_fix_extracted_function_keeps_module_dependencies(tmp_path: Path) -> None:
    from scp.autofix.llm_fix import generate_fix_for_bug

    bug = SimpleNamespace(
        file=str(tmp_path / "does-not-exist.py"),
        line=1,
        bug_type="UnusedImport",
        description="unused import",
        suggested_fix="",
    )
    # Baseline contract: missing source file returns None; extraction must not
    # fail earlier with NameError because helper globals were left behind.
    assert generate_fix_for_bug(bug) is None


def test_cross_func_scanner_extracted_function_keeps_callgraph_helpers(tmp_path: Path) -> None:
    from scp.autofix.scanners.cross_func_taint_scanner import scan_file

    target = tmp_path / "safe_target.py"
    target.write_text("def identity(value):\n    return value\n", encoding="utf-8")
    result = scan_file(target)
    assert isinstance(result, list)


def test_task_kernel_split_preserves_create_contract(tmp_path: Path) -> None:
    from scp.task_kernel import TaskKernel

    kernel = TaskKernel(tmp_path / "kernel.db")
    try:
        task = kernel.create_task("parity-task", "parity", "prove split parity")
        assert task["task_id"] == "parity-task"
        assert task["state"] == "CREATED"
    finally:
        kernel.close()


def test_autofix_engine_constructs_after_split(tmp_path: Path) -> None:
    from scp.autofix.engine import AutoFixEngine

    engine = AutoFixEngine(data_dir=str(tmp_path / "autofix"))
    assert engine.data_dir.exists()


def test_api_server_keeps_public_service_identity() -> None:
    from scp.api_server import app

    assert getattr(app, "title", "")


def test_api_server_extracted_functions_bind_to_authoritative_globals() -> None:
    """Extracted API functions must execute against the composition root state."""
    import scp.api_server as api_server

    assert api_server._ask_impl.__globals__ is api_server.__dict__
    assert api_server._async_fact_check.__globals__ is api_server.__dict__

    lifespan_raw = getattr(api_server.lifespan, "__wrapped__", None)
    assert callable(lifespan_raw)
    assert lifespan_raw.__globals__ is api_server.__dict__


def test_api_server_keeps_detailed_health_contract() -> None:
    """The GOD split may not orphan or duplicate the detailed health endpoint."""
    import scp.api_server as api_server

    matches = [
        route
        for route in api_server.app.routes
        if getattr(route, "path", None) == "/health/detailed"
    ]
    assert len(matches) == 1

    route = matches[0]
    assert "GET" in (getattr(route, "methods", set()) or set())
    assert getattr(route, "endpoint", None) is api_server.health_detailed
    assert route.endpoint.__globals__ is api_server.__dict__


def test_split_facades_keep_public_module_identity() -> None:
    """Facade exports must still look like the stable production modules."""
    from scp.autofix.engine import AutoFixEngine
    from scp.core.fast_learning_engine import FastLearningEngine
    from scp.knowledge.antibody_system import DomainAntibodySystem
    from scp.meta.why_engine import WhyEngine
    from scp.task_kernel import TaskKernel

    for exported_type, expected_module in (
        (AutoFixEngine, "scp.autofix.engine"),
        (FastLearningEngine, "scp.core.fast_learning_engine"),
        (DomainAntibodySystem, "scp.knowledge.antibody_system"),
        (WhyEngine, "scp.meta.why_engine"),
        (TaskKernel, "scp.task_kernel"),
    ):
        assert exported_type.__module__ == expected_module


def test_judge_core_preserves_public_judge_contract() -> None:
    from scp.runtime.judge_parts.judgecore_mixin import JudgeCoreMixin

    assert callable(getattr(JudgeCoreMixin, "judge", None))
