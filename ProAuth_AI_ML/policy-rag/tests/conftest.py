"""
Shared pytest config for this test suite.

Registers the `integration` marker and keeps integration tests (real HTTP
calls to the live triage service, real Groq quota spent, 10-100s per
scenario) OPT-IN — the default `pytest` invocation only runs
test_gates_unit.py's fast, free, deterministic suite. This is deliberate:
this project already hit a real Groq daily-quota exhaustion once from
testing alone (see docs/PROGRESS_TRACKER.md §9.1) — a suite that spends
real tokens on every routine run isn't sustainable as the default.

Run the full thing including integration tests with:
    pytest --run-integration
(requires the triage service actually running — see
tests/test_triage_integration.py's module docstring for how to start it.)
"""
import pytest

# test_triage_graph.py is NOT a pytest file — it's a standalone manual
# eyeball-review script (see its own docstring: "Usage: cd policy-rag &&
# python3 tests/test_triage_graph.py") with top-level code that fires 7
# real Groq/RAG calls immediately on import, no `def test_*` functions and
# no `if __name__ == "__main__"` guard. Because its filename matches
# pytest's default `test_*.py` discovery pattern, a bare `pytest` (or
# `pytest tests/`) invocation would import — and therefore RUN — all 7 of
# its scenarios as an unintended side effect of collection alone, burning
# real Groq quota and taking minutes, before a single real test even
# starts (found live 2026-08-20 while building this suite — a `pytest
# tests/` run hung past a 30s timeout for exactly this reason). Excluded
# from collection here; run it directly with `python3
# tests/test_triage_graph.py` when you want its manual scenarios.
collect_ignore = ["test_triage_graph.py"]


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Also run integration tests that hit the live triage service over real HTTP (spends real Groq quota, slow).",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: real HTTP call to the live triage service, spends Groq quota")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="integration test — pass --run-integration to run (spends real Groq quota)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
