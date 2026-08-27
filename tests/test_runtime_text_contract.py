import asyncio

from scp.api.routes.v104_routes import v104_learn_matrix
from scp.api.routes.v105_routes import v105_toggle_attack_mode


def test_v104_learning_matrix_runtime_text_is_clean_and_semantic():
    result = asyncio.run(v104_learn_matrix())
    assert result["matrix_size"] == "14 quốc gia x 5 lĩnh vực = 70 ô"
    assert result["summary"] == {
        "geography": "14 x 5 = 70 (theo quốc gia)",
        "history": "14 x 3 = 42 (theo quốc gia)",
        "chemistry": "14 x 3 = 42 (theo quốc gia) + 6 x 3 = 18 (theo hợp chất) = 60",
        "physics": "14 x 3 = 42 (theo quốc gia) + 3 (tổng quát) = 45",
        "biology": "14 x 3 = 42 (theo quốc gia) + 3 (tổng quát) = 45",
    }
    assert result["total_country_specific_combinations"] == 238


def test_v105_attack_mode_runtime_text_is_clean_and_state_preserved():
    enabled = asyncio.run(v105_toggle_attack_mode(True))
    disabled = asyncio.run(v105_toggle_attack_mode(False))
    assert enabled["attack_mode"] is True
    assert enabled["message"] == "Attack mode ENABLED — SCP auto-applies restraints"
    assert enabled["run_status"] == "SUCCESS"
    assert disabled["attack_mode"] is False
    assert disabled["message"] == "Attack mode DISABLED — normal permission flow"
    assert disabled["run_status"] == "SUCCESS"
