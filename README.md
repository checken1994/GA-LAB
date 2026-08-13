# SCP DNA Audit - Round 11 Full Package (Windows Edition)

## QUICK START (Windows)

### Buoc 1 - Cai dat (1 lan dau)
Double-click `install-scp.bat`

Script tu:
- Tao Python venv (scp\venv\)
- Cai Python deps tu scp\requirements.txt
- Cai LLM Bridge deps (z-ai-web-dev-sdk)
- Cai Dashboard deps (Next.js)
- Tao .env tu template
- Tao scp\data\ dirs

### Buoc 2 - Cau hinh .env
Mo `.env` bang Notepad, dien:
```
OPENROUTER_API_KEY=<redacted>
```
Lay key free tai https://openrouter.ai/keys

### Buoc 3 - Chay
Double-click `start-scp.bat` -> browser mo http://localhost:3000

### Dung
Double-click `stop-scp.bat`

---

## YEU CAU HE THONG

| Phan mem | Tai tu | Phien ban |
|----------|--------|-----------|
| Python | https://www.python.org/downloads/ | 3.12+ (tick "Add to PATH") |
| Node.js | https://nodejs.org/ | 20+ |
| Bun | PowerShell: `npm install -g bun` | 1.0+ |

---

## NEU .bat KHONG CHAY DUOC

### Cach 1 - Chay tu PowerShell
```powershell
cd C:\Users\check\Downloads\scp-dna-audit-round11-full
.\install-scp.bat
```

### Cach 2 - Keo tha vao CMD
1. Mo Start menu -> go `cmd` -> Enter
2. Keo tha file `.bat` vao cua so CMD
3. Enter

### Cach 3 - Neu SmartScreen block
Right-click file `.bat` -> Properties -> tick "Unblock" -> OK -> chay lai

---

## TROUBLESHOOTING

### Loi: "python khong phai lenh"
- Python chua cai, hoac chua tick "Add Python to PATH"
- Tai lai Python: https://www.python.org/downloads/ -> tick "Add Python to PATH"

### Loi: "bun khong phai lenh"
- Mo PowerShell -> `npm install -g bun`
- Neu npm loi -> cai Node.js truoc: https://nodejs.org/

### Loi: "pip install -r requirements.txt" khong tim thay
- File `requirements.txt` nam trong `scp\` (khong phai root)
- Chay: `cd scp && pip install -r requirements.txt`
- Hoac chay `install-scp.bat` (script tu cd vao scp\)

### Loi: SCP /ask tra 500
- Kiem tra `.env` co `OPENROUTER_API_KEY` khong
- Kiem tra LLM Bridge chay (mo http://localhost:11434/api/tags - phai tra JSON)

---

## PORTS & URLs

| Service | Port | URL |
|---------|------|-----|
| Dashboard | 3000 | http://localhost:3000 |
| SCP API | 8000 | http://localhost:8000/health |
| LLM Bridge | 11434 | http://localhost:11434/api/tags |
| Loop Scheduler | 3030 | http://localhost:3030/ |

---

## CAU TRUC THU MUC

```
scp-dna-audit-round11-full\
+-- install-scp.bat          <- Chay dau tien (1 lan)
+-- start-scp.bat            <- Chay de khoi dong
+-- stop-scp.bat             <- Chay de dung
+-- WINDOWS-README.md        <- Huong dan day du
+-- .env.example             <- Template (copy thanh .env)
+-- dashboard\               <- Next.js 16 dashboard
+-- scp\                     <- SCP Python (378 .py, R11 patched)
|   +-- __main__.py          <- Entry: python -m scp 8000
|   +-- requirements.txt     <- Python deps
|   +-- .env.example
|   +-- autofix\             <- Engine v4 (12/12 modules wired)
|   +-- llm_gateway\
|   +-- venv\                <- Tao boi install-scp.bat
|   +-- data\                <- Tao boi install-scp.bat
+-- mini-services\
|   +-- llm-bridge\          <- Port 11434
|   +-- loop-scheduler\      <- Port 3030
+-- docs\                    <- Bao cao R9/R10/R11
```

---

Built by Ga Lab - R11 Windows Edition
