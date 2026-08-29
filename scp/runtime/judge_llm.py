import requests

def _llm_judge(question: str, ai_answer: str, context: str = "") -> bool:
    try:
        prompt = f"Question: {question}\nContext: {context}\nAI Answer: {ai_answer}\nEvaluate if the AI Answer correctly answers the Question based ONLY on the Context (if provided) or general knowledge. Output only PASS or FAIL."
        resp = requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "llama3.2",
                "messages": [{"role": "system", "content": "You are a factual judge. You MUST output exactly the word PASS or FAIL and nothing else."}, {"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.0}
            },
            timeout=15
        )
        content = resp.json()["message"]["content"].strip().upper()
        return "PASS" in content
    except Exception as e:
        print(f"LLM Judge error: {e}")
        return False
