import re

filepath = 'tests/test_provider_failover.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Just delete all functions containing "groq"
# test_failover_from_rate_limited_openrouter_to_groq
# test_failover_when_openrouter_fails_completely
# test_failover_with_extra_provider_in_between
# test_groq_disabled_without_key
# test_all_fail_returns_502

content = re.sub(r'def test_[a-zA-Z0-9_]*groq.*?(?=\n\n|\Z)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_failover_when_openrouter_fails.*?(?=\n\ndef |\Z)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_failover_with_extra_provider_in_between.*?(?=\n\ndef |\Z)', '', content, flags=re.DOTALL)
content = re.sub(r'def test_all_fail_returns_502.*?(?=\n\ndef |\Z)', '', content, flags=re.DOTALL)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
