import os

bad_strings = [
    'Ă¢â€Â¬Ă¢â‚¬Â',
    'Ă¡ÂºÂ ',
    'Ä‚Â´',
    'Ä‚â€',
    'Ă¡Â»Â¥',
    'Ă¡Â»â€˜',
    'Ă¡Â»Â',
    'Ä‚Âª',
    'Ă¡ÂºÂ¿',
    'Ä‚Â¢?â€šÂ¬?â‚¬Â',
    'Ă¡Â»Â',
]

def fix_mojibake(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        return
    
    new_content = content
    for bad in bad_strings:
        new_content = new_content.replace(bad, '-')
    
    # Also replace anything resembling a mojibake sequence, e.g., 'Ã¡'
    # Actually, let's just replace all non-ascii characters in comments?
    # No, Vietnamese comments are valid.
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {filepath}")

for root, _, files in os.walk("scp"):
    for file in files:
        if file.endswith(".py"):
            fix_mojibake(os.path.join(root, file))

