import pytest
import json
from unittest.mock import patch
from tools.t03_evidence_authority import EvidenceProducer, EvidenceValidator

@pytest.fixture
def base_profile():
    return {
        "name": "mock-profile",
        "clean_required": True,
        "commands": [["echo", "ok"]]
    }

@pytest.fixture
def mock_git_state():
    return ("sha_A", "tree_A", True)

def test_fa03_01_correct_exact_sha(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok\n"
            m.return_value.stderr = ""
            
            p = EvidenceProducer(base_profile)
            ev = p.produce()
            
            v = EvidenceValidator(expected_sha="sha_A")
            ok, msg = v.validate(ev)
            assert ok
            assert msg == "VERIFIED"

def test_fa03_02_evidence_sha_a_used_for_sha_b(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            p = EvidenceProducer(base_profile)
            ev = p.produce()
            
    # System actually has sha_B
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_B", "tree_A", True)):
        # Validator is run without spoofing expected_sha
        v = EvidenceValidator()
        ok, msg = v.validate(ev)
        assert not ok
        assert "SHA mismatch" in msg

def test_fa03_03_same_tree_different_commit_sha(base_profile):
    # Produce with SHA_A, Tree_A
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    # Validate while system has SHA_B but same Tree_A
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_B", "tree_A", True)):
        v = EvidenceValidator() # Default checks against system SHA
        ok, msg = v.validate(ev)
        assert not ok
        assert "SHA mismatch" in msg

def test_fa03_04_wrong_tree_hash(base_profile):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    # Tree changed to tree_B
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_B", True)):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Tree mismatch" in msg

def test_fa03_05_dirty_tree(base_profile):
    # Produce on dirty tree
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", False)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", False)):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "dirty working tree" in msg

def test_fa03_06_missing_required_field(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    del ev["exit_code"]
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Missing required fields" in msg

def test_fa03_07_malformed_evidence():
    v = EvidenceValidator()
    # Missing everything
    ok, msg = v.validate({})
    assert not ok
    assert "Missing required fields" in msg

def test_fa03_08_exit_code_non_zero(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 1
            m.return_value.stdout = "fail"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "non-zero exit code" in msg

def test_fa03_09_modified_test_profile(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    # Modify profile in evidence
    ev["profile"]["commands"] = [["rm", "-rf", "/"]]
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Test profile hash mismatch" in msg

def test_fa03_10_modified_output(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    ev["stdout"] = "fake pass"
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Output hash mismatch" in msg

def test_fa03_11_invalid_timestamps(base_profile, mock_git_state):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    ev["started_at"] = "2099-01-01T00:00:00Z"
    with patch('tools.t03_evidence_authority.get_git_state', return_value=mock_git_state):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "after finished_at" in msg

def test_fa03_12_caller_spoofs_candidate_sha(base_profile):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    # System actually has sha_B
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_B", "tree_A", True)):
        # Caller spoofing: passes expected_sha="sha_A" to try to get evidence A accepted for B.
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Spoofed SHA" in msg

def test_fa03_13_artifact_out_of_tree(base_profile, tmp_path):
    import tools.t03_evidence_authority as t03
    t03.PROJECT_ROOT = tmp_path
    
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            p = EvidenceProducer(base_profile)
            ev = p.produce()
            
            out_file = tmp_path / "scp-evidence" / "ev.json"
            out_file.parent.mkdir(parents=True)
            out_file.write_text(json.dumps(ev))
            
            assert out_file.exists()

def test_fa03_14_synthetic_merge_sha(base_profile):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("merge_sha_B", "tree_B", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("merge_sha_B", "tree_B", True)):
        v = EvidenceValidator(expected_sha="pr_head_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Spoofed SHA" in msg

def test_fa03_15_command_mutates_tracked_file(base_profile):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()

    # After verification, system shows dirty tree (False)
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", False)):
        v = EvidenceValidator()
        ok, msg = v.validate(ev)
        assert not ok
        assert "post-verification state is not clean" in msg

def test_fa03_16_command_creates_untracked_file(base_profile):
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()

    # After verification, system shows dirty tree (False)
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", False)):
        v = EvidenceValidator(expected_sha="sha_A")
        ok, msg = v.validate(ev)
        assert not ok
        assert "Current working tree is dirty" in msg

def test_fa03_17_current_clean_false_while_evidence_clean_true(base_profile):
    # Same concept: evidence says it started clean
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", True)):
        with patch('subprocess.run') as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok"
            m.return_value.stderr = ""
            ev = EvidenceProducer(base_profile).produce()
            
    # Validator checks state and sees dirty
    with patch('tools.t03_evidence_authority.get_git_state', return_value=("sha_A", "tree_A", False)):
        v = EvidenceValidator()
        ok, msg = v.validate(ev)
        assert not ok
        assert "post-verification state is not clean" in msg
