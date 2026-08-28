import re

file_path = r"c:\Users\check\Downloads\scp\scp\task_kernel.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Thêm trạng thái PATROLLING
if '"PATROLLING"' not in content:
    content = content.replace('"READY": {"QUEUED", "CANCELLED"},', '"READY": {"QUEUED", "PATROLLING", "CANCELLED"},')
    content = content.replace('"RECOVERING": {"RECONCILING",', '    "PATROLLING": {"RUNNING", "RECOVERING", "CANCELLED", "FAILED", "CHECKPOINTED"},\n    "RECOVERING": {"RECONCILING",')
    content = content.replace('TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}', 'TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}\nACTIVE_STATES = {"RUNNING", "PATROLLING", "VERIFYING", "RECONCILING", "RECOVERING"}')

# 2. Thêm hàm auto_reconcile_orphans vào TaskKernel class
auto_reconcile_code = """
    def auto_reconcile_orphans(self, actor: str = "kernel_watchdog") -> list[str]:
        '''Tự động rà soát các task bị mồ côi (chết do crash, mất kết nối) và đưa vào RECONCILING'''
        orphans = []
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            # Tìm các task đang LEASED, RUNNING, PATROLLING nhưng đã quá hạn lease (60 giây mặc định)
            rows = self.conn.execute('''
                SELECT task_id, state 
                FROM tasks 
                WHERE state IN ('LEASED', 'RUNNING', 'PATROLLING') 
                  AND (strftime('%s', 'now') - strftime('%s', updated_at)) > 60
            ''').fetchall()
            
            for r in rows:
                tid = r["task_id"]
                # 1. Chuyển sang UNKNOWN
                self.conn.execute("UPDATE tasks SET state='UNKNOWN', updated_at=datetime('now') WHERE task_id=?", (tid,))
                self._append_event(tid, "STATE_TRANSITION", r["state"], "UNKNOWN", actor, "ORPHAN_TIMEOUT", {})
                
                # 2. Quyết định phục hồi
                decision = self.recovery_decision("LOST_RESPONSE", True, "UNKNOWN")
                if decision.state_directive == "RECONCILING":
                    self.conn.execute("UPDATE tasks SET state='RECONCILING', updated_at=datetime('now') WHERE task_id=?", (tid,))
                    self._append_event(tid, "STATE_TRANSITION", "UNKNOWN", "RECONCILING", actor, "AUTO_RECONCILE_INITIATED", {})
                orphans.append(tid)
            self._commit()
        except Exception as e:
            self._rollback()
            raise
        return orphans
"""

if "def auto_reconcile_orphans" not in content:
    # Tìm hàm cuối cùng trong TaskKernel class hoặc append vào sau def _commit
    content = content.replace('def get_task(', auto_reconcile_code + '\n    def get_task(')

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Đã vá xong TaskKernel!")
