import time
import subprocess
import json
import os
import re
from datetime import datetime

LOG_FILE = "data/archives/patrol_reports.jsonl"
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_event(event_type, details):
    timestamp = datetime.now().isoformat()
    record = {"timestamp": timestamp, "type": event_type, "details": details}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def block_malicious_ip(ip):
    # WHITELIST AN TOÀN: Không bao giờ chặn IP nội bộ để tránh tự sát (Self-DoS)
    if ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
        log_event("WHITELIST_SKIP", f"Bỏ qua IP nội bộ: {ip}")
        return False
        
    try:
        # Lệnh can thiệp sâu vào nhân Windows Firewall
        cmd = f'netsh advfirewall firewall add rule name="SCP_PATROL_BLOCK_{ip}" dir=in action=block remoteip={ip}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            log_event("MITIGATION_SUCCESS", f"Đã TỰ ĐỘNG CHẶN thành công IP độc hại: {ip} trên Tường lửa Windows.")
            return True
        else:
            log_event("MITIGATION_FAILED", f"Thiếu quyền Admin để chặn IP {ip}. Cần chạy SCP bằng Run as Administrator.")
            return False
    except Exception as e:
        log_event("MITIGATION_ERROR", str(e))
        return False

def scan_network():
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        return [line.strip() for line in result.stdout.split('\n') if "ESTABLISHED" in line]
    except Exception as e:
        return []

def patrol_cycle():
    net_data = scan_network()
    anomalies = []
    for conn in net_data:
        # Phân tích thông minh: Dò tìm kết nối lạ đến cổng nguy hiểm (VD: 4444 Metasploit, 3389 RDP lậu)
        if ":4444 " in conn or ":3389 " in conn:
            anomalies.append(conn)
            
    if anomalies:
        for anomaly in anomalies:
            # Trích xuất IP của Hacker từ log mạng
            match = re.search(r'(\d+\.\d+\.\d+\.\d+):', anomaly)
            if match:
                hacker_ip = match.group(1)
                log_event("THREAT_DETECTED", f"Phát hiện kết nối dị thường: {anomaly}")
                block_malicious_ip(hacker_ip)
    else:
        log_event("SYSTEM_SAFE", "Mạng ổn định, tuần tra không phát hiện đe dọa.")

if __name__ == "__main__":
    print("SCP ACTIVE MITIGATION PATROL - ONLINE")
    patrol_cycle()
