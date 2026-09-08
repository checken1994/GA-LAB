import tempfile
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import json
import sqlite3
from scp.task_kernel import TaskKernel, InvalidTransition, KernelError, StaleLease

db_path = tempfile.mktemp(suffix='.sqlite3')
kernel = TaskKernel(db_path)
try:
    # 1. Create task
    kernel.create_task('t1', 'owner1', 'test goal', max_attempts=2)
    kernel.transition('t1', 'PLANNING')
    
    # 2. Verify direct transition to FAILED blocked
    try:
        kernel.transition('t1', 'FAILED')
        raise AssertionError('Should have raised InvalidTransition')
    except InvalidTransition as e:
        print('Direct FAILED blocked:', e)

    kernel.transition('t1', 'READY')
    kernel.transition('t1', 'QUEUED')
    lease = kernel.claim('t1', 'worker1')
    kernel.start('t1', lease.lease_id)

    # 3. Verify actor mismatch in commit_failed
    try:
        kernel.commit_failed('t1', lease.lease_id, actor='rogue', failure_classification='FATAL', indictment_ref='ref1')
        raise AssertionError('Should have failed actor check')
    except InvalidTransition as e:
        print('Actor mismatch blocked:', e)

    # 4. Verify empty indictment rejected
    try:
        kernel.commit_failed('t1', lease.lease_id, actor='worker1', failure_classification='FATAL', indictment_ref='   ')
        raise AssertionError('Should have failed indictment check')
    except KernelError as e:
        print('Empty indictment blocked:', e)

    # 5. Verify retryable attempt 1 -> RETRY_SCHEDULED
    res1 = kernel.commit_failed(
        't1',
        lease.lease_id,
        actor='worker1',
        failure_classification='RETRYABLE',
        indictment_ref='ref_attempt1',
        details={'err': 'timeout'}
    )
    print('Attempt 1 state:', res1['state'], 'attempts:', res1['attempts'])
    assert res1['state'] == 'RETRY_SCHEDULED'
    assert res1['attempts'] == 1
    assert res1['active_lease_id'] is None

    # Inspect SQLite directly
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t_row = conn.execute("SELECT * FROM tasks WHERE task_id='t1'").fetchone()
    print('DB task state:', t_row['state'], 'attempts:', t_row['attempts'], 'error:', t_row['error'])
    assert t_row['state'] == 'RETRY_SCHEDULED'
    assert t_row['attempts'] == 1
    err_json = json.loads(t_row['error'])
    assert err_json['indictment_ref'] == 'ref_attempt1'

    e_rows = conn.execute("SELECT * FROM events WHERE task_id='t1' AND type='TASK_RETRY_SCHEDULED'").fetchall()
    print('Retry events in DB:', len(e_rows))
    assert len(e_rows) == 1
    conn.close()

    # Attempt 2 -> transition to QUEUED, claim, and fail again -> Exhausted -> FAILED
    kernel.transition('t1', 'QUEUED')
    lease2 = kernel.claim('t1', 'worker1')
    kernel.start('t1', lease2.lease_id)
    res2 = kernel.commit_failed(
        't1',
        lease2.lease_id,
        actor='worker1',
        failure_classification='RETRYABLE',
        indictment_ref='ref_attempt2'
    )
    print('Attempt 2 state:', res2['state'], 'attempts:', res2['attempts'])
    assert res2['state'] == 'FAILED'
    assert res2['attempts'] == 2
    assert res2['active_lease_id'] is None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t_row2 = conn.execute("SELECT * FROM tasks WHERE task_id='t1'").fetchone()
    print('DB final task state:', t_row2['state'], 'attempts:', t_row2['attempts'], 'error:', t_row2['error'])
    assert t_row2['state'] == 'FAILED'
    err_json2 = json.loads(t_row2['error'])
    assert err_json2['indictment_ref'] == 'ref_attempt2'
    conn.close()

    print('ALL VERIFICATION CHECKS PASSED EMPIRICALLY ON PHYSICAL SQLITE!')

    # 6. Verify AskKernelAdapter integration
    from scp.ask_kernel_adapter import AskKernelAdapter
    trace_path = tempfile.mktemp(suffix='.jsonl')
    adapter = AskKernelAdapter(db_path=db_path, trace_path=trace_path)
    task_ask = adapter.begin('test question?', ['context'], '', 'session-1')
    tid_ask = task_ask['task_id']
    adapter.fail(task_ask, reason='test_failure_reason', failure_classification='FATAL')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t_ask_row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (tid_ask,)).fetchone()
    print('Ask task final state in DB:', t_ask_row['state'], 'active_lease:', t_ask_row['active_lease_id'])
    assert t_ask_row['state'] == 'FAILED'
    assert t_ask_row['active_lease_id'] is None
    e_ask = conn.execute("SELECT * FROM events WHERE task_id=? AND type='TASK_FAILED'", (tid_ask,)).fetchone()
    assert e_ask is not None
    payload_ask = json.loads(e_ask['payload_json'])
    print('Ask event indictment_ref:', payload_ask['indictment_ref'])
    assert 'ask://' in payload_ask['indictment_ref']
    conn.close()
    adapter.kernel.close()
    if os.path.exists(trace_path):
        os.remove(trace_path)

    print('ALL DOWNSTREAM INTEGRATION CHECKS PASSED EMPIRICALLY!')
finally:
    kernel.close()
    if os.path.exists(db_path):
        os.remove(db_path)
