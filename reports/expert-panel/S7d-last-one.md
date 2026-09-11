# S7d — Last one (Mimosa L3 gate defuse: test_security_sweep_s6.py:122)

Panel role: SCP Worker Agent S7d (micro, ĐÚNG 1 finding). Snapshot: working tree (KHÔNG commit). Chỉ sửa đúng 1 file được chỉ định.

## Skill binding (bắt buộc)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |

Decision binding (SCP DNA): #2/#26 (Reality over Model — tính chuỗi DDL chính xác từ `_VERDICT_CACHE_COPY_COLUMNS` tại runtime, không tin mô tả; pytest trước→sau là phán quyết), #5 (bằng chứng độc lập — đọc migration `rotate.py:86-139` thật trước khi chọn pattern), #17 (batch nhỏ — 1 file, 2 hunk), #22 (PASS_WITHIN_SCOPE — không chạy được Mimosa L3 gate cục bộ nên KHÔNG claim "gate sẽ xanh", chỉ claim shape trùng pattern đã-chưa-từng-bị-flag), #7 (rollback — revert từng hunk được).

## Finding

`tests/T03_capability/test_security_sweep_s6.py:122` — SQL 注入 (high). S7c đã defuse bằng biến trung gian `ddl` nhưng gate vẫn flag vì DDL được NỐI trong hàm (dataflow `cols` → `con.execute`). Pattern an toàn đã chứng minh trong cùng file: dòng 47 `con.execute(LEGACY_DDL)` — module-level pure literal, chưa từng bị flag.

## Fix (trước → sau)

| File:line | Trước | Sau |
|---|---|---|
| `tests/T03_capability/test_security_sweep_s6.py` (trước 118–122, sau ~134) | `cols = ", ".join(f"{name} TEXT" ...)`; `ddl = "CREATE TABLE " + "verdict_cache (" + cols + ")"`; `con.execute(ddl)` | `con.execute(CANONICAL_DDL)` |
| `tests/T03_capability/test_security_sweep_s6.py` (mới, sau `LEGACY_DDL`) | — | `CANONICAL_DDL = ("CREATE TABLE verdict_cache (" "cache_key TEXT, ...")` — module-level pure literal |

- `cols` tĩnh hoàn toàn (derive từ constant import) → dùng constant trọn vẹn, loại bỏ TOÀN BỘ dataflow vào `con.execute`. Không còn biến nào nối vào SQL trong hàm.
- Assertion/test KHÔNG đổi. `_VERDICT_CACHE_COPY_COLUMNS` vẫn được dùng ở test 1 + 2 (import không thừa).

## Reality test

- Byte-identity (thực nghiệm, `python -c` nạp module test theo path): `old == m.CANONICAL_DDL` → **True**; repr hai chuỗi trùng khớp 100%.
- pytest: trước = `3 passed in 0.64s, EXIT=0`; sau = `3 passed in 0.67s, EXIT=0`.
- `git status`: chỉ `tests/T03_capability/test_security_sweep_s6.py` modified.

## Residual / open questions

- Không chạy được Mimosa L3 gate cục bộ → claim giới hạn: statement vào `con.execute` giờ là module-level pure literal, trùng shape `LEGACY_DDL` (dòng 47) chưa từng bị flag trong mọi lô. Cần gate chạy lại để xác nhận.
- `CANONICAL_DDL` là literal cứng, không derive từ `_VERDICT_CACHE_COPY_COLUMNS` — drift risk tương đương precedent hiện có (test 1 hardcode inline 13 cột, dòng 70–74). Đã ghi comment "Must mirror" ngay trên constant; migration code (`rotate.py:95`) vẫn là nguồn sự thật runtime.
