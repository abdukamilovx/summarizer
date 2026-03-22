"""CEFR level assessment based on vocabulary size, mastery, and grammar scores."""


class LevelAssessor:
    LEVEL_THRESHOLDS = {
        "A1": (0, 20),
        "A2": (20, 40),
        "B1": (40, 60),
        "B2": (60, 80),
        "C1": (80, 100),
    }

    LEVELS = ["A1", "A2", "B1", "B2", "C1"]

    def __init__(self, storage):
        self.storage = storage

    def assess(self, student_id: int) -> dict:
        """Calculate overall level. Returns {level, score, breakdown, progress_to_next, next_level}."""
        vocab = self.storage.get_vocabulary(student_id)
        grammar = self.storage.get_grammar_areas(student_id)

        # Factor 1: Vocabulary size (max 40 pts, 80 words = full)
        vocab_score = min(40, len(vocab) * 0.5)

        # Factor 2: Average vocabulary mastery (max 20 pts)
        if vocab:
            avg_word_score = sum(v["score"] for v in vocab) / len(vocab)
            mastery_score = avg_word_score * 0.2
        else:
            mastery_score = 0

        # Factor 3: Grammar score (max 40 pts)
        if grammar:
            avg_grammar = sum(g["score"] for g in grammar) / len(grammar)
            grammar_score = avg_grammar * 0.4
        else:
            grammar_score = 20  # neutral default

        total = vocab_score + mastery_score + grammar_score
        level = self._score_to_level(total)
        next_level = self._next_level(level)

        # Calculate progress to next level
        low, _ = self.LEVEL_THRESHOLDS[level]
        if next_level:
            next_low, _ = self.LEVEL_THRESHOLDS[next_level]
            range_size = next_low - low
            progress = int((total - low) / range_size * 100) if range_size > 0 else 100
        else:
            progress = 100

        # Update storage
        try:
            self.storage.update_student_level(student_id, level, total)
        except Exception:
            pass

        return {
            "level": level,
            "score": round(total, 1),
            "progress_to_next": min(100, max(0, progress)),
            "next_level": next_level,
            "breakdown": {
                "vocabulary_size": round(vocab_score, 1),
                "vocabulary_mastery": round(mastery_score, 1),
                "grammar": round(grammar_score, 1),
            },
            "vocab_count": len(vocab),
            "grammar_areas": len(grammar),
        }

    def _score_to_level(self, score: float) -> str:
        for level in reversed(self.LEVELS):
            low, _ = self.LEVEL_THRESHOLDS[level]
            if score >= low:
                return level
        return "A1"

    def _next_level(self, level: str) -> str | None:
        idx = self.LEVELS.index(level)
        if idx < len(self.LEVELS) - 1:
            return self.LEVELS[idx + 1]
        return None

    def format_report(self, student_id: int) -> str:
        """Format a human-readable level report."""
        result = self.assess(student_id)
        student = self.storage.get_student(student_id)
        name = student.get("name", "Student") if student else "Student"

        lines = [
            f"📊 Level Report for {name}",
            f"",
            f"🎯 Level: {result['level']} ({result['score']:.0f}/100)",
        ]

        if result["next_level"]:
            lines.append(f"📈 Progress to {result['next_level']}: {result['progress_to_next']}%")
            bar_filled = result["progress_to_next"] // 5
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            lines.append(f"    [{bar}]")

        b = result["breakdown"]
        lines.extend([
            f"",
            f"📋 Breakdown:",
            f"  Vocabulary size: {b['vocabulary_size']:.0f}/40 ({result['vocab_count']} words)",
            f"  Word mastery: {b['vocabulary_mastery']:.0f}/20",
            f"  Grammar: {b['grammar']:.0f}/40",
        ])

        # Show weak grammar areas
        weak = self.storage.get_weakest_grammar(student_id, limit=3)
        if weak:
            lines.append(f"\n⚠ Weakest areas:")
            for w in weak:
                lines.append(f"  • {w['area']}: {w['score']:.0f}/100 ({w['error_count']} errors)")

        return "\n".join(lines)
