import re

with open(".env", "r", encoding="utf-8") as f:
    text = f.read()

text = re.sub(r'SCP_DEV_MODE=.*', 'SCP_DEV_MODE=0', text)
text = re.sub(r'SCP_SKIP_STARTUP_GATE=.*', 'SCP_SKIP_STARTUP_GATE=0', text)
text = re.sub(r'SCP_AUTO_APPROVE_TIER3=.*', 'SCP_AUTO_APPROVE_TIER3=0', text)
text = re.sub(r'SCP_EVOLUTION_AUTO=.*', 'SCP_EVOLUTION_AUTO=0', text)
text = re.sub(r'SCP_ENABLE_CLOSED_LOOP=.*', 'SCP_ENABLE_CLOSED_LOOP=0', text)
text = re.sub(r'SCP_TIER3_ALLOW_RELAXATION=.*', 'SCP_TIER3_ALLOW_RELAXATION=0', text)
text = re.sub(r'SCP_TIER3_ALLOW_BAREEXCEPTPASS=.*', 'SCP_TIER3_ALLOW_BAREEXCEPTPASS=0', text)

with open(".env", "w", encoding="utf-8") as f:
    f.write(text)
