import re

filepath = 'scp/runtime/multi_llm_crosscheck.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove imports
content = re.sub(r'[ \t]*from scp\.llm_gateway\.client import GroqProvider\n', '', content)

# Remove GroqProvider init and tasks logic
content = re.sub(r'[ \t]*# Xác định secondary.*?GroqProvider\._init_keys\(\)\n[ \t]*tasks = \[.*?\]\n[ \t]*if GroqProvider\.enabled:\n[ \t]*tasks\.append\(\("secondary", "groq_judge"\)\)', '    tasks = [("primary", "judge")]', content, flags=re.DOTALL)

# Also there's mojibake in comments so the regex above might fail.
# Let's just find and replace by strings
content = re.sub(
    r'[ \t]*GroqProvider\._init_keys\(\)\n[ \t]*tasks = \[\("primary", "judge"\)\]\n[ \t]*if GroqProvider\.enabled:\n[ \t]*tasks\.append\(\("secondary", "groq_judge"\)\)\n',
    '    tasks = [("primary", "judge")]\n',
    content
)

content = re.sub(
    r'[ \t]*if task == "groq_judge":.*?else:\n[ \t]*content, provider = gateway\.chat_sync\(prompt, system_prompt=system, task=task\)',
    '            content, provider = gateway.chat_sync(prompt, system_prompt=system, task=task)',
    content,
    flags=re.DOTALL
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
