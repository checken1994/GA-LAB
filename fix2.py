import os
import glob
import re

experts_dir = r'scp\runtime\experts'

for filepath in glob.glob(os.path.join(experts_dir, '*.py')):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = re.sub(r'from scp\.runtime\.slm_base import BaseSLM as BaseSLM as Base', 'from scp.runtime.slm_base import BaseSLM as Base', content)
    content = re.sub(r'from scp\.runtime\.slms import BaseSLM as Base', 'from scp.runtime.slm_base import BaseSLM as Base', content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print("Fixed imports.")
