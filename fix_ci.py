import re

filepath = '.github/workflows/scp-release-gate.yml'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the path to the manifest
content = content.replace(
    r'reports\ROOT_SCP_SNAPSHOT_MANIFEST_20260826.json',
    r'reports\manifests_202608\ROOT_SCP_SNAPSHOT_MANIFEST_20260826.json'
)

# Add SCP_JWT_SECRET to env if it has an env block
if 'env:' in content:
    content = re.sub(
        r'(env:\n)',
        r'\1  SCP_JWT_SECRET: "dummy_secret_for_ci"\n',
        content
    )
else:
    # If no global env, we can try to add it at the job level or just set it globally
    # Typically workflows have jobs:
    content = re.sub(
        r'(jobs:\n  build:\n)',
        r'\1    env:\n      SCP_JWT_SECRET: "dummy_secret_for_ci"\n',
        content
    )

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
