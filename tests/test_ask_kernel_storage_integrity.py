from __future__ import annotations

from types import SimpleNamespace

import pytest

from scp.ask_kernel_adapter import AskKernelAdapter
from scp.kernel_storage import StorageIntegrityError
from scp.task_kernel import KernelError


def test_duplicate_idempotency_key_is_kernel_block_not_storage_leak(tmp_path) -> None:
    adapter = AskKernelAdapter(
        str(tmp_path / "ask.sqlite3"),
        str(tmp_path / "trace.jsonl"),
    )
    request = SimpleNamespace(headers={"X-SCP-Idempotency-Key": "same-request"})
    try:
        first = adapter.begin(
            "What is the verified fact?",
            ["The verified fact is stable."],
            "",
            "session",
            request=request,
        )
        assert first["task_id"]

        with pytest.raises(KernelError) as caught:
            adapter.begin(
                "What is the verified fact?",
                ["The verified fact is stable."],
                "",
                "session",
                request=request,
            )

        assert not isinstance(caught.value, StorageIntegrityError)
        assert "stable logical ask already exists" in str(caught.value)

        task = adapter.kernel.get_task(first["task_id"])
        assert task["state"] in adapter._IN_FLIGHT_STATES
        journal = adapter.kernel.verify_journal(first["task_id"])
        assert journal["hash_chain_valid"] is True
    finally:
        adapter.kernel.close()
