"""Small HTTP boundary around the existing Python pipeline. No LLM-written SQL."""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from decimal import Decimal
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv, set_key
from service import history, process, connect, StorageUnavailable
from rules import records, normalize, RULE_VERSION

ROOT = Path(__file__).parent
load_dotenv(ROOT / '.env')
app = FastAPI(docs_url=None, redoc_url=None)
sessions = {}  # single-worker demo: keys stay in backend memory, never SQLite
COOKIE = 'invoice_desk_session'


def database():
    return os.getenv('DATABASE_PATH', str(ROOT / 'data/history.sqlite3'))


def session(request: Request, response: Response):
    sid = request.cookies.get(COOKIE)
    if not sid or sid not in sessions:
        sid = secrets.token_urlsafe(32)
        sessions[sid] = {}
        response.set_cookie(COOKIE, sid, httponly=True, samesite='strict', secure=os.getenv('COOKIE_SECURE') == '1', max_age=28800)
    return sessions[sid]


@app.middleware('http')
async def protect(request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        allowed = os.getenv('APP_ORIGIN') or os.getenv('RENDER_EXTERNAL_URL') or 'http://127.0.0.1:3000'
        if request.headers.get('origin') not in {allowed, 'http://localhost:3000'}:
            return Response('Request origin not allowed', status_code=403)
    public = request.url.path in ('/api/login', '/api/health', '/api/ready') or (request.url.path == '/api/config' and request.method == 'GET')
    if request.url.path.startswith('/api/') and os.getenv('APP_PASSWORD') and not public:
        state = sessions.get(request.cookies.get(COOKIE), {})
        if not state.get('authenticated'):
            return Response('Workspace sign-in required', status_code=401)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.exception_handler(StorageUnavailable)
async def storage_unavailable(request: Request, error: StorageUnavailable):
    return JSONResponse(status_code=503, content={
        'detail': 'Database unavailable. History and PO balances cannot be verified. No approval can be confirmed until storage is restored.',
        'code': error.code,
    }, headers={'Retry-After': '30'})


@app.get('/api/ready')
def ready():
    """Unlike liveness, readiness verifies the configured database and schema."""
    with connect(database()) as db:
        db.execute('SELECT 1')
    return {'status': 'ready', 'database': 'ok'}


class Login(BaseModel):
    password: str


@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    if not hmac.compare_digest(body.password, os.getenv('APP_PASSWORD', '')):
        raise HTTPException(401, 'Incorrect workspace password')
    session(request, response)['authenticated'] = True
    return {'ok': True}


@app.get('/api/config')
def config(request: Request, response: Response):
    state = session(request, response)
    return {'configured': bool(state.get('key') or os.getenv('GEMINI_API_KEY')), 'key_source': 'Your session' if state.get('key') else 'Server configuration', 'model': state.get('model', os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')), 'local_save': os.getenv('LOCAL_SETUP') == '1', 'login_required': bool(os.getenv('APP_PASSWORD')) and not state.get('authenticated'), 'policy': RULE_VERSION}


class Connection(BaseModel):
    key: str = ''
    model: str = 'gemini-3.5-flash-lite'
    persist: bool = False
    reset: bool = False


@app.post('/api/config')
def save_connection(body: Connection, request: Request, response: Response):
    state = session(request, response)
    if not body.model or len(body.model) > 100 or any(c.isspace() for c in body.model):
        raise HTTPException(400, 'Enter a model ID without spaces')
    if body.key and (len(body.key.strip()) < 20 or any(c.isspace() for c in body.key.strip())):
        raise HTTPException(400, 'The API key appears incomplete or contains whitespace')
    if body.persist and os.getenv('LOCAL_SETUP') != '1':
        raise HTTPException(403, 'Saving keys to disk is disabled on this server')
    if body.reset:
        state.pop('key', None)
    elif body.key.strip():
        state['key'] = body.key.strip()
        if body.persist:
            if os.getenv('LOCAL_SETUP') != '1':
                raise HTTPException(403, 'Saving keys to disk is disabled on this server')
            set_key(str(ROOT / '.env'), 'GEMINI_API_KEY', state['key'])
            os.environ['GEMINI_API_KEY'] = state['key']
    state['model'] = body.model
    return {'ok': True}


@app.get('/api/runs')
def runs():
    return history(database())


@app.get('/api/orders')
def orders():
    prior = history(database())
    result = []
    for row in records('purchase_orders.csv'):
        consumed = sum((Decimal(r['invoice']['total']) for r in prior if r['decision'] == 'approved' and normalize(r['invoice']['po_reference']) == normalize(row['po_reference'])), Decimal('0'))
        result.append(dict(row, reserved=str(consumed), remaining=str(Decimal(row['limit'])-Decimal(row['previously_invoiced'])-consumed), lines=[r for r in records('purchase_order_lines.csv') if r['po_reference'] == row['po_reference']]))
    return {'orders': result, 'vendors': records('vendors.csv')}


@app.post('/api/process')
async def process_invoice(request: Request, response: Response, file: UploadFile = File(...)):
    state = session(request, response)
    key = state.get('key') or os.getenv('GEMINI_API_KEY')
    if not key:
        raise HTTPException(400, 'Add your Gemini key in Connection first')
    data = await file.read(10 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, 'PDF must be no larger than 10 MB')
    model = state.get('model', os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite'))
    queue = Queue()
    def worker():
        try:
            result = process(data, file.filename or 'invoice.pdf', database(), key, model, stage=lambda s: queue.put({'type': 'stage', 'message': s}))
            queue.put({'type': 'result', 'run': result})
        except Exception:
            queue.put({'type': 'error', 'message': 'Storage unavailable. No decision confirmed; check server disk and database path.'})
        finally:
            queue.put(None)
    Thread(target=worker, daemon=True).start()
    async def events():
        while True:
            try:
                event = await asyncio.to_thread(queue.get, True, 10)
            except Empty:
                yield json.dumps({'type': 'heartbeat'}) + '\n'
                continue
            if event is None:
                break
            yield json.dumps(event) + '\n'
    headers = {'X-Accel-Buffering': 'no'}
    if response.headers.get('set-cookie'):
        headers['set-cookie'] = response.headers['set-cookie']
    return StreamingResponse(events(), media_type='application/x-ndjson', headers=headers)


# The free-host Docker build exports the Next.js UI and serves it from Python.
# Local development still uses Next.js on port 3000 with API forwarding.
if (ROOT / 'web/out').is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=ROOT / 'web/out', html=True), name='nextjs-ui')
