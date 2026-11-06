import json
import sys
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
