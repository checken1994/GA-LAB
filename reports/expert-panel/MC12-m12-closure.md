# MC12 — M12 Background WHY closure log (2026-09-11)

Worker: Agent MC12 (mạch đỏ cuối). Branch: `audit/runtime-guard-AUDIT-20260909`.
Pin closure: **fa9da62bb6907b395a7a6a362346b558f056ff10**.

## Timeline

1. **D0** — guard nhánh OK (đầu phiên + trước mỗi commit); đọc 4 SKILL bắt buộc
   (SHA256 khớp bản M10 ghi), CLOSURE-CONTRACT, M10-closure.json (mẫu tốt),
   STATUS-LEDGER. Baseline: `INVENTORY/M12.txt` 10F/16P; re-run đầu session
   **11F/15P** — NASA API trả HTTP 500 thật: test NASA cũ mock parse JSON nhưng
   vẫn gọi internet thật (hidden internet dependency, DNA #26).
2. **Root-cause 10 đỏ + 16 xanh** — 12 RC ghi trong `M12-closure.json.root_causes`.
   3 nhóm HARNESS phát minh contract (DoubtCron `db_path`/`tick()`, WhyEngine
   `verify_decision`/`lookup_sources`, `open_meteo._fetch_weather`) +
   13/16 "passed" là `pass` trắng (FA-01) + **6 PRODUCT_FAIL thật**.
3. **Fix product theo cụm, commit ngay (G9)**:
   - `85fc67f` — PF-1 init_why_db logger (WhyEngine chết 100% trên DB mới),
     PF-2 whyengine logger, PF-3 UPDATE…ORDER BY…LIMIT dead trên SQLite chuẩn
     (plan treo 'pending' vĩnh viễn) + `plan_id`, PF-4 wiring `why_engine` vào
     judge + `why_verify_loop` vào lifespan ACTIVE (trước đó chỉ wire ở
     `scp/api/_lifespan.py` — deployment không dùng), PF-5 seam
     `SCP_WHY_*_BASE` cho local HTTP fixture (mặc định giữ URL thật).
   - `f26324a` — PF-6 bảng thiếu cột `confidence_threshold` (claim query
     RETURNING nó → executed=0 100%), PF-7 open_meteo không encode target,
     harness rewrite 27 test no-mock.
   - `07b6358` — PF-8 `VerificationPlan` chỉ tồn tại nhờ injection importlib →
     NameError runtime khi import trực tiếp; resolve lazy tại 2 điểm dựng.
     Module-level import bị LOẠI sau khi tự falsify (circular thật, đã reproduce).
   - `fa9da62` — D6: claim-release except:pass → log warning.
4. **D1** — flow_12 **27 passed** ×2 deterministic tại pin (7.82s/7.71s);
   regression flow_02 34P, flow_06 22P/0F (count drift 23→22 → known_gaps G7).
   0 mock/patch, 0 skip/xfail, 0 internet (SCP_EGRESS_MODE=deny + local
   ThreadingHTTPServer + SCP_FITNESS_HISTORY redirect chống flake timing).
5. **D2** — build `SCP_GIT_SHA=fa9da62` EXIT=0, force-recreate, /health 200,
   `service_identity.commit` == pin, /readiness 200. Image `73005237bf01`.
   Build đã lặp 3 lần theo 3 pin (điều khoản hồi quy).
6. **D3** — probe trên deployment chính tại pin: doubt_cron start + ledger ghi
   thật; WhyGate ALLOW + audit; **scheduled WHY verify loop chạy thật** — seed
   pending row → cycle đầu sau đúng 180s → `[WHY-VERIFY] cycle: executed=1` →
   row `status=executed/verdict=PASS` với claim + executed_at. Trước fix,
   trực tiếp chạy `execute_pending_plans` trong container trả executed=0 với
   NameError nuốt ở DEBUG — bằng chứng reality cho PF-8.
7. **D4–D7** — seal tham chiếu 4a66b279 (posture giữ nguyên, diff chưa deep-scan);
   AST scan 12 file scope: **0 except:pass / 77 handlers**; TODO: **0**.
8. **D8** — `M12-closure.json` + STATUS-LEDGER (dòng M12 + mục (a) + update
   paragraph) + log này. Evidence backup ngoài repo:
   `$TEMP/m12evidence-backup-20260911` (12 file) trước khi commit.

## Verdict

**CLOSED_WITH_KNOWN_GAP** — D0/D1/D2/D6/D8 = PASS; D3/D4/D5 = PASS_WITH_LIMITS.
`falsification_status = PARTIALLY_FALSIFIED_AT_PIN`. Suite xanh ≠ production-ready;
8 known_gaps phải đọc trước khi tái sử dụng kết quả (quan trọng nhất: G1
why_sources không qua SCP_EGRESS_MODE; G2 empty-answer substring-PASS).

## Guard status

- 3 file WIP cấm: không đụng suốt session (`git add` theo đường dẫn cụ thể,
  stash không đụng). QUAN SÁT: giữa session 3 file này (+ `test_supervisor_child_env.py`,
  `PROMPT_INJECTION_GAP_REPORT.md`) trở lại modified bởi stream khác đang làm
  việc — MC12 không đọc/không commit; ghi nhận ở known_gaps G8.
- Không có sự cố mất evidence trong session MC12 (backup phòng ngừa đã tạo).
