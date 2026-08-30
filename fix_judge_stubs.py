import re

filepath = 'scp/runtime/judge.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add the missing properties
properties = '''
    @property
    def domain_experts(self): return []
    @property
    def falsification(self): return None
    @property
    def error_store(self): return None
    @property
    def governance(self): return None
    @property
    def counter_response(self): return None
    @property
    def canary_monitor(self): return None
    @property
    def attack_memory(self): return None
    @property
    def domain_knowledge_store(self): return None
    @property
    def h8_redteam(self): return None
'''
# Insert them before the def judge or somewhere inside RealityJudge class
content = re.sub(
    r'(class RealityJudge.*?:\n(?: {4}"""[^"]+"""\n)?)(.*?)(?= {4}def judge)',
    r'\1\2' + properties,
    content,
    flags=re.DOTALL
)

# 2. Fix the stubs returning dummy data
content = re.sub(r'def analyze_session_rogue\(.*?\).*?:\n[ \t]*return \{"rogue_score": 0\.0\}', 'def analyze_session_rogue(self, *args, **kwargs) -> dict | None:\n        return None', content)
content = re.sub(r'async def run_threat_intel_crawl\(.*?\).*?:\n[ \t]*return \[\]', 'async def run_threat_intel_crawl(self, *args, **kwargs):\n        return None', content)
content = re.sub(r'async def run_scheduled_crawl\(.*?\).*?:\n[ \t]*return \{\}', 'async def run_scheduled_crawl(self, *args, **kwargs):\n        return None', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
