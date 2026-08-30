import re

filepath = 'scp/core/db_manager.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Delete _cap_table method entirely. It looks like:
# def _cap_table(self, table_name: str, max_rows: int = 1000): ...
# Let's match it and all its content until the next def.
content = re.sub(
    r'[ \t]*def _cap_table\(.*?(?=\n[ \t]*def |\n[ \t]*class |\Z)',
    '\n',
    content,
    flags=re.DOTALL
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
