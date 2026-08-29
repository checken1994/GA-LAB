import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import asyncio
from scp.runtime.judge_llm import LLMJudge, TaskContext, OperationArtifact
from scp.security.capability_epoch import CapabilityAuthority

async def run_judge():
    judge = LLMJudge(None)
    # create fake context
    ctx = TaskContext(
        task_id="test",
        instruction="Read the file and summarize",
        artifacts=[OperationArtifact(path="test.txt", content="This is a test summary", action="READ")]
    )
    result = await judge.evaluate_postcondition(ctx)
    print(f"Judge verdict: {result}")

asyncio.run(run_judge())
