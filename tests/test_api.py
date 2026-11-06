import json
import sys
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from fastapi.testclient import TestClient
import api
from models import Invoice

ORIGIN = {'origin': 'http://127.0.0.1:3000'}


def test_key_isolation_and_no_key_in_responses(monkeypatch):
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    with TestClient(api.app) as a, TestClient(api.app) as b:
        a.get('/api/config'); b.get('/api/config')
        secret = 'synthetic-test-key-never-sent-to-gemini'
        response = a.post('/api/config', json={'key': secret, 'model': 'gemini-3.8-flash'}, headers=ORIGIN)
        assert response.status_code == 200
        assert secret not in response.text
        assert a.get('/api/config').json()['key_source'] == 'Your session'
        assert b.get('/api/config').json()['key_source'] == 'Server configuration'
        assert secret not in a.get('/api/config').text
        assert a.post('/api/config', json={'reset': True}, headers=ORIGIN).status_code == 200
        assert a.get('/api/config').json()['key_source'] == 'Server configuration'


def test_origin_and_persistence_protection(monkeypatch):
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    monkeypatch.delenv('LOCAL_SETUP', raising=False)
    with TestClient(api.app) as client:
        assert client.post('/api/config', json={}).status_code == 403
        assert client.post('/api/config', json={'key': 'synthetic-placeholder-secret-key', 'persist': True}, headers=ORIGIN).status_code == 403


def test_streamed_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'test.sqlite3'))
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-only')
    original = api.process
    root = Path(__file__).parents[1]
    fixture = Invoice.model_validate_json((root / 'samples/01_success.expected.json').read_text())
    monkeypatch.setattr(api, 'process', lambda *a, **kw: original(*a, **kw, extractor=lambda *args: (fixture, {})))
    with TestClient(api.app) as client:
        client.get('/api/config')
        pdf = (root / 'samples/01_success.pdf').read_bytes()
        r = client.post('/api/process', files={'file': ('invoice.pdf', pdf, 'application/pdf')}, headers=ORIGIN)
        assert r.status_code == 200
        events = [json.loads(line) for line in r.text.splitlines()]
        assert any(e['type'] == 'stage' for e in events)
        assert events[-1]['run']['decision'] == 'approved'
        duplicate = client.post('/api/process', files={'file': ('renamed.pdf', pdf, 'application/pdf')}, headers=ORIGIN)
        assert json.loads(duplicate.text.splitlines()[-1])['run']['decision'] == 'rejected'
        assert len(client.get('/api/runs').json()) == 2


def test_password_gate(monkeypatch):
    monkeypatch.setenv('APP_PASSWORD', 'demo-test-password')
    with TestClient(api.app) as client:
        assert client.get('/api/runs').status_code == 401
        assert client.post('/api/config', json={}, headers=ORIGIN).status_code == 401
        assert client.post('/api/login', json={'password': 'wrong'}, headers=ORIGIN).status_code == 401
        assert client.post('/api/login', json={'password': 'demo-test-password'}, headers=ORIGIN).status_code == 200
        assert client.get('/api/config').json()['login_required'] is False


def test_readiness_checks_real_local_storage(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'ready.sqlite3'))
    with TestClient(api.app) as client:
        assert client.get('/api/ready').json() == {'status': 'ready', 'database': 'ok'}
    assert (tmp_path / 'ready.sqlite3').exists()


@pytest.mark.parametrize('route', ['/api/ready', '/api/runs', '/api/orders'])
def test_database_authentication_failure_is_safe_503(route, monkeypatch):
    import psycopg
    secret = 'synthetic-database-password-must-stay-private'
    monkeypatch.delenv('APP_PASSWORD', raising=False)
    monkeypatch.setenv('DATABASE_URL', f'postgresql://test:{secret}@example.invalid/test')
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('password authentication failed: ' + secret)
    monkeypatch.setattr(psycopg, 'connect', fail)
    with TestClient(api.app) as client:
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()['code'] == 'database_authentication_failed'
        assert response.headers['retry-after'] == '30'
        assert secret not in response.text
        assert 'postgresql://' not in response.text
        # A running process alone does not establish database readiness.
        assert client.get('/api/health').status_code == 200


def test_database_network_failure_is_not_reported_as_authentication(monkeypatch):
    import psycopg
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:synthetic-secret@example.invalid/test')
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('connection timed out')
    monkeypatch.setattr(psycopg, 'connect', fail)
    with TestClient(api.app) as client:
        response = client.get('/api/ready')
        assert response.status_code == 503
        assert response.json()['code'] == 'database_unavailable'
