from __future__ import annotations

from pathlib import Path

from tools.check_bandit_policy import classify_medium, evaluate


def _finding(path: Path, line: int, test_id: str) -> dict:
    return {
        "key": f"{test_id}|{path}|{line}|MEDIUM",
        "test_id": test_id,
        "filename": str(path),
        "line": line,
        "severity": "MEDIUM",
        "confidence": "HIGH",
        "test_name": "synthetic",
        "issue_text": "synthetic",
    }


def test_b310_accepts_fixed_https_origin_with_dynamic_path(tmp_path: Path) -> None:
    source = tmp_path / "safe_url.py"
    source.write_text(
        "import urllib.request\n"
        "def fetch(query):\n"
        "    url = 'https://api.example.com/search?q=' + query\n"
        "    req = urllib.request.Request(url)\n"
        "    return urllib.request.urlopen(req, timeout=5)\n",
        encoding="utf-8",
    )
    result = classify_medium(_finding(source, 5, "B310"))
    assert result["policy_class"] == "accepted_guard"
    assert "https://api.example.com" in result["policy_reason"]


def test_b310_rejects_dynamic_authority(tmp_path: Path) -> None:
    source = tmp_path / "unsafe_url.py"
    source.write_text(
        "import urllib.request\n"
        "def fetch(host, query):\n"
        "    url = f'https://{host}/search?q={query}'\n"
        "    return urllib.request.urlopen(url)\n",
        encoding="utf-8",
    )
    result = classify_medium(_finding(source, 4, "B310"))
    assert result["policy_class"] == "actionable"


def test_b310_rejects_plain_http_external_origin(tmp_path: Path) -> None:
    source = tmp_path / "plain_http.py"
    source.write_text(
        "import urllib.request\n"
        "def fetch(query):\n"
        "    url = 'http://example.com/search?q=' + query\n"
        "    return urllib.request.urlopen(url)\n",
        encoding="utf-8",
    )
    result = classify_medium(_finding(source, 4, "B310"))
    assert result["policy_class"] == "actionable"


def test_b108_recognizes_bwrap_tmpfs_mount_target(tmp_path: Path) -> None:
    source = tmp_path / "sandbox.py"
    source.write_text(
        "def build_bwrap_argv(cmd):\n"
        "    return ['bwrap', '--tmpfs', '/tmp', '--'] + cmd\n",
        encoding="utf-8",
    )
    result = classify_medium(_finding(source, 2, "B108"))
    assert result["policy_class"] == "false_positive"


def test_b307_accepts_only_restricted_strategy_eval_shape(tmp_path: Path) -> None:
    source = tmp_path / "hypothesis_eval.py"
    source.write_text(
        "def build(strategy_call, st):\n"
        "    if not strategy_call.startswith('@given(') or not strategy_call.endswith(')'):\n"
        "        return None\n"
        "    args_str = strategy_call[7:-1]\n"
        "    return eval(args_str, {'__builtins__': {}}, {'st': st})\n",
        encoding="utf-8",
    )
    result = classify_medium(_finding(source, 5, "B307"))
    assert result["policy_class"] == "accepted_guard"


def test_unknown_medium_is_actionable_regardless_of_legacy_count(tmp_path: Path) -> None:
    source = tmp_path / "other.py"
    source.write_text("value = 1\n", encoding="utf-8")
    finding = _finding(source, 1, "B999")
    result = evaluate(
        {
            "total": 1,
            "by_severity": {"MEDIUM": 1},
            "findings": [finding],
        },
        legacy_max_medium=999,
    )
    assert result["status"] == "FAIL"
    assert result["actionable_medium"] == 1
    assert result["legacy_count_threshold_is_authority"] is False
