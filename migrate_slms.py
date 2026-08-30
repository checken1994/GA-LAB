import os
import glob
import re

slm_dir = r'scp\runtime\slm_impls'
experts_dir = r'scp\runtime\experts'

if not os.path.exists(experts_dir):
    os.makedirs(experts_dir)

# 1. Move and rename files
for filepath in glob.glob(os.path.join(slm_dir, '*.py')):
    filename = os.path.basename(filepath)
    if filename == '__init__.py':
        new_filename = filename
    else:
        new_filename = filename.replace('_slm.py', '.py')
    
    new_filepath = os.path.join(experts_dir, new_filename)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 2. Replace class XxxSLM with class Xxx
    content = re.sub(r'class ([a-zA-Z0-9_]+)SLM\b', r'class \1', content)
    
    # 3. Fix internal imports if they import from slm_impls
    content = content.replace('scp.runtime.slm_impls', 'scp.runtime.experts')
    # Replace references to XxxSLM in the code
    content = re.sub(r'\b([a-zA-Z0-9_]+)SLM\b', r'\1', content)
    
    # Also change super().__init__(name="XxxSLM") to name="Xxx"
    # Actually the regex above \b([A-Za-z]+)SLM\b handles it if it's not in quotes. Let's do quotes too.
    content = re.sub(r'"([a-zA-Z0-9_]+)SLM"', r'"\1"', content)
    content = re.sub(r"'([a-zA-Z0-9_]+)SLM'", r"'\1'", content)
    
    with open(new_filepath, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Migrated SLMs to {experts_dir}")
