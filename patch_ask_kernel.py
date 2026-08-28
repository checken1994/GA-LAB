import json
import re

with open(r"scp\ask_kernel_adapter.py", "r", encoding="utf-8") as f:
    text = f.read()

# Remove old `_terms` function
text = re.sub(r'def _terms\(text: str\) -> set\[str\]:\n    return set\(re\.findall\(.*?\)[\s\S]*?(?=class AskKernelAdapter:)', '', text)

# Insert the LLM Judge logic inside verify()
# The old logic:
old_ratio_logic = """        evidence_terms = set().union(*(_terms(value) for value in contexts))
        answer_terms = _terms(answer)
        grounded_ratio = len(answer_terms & evidence_terms) / max(1, len(answer_terms))"""

new_ratio_logic = """        # --- SCP V3 ENTERPRISE: LLM-AS-A-JUDGE ---
        # Reality > Model: Thay vì đếm từ (Grounded Ratio), dùng LLM chéo để verify
        try:
            from scp.autofix.llm_fix import _call_openrouter
            prompt = f"Evidence: {contexts}\\n\\nAnswer: {answer}\\n\\nDoes the evidence fully support the answer? Reply YES or NO."
            llm_reply = _call_openrouter(prompt, max_tokens=10)
            if llm_reply and "YES" in llm_reply.upper():
                grounded_ratio = 1.0
            else:
                grounded_ratio = 0.0
        except Exception:
            # Fallback nếu LLM Judge sập -> fail closed
            grounded_ratio = 0.0
"""

text = text.replace(old_ratio_logic, new_ratio_logic)

with open(r"scp\ask_kernel_adapter.py", "w", encoding="utf-8") as f:
    f.write(text)
