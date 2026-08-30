import re

filepath = 'scp/meta/why_gate.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''    FALSIFICATION_REJECT_PATTERNS = [
        r"remove.*block|delete.*rule|skip.*detect",  # relaxation
        r"lower.*threshold|raise.*confidence|looser|relax",  # loosening
        r"allow.*attack|whitelist|bypass.*security",  # security bypass
        r"ignore.*error|suppress.*warning|silent.*fail",  # error suppression
        # Vietnamese equivalents
        r"tắt.*strict|nới lỏng.*bảo mật|bỏ qua.*kiểm tra|giảm.*rate|tắt.*rate|tắt.*bảo vệ",
    ]'''

content = re.sub(
    r'[ \t]*FALSIFICATION_REJECT_PATTERNS = \[[^\]]+\]',
    replacement,
    content
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
