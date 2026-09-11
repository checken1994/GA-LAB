# TB Triage — 117 findings medium/low (Mimosa)

- Scan nguồn: `scan-2026-09-11T19-50-38.893Z-154ca91577a6` và `scan-2026-09-11T21-26-34.664Z-fb9c0c7b664e`
  (2 scans có bộ findings giống hệt nhau: 20 medium + 97 low = 117).
- Agent: TB (B5), 2026-09-12, branch `audit/runtime-guard-AUDIT-20260909`.
- Phương pháp: đọc từng finding, đối chiếu file:line thật, phân loại REAL_FIX / BY_DESIGN / FALSE_POSITIVE (DNA: evidence-first, không sửa mù).

## Tổng hợp

| Triage | Số lượng | Ghi chú |
|---|---:|---|
| REAL_FIX | 5 | 5 insecure temp file (mktemp→mkstemp) trong tools/probes — ĐÃ FIX trong commit `fix(security): address REAL findings from medium triage (B5)` |
| FALSE_POSITIVE | 10 | 4 SSTI (pattern metadata của scanner) + 4 cross-file taint llm-bridge (SQL parameterized) + 1 command-injection (shell=False) + 1 scanner hit vào comment |
| BY_DESIGN | 102 | 95 random non-crypto (sampling/jitter/simulation, đa số có noqa S311) + 7 cross-file taint _probe_http (loopback + safe_urlopen sẵn có) |
| **Tổng** | **117** | |

## Bảng triage đầy đủ (117)

| # | Sev | Kind | Location | Triage | Evidence / lý do |
|---|---|---|---|---|---|
| 0 | low | 命令注入 | `scp/core/safe_process.py:180` | FP | subprocess.run bat buoc shell=False + args dang list + whitelist/timeout (noqa S603 ghi ro tai scp/core/safe_process.py:168-181); khong co shell de inject. |
| 1 | low | 不安全的随机数 | `benchmark/question_generator.py:85` | BY_DESIGN | random non-crypto dung cho sampling/jitter (S311); khong phai material bao mat. |
| 2 | low | 不安全的随机数 | `scp/autofix/enterprise_scanners.py:444` | FP | Scanner hit vao chuoi comment tai lieu ('Pattern: random.randint -> secrets.SystemRandom') tai enterprise_scanners.py:444; khong phai code thuc thi random. |
| 3 | low | 不安全的随机数 | `scp/autofix/property_validator.py:215` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 4 | low | 不安全的随机数 | `scp/autofix/property_validator.py:226` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 5 | low | 不安全的随机数 | `scp/autofix/property_validator.py:238` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 6 | low | 不安全的随机数 | `scp/autofix/property_validator.py:257` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 7 | low | 不安全的随机数 | `scp/autofix/property_validator.py:273` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 8 | low | 不安全的随机数 | `scp/autofix/property_validator.py:296` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 9 | low | 不安全的随机数 | `scp/autofix/property_validator.py:301` | BY_DESIGN | Sinh input random cho property-based fuzzing; do dai khong phai secret. |
| 10 | low | 不安全的随机数 | `scp/benchmark/question_generator.py:317` | BY_DESIGN | Sampling sinh cau hoi benchmark (non-security, da co noqa S311). |
| 11 | low | 不安全的随机数 | `scp/brain/index_parts/retrieval.py:332` | BY_DESIGN | random.Random(42) seeded deterministic cho smoke test (retrieval.py:332 co comment). |
| 12 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:378` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 13 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:383` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 14 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:386` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 15 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:387` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 16 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:391` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 17 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:392` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 18 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:394` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 19 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:397` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 20 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:398` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 21 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:402` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 22 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:403` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 23 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:520` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 24 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:525` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 25 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:528` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 26 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:529` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 27 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:534` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 28 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:535` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 29 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:537` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 30 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:540` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 31 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:541` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 32 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:546` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 33 | low | 不安全的随机数 | `scp/core/fast_learning_engine_parts/fastlearningengine.py:547` | BY_DESIGN | Domain/quiz sampling cho learning engine; khong phai secret. |
| 34 | low | 不安全的随机数 | `scp/core/generator.py:50` | BY_DESIGN | Sinh de toan random cho question spec (S311); khong phai secret. |
| 35 | low | 不安全的随机数 | `scp/core/generator.py:51` | BY_DESIGN | Sinh de toan random cho question spec (S311); khong phai secret. |
| 36 | low | 不安全的随机数 | `scp/core/generator.py:52` | BY_DESIGN | Sinh de toan random cho question spec (S311); khong phai secret. |
| 37 | low | 不安全的随机数 | `scp/core/generator.py:53` | BY_DESIGN | Sinh de toan random cho question spec (S311); khong phai secret. |
| 38 | low | 不安全的随机数 | `scp/core/generator.py:54` | BY_DESIGN | Sinh de toan random cho question spec (S311); khong phai secret. |
| 39 | low | 不安全的随机数 | `scp/core/healing_engine.py:76` | BY_DESIGN | Random suffix cho ISSUE/KNOW id (S311); unique-id, khong phai secret. |
| 40 | low | 不安全的随机数 | `scp/core/healing_engine.py:87` | BY_DESIGN | Random suffix cho ISSUE/KNOW id (S311); unique-id, khong phai secret. |
| 41 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:211` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 42 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:228` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 43 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:263` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 44 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:299` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 45 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:300` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 46 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:304` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 47 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:334` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 48 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:364` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 49 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:396` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 50 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:439` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 51 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:477` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 52 | low | 不安全的随机数 | `scp/core/question_fetchers/data_fetchers.py:515` | BY_DESIGN | random.sample lay mau cau hoi tu nguon cong khai (Wikipedia/trivia). |
| 53 | low | 不安全的随机数 | `scp/core/question_fetchers/knowledge_fetchers.py:95` | BY_DESIGN | random.sample lay mau OLID/knowledge tu nguon cong khai. |
| 54 | low | 不安全的随机数 | `scp/core/question_fetchers/knowledge_fetchers.py:140` | BY_DESIGN | random.sample lay mau OLID/knowledge tu nguon cong khai. |
| 55 | low | 不安全的随机数 | `scp/core/question_fetchers/knowledge_fetchers.py:170` | BY_DESIGN | random.sample lay mau OLID/knowledge tu nguon cong khai. |
| 56 | low | 不安全的随机数 | `scp/core/question_fetchers/knowledge_fetchers.py:198` | BY_DESIGN | random.sample lay mau OLID/knowledge tu nguon cong khai. |
| 57 | low | 不安全的随机数 | `scp/core/question_fetchers/knowledge_fetchers.py:236` | BY_DESIGN | random.sample lay mau OLID/knowledge tu nguon cong khai. |
| 58 | low | 不安全的随机数 | `scp/core/question_fetchers/trivia_fetchers.py:214` | BY_DESIGN | random.choice lay cau hoi trivia tu cache cong khai (S311). |
| 59 | low | 不安全的随机数 | `scp/core/question_fetchers/trivia_fetchers.py:248` | BY_DESIGN | random.choice lay cau hoi trivia tu cache cong khai (S311). |
| 60 | low | 不安全的随机数 | `scp/core/question_fetchers/trivia_fetchers.py:250` | BY_DESIGN | random.choice lay cau hoi trivia tu cache cong khai (S311). |
| 61 | low | 不安全的随机数 | `scp/llm_gateway/client.py:328` | BY_DESIGN | Jitter backoff retry (client.py:328) — jitter non-crypto tieu chuan. |
| 62 | low | 不安全的随机数 | `scp/prediction/predictive.py:249` | BY_DESIGN | Jitter du bao thoi tiet mo phong (S311); khong phai secret. |
| 63 | low | 不安全的随机数 | `scp/prediction/predictive.py:268` | BY_DESIGN | Jitter du bao thoi tiet mo phong (S311); khong phai secret. |
| 64 | low | 不安全的随机数 | `scp/prediction/predictive.py:290` | BY_DESIGN | Jitter du bao thoi tiet mo phong (S311); khong phai secret. |
| 65 | low | 不安全的随机数 | `scp/prediction/predictive.py:308` | BY_DESIGN | Jitter du bao thoi tiet mo phong (S311); khong phai secret. |
| 66 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:90` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 67 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:99` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 68 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:104` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 69 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:146` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 70 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:159` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 71 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:162` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 72 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:177` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 73 | low | 不安全的随机数 | `scp/security/auto_payload_generator.py:190` | BY_DESIGN | Red-team payload sampling — tinh random la muc dich cua attack simulation. |
| 74 | low | 不安全的随机数 | `scp/security/circuit_breaker.py:118` | BY_DESIGN | half_open recovery sampling (circuit_breaker.py:118); khong phai secret. |
| 75 | low | 不安全的随机数 | `scp/security/gcg_attack.py:113` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 76 | low | 不安全的随机数 | `scp/security/gcg_attack.py:131` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 77 | low | 不安全的随机数 | `scp/security/gcg_attack.py:138` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 78 | low | 不安全的随机数 | `scp/security/gcg_attack.py:140` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 79 | low | 不安全的随机数 | `scp/security/gcg_attack.py:148` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 80 | low | 不安全的随机数 | `scp/security/gcg_attack.py:161` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 81 | low | 不安全的随机数 | `scp/security/gcg_attack.py:179` | BY_DESIGN | Adversarial perturbation simulation (S311); attack simulation can random. |
| 82 | low | 不安全的随机数 | `scp/security/threat_simulator.py:305` | BY_DESIGN | Threat mutation simulation (S311); can random de da hoa attack. |
| 83 | low | 不安全的随机数 | `scp/security/threat_simulator.py:355` | BY_DESIGN | Threat mutation simulation (S311); can random de da hoa attack. |
| 84 | low | 不安全的随机数 | `scp/security/threat_simulator.py:356` | BY_DESIGN | Threat mutation simulation (S311); can random de da hoa attack. |
| 85 | low | 不安全的随机数 | `scripts/generate_golden_suite.py:26` | BY_DESIGN | random.Random(SEED=20260829) deterministic, script offline sinh golden dataset. |
| 86 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:121` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 87 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:159` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 88 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:427` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 89 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:428` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 90 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:429` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 91 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:430` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 92 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:434` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 93 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:437` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 94 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:440` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 95 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:443` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 96 | low | 不安全的随机数 | `tools/probes/probe_challenger_m3_token_forgery.py:448` | BY_DESIGN | Probe forge token chu dich: random chi tao tid/fake material de chung minh verifier TU CHOI token gia. |
| 97 | medium | 临时文件不安全 | `tools/probes/probe_auditor_m1_adversarial.py:15` | REAL_FIX | tempfile.mktemp ten file du doan duoc (race/hijack). Da fix thanh tempfile.mkstemp + os.close trong commit fix(security) B5; chay lai 3 probe: ALL PASS / GREEN. |
| 98 | medium | 临时文件不安全 | `tools/probes/probe_auditor_m1_adversarial.py:51` | REAL_FIX | tempfile.mktemp ten file du doan duoc (race/hijack). Da fix thanh tempfile.mkstemp + os.close trong commit fix(security) B5; chay lai 3 probe: ALL PASS / GREEN. |
| 99 | medium | 临时文件不安全 | `tools/probes/probe_auditor_m1_adversarial.py:118` | REAL_FIX | tempfile.mktemp ten file du doan duoc (race/hijack). Da fix thanh tempfile.mkstemp + os.close trong commit fix(security) B5; chay lai 3 probe: ALL PASS / GREEN. |
| 100 | medium | 临时文件不安全 | `tools/probes/probe_gap11_failed.py:4` | REAL_FIX | tempfile.mktemp ten file du doan duoc (race/hijack). Da fix thanh tempfile.mkstemp + os.close trong commit fix(security) B5; chay lai 3 probe: ALL PASS / GREEN. |
| 101 | medium | 临时文件不安全 | `tools/probes/probe_gap11.py:5` | REAL_FIX | tempfile.mktemp ten file du doan duoc (race/hijack). Da fix thanh tempfile.mkstemp + os.close trong commit fix(security) B5; chay lai 3 probe: ALL PASS / GREEN. |
| 102 | medium | 疑似跨文件污点 | `mini-services/llm-bridge/core.ts:873` | FP | Sink cross-file la SQL parameterized 'VALUES(?,?,?,?,?)' tai scp/autofix/deterministic_worker.py:127-134; env cua sidecar TS khong den duoc SQL theo cach khac (mini-services/ nam ngoai pham vi sua cua task nay). |
| 103 | medium | 疑似跨文件污点 | `mini-services/llm-bridge/core.ts:887` | FP | Sink cross-file la SQL parameterized 'VALUES(?,?,?,?,?)' tai scp/autofix/deterministic_worker.py:127-134; env cua sidecar TS khong den duoc SQL theo cach khac (mini-services/ nam ngoai pham vi sua cua task nay). |
| 104 | medium | 疑似跨文件污点 | `mini-services/llm-bridge/core.ts:965` | FP | Sink cross-file la SQL parameterized 'VALUES(?,?,?,?,?)' tai scp/autofix/deterministic_worker.py:127-134; env cua sidecar TS khong den duoc SQL theo cach khac (mini-services/ nam ngoai pham vi sua cua task nay). |
| 105 | medium | 疑似跨文件污点 | `mini-services/llm-bridge/core.ts:980` | FP | Sink cross-file la SQL parameterized 'VALUES(?,?,?,?,?)' tai scp/autofix/deterministic_worker.py:127-134; env cua sidecar TS khong den duoc SQL theo cach khac (mini-services/ nam ngoai pham vi sua cua task nay). |
| 106 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:92` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 107 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:95` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 108 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:98` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 109 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:101` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 110 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:105` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 111 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:113` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 112 | medium | 疑似跨文件污点 | `reports/circuit-closures/M04-evidence/_probe_http.py:126` | BY_DESIGN | Probe bang chung M04: BASE hardcoded loopback 127.0.0.1:8003, da dung safe_urlopen(allow_internal=True) (fix S8, commit 481ac07); env chi giu token day vao header theo thiet ke redaction cua probe. |
| 113 | medium | 模板注入（SSTI） | `scp/autofix/evolution.py:147` | FP | evolution.py:147/149 la regex pattern metadata trong XSS_FIX_PATTERNS dung de DETECT/FIX SSTI, khong co jinja render that. |
| 114 | medium | 模板注入（SSTI） | `scp/autofix/evolution.py:149` | FP | evolution.py:147/149 la regex pattern metadata trong XSS_FIX_PATTERNS dung de DETECT/FIX SSTI, khong co jinja render that. |
| 115 | medium | 模板注入（SSTI） | `scp/autofix/scanners/xss_scanner.py:385` | FP | xss_scanner.py:385/468 la logic detect + docstring cua XSSScanner (matches_bypass_func); scanner khong render template. |
| 116 | medium | 模板注入（SSTI） | `scp/autofix/scanners/xss_scanner.py:468` | FP | xss_scanner.py:385/468 la logic detect + docstring cua XSSScanner (matches_bypass_func); scanner khong render template. |

## Ghi chú scope

- Chỉ nhóm REAL_FIX được sửa code; BY_DESIGN + FP giữ nguyên, justification ở bảng trên (không hạ chuẩn, không skip test).
- `mini-services/`, `reports/circuit-closures/` là vùng được lệnh task bảo vệ (do-not-touch) — các finding chạm vùng này chỉ triage, không sửa file.
- Kỳ vọng scan lại: medium giảm 20 → 15 (5 REAL_FIX hết); HIGH giữ 0.
- PASS = không thấy finding còn lại trong phạm vi quét hiện tại; không claim 'hệ thống sạch'.