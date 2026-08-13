"""POST /quiz — a cached, non-sensitive endpoint.

This is the cache demonstration. A quiz for a given topic is the same every
time, is not tied to any user, and contains nothing private, which makes it safe
to reuse across callers. Conversations and messages are the opposite on all
three counts, so they are never cached.
"""

from fastapi import APIRouter, Depends

from app.cache import quiz_cache
from app.dependencies import get_current_user
from app.models_db import User
from app.schemas import ErrorResponse, QuizRequest, QuizResponse
from app.services import generate_quiz, utc_now

router = APIRouter(tags=["quiz"])


@router.post(
    "/quiz",
    response_model=QuizResponse,
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
    summary="Generate a quiz (cached)",
    description=(
        "Returns quiz questions for a topic. Identical requests inside the cache "
        "window are served from memory, indicated by `cached: true`."
    ),
)
def post_quiz(
    payload: QuizRequest,
    # Requires a token, but the result does not depend on WHICH user asked —
    # that is exactly why it is safe to share one cache entry between them.
    current_user: User = Depends(get_current_user),
) -> QuizResponse:
    # The key is built from the inputs that change the output, and nothing else.
    # Putting the user id in here would give every user their own copy and defeat
    # the point; leaving it out is only safe because the answer is identical for
    # everyone and contains no personal data.
    key = f"quiz:{payload.topic.lower().strip()}:{payload.num_questions}"

    cached_questions = quiz_cache.get(key)

    if cached_questions is not None:
        return QuizResponse(
            topic=payload.topic,
            count=len(cached_questions),
            questions=cached_questions,
            cached=True,
            timestamp=utc_now(),
        )

    questions = generate_quiz(payload.topic, payload.num_questions)
    quiz_cache.set(key, questions)

    return QuizResponse(
        topic=payload.topic,
        count=len(questions),
        questions=questions,
        cached=False,
        timestamp=utc_now(),
    )


@router.get("/cache/stats", tags=["quiz"], summary="Cache statistics")
def cache_stats(current_user: User = Depends(get_current_user)) -> dict:
    """Hits, misses and current size — useful for showing the cache working."""
    return quiz_cache.stats()
