from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any
import time

router = APIRouter(prefix="/swe-bench/v1", tags=["swe-bench-compat"])

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None

@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    return {
        "id": "chatcmpl-scp",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Function execution deferred to agent loop.",
                "tool_calls": []
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

