import pytest
import asyncio
import subprocess
from pathlib import Path
from scp.llm_gateway.client import get_gateway

@pytest.mark.asyncio
async def test_evaluate_branch_against_scp_dna():
    """
    [SCP DNA - Cấp độ Đánh giá Bằng Chứng]
    Bài kiểm tra này sử dụng Hệ thống SCP Hoàn chỉnh để đánh giá chính mã nguồn 
    đã được thay đổi trong nhánh hiện tại.
    """
    # 1. Trích xuất diff của nhánh hiện tại (so với commit gốc, giả sử HEAD~3 hoặc origin/main)
    # Để test chạy ổn định, ta lấy diff của commit hiện tại.
    proc = subprocess.run(["git", "show", "--stat"], capture_output=True, text=True)
    diff_text = proc.stdout
    
    # 2. Tải 29 nguyên lý DNA
    dna_path = Path(".agents/skills/scp-dna/SKILL.md")
    if not dna_path.exists():
        pytest.skip("Không tìm thấy tệp DNA SCP")
    dna_content = dna_path.read_text(encoding="utf-8")
    
    # 3. Sử dụng LLM Gateway để đánh giá (nếu có Egress)
    gateway = get_gateway()
        
    prompt = (
        "Bạn là SCP Judge, hãy áp dụng 29 nguyên lý DNA và 13 Kỹ năng SCP. "
        "Dưới đây là các thay đổi mã nguồn mới nhất trên nhánh này:\n\n"
        f"{diff_text}\n\n"
        "Câu hỏi: Mã nguồn này có vi phạm Fail-Closed, có hardcode, hay có ảo giác không? "
        "Trình bày theo format JSON: {\"verdict\": \"PASS\" hoặc \"FAIL\", \"reason\": \"...\"}"
    )
    
    ans, err = await gateway.chat(question=prompt, task="self_eval")
    
    # Nếu bị chặn bởi policy (ví dụ chạy trong CI strict), bỏ qua
    if not ans or err:
        pytest.skip(f"LLM không khả dụng hoặc bị chặn egress: {err}")
        
    # Đánh giá kết quả
    assert "PASS" in ans.upper(), f"Thay đổi nhánh không đạt chuẩn SCP DNA! Lý do: {ans}"
