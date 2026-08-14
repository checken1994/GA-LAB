from pathlib import Path


def test_ask_request_has_bounded_multimodal_and_history_fields():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scp" / "api_server_parts" / "helpers.py").read_text(encoding="utf-8")
    assert "image_data" in source
    assert "max_length=8_000_000" in source
    assert "conversation_history" in source
    assert "max_length=8" in source


def test_dashboard_preserves_session_and_has_explicit_media_controls():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scp" / "api" / "dashboard_html.py").read_text(encoding="utf-8")
    assert "sessionStorage" in source
    assert "conversation_history" in source
    assert "getUserMedia" in source
    assert "MediaRecorder" not in source
    assert "captureImage" in source
    assert "video: true, audio: false" in source


def test_real_ask_path_prioritizes_current_question_and_accepts_image_data():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scp" / "api_server.py").read_text(encoding="utf-8")
    assert "_history = []" in source
    assert "_history" in source
    assert "current question" in source.lower()
    assert "base64.b64decode" in source
    assert "Invalid or oversized image_data" in source


def test_websocket_chat_passes_conversation_context_to_judge():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scp" / "api" / "chat.py").read_text(encoding="utf-8")
    assert "get_context_string(session_id)" in source
    assert '"conversation_history": _conversation_context' in source
    assert '"current_question": user_message' in source
