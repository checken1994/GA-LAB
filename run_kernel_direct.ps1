Write-Host "Chạy bài kiểm tra trực tiếp qua ask_kernel_adapter.py (Không qua FastAPI để xem chính xác AskKernelAdapter bắt lỗi ở đâu)..."
$env:PYTHONIOENCODING="utf-8"
python c:\Users\check\Downloads\scp\benchmark\run_smoke_test_with_evidence.py
