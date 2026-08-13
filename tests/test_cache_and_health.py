"""The cache demonstration, health check and index route."""

from app.cache import TTLCache


async def test_health_is_public_and_reports_the_database(client):
    response = await client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["version"]
    assert body["timestamp"]


async def test_index_lists_public_and_protected_endpoints(client):
    body = (await client.get("/")).json()

    assert "/auth/login" in body["public_endpoints"]
    assert "/conversations" in body["protected_endpoints"]


async def test_quiz_requires_a_token(client):
    response = await client.post("/quiz", json={"topic": "Python", "num_questions": 3})
    assert response.status_code == 401


async def test_first_quiz_request_is_a_miss_and_the_second_is_a_hit(client, alice):
    """The cache demonstration: identical requests are served from memory."""
    payload = {"topic": "Python lists", "num_questions": 3}

    first = await client.post("/quiz", json=payload, headers=alice["headers"])
    second = await client.post("/quiz", json=payload, headers=alice["headers"])

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True

    # Same content either way — the cache must not change the answer.
    assert first.json()["questions"] == second.json()["questions"]


async def test_a_different_topic_is_a_separate_cache_entry(client, alice):
    await client.post(
        "/quiz", json={"topic": "lists", "num_questions": 3}, headers=alice["headers"]
    )
    other = await client.post(
        "/quiz", json={"topic": "loops", "num_questions": 3}, headers=alice["headers"]
    )

    assert other.json()["cached"] is False


async def test_a_different_question_count_is_a_separate_entry(client, alice):
    await client.post(
        "/quiz", json={"topic": "lists", "num_questions": 3}, headers=alice["headers"]
    )
    other = await client.post(
        "/quiz", json={"topic": "lists", "num_questions": 5}, headers=alice["headers"]
    )

    assert other.json()["cached"] is False
    assert other.json()["count"] == 5


async def test_the_cache_is_shared_between_users(client, alice, bob):
    """Safe here precisely because the result is identical for everyone.

    A quiz depends only on the topic, holds no personal data, and is not owned by
    anyone. That is why one entry can serve both users — and why conversations,
    which fail all three tests, are never cached.
    """
    payload = {"topic": "shared topic", "num_questions": 2}

    alice_first = await client.post("/quiz", json=payload, headers=alice["headers"])
    bob_second = await client.post("/quiz", json=payload, headers=bob["headers"])

    assert alice_first.json()["cached"] is False
    assert bob_second.json()["cached"] is True


async def test_cache_stats_report_hits_and_misses(client, alice):
    payload = {"topic": "stats topic", "num_questions": 2}

    await client.post("/quiz", json=payload, headers=alice["headers"])   # miss
    await client.post("/quiz", json=payload, headers=alice["headers"])   # hit

    stats = (await client.get("/cache/stats", headers=alice["headers"])).json()

    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["entries"] >= 1


def test_cache_entries_expire():
    """Directly tested with a zero-second TTL, so no waiting is required."""
    cache = TTLCache(ttl_seconds=0)

    cache.set("key", "value")

    # With a TTL of zero the entry is already stale when it is read back.
    assert cache.get("key") is None
    assert cache.misses == 1


def test_cache_returns_what_was_stored():
    cache = TTLCache(ttl_seconds=60)

    cache.set("key", [1, 2, 3])

    assert cache.get("key") == [1, 2, 3]
    assert cache.hits == 1


def test_cache_clear_empties_it():
    cache = TTLCache(ttl_seconds=60)
    cache.set("a", 1)

    cache.clear()

    assert cache.get("a") is None
    assert cache.stats()["entries"] == 0
