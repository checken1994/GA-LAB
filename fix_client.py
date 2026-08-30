import re

filepath = 'scp/llm_gateway/client.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Delete GroqProvider class
content = re.sub(
    r'class GroqProvider\(OpenRouterProvider\):.*?(?=class EnvCompatProvider)',
    '',
    content,
    flags=re.DOTALL
)

# Remove groq attributes instantiation in LLMGateway
content = re.sub(r'[ \t]*# Tier 2 - Groq.*?\n[ \t]*for task in tasks:\n[ \t]*setattr\(self, f"groq_\{task\}", GroqProvider\(task=task\)\)\n[ \t]*self\.groq_default = GroqProvider\(task="default"\)\n', '', content)
# Actually, the comment might have different encoding or text.
content = re.sub(r'[ \t]*# Tier 2.*?\n(?:[ \t]*for task in tasks:\n[ \t]*setattr\(self, f"groq_\{task\}", GroqProvider\(task=task\)\)\n[ \t]*self\.groq_default = GroqProvider\(task="default"\)\n)?', '', content)

# Also remove from groq dict in _get_provider_chain
content = re.sub(
    r'[ \t]*groq = \{\n[ \t]*"autofix":.*?\}\.get\(task, self\.groq_default\)\n',
    '',
    content,
    flags=re.DOTALL
)
# And from chain list: chain = [openrouter, *self._extra_providers.get(task, []), groq]
content = re.sub(
    r'chain = \[openrouter, \*self\._extra_providers\.get\(task, \[\]\), groq\]',
    'chain = [openrouter, *self._extra_providers.get(task, [])]',
    content
)

# Remove groq_calls
content = re.sub(r'[ \t]*"groq_calls": 0,\n', '', content)
content = re.sub(r'[ \t]*"groq_default":.*?\n', '', content)
content = re.sub(r'[ \t]*"groq_judge":.*?\n', '', content)
content = re.sub(r'[ \t]*"groq_chat":.*?\n', '', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
