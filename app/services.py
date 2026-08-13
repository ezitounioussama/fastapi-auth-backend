"""Placeholder AI logic. Deterministic Python, no model calls, no API key.

Swapping in a real model means rewriting this file and nothing else: the routers,
the database models and the auth layer all stay as they are.
"""

from datetime import datetime, timezone
from typing import List

from app.schemas import QuizQuestion

_CANNED_ANSWERS = {
    "list": (
        "A list stores several values in order under one name, written with "
        "square brackets: scores = [10, 20, 30]. You reach an item by its "
        "position, counting from 0, so scores[0] is 10."
    ),
    "variable": (
        "A variable is a name attached to a value so you can use it later, for "
        "example age = 25. Assigning again replaces the value."
    ),
    "function": (
        "A function is a named block of code you can run whenever you need it. "
        "You define it with def and it can hand back a result with return."
    ),
    "loop": (
        "A loop repeats work. A for loop walks through a collection, while a "
        "while loop keeps going until its condition stops being true."
    ),
    "dictionary": (
        "A dictionary stores key-value pairs: ages = {'Sara': 25}. You look "
        "values up by key rather than by position."
    ),
    "token": (
        "A JWT is a signed string proving who you are. The server checks the "
        "signature instead of storing a session, and the token expires."
    ),
    "database": (
        "A database stores data on disk so it survives restarts. SQLite keeps "
        "the whole thing in a single file, which suits small projects."
    ),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_assistant_reply(message: str) -> str:
    """Produce the assistant's answer for one user message.

    Falls back to an honest "not wired up yet" reply rather than inventing an
    answer, which is the same rule a real model would be given in its prompt.
    """
    lowered = message.lower()

    for keyword, answer in _CANNED_ANSWERS.items():
        if keyword in lowered:
            return answer

    return (
        "This assistant is running on placeholder logic, so there is no real "
        "answer for that yet. Known example topics: "
        + ", ".join(sorted(_CANNED_ANSWERS))
        + "."
    )


_QUESTION_TEMPLATES = [
    ("Which statement best describes {topic}?",
     ["The correct description", "A wrong description", "An unrelated idea", "None of these"]),
    ("In which situation would you use {topic}?",
     ["The appropriate situation", "A situation where it does not apply", "Never",
      "Only in other languages"]),
    ("What is a common mistake when working with {topic}?",
     ["The usual beginner mistake", "There are no mistakes possible", "Using it correctly",
      "Reading the documentation"]),
    ("Which of these is NOT true about {topic}?",
     ["The false statement", "A true statement", "Another true statement",
      "A third true statement"]),
    ("How would you explain {topic} to a beginner?",
     ["A clear simple explanation", "A confusing explanation", "By avoiding the question",
      "With unrelated jargon"]),
    ("What problem does {topic} solve?",
     ["The problem it addresses", "It solves nothing", "A different problem",
      "It creates problems"]),
    ("Which keyword is most associated with {topic}?",
     ["The related keyword", "An unrelated keyword", "No keyword", "All keywords"]),
    ("What is the main benefit of {topic}?",
     ["The main benefit", "There is no benefit", "It is slower", "It is harder"]),
    ("Where would you look up more about {topic}?",
     ["The official documentation", "Nowhere", "A random guess", "Only in videos"]),
    ("What comes right after learning {topic}?",
     ["The natural next step", "Nothing", "An unrelated topic", "Starting over"]),
]


def generate_quiz(topic: str, num_questions: int) -> List[QuizQuestion]:
    """Build placeholder quiz questions about a topic.

    The correct option is rotated through the four slots rather than always
    sitting at index 0, so a client cannot score without reading the content.
    """
    questions = []

    for index in range(num_questions):
        template, options = _QUESTION_TEMPLATES[index % len(_QUESTION_TEMPLATES)]

        correct = options[0]
        distractors = list(options[1:])
        answer_index = index % 4
        shuffled = distractors[:answer_index] + [correct] + distractors[answer_index:]

        questions.append(
            QuizQuestion(
                number=index + 1,
                question=template.format(topic=topic),
                options=shuffled,
                answer_index=answer_index,
            )
        )

    return questions
