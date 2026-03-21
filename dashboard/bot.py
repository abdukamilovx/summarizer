"""Pearl Project Management Bot вЂ” Р“Р»Р°РІРЅС‹Р№ С„Р°Р№Р» v2"""
import logging, asyncio, threading, json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, constants
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import database as db
try:
    import ai_specialists as ai
except ImportError:
    ai = None
from config import (
    BOT_TOKEN,
    GROUP_CHAT_ID,
    SPECIALISTS,
    WEEKLY_REPORT_DAY,
    WEEKLY_REPORT_HOUR,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_SECRET_KEY,
)
import api_routes

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO,
    handlers=[logging.FileHandler("pearl_bot.log",encoding="utf-8"), logging.StreamHandler()])
logger = logging.getLogger(__name__)
USER_STATE = {}

# в”Ђв”Ђв”Ђ Helpers в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def fmt_date(iso):
    if not iso: return "вЂ”"
    try: return datetime.fromisoformat(iso[:10]).strftime("%d.%m.%Y")
    except: return str(iso)

def get_pid(chat_id, topic_id=None, name=None):
    if topic_id and not name:
        name = f"Тема {topic_id}"
    return db.get_or_create_project(
        name or f"Группа {chat_id}",
        topic_id
    )

def get_main_keyboard():
    """РџРѕСЃС‚РѕСЏРЅРЅР°СЏ РєР»Р°РІРёР°С‚СѓСЂР° СЃ РєРЅРѕРїРєР°РјРё"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("рџ“Љ РЎС‚Р°С‚СѓСЃ"), KeyboardButton("вњ… Р—Р°РґР°С‡Рё")],
        [KeyboardButton("рџ“‹ Р—Р°РјРµС‡Р°РЅРёСЏ"), KeyboardButton("вћ• Р—Р°РґР°С‡Р°")],
        [KeyboardButton("рџ—і Р“РѕР»РѕСЃРѕРІР°РЅРёРµ"), KeyboardButton("рџ“ќ Р–СѓСЂРЅР°Р»")],
        [KeyboardButton("рџ‘Ґ РљРѕРјР°РЅРґР°"), KeyboardButton("рџ“… Р”РµРґР»Р°Р№РЅС‹")],
        [KeyboardButton("рџ“¤ РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ"), KeyboardButton("рџ“€ РћС‚С‡С‘С‚")],
    ], resize_keyboard=True, persistent=True)

# в”Ђв”Ђв”Ђ РљРѕРјР°РЅРґС‹ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def cmd_start(update, ctx):
    db.init_db()
    # РџРѕР»СѓС‡Р°РµРј СѓС‡Р°СЃС‚РЅРёРєРѕРІ РіСЂСѓРїРїС‹
    await update_tg_members(ctx.bot)
    # If /start contains a token (deep-link), handle it in a special flow
    txt = update.message.text or ''
    parts = txt.split()
    if len(parts) > 1:
        token = parts[1].strip()
        # Inform API of completed login
        try:
            import api_routes
            user = {
                'id': update.effective_user.id,
                'first_name': update.effective_user.first_name,
                'last_name': getattr(update.effective_user, 'last_name', None) or '',
                'username': getattr(update.effective_user, 'username', '')
            }
            api_routes.complete_pending_login(token, user)
            await update.message.reply_text("вњ… РђРІС‚РѕСЂРёР·Р°С†РёСЏ С‡РµСЂРµР· РґР°С€Р±РѕСЂРґ РІС‹РїРѕР»РЅРµРЅР°. Р’С‹ РјРѕР¶РµС‚Рµ РІРµСЂРЅСѓС‚СЊСЃСЏ РІ Р±СЂР°СѓР·РµСЂ.")
            return
        except Exception as e:
            logger.warning(f"Error completing pending login: {e}")

    await update.message.reply_text(
        "рџЏ— *Pearl Project Management Bot*\n\nРСЃРїРѕР»СЊР·СѓР№С‚Рµ РєРЅРѕРїРєРё РЅРёР¶Рµ рџ‘‡",
        parse_mode="Markdown", reply_markup=get_main_keyboard())

async def update_tg_members(bot):
    try:
        members = []
        chat = await bot.get_chat(GROUP_CHAT_ID)
        # РџРѕР»СѓС‡Р°РµРј Р°РґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂРѕРІ
        admins = await bot.get_chat_administrators(GROUP_CHAT_ID)
        for a in admins:
            u = a.user
            if not u.is_bot:
                members.append({
                    'id': u.id, 'name': u.full_name,
                    'username': u.username or '',
                    'status': a.status, 'is_online': False
                })
        api_routes.set_tg_members(members)
        logger.info(f"РћР±РЅРѕРІР»РµРЅРѕ СѓС‡Р°СЃС‚РЅРёРєРѕРІ: {len(members)}")
    except Exception as e:
        logger.warning(f"РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СѓС‡Р°СЃС‚РЅРёРєРѕРІ: {e}")

async def cmd_status(update, ctx):
    to = db.get_tasks(status='open')
    tc = db.get_tasks(status='closed')
    zo = db.get_zamechaniya(status='open')
    today = datetime.now().date()
    overdue = [t for t in to if t.get('deadline') and datetime.fromisoformat(t['deadline'][:10]).date() < today]
    text = (f"рџ“Љ *РЎРўРђРўРЈРЎ РџР РћР•РљРўРђ*\n\n"
            f"вњ… Р—Р°РґР°С‡Рё РѕС‚РєСЂС‹С‚С‹: {len(to)}\n"
            f"рџЏЃ Р—Р°РґР°С‡Рё Р·Р°РєСЂС‹С‚С‹: {len(tc)}\n"
            f"вљ пёЏ РџСЂРѕСЃСЂРѕС‡РµРЅРѕ: {len(overdue)}\n\n"
            f"рџ“‹ Р—Р°РјРµС‡Р°РЅРёСЏ: рџ”ґ {len(zo)} РѕС‚РєСЂС‹С‚Рѕ\n")
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_deadlines(update, ctx):
    tasks = db.get_tasks(status='open')
    if not tasks:
        await update.message.reply_text("вњ… РќРµС‚ РѕС‚РєСЂС‹С‚С‹С… Р·Р°РґР°С‡!", reply_markup=get_main_keyboard())
        return
    today = datetime.now().date()
    lines = ["рџ“‹ *РћРўРљР Р«РўР«Р• Р—РђР”РђР§Р*\n"]
    for t in tasks[:15]:
        dl = t.get('deadline','')
        over = ""
        if dl:
            try:
                if datetime.fromisoformat(dl[:10]).date() < today: over = " вљ пёЏ"
            except: pass
        lines.append(f"вЂў *#{t['id']}* {t['title']}\n  рџ‘¤ {t.get('responsible','вЂ”')} | рџ“… {fmt_date(dl)}{over}")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cmd_zamechaniya(update, ctx):
    items = db.get_zamechaniya(status='open')
    closed = db.get_zamechaniya(status='closed')
    lines = [f"рџ“‹ *Р—РђРњР•Р§РђРќРРЇ*\nРћС‚РєСЂС‹С‚Рѕ: {len(items)} | Р—Р°РєСЂС‹С‚Рѕ: {len(closed)}\n"]
    for z in items[:10]:
        lines.append(f"рџ”ґ *#{z['id']}* [{z.get('section','вЂ”')}] {z['description'][:60]}\n  рџ‘¤ {z.get('responsible','вЂ”')}")
    if not items: lines.append("вњ… РќРµС‚ РѕС‚РєСЂС‹С‚С‹С… Р·Р°РјРµС‡Р°РЅРёР№!")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cmd_create_task(update, ctx):
    USER_STATE[update.effective_user.id] = {"action": "create_task_title"}
    await update.message.reply_text("рџ“ќ *РЎРѕР·РґР°РЅРёРµ Р·Р°РґР°С‡Рё*\n\nРќР°Р·РІР°РЅРёРµ Р·Р°РґР°С‡Рё:", parse_mode="Markdown")

async def cmd_vote(update, ctx):
    args = " ".join(ctx.args).strip() if ctx.args else ""
    if not args:
        USER_STATE[update.effective_user.id] = {"action": "vote_proposal"}
        await update.message.reply_text("рџ—і РћРїРёС€РёС‚Рµ РїСЂРµРґР»РѕР¶РµРЅРёРµ РґР»СЏ РіРѕР»РѕСЃРѕРІР°РЅРёСЏ:")
        return
    await _start_vote(update, args)

async def _start_vote(update, proposal):
    pid = get_pid(update.effective_chat.id)
    author = update.effective_user.full_name
    vid = db.create_vote(pid, update.effective_chat.id, proposal, author)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("вњ… Р—Р°", callback_data=f"vote:{vid}:yes"),
        InlineKeyboardButton("вќЊ РџСЂРѕС‚РёРІ", callback_data=f"vote:{vid}:no"),
        InlineKeyboardButton("рџ’¬ РћР±СЃСѓРґРёС‚СЊ", callback_data=f"vote:{vid}:discuss"),
    ],[InlineKeyboardButton("рџ”’ Р—Р°РєСЂС‹С‚СЊ", callback_data=f"vote:{vid}:close")]])
    msg = await update.message.reply_text(
        f"рџ—і *Р“РћР›РћРЎРћР’РђРќРР• #{vid}*\n\n{proposal}\n\nвњ… 0  вќЊ 0  рџ’¬ 0",
        parse_mode="Markdown", reply_markup=kb)
    db.update_vote_message_id(vid, msg.message_id)

async def cmd_changelog(update, ctx):
    changes = db.get_changes(limit=10)
    if not changes:
        await update.message.reply_text("рџ“‹ Р–СѓСЂРЅР°Р» РїСѓСЃС‚", reply_markup=get_main_keyboard())
        return
    lines = ["рџ“ќ *Р–РЈР РќРђР› РР—РњР•РќР•РќРР™*\n"]
    for c in changes:
        lines.append(f"рџ“Њ *{fmt_date(c['created_at'])}* [{c.get('section','вЂ”')}]\n{c['description'][:80]}\n_РђРІС‚РѕСЂ: {c.get('author','вЂ”')}_")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cmd_team(update, ctx):
    lines = ["рџ‘Ґ *РљРћРњРђРќР”Рђ*\n"]
    for k, s in SPECIALISTS.items():
        lines.append(f"{s['emoji']} *{s['name']}*\n{s['role']}")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown", reply_markup=get_main_keyboard())

async def cmd_weekly_report(update, ctx):
    await _send_weekly_report(ctx.bot, update.effective_chat.id)

async def cmd_sync(update, ctx):
    db.export_dashboard_json()
    await update.message.reply_text("рџ”„ РЎРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅРѕ СЃ РґР°С€Р±РѕСЂРґРѕРј!", reply_markup=get_main_keyboard())

async def cmd_add_zam(update, ctx):
    args = " ".join(ctx.args).strip() if ctx.args else ""
    if not args:
        USER_STATE[update.effective_user.id] = {"action": "add_zam_desc"}
        await update.message.reply_text("рџ“ќ РћРїРёС€РёС‚Рµ Р·Р°РјРµС‡Р°РЅРёРµ (Р Р°Р·РґРµР»: РѕРїРёСЃР°РЅРёРµ):")
        return
    pid = get_pid(update.effective_chat.id)
    zid = db.add_zamechaniye(pid, args)
    db.export_dashboard_json()
    await update.message.reply_text(f"вњ… Р—Р°РјРµС‡Р°РЅРёРµ #{zid} Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°РЅРѕ!", reply_markup=get_main_keyboard())

async def cmd_close_zam(update, ctx):
    if not ctx.args:
        await update.message.reply_text("РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: /close_zam [id]")
        return
    db.close_zamechaniye(int(ctx.args[0]))
    db.export_dashboard_json()
    await update.message.reply_text(f"вњ… Р—Р°РјРµС‡Р°РЅРёРµ #{ctx.args[0]} Р·Р°РєСЂС‹С‚Рѕ!", reply_markup=get_main_keyboard())

async def cmd_close_task(update, ctx):
    if not ctx.args:
        await update.message.reply_text("РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: /close_task [id]")
        return
    db.close_task(int(ctx.args[0]))
    db.export_dashboard_json()
    await update.message.reply_text(f"вњ… Р—Р°РґР°С‡Р° #{ctx.args[0]} Р·Р°РєСЂС‹С‚Р°!", reply_markup=get_main_keyboard())

# в”Ђв”Ђв”Ђ РћР±СЂР°Р±РѕС‚С‡РёРє РєРЅРѕРїРѕРє РєР»Р°РІРёР°С‚СѓСЂС‹ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def handle_message(update, ctx):
    if not update.message or not update.message.text:
        return

    # РўРѕР»СЊРєРѕ РіСЂСѓРїРїС‹
    if update.effective_chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    text = update.message.text
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id
    uid = user.id
    pid = get_pid(chat_id, thread_id)
    logger.debug(f"chat_id: {chat_id}")
    logger.debug(f"thread_id: {thread_id}")
    logger.debug(f"pid: {pid}")
    if getattr(update.message, "forum_topic_created", None):
        topic_name = update.message.forum_topic_created.name
        if thread_id and topic_name:
            db.rename_project(pid, topic_name)

    # РњСѓР»СЊС‚РёС€Р°РіРѕРІС‹Р№ РґРёР°Р»РѕРі
    if uid in USER_STATE:
        await handle_state(update, ctx, pid)
        return

    # РљРЅРѕРїРєРё
    btn_map = {
        "рџ“Љ РЎС‚Р°С‚СѓСЃ": cmd_status,
        "вњ… Р—Р°РґР°С‡Рё": cmd_deadlines,
        "рџ“‹ Р—Р°РјРµС‡Р°РЅРёСЏ": cmd_zamechaniya,
        "вћ• Р—Р°РґР°С‡Р°": cmd_create_task,
        "рџ—і Р“РѕР»РѕСЃРѕРІР°РЅРёРµ": cmd_vote,
        "рџ“ќ Р–СѓСЂРЅР°Р»": cmd_changelog,
        "рџ‘Ґ РљРѕРјР°РЅРґР°": cmd_team,
        "рџ“… Р”РµРґР»Р°Р№РЅС‹": cmd_deadlines,
        "рџ“¤ РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ": cmd_sync,
        "рџ“€ РћС‚С‡С‘С‚": cmd_weekly_report,
    }

    if text in btn_map:
        await btn_map[text](update, ctx)
        return

    # в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ Р›РћР“ РџРћР›Р¬Р—РћР’РђРўР•Р›РЇ (РЎР РђР—РЈ) в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    username = user.username
    display_name = f"@{username}" if username else user.full_name

    db.log_message(
        pid,
        chat_id,
        update.message.message_id,
        display_name,
        "user",
        text,
        thread_id
    )

    api_routes.sse_push({
        'type': 'new_message',
        'project_id': pid,
        'from': display_name,
        'text': text,
        'role': 'user',
        'thread_id': thread_id
    })

    # в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ РљРѕРЅС„Р»РёРєС‚С‹ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    conflicts = ai.detect_conflicts(text)
    for c in conflicts:
        await update.message.reply_text(c["warning"], parse_mode="Markdown")

    # в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ AI СЃРїРµС†РёР°Р»РёСЃС‚ в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    spec_key = ai.detect_specialist(text)
    if not spec_key:
        return

    spec = SPECIALISTS[spec_key]

    await ctx.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)

    context = db.get_recent_messages(pid, 6)

    reply = ai.get_specialist_reply(
        spec_key,
        text,
        [{"role": m["role"], "text": m["text"]} for m in context]
    )

    msg_text = f"{spec['emoji']} *{spec['name']}*\n\n{reply}"
    sent = await update.message.reply_text(msg_text, parse_mode="Markdown")

    db.log_message(
        pid,
        chat_id,
        sent.message_id,
        spec["name"],
        "assistant",
        reply
    )

    api_routes.sse_push({
        'type': 'new_message',
        'project_id': pid,
        'from': spec['name'],
        'text': reply,
        'role': 'assistant'
    })

    db.export_dashboard_json()


# в”Ђв”Ђв”Ђ РњСѓР»СЊС‚РёС€Р°РіРѕРІС‹Р№ РґРёР°Р»РѕРі в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def handle_state(update, ctx, pid):
    uid = update.effective_user.id
    text = update.message.text
    state = USER_STATE[uid]
    action = state["action"]

    if action == "add_zam_desc":
        section, desc = ("", text)
        if ":" in text: parts=text.split(":",1); section=parts[0].strip().upper(); desc=parts[1].strip()
        USER_STATE[uid] = {"action":"add_zam_resp","data":{"desc":desc,"section":section}}
        await update.message.reply_text("рџ‘¤ РћС‚РІРµС‚СЃС‚РІРµРЅРЅС‹Р№ (РёР»Рё '-'):")
        return
    if action == "add_zam_resp":
        data = state["data"]
        resp = text if text != "-" else None
        zid = db.add_zamechaniye(pid, data["desc"], section=data.get("section"), responsible=resp)
        del USER_STATE[uid]
        db.export_dashboard_json()
        await update.message.reply_text(f"вњ… Р—Р°РјРµС‡Р°РЅРёРµ #{zid} Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°РЅРѕ!\nрџ“ќ {data['desc']}\nрџ”§ {data.get('section','вЂ”')}\nрџ‘¤ {resp or 'вЂ”'}\nР—Р°РєСЂС‹С‚СЊ: /close_zam {zid}", reply_markup=get_main_keyboard())
        return

    if action == "create_task_title":
        USER_STATE[uid] = {"action":"create_task_resp","data":{"title":text}}
        await update.message.reply_text("рџ‘¤ РћС‚РІРµС‚СЃС‚РІРµРЅРЅС‹Р№:"); return
    if action == "create_task_resp":
        state["data"]["responsible"] = text
        USER_STATE[uid] = {**state,"action":"create_task_sec"}
        await update.message.reply_text("рџ”§ Р Р°Р·РґРµР» (РђР /РљР–/РћР’РёРљ/...):"); return
    if action == "create_task_sec":
        state["data"]["section"] = text
        USER_STATE[uid] = {**state,"action":"create_task_dl"}
        await update.message.reply_text("рџ“… РЎСЂРѕРє (Р”Р”.РњРњ.Р“Р“Р“Р“ РёР»Рё '-'):"); return
    if action == "create_task_dl":
        data = state["data"]
        deadline = None
        if text != "-":
            try: deadline = datetime.strptime(text,"%d.%m.%Y").date().isoformat()
            except: await update.message.reply_text("вќЊ Р¤РѕСЂРјР°С‚: Р”Р”.РњРњ.Р“Р“Р“Р“"); return
        tid = db.add_task(pid, data["title"], data["responsible"], data["section"], deadline)
        del USER_STATE[uid]
        db.export_dashboard_json()
        api_routes.sse_push({'type':'task_update'})
        await update.message.reply_text(f"вњ… Р—Р°РґР°С‡Р° #{tid} СЃРѕР·РґР°РЅР°!\nрџ“‹ {data['title']}\nрџ‘¤ {data['responsible']}\nрџ”§ {data['section']}\nрџ“… {fmt_date(deadline)}\nР—Р°РєСЂС‹С‚СЊ: /close_task {tid}", reply_markup=get_main_keyboard())
        return

    if action == "vote_proposal":
        del USER_STATE[uid]
        await _start_vote(update, text)
        return

# в”Ђв”Ђв”Ђ Callback votes в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def callback_vote(update, ctx):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts)!=3 or parts[0]!="vote": return
    vid, choice = int(parts[1]), parts[2]
    vote = db.get_vote(vid)
    if not vote: return
    if vote["status"]=="closed": await query.answer("Р“РѕР»РѕСЃРѕРІР°РЅРёРµ Р·Р°РєСЂС‹С‚Рѕ",show_alert=True); return

    if choice == "close":
        db.close_vote(vid)
        vote = db.get_vote(vid)
        if vote["yes_count"] > vote["no_count"]:
            db.add_change(vote["project_id"], vote["proposal"], vote["author"], "Р“РѕР»РѕСЃРѕРІР°РЅРёРµ",
                          f"вњ… {vote['yes_count']} Р·Р°, вќЊ {vote['no_count']} РїСЂРѕС‚РёРІ")
        await query.edit_message_text(
            f"рџ”’ *Р“РћР›РћРЎРћР’РђРќРР• #{vid} Р—РђРљР Р«РўРћ*\n\n{vote['proposal']}\n\nвњ… {vote['yes_count']}  вќЊ {vote['no_count']}  рџ’¬ {vote['discuss_count']}\n\n{'вњ… Р РµС€РµРЅРёРµ РїСЂРёРЅСЏС‚Рѕ Рё Р·Р°РїРёСЃР°РЅРѕ РІ Р¶СѓСЂРЅР°Р»' if vote['yes_count']>vote['no_count'] else 'вќЊ Р РµС€РµРЅРёРµ РЅРµ РїСЂРёРЅСЏС‚Рѕ'}",
            parse_mode="Markdown")
        db.export_dashboard_json()
        return

    ok, _ = db.register_vote(vid, query.from_user.id, choice)
    if not ok: await query.answer("Р’С‹ СѓР¶Рµ РіРѕР»РѕСЃРѕРІР°Р»Рё!",show_alert=True); return
    vote = db.get_vote(vid)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("вњ… Р—Р°", callback_data=f"vote:{vid}:yes"),
        InlineKeyboardButton("вќЊ РџСЂРѕС‚РёРІ", callback_data=f"vote:{vid}:no"),
        InlineKeyboardButton("рџ’¬ РћР±СЃСѓРґРёС‚СЊ", callback_data=f"vote:{vid}:discuss"),
    ],[InlineKeyboardButton("рџ”’ Р—Р°РєСЂС‹С‚СЊ", callback_data=f"vote:{vid}:close")]])
    await query.edit_message_text(
        f"рџ—і *Р“РћР›РћРЎРћР’РђРќРР• #{vid}*\n\n{vote['proposal']}\n\nвњ… {vote['yes_count']}  вќЊ {vote['no_count']}  рџ’¬ {vote['discuss_count']}\n_РђРІС‚РѕСЂ: {vote['author']}_",
        parse_mode="Markdown", reply_markup=kb)

# в”Ђв”Ђв”Ђ Weekly report в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
async def _send_weekly_report(bot, chat_id):
    s = db.get_weekly_stats()
    to = db.get_tasks(status='open')
    today = datetime.now().date()
    over = [t for t in to if t.get('deadline') and datetime.fromisoformat(t['deadline'][:10]).date()<today]
    text = (f"рџ“Љ *Р•Р–Р•РќР•Р”Р•Р›Р¬РќР«Р™ РћРўР§РЃРў*\n_{datetime.now().strftime('%d.%m.%Y')}_\n\n"
            f"Р—Р°РґР°С‡Рё: рџ“Ґ {s['tasks_opened']} СЃРѕР·РґР°РЅРѕ | вњ… {s['tasks_closed']} Р·Р°РєСЂС‹С‚Рѕ | рџ”ґ {len(to)} РѕС‚РєСЂС‹С‚Рѕ | вљ пёЏ {len(over)} РїСЂРѕСЃСЂРѕС‡РµРЅРѕ\n"
            f"Р—Р°РјРµС‡Р°РЅРёСЏ: рџ“Ґ {s['zam_opened']} | вњ… {s['zam_closed']} СѓСЃС‚СЂР°РЅРµРЅРѕ\n"
            f"РР·РјРµРЅРµРЅРёР№: рџ“ќ {s['changes_added']}")
    await bot.send_message(chat_id, text, parse_mode="Markdown")
    db.export_dashboard_json()

async def scheduled_weekly_report(ctx):
    await _send_weekly_report(ctx.bot, GROUP_CHAT_ID)

# в”Ђв”Ђв”Ђ Flask в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def run_flask():
    try:
        from flask import Flask, send_from_directory
        from flask_cors import CORS
        app = Flask(__name__, static_folder="dashboard")
        app.secret_key = DASHBOARD_SECRET_KEY
        app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=False,
        )
        CORS(app, supports_credentials=True)
        app.register_blueprint(api_routes.api)

        @app.route("/")
        def index():
            return send_from_directory("dashboard telegram+html", "index.html")

        @app.route('/tg_oauth_callback')
        def tg_oauth_callback():
            # Simple callback page: reads query/hash params and POSTs them to /api/auth/telegram
            html = '''
<!doctype html>
<html><head><meta charset="utf-8"><title>Telegram OAuth Callback</title></head>
<body style="background:#0c1222;color:#e8edf5;font-family:Arial,Helvetica,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
<div style="max-width:720px;padding:1rem;border-radius:8px;background:#141d30;border:1px solid #1e2d4a;text-align:left">
    <h3 style="color:#38bdf8">Telegram OAuth Callback</h3>
    <div id="status" style="color:#7b8ba8;margin-top:.5rem">РћР±СЂР°Р±РѕС‚РєР°...</div>
    <pre id="dump" style="margin-top:.6rem;color:#e8edf5;white-space:pre-wrap;font-size:13px"></pre>
</div>
<script>
function parseParams(s){
    if(!s) return {};
    if(s.startsWith('#')) s = s.substring(1);
    if(s.startsWith('?')) s = s.substring(1);
    const params = {};
    s.split('&').forEach(p=>{ const kv=p.split('='); if(kv[0]) params[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]||''); });
    return params;
}
const qs = parseParams(location.search);
const hs = parseParams(location.hash);
const payload = Object.assign({}, qs, hs);
document.getElementById('dump').textContent = JSON.stringify(payload, null, 2);
fetch('/api/auth/telegram', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
    .then(r=>r.json()).then(j=>{
        document.getElementById('status').textContent = j.ok ? 'РђРІС‚РѕСЂРёР·Р°С†РёСЏ СѓСЃРїРµС€РЅР° вЂ” РјРѕР¶РЅРѕ Р·Р°РєСЂС‹С‚СЊ РІРєР»Р°РґРєСѓ.' : ('РћС€РёР±РєР°: '+(j.error||JSON.stringify(j)));
    }).catch(e=>{ document.getElementById('status').textContent = 'РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё РЅР° СЃРµСЂРІРµСЂ: '+e; });
</script>
</body></html>
'''
            return html

        @app.after_request
        def no_cache(r):
            r.headers['Cache-Control'] = 'no-cache'
            return r

        logger.info(f"рџЊђ Р”Р°С€Р±РѕСЂРґ: http://localhost:{DASHBOARD_PORT}")
        app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Flask error: {e}")

async def create_telegram_tab(name, telegram_id=None, topic_id=None):
    """
    РЎРѕР·РґР°С‘С‚ РЅРѕРІСѓСЋ РІРєР»Р°РґРєСѓ (topic/thread) РІ Telegram-РіСЂСѓРїРїРµ.
    Р•СЃР»Рё topic_id СѓРєР°Р·Р°РЅ вЂ” РѕР±РЅРѕРІР»СЏРµС‚ РёРјСЏ С‚РµРјС‹.
    Р•СЃР»Рё РЅРµ СѓРєР°Р·Р°РЅ вЂ” СЃРѕР·РґР°С‘С‚ РЅРѕРІСѓСЋ С‚РµРјСѓ.
    """

    app = Application.builder().token(BOT_TOKEN).build()
    chat_id = telegram_id or GROUP_CHAT_ID
    try:
        if topic_id:
            await app.bot.edit_forum_topic(
                chat_id=chat_id,
                message_thread_id=topic_id,
                name=name
            )
            return {'topic_id': topic_id, 'name': name}
        else:
            topic = await app.bot.create_forum_topic(chat_id, name)
            topic_id_created = getattr(topic, 'message_thread_id', None) or getattr(topic, 'id', None)
            logger.info(f"Создана новая тема: {topic_id_created} — {name}")
            return {'topic_id': topic_id_created, 'name': name}
    except Exception as e:
        logger.warning(f"Ошибка создания/обновления темы: {e}")
        return None
    finally:
        await app.shutdown()

# в”Ђв”Ђв”Ђ Main в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
def main():
    db.init_db()
    db.export_dashboard_json()
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    import api_routes
    api_routes.set_bot(app)

    async def post_init(application):
        api_routes.set_loop(asyncio.get_running_loop())
        logger.info("Telegram loop registered")

    app.post_init = post_init

    # в”Ђв”Ђв”Ђ Handlers Р”Рћ Р·Р°РїСѓСЃРєР° в”Ђв”Ђв”Ђ
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("deadlines", cmd_deadlines))
    app.add_handler(CommandHandler("zamechaniya", cmd_zamechaniya))
    app.add_handler(CommandHandler("add_zam", cmd_add_zam))
    app.add_handler(CommandHandler("close_zam", cmd_close_zam))
    app.add_handler(CommandHandler("create_task", cmd_create_task))
    app.add_handler(CommandHandler("close_task", cmd_close_task))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("changelog", cmd_changelog))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("weekly_report", cmd_weekly_report))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CallbackQueryHandler(callback_vote, pattern=r"^vote:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_daily(
        scheduled_weekly_report,
        time=datetime.now().replace(
            hour=WEEKLY_REPORT_HOUR,
            minute=0,
            second=0
        ).time(),
        days=(WEEKLY_REPORT_DAY,)
    )

    logger.info("рџљЂ Pearl Bot Р·Р°РїСѓС‰РµРЅ!")

    # в”Ђв”Ђв”Ђ РћРґРёРЅ РµРґРёРЅСЃС‚РІРµРЅРЅС‹Р№ Р·Р°РїСѓСЃРє в”Ђв”Ђв”Ђ
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

