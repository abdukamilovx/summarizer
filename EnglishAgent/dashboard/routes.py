"""Dashboard API routes and WebSocket endpoint."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Set by server.py at startup
analytics_hub = None
storage = None


@router.get("/", response_class=HTMLResponse)
async def dashboard_page():
    template = Path(__file__).parent / "templates" / "dashboard.html"
    return HTMLResponse(template.read_text(encoding="utf-8"))


@router.get("/api/sessions")
async def get_sessions():
    if analytics_hub is None:
        return []
    return analytics_hub.get_all_sessions()


@router.get("/api/students")
async def get_students():
    """Get all students with stats."""
    if storage is None:
        return []
    students = storage.get_all_students()
    result = []
    for s in students:
        stats = storage.get_student_stats(s["student_id"])
        result.append({**s, **stats})
    return result


@router.get("/api/students/{student_id}/grammar")
async def get_student_grammar(student_id: int):
    """Get grammar areas for a student."""
    if storage is None:
        return []
    return storage.get_grammar_areas(student_id)


@router.get("/api/students/{student_id}/vocabulary")
async def get_student_vocabulary(student_id: int):
    """Get vocabulary list for a student."""
    if storage is None:
        return []
    return storage.get_vocabulary(student_id)


@router.get("/api/students/{student_id}/progress")
async def get_student_progress(student_id: int):
    """Get session history and level progress."""
    if storage is None:
        return {"sessions": [], "level": "A1", "level_score": 0}
    student = storage.get_student(student_id)
    sessions = storage.get_session_history(student_id)
    return {
        "level": student["level"] if student else "A1",
        "level_score": student["level_score"] if student else 0,
        "sessions": sessions,
    }


@router.get("/api/students/{student_id}/topics")
async def get_student_topics(student_id: int):
    """Get completed topics for a student."""
    if storage is None:
        return []
    return storage.get_completed_topics(student_id)


@router.get("/api/students/{student_id}/pronunciation")
async def get_student_pronunciation(student_id: int):
    """Get pronunciation stats for a student."""
    if storage is None:
        return []
    return storage.get_pronunciation_stats(student_id)


@router.get("/api/students/{student_id}/badges")
async def get_student_badges(student_id: int):
    """Get badges for a student."""
    if storage is None:
        return []
    return storage.get_badges(student_id)


@router.get("/api/leaderboard")
async def get_leaderboard():
    """Get top students by XP."""
    if storage is None:
        return []
    return storage.get_leaderboard(limit=20)


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket):
    if analytics_hub is None:
        await websocket.close()
        return

    await websocket.accept()
    queue = analytics_hub.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        analytics_hub.unsubscribe(queue)
