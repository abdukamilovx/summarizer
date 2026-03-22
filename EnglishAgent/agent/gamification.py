"""Gamification system: badges, XP rules, achievement checking."""

BADGES = {
    "first_lesson": {
        "name": "First Steps",
        "emoji": "🐣",
        "description": "Complete your first lesson",
    },
    "word_collector_10": {
        "name": "Word Collector",
        "emoji": "📚",
        "description": "Learn 10 words",
    },
    "word_master_50": {
        "name": "Vocabulary Master",
        "emoji": "🎓",
        "description": "Learn 50 words",
    },
    "word_legend_100": {
        "name": "Word Legend",
        "emoji": "👑",
        "description": "Learn 100 words",
    },
    "streak_3": {
        "name": "3-Day Streak",
        "emoji": "🔥",
        "description": "Study 3 days in a row",
    },
    "streak_7": {
        "name": "Week Warrior",
        "emoji": "⚡",
        "description": "Study 7 days in a row",
    },
    "streak_30": {
        "name": "Monthly Master",
        "emoji": "🏅",
        "description": "Study 30 days in a row",
    },
    "quiz_ace": {
        "name": "Quiz Ace",
        "emoji": "🏆",
        "description": "Get 100% on a quiz",
    },
    "grammar_hero": {
        "name": "Grammar Hero",
        "emoji": "📝",
        "description": "All grammar areas above 70%",
    },
    "level_a2": {
        "name": "Level Up A2",
        "emoji": "⬆️",
        "description": "Reach level A2",
    },
    "level_b1": {
        "name": "Level Up B1",
        "emoji": "🚀",
        "description": "Reach level B1",
    },
    "level_b2": {
        "name": "Level Up B2",
        "emoji": "🌟",
        "description": "Reach level B2",
    },
    "topic_explorer_5": {
        "name": "Topic Explorer",
        "emoji": "🗺️",
        "description": "Complete 5 different topics",
    },
    "topic_explorer_10": {
        "name": "Topic Master",
        "emoji": "🌍",
        "description": "Complete 10 different topics",
    },
    "chatterbox": {
        "name": "Chatterbox",
        "emoji": "💬",
        "description": "Send 100 messages total",
    },
    "early_bird": {
        "name": "Early Bird",
        "emoji": "🌅",
        "description": "Complete 10 lessons",
    },
}

XP_RULES = {
    "correct_quiz_answer": 10,
    "lesson_complete": 50,
    "new_word": 5,
    "streak_bonus": 20,
    "topic_complete": 30,
    "perfect_quiz": 100,
}


def check_badges(storage, student_id: int) -> list[str]:
    """Check all badge conditions and award new ones. Returns list of newly earned badge names."""
    newly_earned = []

    student = storage.get_student(student_id)
    if not student:
        return []

    stats = storage.get_student_stats(student_id)
    badges = {b["badge_name"] for b in storage.get_badges(student_id)}

    # Session-based badges
    if stats["session_count"] >= 1 and "first_lesson" not in badges:
        if storage.award_badge(student_id, "first_lesson"):
            newly_earned.append("first_lesson")

    if stats["session_count"] >= 10 and "early_bird" not in badges:
        if storage.award_badge(student_id, "early_bird"):
            newly_earned.append("early_bird")

    # Vocabulary badges
    if stats["vocabulary_total"] >= 10 and "word_collector_10" not in badges:
        if storage.award_badge(student_id, "word_collector_10"):
            newly_earned.append("word_collector_10")

    if stats["vocabulary_total"] >= 50 and "word_master_50" not in badges:
        if storage.award_badge(student_id, "word_master_50"):
            newly_earned.append("word_master_50")

    if stats["vocabulary_total"] >= 100 and "word_legend_100" not in badges:
        if storage.award_badge(student_id, "word_legend_100"):
            newly_earned.append("word_legend_100")

    # Streak badges
    streak = student.get("streak_days", 0)
    if streak >= 3 and "streak_3" not in badges:
        if storage.award_badge(student_id, "streak_3"):
            newly_earned.append("streak_3")

    if streak >= 7 and "streak_7" not in badges:
        if storage.award_badge(student_id, "streak_7"):
            newly_earned.append("streak_7")

    if streak >= 30 and "streak_30" not in badges:
        if storage.award_badge(student_id, "streak_30"):
            newly_earned.append("streak_30")

    # Grammar hero
    grammar = storage.get_grammar_areas(student_id)
    if grammar and all(g["score"] >= 70 for g in grammar) and "grammar_hero" not in badges:
        if storage.award_badge(student_id, "grammar_hero"):
            newly_earned.append("grammar_hero")

    # Level badges
    level = student.get("level", "A1")
    level_badges = {"A2": "level_a2", "B1": "level_b1", "B2": "level_b2"}
    levels_order = ["A1", "A2", "B1", "B2", "C1"]
    student_idx = levels_order.index(level) if level in levels_order else 0
    for l, badge_name in level_badges.items():
        l_idx = levels_order.index(l)
        if student_idx >= l_idx and badge_name not in badges:
            if storage.award_badge(student_id, badge_name):
                newly_earned.append(badge_name)

    # Topic explorer badges
    topics = storage.get_completed_topics(student_id)
    unique_topics = len({t["topic"] for t in topics})
    if unique_topics >= 5 and "topic_explorer_5" not in badges:
        if storage.award_badge(student_id, "topic_explorer_5"):
            newly_earned.append("topic_explorer_5")
    if unique_topics >= 10 and "topic_explorer_10" not in badges:
        if storage.award_badge(student_id, "topic_explorer_10"):
            newly_earned.append("topic_explorer_10")

    # Message count badge (approximate from sessions)
    sessions = storage.get_session_history(student_id, limit=100)
    total_messages = sum(s.get("message_count", 0) for s in sessions)
    if total_messages >= 100 and "chatterbox" not in badges:
        if storage.award_badge(student_id, "chatterbox"):
            newly_earned.append("chatterbox")

    return newly_earned


def format_badges(badge_names: list[str]) -> str:
    """Format badge names into emoji display string."""
    parts = []
    for name in badge_names:
        badge = BADGES.get(name)
        if badge:
            parts.append(f"{badge['emoji']} {badge['name']}")
    return " | ".join(parts) if parts else ""


def format_new_badges_message(badge_names: list[str]) -> str:
    """Format a notification about newly earned badges."""
    if not badge_names:
        return ""
    lines = ["🎉 New badges earned!"]
    for name in badge_names:
        badge = BADGES.get(name)
        if badge:
            lines.append(f"  {badge['emoji']} *{badge['name']}* — {badge['description']}")
    return "\n".join(lines)
