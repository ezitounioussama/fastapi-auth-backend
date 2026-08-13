"""Conversations, messages and persistence."""

from app.models_db import Conversation, Message


# --------------------------------------------------------------------------
# Protection
# --------------------------------------------------------------------------


async def test_every_conversation_route_needs_a_token(client):
    """No anonymous access anywhere in the group."""
    calls = [
        ("post", "/conversations", {"title": "x"}),
        ("get", "/conversations", None),
        ("get", "/conversations/1", None),
        ("post", "/conversations/1/messages", {"content": "hello"}),
        ("get", "/conversations/1/messages", None),
        ("delete", "/conversations/1", None),
    ]

    for method, url, body in calls:
        request = getattr(client, method)
        response = await (request(url, json=body) if body else request(url))
        assert response.status_code == 401, f"{method.upper()} {url} was not protected"


# --------------------------------------------------------------------------
# Creating and reading
# --------------------------------------------------------------------------


async def test_create_a_conversation(client, alice):
    response = await client.post(
        "/conversations", json={"title": "Learning SQL"}, headers=alice["headers"]
    )

    body = response.json()
    assert response.status_code == 201
    assert body["title"] == "Learning SQL"
    assert body["user_id"] == alice["user_id"]
    assert body["message_count"] == 0


async def test_a_new_conversation_is_stored_in_the_database(client, alice, db_session):
    await client.post(
        "/conversations", json={"title": "Persisted"}, headers=alice["headers"]
    )

    row = db_session.query(Conversation).filter(Conversation.title == "Persisted").first()
    assert row is not None
    assert row.user_id == alice["user_id"]


async def test_create_rejects_an_empty_title(client, alice):
    response = await client.post(
        "/conversations", json={"title": ""}, headers=alice["headers"]
    )
    assert response.status_code == 422


async def test_reading_a_conversation_includes_its_messages(client, alice):
    created = await client.post(
        "/conversations", json={"title": "With messages"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a variable?"},
        headers=alice["headers"],
    )

    detail = await client.get(f"/conversations/{conversation_id}", headers=alice["headers"])
    body = detail.json()

    assert detail.status_code == 200
    assert len(body["messages"]) == 2  # the question and the reply


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------


async def test_posting_a_message_saves_both_turns(client, alice):
    """The brief's requirement: store the user message AND the assistant reply."""
    created = await client.post(
        "/conversations", json={"title": "Exchange"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a Python list?"},
        headers=alice["headers"],
    )

    body = response.json()
    assert response.status_code == 201
    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["content"] == "What is a Python list?"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"]


async def test_both_turns_are_rows_in_the_database(client, alice, db_session):
    created = await client.post(
        "/conversations", json={"title": "Stored turns"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a dictionary?"},
        headers=alice["headers"],
    )

    rows = (
        db_session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .all()
    )

    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[1].role == "assistant"


async def test_the_assistant_answers_a_known_topic(client, alice):
    created = await client.post(
        "/conversations", json={"title": "Known topic"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    response = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "explain a dictionary please"},
        headers=alice["headers"],
    )

    assert "key-value" in response.json()["assistant_message"]["content"]


async def test_history_builds_up_across_turns(client, alice):
    created = await client.post(
        "/conversations", json={"title": "Several turns"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    for question in ("What is a list?", "What is a loop?", "What is a function?"):
        await client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": question},
            headers=alice["headers"],
        )

    messages = (
        await client.get(
            f"/conversations/{conversation_id}/messages", headers=alice["headers"]
        )
    ).json()

    assert len(messages) == 6  # three questions, three answers
    assert [m["role"] for m in messages] == [
        "user", "assistant", "user", "assistant", "user", "assistant"
    ]


async def test_messages_come_back_oldest_first(client, alice):
    created = await client.post(
        "/conversations", json={"title": "Order"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    for question in ("first question", "second question"):
        await client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": question},
            headers=alice["headers"],
        )

    messages = (
        await client.get(
            f"/conversations/{conversation_id}/messages", headers=alice["headers"]
        )
    ).json()

    assert messages[0]["content"] == "first question"
    assert messages[2]["content"] == "second question"
    assert [m["id"] for m in messages] == sorted(m["id"] for m in messages)


async def test_message_content_is_validated(client, alice):
    created = await client.post(
        "/conversations", json={"title": "Validation"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    for body in ({"content": ""}, {}, {"content": "x" * 2001}):
        response = await client.post(
            f"/conversations/{conversation_id}/messages",
            json=body,
            headers=alice["headers"],
        )
        assert response.status_code == 422, body


async def test_message_count_reflects_stored_messages(client, alice):
    created = await client.post(
        "/conversations", json={"title": "Counting"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a loop?"},
        headers=alice["headers"],
    )

    listing = (await client.get("/conversations", headers=alice["headers"])).json()
    assert listing[0]["message_count"] == 2


# --------------------------------------------------------------------------
# Deletion cascade
# --------------------------------------------------------------------------


async def test_deleting_a_conversation_removes_its_messages(client, alice, db_session):
    """The cascade must not leave orphan message rows behind."""
    created = await client.post(
        "/conversations", json={"title": "To delete"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a list?"},
        headers=alice["headers"],
    )

    assert db_session.query(Message).filter(
        Message.conversation_id == conversation_id
    ).count() == 2

    await client.delete(f"/conversations/{conversation_id}", headers=alice["headers"])

    assert db_session.query(Message).filter(
        Message.conversation_id == conversation_id
    ).count() == 0
