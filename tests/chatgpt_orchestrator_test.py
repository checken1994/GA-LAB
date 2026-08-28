"""Safe ChatGPT tab test for SCP V3.1.

Default mode is dry-run: it inspects DevTools targets and confirms that a
ChatGPT hostname is open, but it does not send anything. Use --send-confirmed
only after the user has explicitly approved sending the harmless test prompt.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.web_control.ai_orchestrator import AIOrchestrator
from scp.web_control.browser_session import BrowserSession

DEFAULT_PROMPT = "Trả lời đúng chuỗi sau và không thêm chữ nào: SCP_CHATGPT_TEST_OK"


def write_log(record: dict) -> None:
    root = Path(__file__).resolve().parents[1]
    log_path = root / "data" / "pc_controller" / "chatgpt-test.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    print(f"log={log_path}")


async def inspect_or_send(send_confirmed: bool, prompt: str) -> int:
    browser = BrowserSession()
    targets = await browser.targets()
    chatgpt_pages = [
        {"title": page.get("title", ""), "url": page.get("url", ""), "id": page.get("id", "")}
        for page in targets
        if page.get("type") == "page" and any(host in str(page.get("url", "")).lower() for host in ("chatgpt.com", "chat.openai.com"))
    ]
    print(f"chatgpt_pages={len(chatgpt_pages)}")
    for page in chatgpt_pages:
        print(f"chatgpt_tab={page['title']} | {page['url']}")
    if not chatgpt_pages:
        record = {"timestamp": time.time(), "mode": "dry-run" if not send_confirmed else "send", "success": False, "error": "No ChatGPT hostname tab found", "pages": chatgpt_pages}
        write_log(record)
        return 2
    if not send_confirmed:
        record = {"timestamp": time.time(), "mode": "dry-run", "success": True, "wouldSend": prompt, "pages": chatgpt_pages}
        write_log(record)
        print("DRY_RUN_OK: nothing was sent")
        return 0
    orchestrator = AIOrchestrator(browser)
    result = await orchestrator.ask_ai(
        "chatgpt",
        prompt,
        approved=True,
        use_browser=True,
        allow_api_fallback=False,
    )
    record = {"timestamp": time.time(), "mode": "send-confirmed", "prompt": prompt, "result": result}
    write_log(record)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SCP V3.1 ChatGPT orchestrator test")
    parser.add_argument("--send-confirmed", action="store_true", help="Send the harmless prompt; requires prior user confirmation")
    parser.add_argument("--prompt", default=os.environ.get("SCP_CHATGPT_TEST_PROMPT", DEFAULT_PROMPT), help="Harmless prompt to send")
    args = parser.parse_args()
    return asyncio.run(inspect_or_send(args.send_confirmed, args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
