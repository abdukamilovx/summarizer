"""Pearl PM — Database (extended with Gantt tables)"""
import sqlite3, json
from datetime import datetime
from config import DB_PATH, EXPORT_JSON

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        topic_id INTEGER, telegram_id INTEGER, start_date TEXT, end_date TEXT,
        status TEXT DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS gantt_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
        code TEXT NOT NULL, name TEXT NOT NULL, sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (project_id) REFERENCES projects(id));
    CREATE TABLE IF NOT EXISTS gantt_subsections (
        id INTEGER PRIMARY KEY AUTOINCREMENT, section_id INTEGER NOT NULL,
        code TEXT NOT NULL, name TEXT NOT NULL, start_day INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 10, status TEXT DEFAULT 'not_started',
        progress INTEGER DEFAULT 0, assignee TEXT DEFAULT '', depends_on TEXT DEFAULT '',
        FOREIGN KEY (section_id) REFERENCES gantt_sections(id));
    CREATE TABLE IF NOT EXISTS deadlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, subsection_id INTEGER,
        project_id INTEGER, subsection_code TEXT, deadline_date TEXT,
        set_by TEXT DEFAULT 'Dashboard', change_reason TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        telegram_id TEXT DEFAULT '', position TEXT DEFAULT '',
        phone TEXT DEFAULT '', email TEXT DEFAULT '', color TEXT DEFAULT '#38bdf8',
        created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS rfi (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        request_text TEXT NOT NULL, proposed_date TEXT,
        status TEXT DEFAULT 'open', created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        title TEXT NOT NULL, responsible TEXT, section TEXT, deadline TEXT,
        status TEXT DEFAULT 'open', priority TEXT DEFAULT 'normal',
        message_id INTEGER, created_at TEXT DEFAULT (datetime('now')), closed_at TEXT);
    CREATE TABLE IF NOT EXISTS zamechaniya (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        description TEXT NOT NULL, source TEXT DEFAULT 'экспертиза',
        responsible TEXT, section TEXT, status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now')), closed_at TEXT);
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        description TEXT NOT NULL, author TEXT, section TEXT, impact TEXT,
        created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        chat_id INTEGER, message_id INTEGER, proposal TEXT NOT NULL,
        author TEXT, yes_count INTEGER DEFAULT 0, no_count INTEGER DEFAULT 0,
        discuss_count INTEGER DEFAULT 0, voters TEXT DEFAULT '[]',
        status TEXT DEFAULT 'open', created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS messages_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,
        chat_id INTEGER, message_id INTEGER, thread_id INTEGER,
        from_user TEXT, role TEXT DEFAULT 'user', text TEXT,
        source TEXT DEFAULT 'telegram', created_at TEXT DEFAULT (datetime('now')));
    """)
    conn.commit(); conn.close()

# Projects
def get_all_projects():
    conn=get_conn(); rows=conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall(); conn.close(); return [dict(r) for r in rows]
def get_project(pid):
    conn=get_conn(); row=conn.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone(); conn.close(); return dict(row) if row else None
def get_project_by_topic(topic_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM projects WHERE topic_id=?",(topic_id,)).fetchone(); conn.close(); return dict(row) if row else None
def create_project(name,start_date=None,end_date=None,topic_id=None):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO projects (name,start_date,end_date,topic_id) VALUES (?,?,?,?)",(name,start_date,end_date,topic_id)); pid=c.lastrowid; conn.commit(); conn.close(); return pid
def delete_project(pid):
    conn=get_conn()
    for t in ['gantt_sections','tasks','zamechaniya','changes','messages_log','rfi','votes']: conn.execute(f"DELETE FROM {t} WHERE project_id=?",(pid,))
    conn.execute("DELETE FROM projects WHERE id=?",(pid,)); conn.commit(); conn.close()
def get_or_create_project(name,topic_id=None):
    conn=get_conn()
    if topic_id:
        row=conn.execute("SELECT id FROM projects WHERE topic_id=?",(topic_id,)).fetchone()
        if row:
            pid=row["id"]
            conn.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))
            conn.commit()
            conn.close()
            return pid
    row=conn.execute("SELECT id FROM projects WHERE name=?",(name,)).fetchone()
    if row:
        pid=row["id"]
        if topic_id:
            conn.execute("UPDATE projects SET topic_id=? WHERE id=?", (topic_id, pid))
            conn.commit()
    else:
        c=conn.cursor(); c.execute("INSERT INTO projects (name,topic_id) VALUES (?,?)",(name,topic_id)); pid=c.lastrowid; conn.commit()
    conn.close(); return pid
def update_project_dates(pid,start_date,end_date):
    conn=get_conn(); conn.execute("UPDATE projects SET start_date=?,end_date=? WHERE id=?",(start_date,end_date,pid)); conn.commit(); conn.close()
def update_project_telegram_id(pid, tg_id):
    conn=get_conn(); conn.execute("UPDATE projects SET telegram_id=? WHERE id=?",(tg_id,pid)); conn.commit(); conn.close()
def update_project_topic(pid, topic_id):
    conn=get_conn(); conn.execute("UPDATE projects SET topic_id=? WHERE id=?", (topic_id, pid)); conn.commit(); conn.close()
def rename_project(pid, name):
    conn=get_conn(); conn.execute("UPDATE projects SET name=? WHERE id=?", (name, pid)); conn.commit(); conn.close()

# Gantt Sections
def get_sections(project_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM gantt_sections WHERE project_id=? ORDER BY sort_order,id",(project_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]
def add_section(project_id,code,name,sort_order=0):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO gantt_sections (project_id,code,name,sort_order) VALUES (?,?,?,?)",(project_id,code,name,sort_order)); sid=c.lastrowid; conn.commit(); conn.close(); return sid
def delete_section(section_id):
    conn=get_conn(); conn.execute("DELETE FROM gantt_subsections WHERE section_id=?",(section_id,)); conn.execute("DELETE FROM gantt_sections WHERE id=?",(section_id,)); conn.commit(); conn.close()

# Gantt Subsections
def get_subsections(section_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM gantt_subsections WHERE section_id=? ORDER BY id",(section_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]
def add_subsection(section_id,code,name,start_day=0,duration=10):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO gantt_subsections (section_id,code,name,start_day,duration) VALUES (?,?,?,?,?)",(section_id,code,name,start_day,duration)); sid=c.lastrowid; conn.commit(); conn.close(); return sid
def update_subsection(sub_id,**kwargs):
    allowed=['status','progress','assignee','start_day','duration','depends_on']
    sets=[]; vals=[]
    for k,v in kwargs.items():
        if k in allowed: sets.append(f"{k}=?"); vals.append(v)
    if not sets: return
    vals.append(sub_id); conn=get_conn(); conn.execute(f"UPDATE gantt_subsections SET {','.join(sets)} WHERE id=?",vals); conn.commit(); conn.close()
def get_subsection_by_code(project_id,code):
    conn=get_conn(); row=conn.execute("SELECT s.* FROM gantt_subsections s JOIN gantt_sections sec ON s.section_id=sec.id WHERE sec.project_id=? AND s.code=?",(project_id,code)).fetchone(); conn.close(); return dict(row) if row else None
def get_gantt_data(project_id):
    project=get_project(project_id)
    if not project: return None
    sections=get_sections(project_id)
    items=[]
    for sec in sections:
        subs=get_subsections(sec['id']); sec['subsections']=subs
        for sub in subs: items.append({**sub,'section_code':sec['code'],'section_name':sec['name']})
    return {'project':project,'sections':sections,'items':items}

# Deadlines
def set_deadline(project_id,subsection_code,deadline_date,set_by='Dashboard',reason=''):
    sub=get_subsection_by_code(project_id,subsection_code); sub_id=sub['id'] if sub else None
    conn=get_conn()
    ex=conn.execute("SELECT id FROM deadlines WHERE project_id=? AND subsection_code=?",(project_id,subsection_code)).fetchone()
    if ex: conn.execute("UPDATE deadlines SET deadline_date=?,set_by=?,change_reason=?,created_at=datetime('now') WHERE id=?",(deadline_date,set_by,reason,ex['id']))
    else: conn.execute("INSERT INTO deadlines (subsection_id,project_id,subsection_code,deadline_date,set_by,change_reason) VALUES (?,?,?,?,?,?)",(sub_id,project_id,subsection_code,deadline_date,set_by,reason))
    conn.commit(); conn.close()
def get_deadlines(project_id):
    conn=get_conn(); rows=conn.execute("SELECT d.*,s.name as sub_name FROM deadlines d LEFT JOIN gantt_subsections s ON d.subsection_id=s.id WHERE d.project_id=? ORDER BY d.deadline_date",(project_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]
def update_deadline(dl_id,deadline_date,reason=''):
    conn=get_conn(); conn.execute("UPDATE deadlines SET deadline_date=?,change_reason=? WHERE id=?",(deadline_date,reason,dl_id)); conn.commit(); conn.close()

# Members
def get_all_members():
    conn=get_conn(); rows=conn.execute("SELECT * FROM members ORDER BY name").fetchall(); conn.close(); return [dict(r) for r in rows]
def add_member(name,telegram_id='',position='',phone='',email='',color='#38bdf8'):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO members (name,telegram_id,position,phone,email,color) VALUES (?,?,?,?,?,?)",(name,telegram_id,position,phone,email,color)); mid=c.lastrowid; conn.commit(); conn.close(); return mid
def delete_member(mid):
    conn=get_conn(); conn.execute("DELETE FROM members WHERE id=?",(mid,)); conn.commit(); conn.close()

# RFI
def get_rfi(project_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM rfi WHERE project_id=? ORDER BY created_at DESC",(project_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]
def add_rfi(project_id,request_text,proposed_date=None):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO rfi (project_id,request_text,proposed_date) VALUES (?,?,?)",(project_id,request_text,proposed_date)); rid=c.lastrowid; conn.commit(); conn.close(); return rid

# Tasks
def add_task(project_id,title,responsible,section,deadline,priority='normal',message_id=None):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO tasks (project_id,title,responsible,section,deadline,priority,message_id) VALUES (?,?,?,?,?,?,?)",(project_id,title,responsible,section,deadline,priority,message_id)); tid=c.lastrowid; conn.commit(); conn.close(); return tid
def close_task(tid):
    conn=get_conn(); conn.execute("UPDATE tasks SET status='closed',closed_at=datetime('now') WHERE id=?",(tid,)); conn.commit(); conn.close()
def get_tasks(project_id=None,status='open'):
    conn=get_conn()
    if project_id: rows=conn.execute("SELECT * FROM tasks WHERE project_id=? AND status=? ORDER BY deadline",(project_id,status)).fetchall()
    else: rows=conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY deadline",(status,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

# Zamechaniya
def add_zamechaniye(project_id,description,source='экспертиза',responsible=None,section=None):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO zamechaniya (project_id,description,source,responsible,section) VALUES (?,?,?,?,?)",(project_id,description,source,responsible,section)); zid=c.lastrowid; conn.commit(); conn.close(); return zid
def close_zamechaniye(zid):
    conn=get_conn(); conn.execute("UPDATE zamechaniya SET status='closed',closed_at=datetime('now') WHERE id=?",(zid,)); conn.commit(); conn.close()
def get_zamechaniya(project_id=None,status='open'):
    conn=get_conn()
    if project_id: rows=conn.execute("SELECT * FROM zamechaniya WHERE project_id=? AND status=? ORDER BY created_at DESC",(project_id,status)).fetchall()
    else: rows=conn.execute("SELECT * FROM zamechaniya WHERE status=? ORDER BY created_at DESC",(status,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

# Changes
def add_change(project_id,description,author,section,impact=''):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO changes (project_id,description,author,section,impact) VALUES (?,?,?,?,?)",(project_id,description,author,section,impact)); cid=c.lastrowid; conn.commit(); conn.close(); return cid
def get_changes(project_id=None,limit=30):
    conn=get_conn()
    if project_id: rows=conn.execute("SELECT * FROM changes WHERE project_id=? ORDER BY created_at DESC LIMIT ?",(project_id,limit)).fetchall()
    else: rows=conn.execute("SELECT * FROM changes ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    conn.close(); return [dict(r) for r in rows]

# Votes
def create_vote(project_id,chat_id,proposal,author):
    conn=get_conn(); c=conn.cursor(); c.execute("INSERT INTO votes (project_id,chat_id,proposal,author) VALUES (?,?,?,?)",(project_id,chat_id,proposal,author)); vid=c.lastrowid; conn.commit(); conn.close(); return vid
def update_vote_message_id(vote_id,message_id):
    conn=get_conn(); conn.execute("UPDATE votes SET message_id=? WHERE id=?",(message_id,vote_id)); conn.commit(); conn.close()
def register_vote(vote_id,user_id,choice):
    conn=get_conn(); vote=dict(conn.execute("SELECT * FROM votes WHERE id=?",(vote_id,)).fetchone())
    voters=json.loads(vote['voters'])
    if user_id in voters: conn.close(); return False,'already_voted'
    voters.append(user_id); col={'yes':'yes_count','no':'no_count','discuss':'discuss_count'}[choice]
    conn.execute(f"UPDATE votes SET {col}={col}+1,voters=? WHERE id=?",(json.dumps(voters),vote_id)); conn.commit(); conn.close(); return True,'ok'
def get_vote(vote_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM votes WHERE id=?",(vote_id,)).fetchone(); conn.close(); return dict(row) if row else None
def close_vote(vote_id):
    conn=get_conn(); conn.execute("UPDATE votes SET status='closed' WHERE id=?",(vote_id,)); conn.commit(); conn.close()
def get_votes(project_id=None):
    conn=get_conn()
    if project_id: rows=conn.execute("SELECT * FROM votes WHERE project_id=? ORDER BY created_at DESC",(project_id,)).fetchall()
    else: rows=conn.execute("SELECT * FROM votes ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close(); return [dict(r) for r in rows]

# Messages
def log_message(project_id,chat_id,message_id,from_user,role,text,thread_id=None,source='telegram'):
    conn=get_conn(); conn.execute("INSERT INTO messages_log (project_id,chat_id,message_id,thread_id,from_user,role,text,source) VALUES (?,?,?,?,?,?,?,?)",(project_id,chat_id,message_id,thread_id,from_user,role,str(text)[:2000],source)); conn.commit(); conn.close()
def get_messages(project_id=None,limit=50):
    conn=get_conn()
    if project_id: rows=conn.execute("SELECT * FROM messages_log WHERE project_id=? ORDER BY created_at DESC LIMIT ?",(project_id,limit)).fetchall()
    else: rows=conn.execute("SELECT * FROM messages_log ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    conn.close(); return [dict(r) for r in reversed(rows)]
def get_recent_messages(project_id=None,limit=10): return get_messages(project_id,limit)

# Stats
def get_weekly_stats():
    from datetime import timedelta
    week_ago=(datetime.now()-timedelta(days=7)).isoformat()
    conn=get_conn()
    s={'tasks_opened':conn.execute("SELECT COUNT(*) FROM tasks WHERE created_at>=?",(week_ago,)).fetchone()[0],
       'tasks_closed':conn.execute("SELECT COUNT(*) FROM tasks WHERE closed_at>=?",(week_ago,)).fetchone()[0],
       'tasks_overdue':conn.execute("SELECT COUNT(*) FROM tasks WHERE status='open' AND deadline<datetime('now')").fetchone()[0],
       'zam_opened':conn.execute("SELECT COUNT(*) FROM zamechaniya WHERE created_at>=?",(week_ago,)).fetchone()[0],
       'zam_closed':conn.execute("SELECT COUNT(*) FROM zamechaniya WHERE closed_at>=?",(week_ago,)).fetchone()[0],
       'changes_added':conn.execute("SELECT COUNT(*) FROM changes WHERE created_at>=?",(week_ago,)).fetchone()[0]}
    conn.close(); return s

def get_workload_stats():
    conn=get_conn()
    bm=conn.execute("SELECT responsible,COUNT(*) as cnt FROM tasks WHERE status='open' GROUP BY responsible ORDER BY cnt DESC").fetchall()
    bs=conn.execute("SELECT section,COUNT(*) as cnt FROM tasks WHERE status='open' GROUP BY section ORDER BY cnt DESC").fetchall()
    conn.close(); return {'by_member':[dict(r) for r in bm],'by_section':[dict(r) for r in bs]}

def export_dashboard_json():
    import os; os.makedirs('dashboard',exist_ok=True)
    data={'exported_at':datetime.now().isoformat(),'projects':get_all_projects(),
          'tasks_open':get_tasks(status='open'),'tasks_closed':get_tasks(status='closed'),
          'zamechaniya_open':get_zamechaniya(status='open'),'zamechaniya_closed':get_zamechaniya(status='closed'),
          'changes':get_changes(limit=50),'messages':get_messages(limit=30),'members':get_all_members()}
    with open(EXPORT_JSON,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2,default=str)
    return data
