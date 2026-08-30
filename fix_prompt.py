import re

filepath = 'scp/api_server.py'
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
except UnicodeDecodeError:
    with open(filepath, 'r', encoding='latin-1') as f:
        content = f.read()

correct_prompt = 'Bạn là SCP — một trợ lý AI thông minh. Trả lời ngắn gọn, chính xác, bằng tiếng Việt. Chỉ trả lời câu hỏi HIỆN TẠI ở cuối yêu cầu. Không tiếp tục chủ đề cũ nếu câu hỏi mới đổi chủ đề. Nếu thiếu dữ liệu, nói rõ chưa đủ dữ liệu thay vì đoán.'
# find the system_prompt block
content = re.sub(
    r'system_prompt=\([\s\S]*?N\?u thi\?u d\? li\?u[^\"]*\"\s*\)',
    f'system_prompt=(\n                        "{correct_prompt}"\n                    )',
    content
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
