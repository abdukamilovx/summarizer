"""
Pearl PM — Flask API Routes
Все REST эндпоинты для дашборда
"""
from flask import Blueprint, request, jsonify, Response, session
import json, asyncio, threading
import logging
import time
import hmac
import hashlib
import sqlite3

logger = logging.getLogger(__name__)
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)
import database as db

api = Blueprint('api', __name__)

_bot_app = None
_bot_loop = None

def set_bot(app):
    global _bot_app
    _bot_app = app

def set_loop(loop):
    global _bot_loop
    _bot_loop = loop

# SSE клиенты для real-time обновлений
_sse_clients = []

LOGIN_TOKEN_TTL_SECONDS = 300
_auth_db_ready = False

def _auth_conn():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_auth_table():
    global _auth_db_ready
    if _auth_db_ready:
        return
    conn = _auth_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS auth_login_tokens (
            token TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            user_json TEXT,
            created_ts REAL NOT NULL,
            completed_ts REAL
        )
    """)
    conn.commit()
    conn.close()
    _auth_db_ready = True

def _public_auth_paths(path: str) -> bool:
    if path == '/api/config':
        return True
    if path in ('/api/auth/me', '/api/auth/logout'):
        return True
    if path.startswith('/api/auth/telegram'):
        return True
    return False

def _purge_expired_logins():
    _ensure_auth_table()
    now = time.time()
    cutoff = now - LOGIN_TOKEN_TTL_SECONDS
    conn = _auth_conn()
    conn.execute("DELETE FROM auth_login_tokens WHERE created_ts < ?", (cutoff,))
    conn.commit()
    conn.close()

def _create_pending_token(token: str):
    _ensure_auth_table()
    conn = _auth_conn()
    conn.execute(
        "INSERT OR REPLACE INTO auth_login_tokens (token, status, user_json, created_ts, completed_ts) VALUES (?, 'pending', NULL, ?, NULL)",
        (token, time.time()),
    )
    conn.commit()
    conn.close()

def _complete_token(token: str, user: dict) -> bool:
    _ensure_auth_table()
    conn = _auth_conn()
    row = conn.execute(
        "SELECT token FROM auth_login_tokens WHERE token = ? AND status = 'pending'",
        (token,),
    ).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "UPDATE auth_login_tokens SET status='completed', user_json=?, completed_ts=? WHERE token=?",
        (json.dumps(user, ensure_ascii=False), time.time(), token),
    )
    conn.commit()
    conn.close()
    return True

def _consume_completed_token(token: str):
    _ensure_auth_table()
    conn = _auth_conn()
    row = conn.execute(
        "SELECT user_json FROM auth_login_tokens WHERE token=? AND status='completed'",
        (token,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("DELETE FROM auth_login_tokens WHERE token=?", (token,))
    conn.commit()
    conn.close()
    try:
        return json.loads(row["user_json"] or "{}")
    except Exception:
        return None

def _sanitize_tg_user(payload: dict) -> dict:
    try:
        user_id = int(payload.get('id', 0) or 0)
    except (TypeError, ValueError):
        user_id = 0
    try:
        auth_date = int(payload.get('auth_date', 0) or 0)
    except (TypeError, ValueError):
        auth_date = 0
    return {
        'id': user_id,
        'first_name': (payload.get('first_name') or '').strip(),
        'last_name': (payload.get('last_name') or '').strip(),
        'username': (payload.get('username') or '').strip(),
        'photo_url': (payload.get('photo_url') or '').strip(),
        'auth_date': auth_date,
    }

def _is_allowed_user(user: dict) -> bool:
    from config import DASHBOARD_ALLOWED_TG_IDS
    if not DASHBOARD_ALLOWED_TG_IDS:
        return True
    return user.get('id') in DASHBOARD_ALLOWED_TG_IDS

@api.before_request
def require_dashboard_auth():
    if _public_auth_paths(request.path):
        return None
    tg_user = session.get('tg_user')
    if not tg_user:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    return None

def sse_push(data: dict):
    """Отправляет событие всем SSE-клиентам"""
    msg = f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    dead = []
    for q in _sse_clients:
        try:
            q.put(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        try: _sse_clients.remove(q)
        except: pass


# ─── SSE stream ───────────────────────────────────────────────────────────────
@api.route('/api/stream')
def sse_stream():
    from queue import Queue
    q = Queue()
    _sse_clients.append(q)
    def gen():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                msg = q.get(timeout=30)
                yield msg
            except Exception:
                yield "data: {\"type\":\"ping\"}\n\n"
    return Response(gen(), mimetype='text/event-stream',
                    headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


# ─── Projects ─────────────────────────────────────────────────────────────────
@api.route('/api/projects', methods=['GET'])
def get_projects():
    return jsonify(db.get_all_projects())

@api.route('/api/projects', methods=['POST'])
def create_project():
    d = request.json or {}
    name = d.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'No project name'}), 400

    topic_id = d.get('topic_id')
    telegram_id = d.get('telegram_id')
    if topic_id in ('', None):
        topic_id = None
    else:
        try:
            topic_id = int(topic_id)
        except (TypeError, ValueError):
            topic_id = None

    if topic_id:
        pid = db.get_or_create_project(name, topic_id)
    else:
        pid = db.create_project(name, d.get('start_date'), d.get('end_date'))

    if _bot_app and _bot_loop and not topic_id:
        import bot
        future = asyncio.run_coroutine_threadsafe(
            bot.create_telegram_tab(name, telegram_id, None), _bot_loop
        )
        try:
            result = future.result(timeout=20)
            created_topic_id = result.get('topic_id') if isinstance(result, dict) else None
            if created_topic_id:
                db.update_project_topic(pid, int(created_topic_id))
        except Exception as e:
            logger.warning("Failed to auto-create Telegram topic for project=%s: %s", name, e)

    if d.get('start_date') or d.get('end_date'):
        db.update_project_dates(pid, d.get('start_date'), d.get('end_date'))

    db.export_dashboard_json()
    return jsonify({'ok': True, 'id': pid, 'project': db.get_project(pid)})

@api.route('/api/config', methods=['GET'])
def get_config():
    from config import BOT_USERNAME
    return jsonify({'bot_username': BOT_USERNAME or ''})

# ─── Telegram Auth ──────────────────────────────────────────────────────────
@api.route('/api/auth/telegram', methods=['POST'])
def telegram_auth():
    user = request.json or {}
    _purge_expired_logins()
    try:
        logger.info("Telegram auth endpoint hit from %s", request.remote_addr)
        logger.debug("Headers: %s", dict(request.headers))
        logger.debug("Payload: %s", user)
    except Exception:
        pass

    from config import BOT_TOKEN
    if not BOT_TOKEN:
        return jsonify({'ok': False, 'error': 'BOT_TOKEN is not configured'}), 500

    try:
        auth_date = int(user.get('auth_date', 0))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Invalid auth_date'}), 400
    now = int(time.time())
    if auth_date <= 0 or now - auth_date > 86400 or auth_date - now > 300:
        logger.warning("Stale Telegram auth payload: auth_date=%s", auth_date)
        return jsonify({'ok': False, 'error': 'Session expired'}), 403

    data = {k: v for k, v in user.items() if k != 'hash' and v is not None}
    check_list = [f"{k}={v}" for k, v in sorted(data.items())]
    data_check_string = "\n".join(check_list)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    received_hash = user.get('hash') or ''
    if not hmac.compare_digest(computed_hash, received_hash):
        logger.warning("Telegram auth hash mismatch. computed=%s received=%s data=%s", computed_hash, received_hash, data_check_string)
        return jsonify({'ok': False, 'error': 'Invalid signature'}), 403

    safe_user = _sanitize_tg_user(user)
    if not safe_user['id']:
        return jsonify({'ok': False, 'error': 'Invalid Telegram user id'}), 400
    if not _is_allowed_user(safe_user):
        return jsonify({'ok': False, 'error': 'Access denied'}), 403

    session['tg_user'] = safe_user
    session.permanent = True
    logger.info("Telegram auth stored for user id=%s", safe_user.get('id'))
    return jsonify({'ok': True, 'user': safe_user})


@api.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = session.get('tg_user')
    if not user:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    return jsonify({'ok': True, 'user': user})


@api.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.pop('tg_user', None)
    return jsonify({'ok': True})


@api.route('/api/auth/telegram/link', methods=['POST'])
def telegram_auth_link():
    """Creates one-time deep-link token for Telegram login via t.me/BOT?start=token"""
    import uuid
    from config import BOT_USERNAME
    _purge_expired_logins()
    if not BOT_USERNAME:
        return jsonify({'ok': False, 'error': 'BOT_USERNAME is not configured'}), 500
    token = uuid.uuid4().hex
    _create_pending_token(token)
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    return jsonify({'ok': True, 'token': token, 'link': link})


def complete_pending_login(token, user):
    """Called by bot when /start token is received."""
    if not token:
        return False
    _purge_expired_logins()
    safe_user = _sanitize_tg_user(user or {})
    if not safe_user.get('id'):
        logger.warning("Invalid Telegram user from bot for token=%s", token)
        return False
    if not _is_allowed_user(safe_user):
        logger.warning("Access denied for Telegram user=%s token=%s", safe_user.get('id'), token)
        return False
    if not _complete_token(token, safe_user):
        logger.warning("Pending login token not found or expired: %s", token)
        return False
    logger.info("Completed pending login for token=%s user_id=%s", token, safe_user.get('id'))
    try:
        sse_push({'type': 'tg_login', 'token': token, 'user': safe_user})
    except Exception:
        pass
    return True


@api.route('/api/auth/telegram/check/<token>', methods=['GET'])
def telegram_auth_check(token):
    """Checks whether a deep-link token has been completed and finalizes the session."""
    _purge_expired_logins()
    completed_user = _consume_completed_token(token)
    if completed_user:
        session['tg_user'] = completed_user
        session.permanent = True
        return jsonify({'ok': True, 'user': completed_user})
    return jsonify({'ok': False}), 404


@api.route('/api/projects/sync', methods=['POST'])
def sync_project():
    d = request.json or {}
    name = d.get('name', '').strip()
    topic_id = d.get('topic_id')
    telegram_id = d.get('telegram_id')
    if not name:
        return jsonify({'ok': False, 'error': 'No project name'}), 400

    if topic_id in ('', None):
        topic_id = None
    else:
        try:
            topic_id = int(topic_id)
        except (TypeError, ValueError):
            topic_id = None

    pid = db.get_or_create_project(name, topic_id)
    project = db.get_project(pid) or {}
    # Reuse existing bound topic to avoid duplicate Telegram threads.
    if not topic_id and project.get('topic_id'):
        topic_id = int(project.get('topic_id'))
    synced_topic_id = topic_id

    if _bot_app and _bot_loop:
        import bot
        future = asyncio.run_coroutine_threadsafe(
            bot.create_telegram_tab(name, telegram_id, topic_id), _bot_loop
        )
        try:
            result = future.result(timeout=20)
            result_topic_id = result.get('topic_id') if isinstance(result, dict) else None
            if result_topic_id:
                synced_topic_id = int(result_topic_id)
        except Exception as e:
            logger.warning("Telegram sync failed for project=%s: %s", name, e)

    if synced_topic_id:
        db.update_project_topic(pid, synced_topic_id)
    if d.get('start_date') or d.get('end_date'):
        db.update_project_dates(pid, d.get('start_date'), d.get('end_date'))
    db.rename_project(pid, name)
    db.export_dashboard_json()
    return jsonify({'ok': True, 'id': pid, 'project': db.get_project(pid), 'synced': bool(synced_topic_id), 'topic_id': synced_topic_id})

@api.route('/api/projects/<int:pid>', methods=['GET'])
def get_project(pid):
    p = db.get_project(pid)
    return jsonify(p) if p else (jsonify({'error':'Not found'}), 404)

@api.route('/api/projects/<int:pid>', methods=['DELETE'])
def delete_project(pid):
    db.delete_project(pid)
    db.export_dashboard_json()
    return jsonify({'ok':True})

@api.route('/api/projects/<int:pid>/dates', methods=['POST'])
def set_project_dates(pid):
    d = request.json or {}
    db.update_project_dates(pid, d.get('start_date'), d.get('end_date'))
    return jsonify({'ok':True})


# ─── Gantt ────────────────────────────────────────────────────────────────────
@api.route('/api/projects/<int:pid>/gantt', methods=['GET'])
def get_gantt(pid):
    data = db.get_gantt_data(pid)
    if not data:
        return jsonify({'ok':False,'error':'Project not found'}), 404
    return jsonify(data)

@api.route('/api/sections', methods=['POST'])
def add_section():
    d = request.json or {}
    pid = d.get('project_id')
    code = d.get('code','').strip()
    name = d.get('name','').strip()
    if not pid or not code or not name:
        return jsonify({'ok':False,'error':'Нет данных'}), 400
    sid = db.add_section(pid, code, name, d.get('sort_order', 0))
    # Если передан шаблон подразделов
    template_subs = d.get('subsections', [])
    start = 0
    for sub in template_subs:
        db.add_subsection(sid, sub['c'], sub['n'], start, sub.get('d', 10))
        start += sub.get('d', 10)
    return jsonify({'ok':True,'id':sid})

@api.route('/api/sections/<int:sid>', methods=['DELETE'])
def del_section(sid):
    db.delete_section(sid)
    return jsonify({'ok':True})

@api.route('/api/subsections', methods=['POST'])
def add_subsection():
    d = request.json or {}
    sid = d.get('section_id')
    code = d.get('code','').strip()
    name = d.get('name','').strip()
    if not sid or not code or not name:
        return jsonify({'ok':False,'error':'Нет данных'}), 400
    sub_id = db.add_subsection(sid, code, name,
                                d.get('start_day', 0), d.get('duration', 10))
    return jsonify({'ok':True,'id':sub_id})

@api.route('/api/subsections/<int:sub_id>', methods=['PATCH'])
def patch_subsection(sub_id):
    d = request.json or {}
    db.update_subsection(sub_id, **d)
    sse_push({'type':'gantt_update','sub_id':sub_id,'data':d})
    return jsonify({'ok':True})


# ─── Deadlines ────────────────────────────────────────────────────────────────
@api.route('/api/deadlines/<int:pid>', methods=['GET'])
def get_deadlines(pid):
    return jsonify(db.get_deadlines(pid))

@api.route('/api/deadlines', methods=['POST'])
def set_deadline():
    d = request.json or {}
    pid = d.get('project_id')
    code = d.get('subsection_code','').strip()
    date = d.get('deadline_date','')[:10]
    if not pid or not code or not date:
        return jsonify({'ok':False,'error':'Нет данных'}), 400
    db.set_deadline(pid, code, date, d.get('set_by','Dashboard'), d.get('change_reason',''))
    sse_push({'type':'deadline_update','project_id':pid})
    return jsonify({'ok':True})

@api.route('/api/deadlines/<int:dl_id>', methods=['PUT'])
def update_deadline(dl_id):
    d = request.json or {}
    date = d.get('deadline_date','')[:10]
    db.update_deadline(dl_id, date, d.get('change_reason',''))
    return jsonify({'ok':True})


# ─── Members ─────────────────────────────────────────────────────────────────
@api.route('/api/members/all', methods=['GET'])
def get_members():
    return jsonify(db.get_all_members())

@api.route('/api/members', methods=['POST'])
def add_member():
    d = request.json or {}
    name = d.get('name','').strip()
    if not name:
        return jsonify({'ok':False,'error':'Нет имени'}), 400
    mid = db.add_member(name, d.get('telegram_id',''), d.get('position',''),
                         d.get('phone',''), d.get('email',''), d.get('color','#38bdf8'))
    db.export_dashboard_json()
    return jsonify({'ok':True,'id':mid})

@api.route('/api/members/<int:mid>', methods=['DELETE'])
def del_member(mid):
    db.delete_member(mid)
    return jsonify({'ok':True})


# ─── Messages ────────────────────────────────────────────────────────────────

@api.route('/api/participants', methods=['GET'])
def participants():
    source = (request.args.get('source') or 'all').strip().lower()
    q = (request.args.get('q') or '').strip().lower()
    status = (request.args.get('status') or 'all').strip().lower()
    only_username = (request.args.get('only_username') or 'false').lower() == 'true'

    team = db.get_all_members()
    team_by_tg = {}
    for m in team:
        tg = str(m.get('telegram_id') or '').strip()
        if tg:
            team_by_tg[tg] = m

    result = []

    if source in ('all', 'telegram'):
        for t in _tg_members_cache:
            tid = t.get('id')
            if not tid:
                continue
            username = (t.get('username') or '').strip()
            name = (t.get('name') or '').strip()
            tg_status = (t.get('status') or '').strip().lower()

            if status != 'all' and tg_status != status:
                continue
            if only_username and not username:
                continue
            if q and q not in name.lower() and q not in username.lower():
                continue

            team_row = team_by_tg.get(str(tid))
            result.append({
                'id': tid,
                'name': name,
                'username': username,
                'status': tg_status or 'member',
                'source': 'telegram',
                'in_team': bool(team_row),
                'team_member_id': team_row.get('id') if team_row else None,
                'position': team_row.get('position') if team_row else '',
            })

    if source in ('all', 'team'):
        for m in team:
            tg = str(m.get('telegram_id') or '').strip()
            username = ''
            tg_status = 'team'
            for t in _tg_members_cache:
                if str(t.get('id')) == tg:
                    username = (t.get('username') or '').strip()
                    tg_status = (t.get('status') or '').strip().lower() or 'member'
                    break
            name = (m.get('name') or '').strip()
            if status != 'all' and tg_status != status and status != 'team':
                continue
            if only_username and not username:
                continue
            if q and q not in name.lower() and q not in username.lower():
                continue
            result.append({
                'id': int(tg) if tg.isdigit() else None,
                'name': name,
                'username': username,
                'status': tg_status,
                'source': 'team',
                'in_team': True,
                'team_member_id': m.get('id'),
                'position': m.get('position') or '',
            })

    return jsonify(result)

@api.route('/api/participants/add_by_criteria', methods=['POST'])
def add_participants_by_criteria():
    d = request.json or {}
    q = (d.get('q') or '').strip().lower()
    status = (d.get('status') or 'all').strip().lower()
    only_username = bool(d.get('only_username'))
    default_position = (d.get('position') or '').strip()

    team = db.get_all_members()
    existing_tg = {str(m.get('telegram_id')) for m in team if str(m.get('telegram_id') or '').strip()}
    added = []

    for t in _tg_members_cache:
        tid = t.get('id')
        if not tid:
            continue
        tid_s = str(tid)
        username = (t.get('username') or '').strip()
        name = (t.get('name') or '').strip()
        tg_status = (t.get('status') or '').strip().lower()

        if tid_s in existing_tg:
            continue
        if status != 'all' and tg_status != status:
            continue
        if only_username and not username:
            continue
        if q and q not in name.lower() and q not in username.lower():
            continue

        mid = db.add_member(
            name=name or f"User {tid}",
            telegram_id=tid_s,
            position=default_position
        )
        existing_tg.add(tid_s)
        added.append({'member_id': mid, 'telegram_id': tid, 'name': name, 'username': username})

    if added:
        db.export_dashboard_json()
    return jsonify({'ok': True, 'added_count': len(added), 'added': added})


@api.route('/api/messages/<int:pid>', methods=['GET'])
def get_messages(pid):
    limit = int(request.args.get('limit', 50))
    return jsonify(db.get_messages(pid, limit))

@api.route('/api/messages/0', methods=['GET'])
def get_all_messages():
    limit = int(request.args.get('limit', 50))
    return jsonify(db.get_messages(None, limit))

@api.route('/api/messages/send', methods=['POST'])
def send_message_api():
    from config import GROUP_CHAT_ID

    d = request.json or {}
    print("🔥 SEND API HIT")
    print("JSON:", d)

    text = d.get('text','').strip()
    chat_id = d.get('chat_id', GROUP_CHAT_ID)
    thread_id = d.get('thread_id')
    project_id = d.get("project_id")
    try:
        project_id = int(project_id) if project_id not in (None, '') else None
    except (TypeError, ValueError):
        project_id = None

    if thread_id in (None, '') and project_id:
        p = db.get_project(project_id)
        if p and p.get('topic_id'):
            thread_id = int(p.get('topic_id'))

    if not text:
        return jsonify({'ok':False,'error':'Нет текста'}), 400

    _send_tg_message(
        chat_id=chat_id,
        text=text,
        thread_id=thread_id,
        project_id=project_id
    )

    return jsonify({'ok':True})

# Глобальная ссылка на бота (устанавливается из bot.py)
import asyncio

def _send_tg_message(chat_id, text, thread_id=None, project_id=None):
    print("🔥 SEND API RETURNING 200")
    global _bot_app, _bot_loop
    
    if not _bot_app or not _bot_loop:
        print("❌ Bot or loop not initialized")
        return

    async def send():
        try:
            sent = await _bot_app.bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=thread_id
            )

            print("✅ TG SENT OK")

            # ─── Логируем в БД ─────────────────────
            if project_id:
                db.log_message(
                    project_id,
                    chat_id,
                    sent.message_id,
                    "Dashboard",
                    "user",
                    text,
                    thread_id=thread_id,
                    source="dashboard"
                )

                sse_push({
                    "type": "new_message",
                    "project_id": project_id,
                    "from": "Dashboard",
                    "text": text,
                    "role": "user"
                })

        except Exception as e:
            print("❌ TG SEND ERROR:", e)

    asyncio.run_coroutine_threadsafe(send(), _bot_loop)
    print("LOOP:", _bot_loop)

# ─── Telegram group members (live from bot) ──────────────────────────────────
_tg_members_cache = []

def set_tg_members(members):
    global _tg_members_cache
    _tg_members_cache = members

@api.route('/api/telegram/members', methods=['GET'])
def tg_members():
    return jsonify(_tg_members_cache)

@api.route('/api/telegram/action', methods=['POST'])
def tg_action():
    """Telegram actions: set_deadline, set_status, notify"""
    d = request.json or {}
    action = d.get('action')
    pid = d.get('project_id', 1)
    msg = d.get('message','')

    if action == 'set_deadline':
        code = d.get('subsection_code','')
        date = d.get('deadline_date','')[:10] if d.get('deadline_date') else ''
        if code and date:
            db.set_deadline(pid, code, date, d.get('sender_name','Bot'))
            reply = f"✅ Срок {code}: {date}"
            _send_tg_message(d.get('chat_id', 0) or 0, reply)
            return jsonify({'ok':True,'reply':reply})

    elif action == 'set_status':
        code = d.get('subsection_code','')
        status = d.get('status','')
        sub = db.get_subsection_by_code(pid, code)
        if sub:
            db.update_subsection(sub['id'], status=status)
            return jsonify({'ok':True,'reply':f"✅ {code}: {status}"})

    elif action == 'notify':
        from config import GROUP_CHAT_ID
        _send_tg_message(GROUP_CHAT_ID, msg)
        return jsonify({'ok':True})

    return jsonify({'ok':False,'error':'Unknown action'})


# ─── RFI ─────────────────────────────────────────────────────────────────────
@api.route('/api/rfi', methods=['GET'])
def get_rfi():
    pid = request.args.get('project_id', 1)
    return jsonify(db.get_rfi(int(pid)))

@api.route('/api/rfi', methods=['POST'])
def add_rfi():
    d = request.json or {}
    rid = db.add_rfi(d.get('project_id',1), d.get('request_text',''), d.get('proposed_date'))
    return jsonify({'ok':True,'id':rid})


# ─── Tasks ────────────────────────────────────────────────────────────────────
@api.route('/api/tasks', methods=['GET'])
def get_tasks_api():
    pid = request.args.get('project_id')
    status = request.args.get('status','open')
    return jsonify(db.get_tasks(int(pid) if pid else None, status))

@api.route('/api/tasks', methods=['POST'])
def add_task_api():
    d = request.json or {}
    tid = db.add_task(d.get('project_id',1), d.get('title',''), d.get('responsible',''),
                      d.get('section',''), d.get('deadline'), d.get('priority','normal'))
    db.export_dashboard_json()
    sse_push({'type':'task_update'})
    return jsonify({'ok':True,'id':tid})

@api.route('/api/tasks/<int:tid>/close', methods=['POST'])
def close_task_api(tid):
    db.close_task(tid)
    db.export_dashboard_json()
    sse_push({'type':'task_update'})
    return jsonify({'ok':True})


# ─── Zamechaniya ──────────────────────────────────────────────────────────────
@api.route('/api/zamechaniya', methods=['GET'])
def get_zam_api():
    pid = request.args.get('project_id')
    status = request.args.get('status','open')
    return jsonify(db.get_zamechaniya(int(pid) if pid else None, status))

@api.route('/api/zamechaniya', methods=['POST'])
def add_zam_api():
    d = request.json or {}
    zid = db.add_zamechaniye(d.get('project_id',1), d.get('description',''),
                              d.get('source','экспертиза'), d.get('responsible'), d.get('section'))
    db.export_dashboard_json()
    return jsonify({'ok':True,'id':zid})

@api.route('/api/zamechaniya/<int:zid>/close', methods=['POST'])
def close_zam_api(zid):
    db.close_zamechaniye(zid)
    db.export_dashboard_json()
    return jsonify({'ok':True})


# ─── Changes ─────────────────────────────────────────────────────────────────
@api.route('/api/changes', methods=['GET'])
def get_changes_api():
    pid = request.args.get('project_id')
    return jsonify(db.get_changes(int(pid) if pid else None))

@api.route('/api/changes', methods=['POST'])
def add_change_api():
    d = request.json or {}
    cid = db.add_change(d.get('project_id',1), d.get('description',''),
                         d.get('author','Dashboard'), d.get('section',''), d.get('impact',''))
    db.export_dashboard_json()
    return jsonify({'ok':True,'id':cid})


# ─── Votes ────────────────────────────────────────────────────────────────────
@api.route('/api/votes', methods=['GET'])
def get_votes_api():
    pid = request.args.get('project_id')
    return jsonify(db.get_votes(int(pid) if pid else None))

@api.route('/api/votes', methods=['POST'])
def create_vote_api():
    d = request.json or {}
    from config import GROUP_CHAT_ID
    vid = db.create_vote(d.get('project_id',1), GROUP_CHAT_ID,
                          d.get('proposal',''), d.get('author','Dashboard'))
    return jsonify({'ok':True,'id':vid})


# ─── Dashboard data ───────────────────────────────────────────────────────────
@api.route('/api/data', methods=['GET'])
def full_data():
    return jsonify(db.export_dashboard_json())

@api.route('/api/workload', methods=['GET'])
def workload():
    return jsonify(db.get_workload_stats())

@api.route('/api/stats/weekly', methods=['GET'])
def weekly_stats():
    return jsonify(db.get_weekly_stats())

@api.route('/api/debug/models', methods=['GET'])
def debug_models():
    return jsonify({'ok':True,'db':db.DB_PATH,'projects':len(db.get_all_projects())})


# ─── Simulation (заглушка) ────────────────────────────────────────────────────
@api.route('/api/simulation/start/<int:pid>', methods=['POST'])
def sim_start(pid):
    return jsonify({'ok':True,'message':'Симуляция запущена (заглушка)'})

@api.route('/api/simulation/stop/<int:pid>', methods=['POST'])
def sim_stop(pid):
    return jsonify({'ok':True})
