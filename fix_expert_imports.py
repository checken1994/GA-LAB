import os
import glob
import re

experts_dir = r'scp\runtime\experts'

for filepath in glob.glob(os.path.join(experts_dir, '*.py')):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix the import I messed up in the template
    content = content.replace('from scp.runtime.experts.__init__ import Base', 'from scp.runtime.slm_base import BaseSLM as Base')
    
    # Fix where I replaced BaseSLM with Base inside the existing files
    # Actually wait, in migrate_slms.py I did: content = re.sub(r'\b([a-zA-Z0-9_]+)SLM\b', r'\1', content)
    # This turned BaseSLM into Base everywhere!
    # And it turned SLMResponse into Response!
    # So I need to change Base back to BaseSLM or import BaseSLM as Base.
    content = content.replace('from scp.runtime.slms import Base', 'from scp.runtime.slm_base import BaseSLM as Base')
    content = content.replace('from scp.runtime.slm_base import Base', 'from scp.runtime.slm_base import BaseSLM as Base')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print("Fixed imports in experts.")
