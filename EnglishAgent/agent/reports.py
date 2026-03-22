"""Weekly parent report generation."""


def generate_weekly_report(storage, student_id: int) -> str:
    """Generate a formatted weekly progress report for parents."""
    stats = storage.get_weekly_stats(student_id)
    student_stats = storage.get_student_stats(student_id)
    badges = storage.get_badges(student_id)

    name = stats.get("student_name", "Student")
    duration_min = int(stats["total_duration"] / 60) if stats["total_duration"] else 0
    hours = duration_min // 60
    mins = duration_min % 60

    lines = [
        f"📊 Weekly Report: {name}",
        f"{'═' * 30}",
        "",
        "📅 Study Activity (last 7 days):",
        f"  • Sessions: {stats['session_count']}",
        f"  • Study time: {hours}h {mins}m",
        f"  • Messages exchanged: {stats['total_messages']}",
        "",
        "📖 Vocabulary:",
        f"  • New words this week: {stats['new_words']}",
        f"  • Total words learned: {student_stats['vocabulary_total']}",
        f"  • Words mastered (80%+): {student_stats['vocabulary_mastered']}",
        f"  • Pending homework: {student_stats['pending_homework']} words",
        "",
        f"🎯 Level: {stats['level']} ({stats['level_score']:.0f}/100)",
    ]

    # Streak info
    if stats.get("streak"):
        lines.append(f"🔥 Current streak: {stats['streak']} days")

    # XP
    if stats.get("xp"):
        lines.append(f"⭐ Total XP: {stats['xp']}")

    # Weak grammar areas
    weak = stats.get("weak_grammar", [])
    if weak:
        lines.append("")
        lines.append("⚠ Areas to improve:")
        for g in weak[:3]:
            area = g["area"].replace("_", " ").title()
            lines.append(f"  • {area}: {g['score']:.0f}% ({g['error_count']} errors)")

    # Recent badges
    if badges:
        from agent.gamification import BADGES
        lines.append("")
        lines.append("🏆 Achievements:")
        for b in badges[:5]:
            badge_info = BADGES.get(b["badge_name"], {})
            emoji = badge_info.get("emoji", "🏅")
            name_b = badge_info.get("name", b["badge_name"])
            lines.append(f"  {emoji} {name_b}")

    # Recommendations
    lines.append("")
    lines.append("💡 Recommendations:")
    recs = _generate_recommendations(stats, student_stats)
    for r in recs:
        lines.append(f"  • {r}")

    return "\n".join(lines)


def _generate_recommendations(weekly: dict, overall: dict) -> list[str]:
    """Generate personalized recommendations based on data."""
    recs = []

    # Study frequency
    if weekly["session_count"] < 3:
        recs.append("Try to study at least 3 times per week for best results")
    elif weekly["session_count"] >= 5:
        recs.append("Great consistency! Keep up the daily practice")

    # Vocabulary
    if overall["pending_homework"] > 10:
        recs.append("There are many homework words to review — use /quiz more often")
    if overall["vocabulary_mastered"] < overall["vocabulary_total"] * 0.3:
        recs.append("Review learned words regularly — repetition helps memory")

    # Grammar
    weak = weekly.get("weak_grammar", [])
    if weak:
        worst = weak[0]
        area = worst["area"].replace("_", " ")
        recs.append(f"Focus on {area} — it's the weakest grammar area right now")

    # Fallback
    if not recs:
        recs.append("Keep practicing! Regular conversation is the best way to improve")

    return recs[:3]
