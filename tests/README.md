# Test layout

- `reality-tests/` contains individual reality contracts.
- `scripts/run_reality_tests_portable.py` is the portable orchestrator.
- Runtime output is written to `reports/reality/reality-tests-results.json`.
- `pytest -q` collects `tests/` and `scp/tests/`; reality contracts are executed separately by the portable orchestrator.
- Infrastructure error/unknown states must fail closed; they are not equivalent to PASS.
