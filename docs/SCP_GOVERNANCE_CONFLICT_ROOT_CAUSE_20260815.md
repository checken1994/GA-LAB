# SCP — Root cause lỗi câu trả lời đúng bị `CONFLICT`

**Ngày kiểm tra:** 15/08/2026  
**Môi trường:** PC Windows thật tại `C:\Users\check\Downloads\scp`  
**Phạm vi:** Chỉ sửa code/logic. Không tạo test cố định mới cho SCP. Không sửa production `.env`.

## Kết luận ngắn

Lỗi không nằm ở phép tính và cũng không phải do Governance KILL. Lỗi nằm ở việc nhiều lớp trong JudgeCore dùng các quy tắc khác nhau để đánh giá cùng một câu hỏi.

Đối với câu `2 + 2 = ?`, một nhánh có câu trả lời `2 + 2 = 4`, nhưng nhánh so khớp trước đó chỉ so chuỗi và từ. Khi nhiều SLM trả về các cách viết khác nhau, JudgeCore không nhận ra rằng `4` và `2 + 2 = 4` là cùng một kết quả. Nó đặt `verdict_type = CONFLICT` với lý do `AI không match bất kỳ SLM nào`.

Sau khi đã sửa nhánh so khớp, một lỗi thứ hai lộ ra. R17 claim gate thấy các claim của câu trả lời chưa có nguồn bên ngoài và tiếp tục đổi `PASS` thành `UNKNOWN`:

```text
[R17] UPHOLD: 3/3 claims unverified
```

Điều này hợp lý với câu hỏi kiến thức mở, nhưng là **false positive** với phép tính có thể kiểm tra độc lập bằng bộ tính toán an toàn đã có sẵn trong `scp/core/math_evaluator.py`.

## Chuỗi lỗi trước khi sửa

| Bước | Điều xảy ra | Hậu quả |
|---|---|---|
| 1 | Model/SLM tạo hoặc chọn `2 + 2 = 4` | Nội dung đáp án đúng |
| 2 | JudgeCore so khớp AI answer với SLM answer bằng substring và word overlap | `4` và `2 + 2 = 4` có thể không được nhận là cùng giá trị |
| 3 | Nhánh disagreement đặt `verdict_type = CONFLICT` | Câu đúng bị gắn nhãn xung đột |
| 4 | Sau khi nối verifier toán, claim verifier thấy `3/3` claim chưa có nguồn ngoài | `R17-FIX-2` hạ `PASS` thành `UNKNOWN` |
| 5 | API giữ lại câu trả lời kèm cảnh báo khi `UNKNOWN` | Người dùng thấy đáp án nhưng SCP không xác nhận là đúng |

### Bằng chứng mã nguồn

Trong `scp/runtime/judge_parts/judgecore_mixin.py`, vùng so khớp SLM trước bản vá chỉ kiểm tra chuỗi và số từ. Nếu không tìm thấy `matched_slm`, code đặt:

```python
verdict_type = "CONFLICT"
reasoning = "Các SLM có mâu thuẫn và AI không match bất kỳ SLM nào"
```

Trong cùng file, vùng R17-FIX-2 có quy tắc:

```python
if _total > 0 and _unverified / _total > 0.5:
    if verdict.verdict == "PASS":
        verdict.verdict = "UNKNOWN"
```

Quy tắc này không phân biệt claim kiến thức cần nguồn ngoài với phép tính có thể tự kiểm tra an toàn.

## Bản sửa đã thực hiện

### 1. So khớp số học không phụ thuộc cách viết

JudgeCore giờ nhận dạng câu hỏi có dạng số học đơn giản. Nó lấy số cuối trong câu trả lời của AI và số cuối trong câu trả lời SLM, sau đó so sánh bằng `Decimal`.

Ví dụ:

```text
AI: 2 + 2 = 4
SLM: 4
```

Hai câu được coi là cùng kết quả số học. Logic này **không bỏ qua luật primary/non-primary**. Nếu câu trả lời chỉ khớp SLM phụ, nó vẫn có thể bị `CONFLICT` theo luật an toàn cũ.

### 2. Dùng bộ kiểm tra toán deterministic đã có

JudgeCore đã nối `scp/core/math_evaluator.py`, không viết một bộ tính toán mới. Bộ này tự phân tích biểu thức qua AST an toàn và trả `PASS`, `FAIL` hoặc `UNKNOWN`.

Khi bộ tính toán trả `PASS`, JudgeCore ghi:

```text
Deterministic math verify PASS
```

và đặt độ tin cậy tối thiểu là `0.99` cho kết quả toán đó.

### 3. R17 không được hạ một phép tính đã kiểm tra độc lập

R17 vẫn hoạt động bình thường với câu kiến thức chưa được kiểm chứng. Nhưng nếu:

```text
_math_verdict == "PASS"
verdict.verdict == "PASS"
```

thì R17 không được hạ kết quả đó xuống `UNKNOWN` chỉ vì claim verifier không tìm thấy nguồn web. Câu sai vẫn bị `FAIL`; câu không parse được vẫn đi qua luật cũ.

### 4. Không nới lỏng lớp an toàn

Bản sửa không tắt WHY Gate, Governance, Antibody, primary/non-primary check, policy gate hoặc fail-closed. Các lớp này vẫn chạy sau deterministic math verifier và vẫn có thể chặn câu hỏi nguy hiểm.

## Reality evidence sau bản vá

Backend live được restart đúng process đang giữ cổng 8000:

```text
python.exe -m scp 8000
```

Health sau restart:

```text
HTTP 200
```

Các ca thực tế sau bản vá:

| Ca | Kết quả |
|---|---|
| Câu đúng `2 + 2 = ?` | `PASS`, confidence `0.99`, answer `2 + 2 = 4` |
| Câu trả lời sai `2 + 2 = 5` | `FAIL`, confidence `0.99`, answer bị giữ lại |
| Tấn công yêu cầu bỏ luật an toàn và xóa policy bằng PowerShell | `FAIL`, answer bị giữ lại |

Kết quả này chứng minh bản vá đã sửa đúng lỗi phân loại câu đúng và không biến câu sai hoặc yêu cầu nguy hiểm thành `PASS`.

## Các điểm không được kết luận quá mức

Bản vá này chỉ xử lý lỗi **câu trả lời số học đúng bị CONFLICT/UNKNOWN**. Nó không chứng minh toàn bộ factual benchmark đã đạt điểm cao.

Các câu địa lý, câu kiến thức mở và prompt injection vẫn phải qua evidence, claim verifier, WHY và Governance. Nếu không có nguồn đủ mạnh, `UNKNOWN` hoặc `CONFLICT` vẫn có thể là kết quả đúng theo nguyên tắc `PASS != TRUE`.

## File đã thay đổi

```text
scp/runtime/judge_parts/judgecore_mixin.py
```

Không tạo test cố định mới. Việc kiểm tra dùng reality run qua endpoint thật `/ask` và kiểm tra cú pháp Python.

## Kết luận cuối

Nguyên nhân gốc là **SCP dùng nhiều bộ phán quyết nhưng không truyền kết quả kiểm chứng deterministic từ đầu đến cuối**. Lớp so khớp không hiểu hai cách viết số học là tương đương; sau đó R17 lại coi mọi claim chưa có nguồn ngoài như chưa đủ tin, kể cả phép tính đã có thể tự tính.

Bản sửa đúng là: **tính độc lập trước, truyền bằng chứng qua JudgeCore, rồi mới áp dụng claim gate; không dùng thiếu nguồn web để phủ nhận kết quả đã được tính bằng bộ kiểm tra an toàn.**
