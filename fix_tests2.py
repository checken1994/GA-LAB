import re

filepath = 'tests/test_provider_failover.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the orphaned code inside _keyed
content = re.sub(
    r'    monkeypatch.setattr\(target, "_key_cycle".*?\n\n\n\n\n    gateway = LLMGateway\(\).*?openrouter_calls", 0\) >= 0',
    '    monkeypatch.setattr(target, "_key_cycle", itertools.cycle(["test-key"]), raising=False)\n',
    content,
    flags=re.DOTALL
)

# Remove Groq lines in other tests
content = re.sub(r'[ \t]*_keyed\(monkeypatch, GroqProvider\)\n', '', content)
content = re.sub(r'[ \t]*gateway\.groq_chat\._client = .*?\n', '', content)

content = re.sub(r'names == \["openrouter", "deepseek", "groq"\]', 'names == ["openrouter", "deepseek"]', content)

# Remove disabled test entirely
content = re.sub(
    r'\n\n\n    monkeypatch\.delenv\("GROQ_API_KEY".*?assert provider\.enabled is False\n',
    '',
    content,
    flags=re.DOTALL
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
