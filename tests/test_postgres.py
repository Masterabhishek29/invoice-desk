"""Regression for Neon pooled connections rejecting startup options."""
from types import SimpleNamespace
import psycopg
from psycopg.pq import TransactionStatus
from service import PostgresHistory


def test_pooled_timeout_is_transaction_local(monkeypatch):
    calls = []
    class Connection:
        info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        def execute(self, sql, params=()):
            calls.append(sql)
            self.info.transaction_status = TransactionStatus.INTRANS
            return []
        def commit(self):
            self.info.transaction_status = TransactionStatus.IDLE
        def rollback(self):
            self.info.transaction_status = TransactionStatus.IDLE
        def close(self):
            pass
    def pooled_connect(url, **kwargs):
        # Mirrors the actual PgBouncer failure observed in Render logs.
        if 'options' in kwargs:
            raise psycopg.OperationalError('unsupported startup parameter in options: statement_timeout')
        return Connection()
    monkeypatch.setattr(psycopg, 'connect', pooled_connect)
    db = PostgresHistory('postgresql://synthetic.invalid/test')
    db.execute('SELECT 1')
    db.db.commit()
    db.execute('BEGIN IMMEDIATE')
    db.execute('SELECT payload FROM runs')
    # Initialization, a new read transaction, and a new reservation transaction
    # each get their own timeout; subsequent SQL in that transaction reuses it.
    assert calls.count("SET LOCAL statement_timeout = '30s'") == 3
    assert 'SELECT pg_advisory_xact_lock(73451022)' in calls
