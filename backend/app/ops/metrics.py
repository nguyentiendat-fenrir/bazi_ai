"""Operations metrics and local alerts for admins (docs/12 · Observability; T051).

Database aggregates come from ``bazi_operations_metrics`` (M016: counts only, across
owners). This process adds what only it knows: the connection pool, recent retrieval
latency and free disk on the object store. Alerts are derived on read, so changing a
threshold needs no migration.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import math
import shutil
import threading

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..llm import budget

DISK_LOW_FREE = 0.10              # alert below 10 % free on the object store
BACKUP_OVERDUE = timedelta(hours=26)   # daily backups plus slack (RPO ≤ 24 h)
QUEUE_STUCK_SECONDS = 30 * 60

_latencies: deque[float] = deque(maxlen=500)
_lock = threading.Lock()


def record_search(milliseconds: float) -> None:
    """Called by /search and the reasoning tool; this process only, newest 500."""
    with _lock:
        _latencies.append(milliseconds)


def _percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(share * len(ordered)) - 1)], 1)


def process_metrics(engine: Engine, storage_root: str | None) -> dict:
    with _lock:
        window = list(_latencies)
    pool = engine.pool
    db_pool = {'status': pool.status()}
    for name in ('size', 'checkedout', 'overflow'):
        method = getattr(pool, name, None)
        if callable(method):
            db_pool[name] = method()
    disk = None
    if storage_root:
        try:
            usage = shutil.disk_usage(storage_root)
            disk = {'total_bytes': usage.total, 'free_bytes': usage.free,
                    'free_share': round(usage.free / usage.total, 4)}
        except OSError:
            disk = None
    return {'retrieval_ms': {'samples': len(window), 'p50': _percentile(window, 0.5),
                             'p95': _percentile(window, 0.95)},
            'db_pool': db_pool, 'disk': disk}


def alerts(database: dict, process: dict, budgets: list[dict], now: datetime) -> list[dict]:
    found = []

    def add(code: str, severity: str, message: str) -> None:
        found.append({'code': code, 'severity': severity, 'message': message})

    disk = process.get('disk')
    if disk and disk['free_share'] < DISK_LOW_FREE:
        add('DISK_LOW', 'high', f"Ổ lưu tệp còn {disk['free_share']:.0%} trống.")
    last = database.get('last_backup_at')
    if last is None:
        add('BACKUP_MISSING', 'high', 'Chưa có bản backup nào được ghi nhận.')
    elif now - datetime.fromisoformat(last) > BACKUP_OVERDUE:
        add('BACKUP_OVERDUE', 'high', f'Backup gần nhất lúc {last}, quá 26 giờ.')
    if database['ingestion']['repeated_failures']:
        add('JOB_REPEATED_FAILURE', 'medium', f"{database['ingestion']['repeated_failures']} phiên"
            ' bản sách lỗi ≥ 3 lần trong 24 giờ.')
    if database['stages']['expired_leases']:
        add('LEASE_EXPIRED', 'medium', f"{database['stages']['expired_leases']} bước xử lý hết"
            ' hạn giữ chỗ mà vẫn ở trạng thái chạy (worker có thể đã chết).')
    for queue in ('ingestion', 'chat'):
        age = database[queue]['oldest_queued_seconds']
        if age is not None and age > QUEUE_STUCK_SECONDS:
            add('QUEUE_STUCK', 'medium', f'Hàng đợi {queue} có việc chờ {age // 60} phút.')
    for row in budgets:
        if row['daily_budget'] > 0 and row['spent_today'] >= row['daily_budget']:
            add('BUDGET_EXCEEDED', 'high', f"Profile {row['profile_id'][:8]} đã dùng hết ngân"
                ' sách ngày.')
    if not database['corpus_empty'] and not database['active_embedding']:
        add('NO_ACTIVE_EMBEDDING', 'high', 'Kho đang dùng không có bộ embedding sẵn sàng.')
    return found


def collect(conn: Connection, engine: Engine, storage_root: str | None,
            admin_id) -> dict:
    now = datetime.now(timezone.utc)
    database = conn.execute(text('SELECT bazi_operations_metrics()')).scalar_one()
    database['feedback_7d'] = conn.execute(text(
        "SELECT bazi_feedback_totals(now() - interval '7 days')")).scalar_one()
    process = process_metrics(engine, storage_root)
    today = datetime.combine(now.date(), datetime.min.time(), timezone.utc)
    budgets = budget.summary(conn, admin_id, today, today + timedelta(days=1))['budgets']
    return {'collected_at': now, 'database': database, 'process': process,
            'alerts': alerts(database, process, budgets, now)}
