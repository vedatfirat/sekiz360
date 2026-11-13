"""Operasyon360 Pano & Evrak: single-organization self-hosted board/document portal.
Run: python app.py   |   dependencies: fastapi uvicorn python-multipart itsdangerous
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('APP_DATA_DIR', str(BASE / 'data'))).resolve()
UPLOADS = DATA / 'uploads'
DB_PATH = DATA / 'database.sqlite3'
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
UPLOADS.mkdir(mode=0o700, parents=True, exist_ok=True)
SECRET_PATH = DATA / '.appsecret'
if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    try: SECRET_PATH.chmod(0o600)
    except OSError: pass
SECRET = SECRET_PATH.read_text(encoding='utf-8')
signer = URLSafeTimedSerializer(SECRET, salt='operasyon360-session-v1')
SESSION_COOKIE = 'op360_session'
SECURE_COOKIE = os.getenv('APP_SECURE_COOKIE', '').lower() in ('1', 'true', 'yes')
MAX_UPLOAD = 20 * 1024 * 1024
ALLOWED = {'.pdf': 'application/pdf', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
           '.txt':'text/plain', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
           '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
STATUS = ['Yapılacak', 'Devam Ediyor', 'Tamamlandı']
LOGIN_ATTEMPTS: dict[str, list[float]] = {}

@contextmanager
def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 10000')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally: conn.close()

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def phash(password: str) -> str:
    salt = secrets.token_bytes(16)
    out = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + '$' + out.hex()

def pcheck(password: str, saved: str) -> bool:
    try:
        ss, hh = saved.split('$', 1)
        hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(ss), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(hashed.hex(), hh)
    except Exception: return False

def dictrow(r): return dict(r) if r is not None else None

def activity(conn, uid, action, obj, obj_id, detail=''):
    conn.execute('INSERT INTO activity (user_id,action,object_type,object_id,details,at) VALUES (?,?,?,?,?,?)',
                 (uid,action,obj,str(obj_id),detail[:800],now()))

def seed():
    with open_db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','viewer')),
          active INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS boards (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT NOT NULL DEFAULT '',
          project_ref TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#ED6B43',
          icon TEXT NOT NULL DEFAULT 'layers', visible_to_all INTEGER NOT NULL DEFAULT 1,
          parent_card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
          archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS board_members (
          board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          PRIMARY KEY(board_id,user_id));
        CREATE TABLE IF NOT EXISTS cards (
          id INTEGER PRIMARY KEY, board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
          title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Yapılacak',
          tag TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
          owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          x REAL NOT NULL DEFAULT 60, y REAL NOT NULL DEFAULT 70,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY, board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
          card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
          title TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', current_version INTEGER NOT NULL DEFAULT 1,
          archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS document_versions (
          id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          version INTEGER NOT NULL, original_filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
          mime TEXT NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(document_id,version));
        CREATE TABLE IF NOT EXISTS activity (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
          details TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS cards_by_board ON cards(board_id);
        CREATE INDEX IF NOT EXISTS docs_by_board ON documents(board_id);
        ''')
        if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
            password = os.getenv('INITIAL_ADMIN_PASSWORD') or secrets.token_urlsafe(22)
            if len(password) < 16:
                raise RuntimeError('INITIAL_ADMIN_PASSWORD must have at least 16 characters')
            c.execute('INSERT INTO users (name,email,password_hash,role,active,created_at) VALUES (?,?,?,?,1,?)',
                      ('Yönetici','admin@local',phash(password),'admin',now()))
            first = DATA / 'ILK_GIRIS_BILGILERI.txt'
            first.write_text('Operasyon360 - Ilk Giris\nAdres: http://127.0.0.1:8765\nE-posta: admin@local\nSifre: '+password+'\n\nIlk giristen sonra yonetici sifresini degistirin.\nBu dosyayi paylasmayin.\n', encoding='utf-8')
            try: first.chmod(0o600)
            except OSError: pass
            b1 = c.execute('INSERT INTO boards(title,subtitle,project_ref,color,icon,visible_to_all,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                  ('Genel Duyurular','Tüm personele açık şirket panosu','GENEL','#EC7550','megaphone',1,now(),now())).lastrowid
            b2 = c.execute('INSERT INTO boards(title,subtitle,project_ref,color,icon,visible_to_all,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                  ('Etkinlik Operasyonları','Proje hazırlığı, saha planı ve talimatlar','PRJ-2026-001','#536DEA','calendar',1,now(),now())).lastrowid
            b3 = c.execute('INSERT INTO boards(title,subtitle,project_ref,color,icon,visible_to_all,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                  ('Yönetim Evrakları','Yalnızca yetki verilen personel için','ÖZEL','#7A63D4','lock',0,now(),now())).lastrowid
            demo_cards = [(b1,'Personel duyuruları','Haftalık program ve güncel duyuruları buradan takip edin.','Devam Ediyor','Duyuru',65,75),
                          (b1,'Çalışma kuralları','İlgili evraklar pano üzerinden paylaşılacak.','Yapılacak','Evrak',405,160),
                          (b2,'Kurulum planı','Saha ekipleri, saatler ve malzeme çıkış notları bu kartta.','Yapılacak','Operasyon',80,80),
                          (b2,'Saha güvenliği','Etkinliğe gitmeden önce kontrol edilmesi gereken hususlar.','Yapılacak','Kontrol',445,100),
                          (b3,'Yönetim notu','Bu pano çalışanlara varsayılan olarak kapalıdır.','Yapılacak','Özel',85,85)]
            for bid,title,body,status,tag,x,y in demo_cards:
                c.execute('INSERT INTO cards(board_id,title,body,status,tag,x,y,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                           (bid,title,body,status,tag,x,y,now(),now()))
            # Public example document. No confidential or live company data is seeded.
            demo_name = uuid.uuid4().hex + '.txt'
            demo_file = UPLOADS / demo_name
            demo_text = ('PERSONEL BILGILENDIRME ORNEGI\n\nBu dosya ornek evraktir.\n'
                         'Gercek is talimatlari ve sozlesmeler yonetici tarafindan yuklenmelidir.\n')
            demo_file.write_text(demo_text, encoding='utf-8')
            docid = c.execute('INSERT INTO documents(board_id,title,notes,created_at,updated_at) VALUES (?,?,?,?,?)',
                              (b1,'Örnek Personel Bilgilendirmesi','Örnek dosya - gerçek evrakla değiştirilebilir',now(),now())).lastrowid
            c.execute('INSERT INTO document_versions(document_id,version,original_filename,stored_filename,mime,size,created_at) VALUES (?,?,?,?,?,?,?)',
                      (docid,1,'ornek-personel-bilgilendirme.txt',demo_name,'text/plain',len(demo_text.encode('utf-8')),now()))

seed()
app = FastAPI(title='Operasyon360 Pano & Evrak', docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')

@app.middleware('http')
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api') else 'private, max-age=0'
    return response

@app.exception_handler(HTTPException)
async def api_error(_req, exc):
    return JSONResponse({'error': str(exc.detail)}, status_code=exc.status_code)

@app.get('/')
def index(): return FileResponse(BASE / 'static' / 'index.html')

@app.get('/health')
def health(): return {'ok':True, 'service':'Operasyon360 Pano & Evrak', 'version':'1.0'}

def actor(req: Request) -> dict:
    token = req.cookies.get(SESSION_COOKIE)
    if not token: raise HTTPException(401,'Giriş yapmanız gerekiyor')
    try: payload = signer.loads(token, max_age=86400*7)
    except (BadSignature, SignatureExpired): raise HTTPException(401,'Oturum süresi doldu')
    with open_db() as c:
        r = c.execute('SELECT id,name,email,role,active,session_version FROM users WHERE id=?', (payload.get('id'),)).fetchone()
    if not r or not r['active'] or r['session_version'] != payload.get('sv'): raise HTTPException(401,'Oturum geçersiz')
    return dict(r)

def csrf_expected(u):
    msg = f"csrf:{u['id']}:{u['session_version']}".encode()
    return hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()

def authorize(req: Request, admin=False, write=False):
    u = actor(req)
    if admin and u['role'] != 'admin': raise HTTPException(403,'Bu işlem yalnızca yöneticiye açıktır')
    if write and not hmac.compare_digest(req.headers.get('X-CSRF-Token',''), csrf_expected(u)):
        raise HTTPException(403,'Güvenlik doğrulaması başarısız')
    return u

def can_view(c, u, bid):
    if u['role'] == 'admin': return True
    seen = set()
    while bid is not None and bid not in seen:
        seen.add(bid)
        board = c.execute('SELECT id,visible_to_all,archived,parent_card_id FROM boards WHERE id=?',(bid,)).fetchone()
        if not board or board['archived']: return False
        member = c.execute('SELECT 1 FROM board_members WHERE board_id=? AND user_id=?',(bid,u['id'])).fetchone()
        if not board['visible_to_all'] and not member: return False
        if board['parent_card_id']:
            parent = c.execute('SELECT board_id FROM cards WHERE id=?',(board['parent_card_id'],)).fetchone()
            if not parent: return False
            bid = parent['board_id']
        else: bid = None
    return bid is None

def permitted(c, u, bid):
    if not can_view(c,u,bid): raise HTTPException(403,'Bu panoya erişim yetkiniz yok')

class Credentials(BaseModel):
    email: str
    password: str

@app.post('/api/login')
def login(v: Credentials, req: Request):
    ip = req.client.host if req.client else 'unknown'
    attempts = [t for t in LOGIN_ATTEMPTS.get(ip, []) if time.time()-t<300]
    if len(attempts)>=12: raise HTTPException(429,'Çok fazla deneme, 5 dakika sonra tekrar deneyin')
    with open_db() as c:
        r = c.execute('SELECT * FROM users WHERE email=?',(v.email.strip().lower(),)).fetchone()
        if not r or not r['active'] or not pcheck(v.password,r['password_hash']):
            attempts.append(time.time());LOGIN_ATTEMPTS[ip]=attempts
            raise HTTPException(401,'E-posta veya şifre hatalı')
        LOGIN_ATTEMPTS.pop(ip,None)
        activity(c,r['id'],'login','session',r['id'])
        token=signer.dumps({'id':r['id'],'sv':r['session_version']})
    res=JSONResponse({'ok':True})
    res.set_cookie(SESSION_COOKIE,token,httponly=True,secure=SECURE_COOKIE,samesite='lax',max_age=86400*7,path='/')
    return res

@app.post('/api/logout')
def logout(req: Request):
    u=authorize(req,write=True)
    with open_db() as c: activity(c,u['id'],'logout','session',u['id'])
    res=JSONResponse({'ok':True});res.delete_cookie(SESSION_COOKIE,path='/');return res

@app.get('/api/me')
def me(req: Request):
    u=actor(req)
    return {'user':{k:u[k] for k in ('id','name','email','role')},'csrf':csrf_expected(u)}

@app.get('/api/boards')
def boards(req: Request):
    u=actor(req)
    with open_db() as c:
        allb=[dict(x) for x in c.execute('SELECT * FROM boards WHERE archived=0 ORDER BY updated_at DESC,id DESC').fetchall()]
        visible=[b for b in allb if can_view(c,u,b['id'])]
        for b in visible:
            b['card_count']=c.execute('SELECT COUNT(*) FROM cards WHERE board_id=?',(b['id'],)).fetchone()[0]
            b['document_count']=c.execute('SELECT COUNT(*) FROM documents WHERE board_id=? AND archived=0',(b['id'],)).fetchone()[0]
        return visible

@app.get('/api/boards/{board_id}')
def board_detail(board_id:int,req:Request):
    u=actor(req)
    with open_db() as c:
        b=c.execute('SELECT * FROM boards WHERE id=? AND archived=0',(board_id,)).fetchone()
        if not b: raise HTTPException(404,'Pano bulunamadı')
        permitted(c,u,board_id)
        cards=[dict(x) for x in c.execute('''SELECT cards.*,users.name AS owner_name,(SELECT id FROM boards WHERE parent_card_id=cards.id AND archived=0 LIMIT 1) AS child_board_id
               FROM cards LEFT JOIN users ON users.id=cards.owner_id WHERE cards.board_id=? ORDER BY cards.id''',(board_id,)).fetchall()]
        docs=[dict(x) for x in c.execute('''SELECT documents.*,document_versions.original_filename,document_versions.mime,document_versions.size
            FROM documents JOIN document_versions ON document_versions.document_id=documents.id AND document_versions.version=documents.current_version
            WHERE documents.board_id=? AND documents.archived=0 ORDER BY documents.updated_at DESC''',(board_id,)).fetchall()]
        members=[x['user_id'] for x in c.execute('SELECT user_id FROM board_members WHERE board_id=?',(board_id,)).fetchall()] if u['role']=='admin' else []
        return {'board':dict(b),'cards':cards,'documents':docs,'members':members}

class BoardModel(BaseModel):
    title: str = Field(min_length=2,max_length=140)
    subtitle: str = Field(default='',max_length=500)
    project_ref: str = Field(default='',max_length=80)
    color: str = Field(default='#ED6B43',pattern=r'^#[0-9A-Fa-f]{6}$')
    visible_to_all: bool = True
    member_ids: list[int] = []

@app.post('/api/boards')
def add_board(v:BoardModel,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        b=c.execute('INSERT INTO boards(title,subtitle,project_ref,color,icon,visible_to_all,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (v.title.strip(),v.subtitle.strip(),v.project_ref.strip(),v.color,'layers',int(v.visible_to_all),now(),now())).lastrowid
        save_members(c,b,v.member_ids)
        activity(c,u['id'],'create','board',b,v.title)
    return {'id':b}

def save_members(c,bid,ids):
    c.execute('DELETE FROM board_members WHERE board_id=?',(bid,))
    for uid in set(ids):
        if c.execute('SELECT 1 FROM users WHERE id=? AND active=1 AND role="viewer"',(uid,)).fetchone():
            c.execute('INSERT INTO board_members(board_id,user_id) VALUES (?,?)',(bid,uid))

@app.patch('/api/boards/{bid}')
def edit_board(bid:int,v:BoardModel,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        if not c.execute('SELECT id FROM boards WHERE id=? AND archived=0',(bid,)).fetchone(): raise HTTPException(404,'Pano yok')
        c.execute('UPDATE boards SET title=?,subtitle=?,project_ref=?,color=?,visible_to_all=?,updated_at=? WHERE id=?',
                  (v.title.strip(),v.subtitle.strip(),v.project_ref.strip(),v.color,int(v.visible_to_all),now(),bid))
        save_members(c,bid,v.member_ids)
        activity(c,u['id'],'update','board',bid,v.title)
    return {'ok':True}

@app.delete('/api/boards/{bid}')
def archive_board(bid:int,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        if not c.execute('SELECT id FROM boards WHERE id=?',(bid,)).fetchone(): raise HTTPException(404,'Pano yok')
        c.execute('UPDATE boards SET archived=1,updated_at=? WHERE id=?',(now(),bid))
        activity(c,u['id'],'archive','board',bid)
    return {'ok':True}

class CardModel(BaseModel):
    title: str = Field(min_length=1,max_length=160)
    body: str = Field(default='',max_length=10000)
    status: str = 'Yapılacak'
    tag: str = Field(default='',max_length=50)
    due_date: str = Field(default='',max_length=20)
    owner_id: int | None = None
    x: float = Field(default=60,ge=0,le=2500)
    y: float = Field(default=70,ge=0,le=2500)

def valid_card(v):
    if v.status not in STATUS: raise HTTPException(422,'Geçersiz kart durumu')

@app.post('/api/boards/{bid}/cards')
def add_card(bid:int,v:CardModel,req:Request):
    u=authorize(req,admin=True,write=True);valid_card(v)
    with open_db() as c:
        if not c.execute('SELECT id FROM boards WHERE id=? AND archived=0',(bid,)).fetchone():raise HTTPException(404,'Pano yok')
        if v.owner_id and not c.execute('SELECT id FROM users WHERE id=? AND active=1',(v.owner_id,)).fetchone():raise HTTPException(422,'Çalışan yok')
        cid=c.execute('INSERT INTO cards(board_id,title,body,status,tag,due_date,owner_id,x,y,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
             (bid,v.title.strip(),v.body,v.status,v.tag,v.due_date,v.owner_id,v.x,v.y,now(),now())).lastrowid
        c.execute('UPDATE boards SET updated_at=? WHERE id=?',(now(),bid))
        activity(c,u['id'],'create','card',cid,v.title)
    return {'id':cid}

@app.patch('/api/cards/{cid}')
def edit_card(cid:int,v:CardModel,req:Request):
    u=authorize(req,admin=True,write=True);valid_card(v)
    with open_db() as c:
        old=c.execute('SELECT board_id FROM cards WHERE id=?',(cid,)).fetchone()
        if not old: raise HTTPException(404,'Kart yok')
        c.execute('UPDATE cards SET title=?,body=?,status=?,tag=?,due_date=?,owner_id=?,x=?,y=?,updated_at=? WHERE id=?',
                  (v.title.strip(),v.body,v.status,v.tag,v.due_date,v.owner_id,v.x,v.y,now(),cid))
        c.execute('UPDATE boards SET updated_at=? WHERE id=?',(now(),old['board_id']))
        activity(c,u['id'],'update','card',cid,v.title)
    return {'ok':True}

@app.patch('/api/cards/{cid}/position')
async def move_card(cid:int,req:Request):
    u=authorize(req,admin=True,write=True)
    v=await req.json()
    try: x,y=float(v['x']),float(v['y'])
    except Exception:raise HTTPException(422,'Koordinat hatalı')
    if not (0<=x<=2500 and 0<=y<=2500):raise HTTPException(422,'Koordinat sınırı dışında')
    with open_db() as c:
        if not c.execute('SELECT 1 FROM cards WHERE id=?',(cid,)).fetchone():raise HTTPException(404,'Kart yok')
        c.execute('UPDATE cards SET x=?,y=?,updated_at=? WHERE id=?',(x,y,now(),cid))
    return {'ok':True}

@app.delete('/api/cards/{cid}')
def delete_card(cid:int,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        if c.execute('SELECT 1 FROM boards WHERE parent_card_id=? AND archived=0',(cid,)).fetchone():
            raise HTTPException(409,'Bu kartın alt panosu var. Önce alt panoyu arşivleyin')
        c.execute('DELETE FROM cards WHERE id=?',(cid,))
        activity(c,u['id'],'delete','card',cid)
    return {'ok':True}

@app.post('/api/cards/{cid}/subboard')
def make_subboard(cid:int,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        cr=c.execute('SELECT * FROM cards WHERE id=?',(cid,)).fetchone()
        if not cr:raise HTTPException(404,'Kart yok')
        old=c.execute('SELECT id FROM boards WHERE parent_card_id=? AND archived=0',(cid,)).fetchone()
        if old:return {'id':old['id']}
        parent=c.execute('SELECT * FROM boards WHERE id=?',(cr['board_id'],)).fetchone()
        bid=c.execute('INSERT INTO boards(title,subtitle,project_ref,color,icon,visible_to_all,parent_card_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
             (cr['title'],'Bu kartın alt panosu',parent['project_ref'],parent['color'],'layers',1,cid,now(),now())).lastrowid
        activity(c,u['id'],'create','subboard',bid,cr['title'])
    return {'id':bid}

async def save_upload(c, file: UploadFile):
    filename=Path((file.filename or '').replace('\\','/')).name
    ext=Path(filename).suffix.lower()
    if ext not in ALLOWED: raise HTTPException(415,'Desteklenen dosyalar: PDF, PNG, JPG, TXT, DOCX, XLSX')
    data=await file.read(MAX_UPLOAD+1)
    if len(data)>MAX_UPLOAD:raise HTTPException(413,'Dosya en fazla 20 MB olabilir')
    if not data:raise HTTPException(422,'Boş dosya yüklenemez')
    if ext=='.pdf' and not data.startswith(b'%PDF-'):raise HTTPException(415,'Geçersiz PDF')
    if ext in ('.jpg','.jpeg') and not data.startswith(b'\xff\xd8\xff'):raise HTTPException(415,'Geçersiz JPG')
    if ext=='.png' and not data.startswith(b'\x89PNG\r\n\x1a\n'):raise HTTPException(415,'Geçersiz PNG')
    if ext in ('.docx','.xlsx') and not data.startswith(b'PK'):raise HTTPException(415,'Geçersiz Office dosyası')
    if ext=='.txt':
        try:data.decode('utf-8')
        except UnicodeDecodeError:raise HTTPException(415,'Metin UTF-8 olmalıdır')
    stored=uuid.uuid4().hex + ext
    path=UPLOADS / stored
    with path.open('xb') as f:f.write(data)
    try:path.chmod(0o600)
    except OSError:pass
    return (filename,stored,ALLOWED[ext],len(data))

@app.get('/api/documents')
def list_documents(req:Request):
    u=actor(req)
    with open_db() as c:
        rows=c.execute('''SELECT documents.*,boards.title AS board_title,document_versions.original_filename,document_versions.mime,document_versions.size
            FROM documents JOIN boards ON boards.id=documents.board_id
            JOIN document_versions ON document_versions.document_id=documents.id AND document_versions.version=documents.current_version
            WHERE documents.archived=0 AND boards.archived=0 ORDER BY documents.updated_at DESC''').fetchall()
        return [dict(x) for x in rows if can_view(c,u,x['board_id'])]

@app.post('/api/documents')
async def upload_document(req:Request, title:str=Form(...), notes:str=Form(''), board_id:int=Form(...), card_id:str=Form(''), file:UploadFile=File(...)):
    u=authorize(req,admin=True,write=True)
    if not title.strip() or len(title)>150: raise HTTPException(422,'Evrak adı 1-150 karakter olmalıdır')
    with open_db() as c:
        if not c.execute('SELECT id FROM boards WHERE id=? AND archived=0',(board_id,)).fetchone():raise HTTPException(404,'Pano bulunamadı')
        cid=int(card_id) if card_id.strip().isdigit() else None
        if cid and not c.execute('SELECT 1 FROM cards WHERE id=? AND board_id=?',(cid,board_id)).fetchone():raise HTTPException(422,'Kart bu panoya ait değil')
        original, stored, mime, size=await save_upload(c,file)
        try:
            did=c.execute('INSERT INTO documents(board_id,card_id,title,notes,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                 (board_id,cid,title.strip(),notes[:2000],now(),now())).lastrowid
            c.execute('INSERT INTO document_versions(document_id,version,original_filename,stored_filename,mime,size,created_at) VALUES (?,?,?,?,?,?,?)',
                 (did,1,original,stored,mime,size,now()))
            activity(c,u['id'],'upload','document',did,original)
        except Exception:
            (UPLOADS / stored).unlink(missing_ok=True)
            raise
    return {'id':did}

@app.get('/api/documents/{did}/versions')
def versions(did:int,req:Request):
    u=actor(req)
    with open_db() as c:
        doc=c.execute('SELECT * FROM documents WHERE id=? AND archived=0',(did,)).fetchone()
        if not doc:raise HTTPException(404,'Evrak yok')
        permitted(c,u,doc['board_id'])
        return [dict(x) for x in c.execute('SELECT version,original_filename,mime,size,created_at FROM document_versions WHERE document_id=? ORDER BY version DESC',(did,)).fetchall()]

@app.post('/api/documents/{did}/versions')
async def new_document_version(did:int,req:Request,file:UploadFile=File(...)):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        doc=c.execute('SELECT * FROM documents WHERE id=? AND archived=0',(did,)).fetchone()
        if not doc:raise HTTPException(404,'Evrak yok')
        original,stored,mime,size=await save_upload(c,file)
        newver=doc['current_version']+1
        try:
            c.execute('INSERT INTO document_versions(document_id,version,original_filename,stored_filename,mime,size,created_at) VALUES (?,?,?,?,?,?,?)',
                 (did,newver,original,stored,mime,size,now()))
            c.execute('UPDATE documents SET current_version=?,updated_at=? WHERE id=?',(newver,now(),did))
            activity(c,u['id'],'new_version','document',did,str(newver))
        except Exception:
            (UPLOADS/stored).unlink(missing_ok=True)
            raise
    return {'ok':True,'version':newver}

@app.get('/api/documents/{did}/file')
def download(did:int,req:Request,version:int=0):
    u=actor(req)
    with open_db() as c:
        d=c.execute('SELECT * FROM documents WHERE id=? AND archived=0',(did,)).fetchone()
        if not d:raise HTTPException(404,'Evrak yok')
        permitted(c,u,d['board_id'])
        v=version or d['current_version']
        item=c.execute('SELECT * FROM document_versions WHERE document_id=? AND version=?',(did,v)).fetchone()
        if not item:raise HTTPException(404,'Sürüm yok')
        path=UPLOADS / item['stored_filename']
        if not path.is_file():raise HTTPException(404,'Dosya bulunamadı')
        activity(c,u['id'],'view','document',did,'v'+str(v))
        mime=item['mime']; disposition='inline' if mime in ('application/pdf','image/png','image/jpeg','text/plain') else 'attachment'
        return FileResponse(path,media_type=mime,filename=item['original_filename'],content_disposition_type=disposition,
                            headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

@app.delete('/api/documents/{did}')
def archive_document(did:int,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        if not c.execute('SELECT 1 FROM documents WHERE id=?',(did,)).fetchone():raise HTTPException(404,'Evrak yok')
        c.execute('UPDATE documents SET archived=1,updated_at=? WHERE id=?',(now(),did))
        activity(c,u['id'],'archive','document',did)
    return {'ok':True}

@app.get('/api/users')
def list_users(req:Request):
    authorize(req,admin=True)
    with open_db() as c:
        return [dict(x) for x in c.execute('SELECT id,name,email,role,active,created_at FROM users ORDER BY id').fetchall()]

class NewUser(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    email: str = Field(min_length=5,max_length=150)
    password: str = Field(min_length=10,max_length=160)

@app.post('/api/users')
def add_user(v:NewUser,req:Request):
    u=authorize(req,admin=True,write=True)
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$',v.email):raise HTTPException(422,'Geçersiz e-posta')
    with open_db() as c:
        try:
            uid=c.execute('INSERT INTO users(name,email,password_hash,role,active,created_at) VALUES (?,?,?,"viewer",1,?)',
                          (v.name.strip(),v.email.strip().lower(),phash(v.password),now())).lastrowid
        except sqlite3.IntegrityError:raise HTTPException(409,'E-posta zaten kullanılıyor')
        activity(c,u['id'],'create','user',uid,v.email)
    return {'id':uid}

class UserEdit(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    active: bool = True

@app.patch('/api/users/{uid}')
def edit_user(uid:int,v:UserEdit,req:Request):
    u=authorize(req,admin=True,write=True)
    if uid==u['id'] and not v.active:raise HTTPException(409,'Kendi hesabınızı kapatamazsınız')
    with open_db() as c:
        target=c.execute('SELECT id,role FROM users WHERE id=?',(uid,)).fetchone()
        if not target:raise HTTPException(404,'Çalışan yok')
        if target['role']=='admin' and uid!=u['id']:raise HTTPException(403,'Diğer yönetici hesabı değiştirilemez')
        c.execute('UPDATE users SET name=?,active=?,session_version=session_version+1 WHERE id=?',(v.name.strip(),int(v.active),uid))
        activity(c,u['id'],'update','user',uid)
    return {'ok':True}

class PasswordEdit(BaseModel):
    password: str = Field(min_length=10,max_length=160)

@app.post('/api/users/{uid}/password')
def set_password(uid:int,v:PasswordEdit,req:Request):
    u=authorize(req,admin=True,write=True)
    with open_db() as c:
        target=c.execute('SELECT id,role FROM users WHERE id=?',(uid,)).fetchone()
        if not target:raise HTTPException(404,'Kullanıcı yok')
        if target['role']=='admin' and uid!=u['id']:raise HTTPException(403,'Diğer yönetici şifresi değiştirilemez')
        c.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',(phash(v.password),uid))
        activity(c,u['id'],'change_password','user',uid)
    return {'ok':True}

@app.get('/api/activity')
def list_activity(req:Request):
    authorize(req,admin=True)
    with open_db() as c:
        return [dict(x) for x in c.execute('''SELECT a.*,u.name AS actor_name FROM activity a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 180''').fetchall()]

if __name__ == '__main__':
    import uvicorn
    port = int(os.getenv('PORT','8765'))
    host = os.getenv('HOST','127.0.0.1')
    print('Operasyon360 Pano & Evrak: http://127.0.0.1:'+str(port), flush=True)
    print('Ilk giris bilgileri: '+str(DATA / 'ILK_GIRIS_BILGILERI.txt'), flush=True)
    uvicorn.run(app,host=host,port=port)
