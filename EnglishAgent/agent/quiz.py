"""Vocabulary quiz engine with spaced repetition ordering."""

import json

from openai import OpenAI

from agent.prompts import QUIZ_CHECK_PROMPT, QUIZ_PROMPT


class VocabularyQuiz:
    """Tests student on ALL vocabulary from ALL previous homework assignments.

    Words are ordered by spaced repetition: lowest score first, least tested first.
    """

    def __init__(self, storage, student_id: int, api_key: str):
        self.storage = storage
        self.student_id = student_id
        self.client = OpenAI(api_key=api_key)
        self.pending_words: list[dict] = []
        self.current_word: dict | None = None
        self.results: list[dict] = []
        self.active = False
        self._current_question: str = ""

    def should_quiz(self) -> bool:
        """Check if student has vocabulary words to test."""
        words = self.storage.get_pending_homework(self.student_id)
        return len(words) > 0

    def words_count(self) -> int:
        """How many words will be in the quiz."""
        return len(self.storage.get_pending_homework(self.student_id))

    def start(self) -> str:
        """Load words, apply spaced repetition order, return first question."""
        self.pending_words = self.storage.get_pending_homework(self.student_id)
        # Sort: lowest score first (weakest), then least tested
        self.pending_words.sort(
            key=lambda w: (w.get("score", 0), w.get("times_tested", 0))
        )
        # Limit to 10 words per quiz to keep it manageable
        self.pending_words = self.pending_words[:10]
        self.active = True
        self.results = []

        total = len(self.pending_words)
        intro = f"📝 Vocabulary Quiz! ({total} words)\nLet's see how well you remember!\n\n"
        return intro + self._ask_next()

    def _ask_next(self) -> str:
        """Generate next quiz question using GPT."""
        if not self.pending_words:
            self.active = False
            return self._generate_summary()

        self.current_word = self.pending_words.pop(0)
        word = self.current_word.get("word", "")
        translation = self.current_word.get("translation_ru", "")
        question_num = len(self.results) + 1
        total = question_num + len(self.pending_words)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": QUIZ_PROMPT.format(
                            word=word, translation=translation
                        ),
                    },
                    {"role": "user", "content": "Generate the quiz question."},
                ],
                max_tokens=150,
                temperature=0.7,
            )
            question = response.choices[0].message.content.strip()
        except Exception:
            question = f'Can you use the word "{word}" in a sentence?'

        self._current_question = question
        return f"Question {question_num}/{total}:\n{question}"

    def check_answer(self, student_answer: str) -> tuple[str, bool]:
        """Check answer, update score, return (feedback_text, is_quiz_done).

        The feedback includes the next question if quiz continues.
        """
        if not self.current_word:
            return "No active question.", True

        word = self.current_word.get("word", "")

        # Use GPT to evaluate the answer
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": QUIZ_CHECK_PROMPT.format(
                            word=word, answer=student_answer
                        ),
                    },
                    {"role": "user", "content": "Evaluate this answer."},
                ],
                max_tokens=150,
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            result = json.loads(raw)
            correct = result.get("correct", False)
            feedback = result.get("feedback", "")
        except Exception:
            # Fallback: check if word appears in answer
            correct = word.lower() in student_answer.lower()
            feedback = "Good try!" if correct else f'The word was "{word}". Keep practicing!'

        # Update storage
        try:
            self.storage.update_word_score(self.student_id, word, correct)
            self.storage.mark_homework_tested(
                self.student_id, word, 1.0 if correct else 0.0
            )
        except Exception:
            pass

        self.results.append({
            "word": word,
            "correct": correct,
            "student_answer": student_answer,
        })

        # Build response
        icon = "✅" if correct else "❌"
        response_text = f"{icon} {feedback}"

        # Next question or summary
        if self.pending_words:
            response_text += "\n\n" + self._ask_next()
            return response_text, False
        else:
            self.active = False
            response_text += "\n\n" + self._generate_summary()
            return response_text, True

    def _generate_summary(self) -> str:
        """Generate quiz summary."""
        if not self.results:
            return "No questions were answered."

        correct = sum(1 for r in self.results if r["correct"])
        total = len(self.results)
        percentage = int(correct / total * 100) if total > 0 else 0

        lines = [
            f"🏆 Quiz Complete!",
            f"Score: {correct}/{total} ({percentage}%)",
        ]

        # Show wrong answers for review
        wrong = [r for r in self.results if not r["correct"]]
        if wrong:
            lines.append("\n📖 Review these words:")
            for r in wrong:
                lines.append(f"  • {r['word']}")

        if percentage >= 80:
            lines.append("\n🌟 Excellent work!")
        elif percentage >= 50:
            lines.append("\n👍 Good effort! Keep practicing!")
        else:
            lines.append("\n💪 Don't worry, practice makes perfect!")

        return "\n".join(lines)
