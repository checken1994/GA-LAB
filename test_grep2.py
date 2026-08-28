import glob
for file in glob.glob('scp/**/*.py', recursive=True):
    with open(file, 'r', encoding='utf-8') as f:
        try:
            content = f.read()
            if '_is_protected_path' in content:
                print(f"FOUND IN: {file}")
        except:
            pass
