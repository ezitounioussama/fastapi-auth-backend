"""Ownership tests — the security requirement of this checkpoint.

Every test here follows the same shape: Alice creates something, then Bob tries
to reach it. Bob must always fail, on every verb, and the failure must not tell
him whether the thing exists.
"""


async def test_bob_cannot_read_alices_conversation(client, alice, bob):
    """The headline test: User A's conversation is invisible to User B."""
    created = await client.post(
        "/conversations", json={"title": "Alice's private notes"}, headers=alice["headers"]
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    # Alice can read her own thread.
    as_alice = await client.get(f"/conversations/{conversation_id}", headers=alice["headers"])
    assert as_alice.status_code == 200
    assert as_alice.json()["title"] == "Alice's private notes"

    # Bob, with a perfectly valid token of his own, cannot.
    as_bob = await client.get(f"/conversations/{conversation_id}", headers=bob["headers"])
    assert as_bob.status_code == 404

    # And the body must not leak the title or any other content.
    assert "Alice's private notes" not in as_bob.text


async def test_the_refusal_is_404_not_403(client, alice, bob):
    """404 rather than 403, so Bob cannot confirm the row exists.

    A 403 would mean "this exists but is not yours", which lets an attacker walk
    the ids and map out other people's data. A 404 is indistinguishable from a
    row that was never there.
    """
    created = await client.post(
        "/conversations", json={"title": "secret"}, headers=alice["headers"]
    )
    real_id = created.json()["id"]

    existing_but_not_mine = await client.get(
        f"/conversations/{real_id}", headers=bob["headers"]
    )
    never_existed = await client.get("/conversations/999999", headers=bob["headers"])

    # Same status and same body for both cases.
    assert existing_but_not_mine.status_code == never_existed.status_code == 404
    assert existing_but_not_mine.json() == never_existed.json()


async def test_bob_cannot_post_a_message_into_alices_conversation(client, alice, bob):
    created = await client.post(
        "/conversations", json={"title": "Alice's thread"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    attempt = await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Bob writing where he should not"},
        headers=bob["headers"],
    )
    assert attempt.status_code == 404

    # Nothing may have been written.
    messages = await client.get(
        f"/conversations/{conversation_id}/messages", headers=alice["headers"]
    )
    assert messages.json() == []


async def test_bob_cannot_list_alices_messages(client, alice, bob):
    created = await client.post(
        "/conversations", json={"title": "Alice's thread"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    await client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "What is a Python list?"},
        headers=alice["headers"],
    )

    as_bob = await client.get(
        f"/conversations/{conversation_id}/messages", headers=bob["headers"]
    )
    assert as_bob.status_code == 404
    assert "Python list" not in as_bob.text


async def test_bob_cannot_delete_alices_conversation(client, alice, bob):
    """Modification is guarded by the same rule as reading."""
    created = await client.post(
        "/conversations", json={"title": "Do not delete me"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    attempt = await client.delete(
        f"/conversations/{conversation_id}", headers=bob["headers"]
    )
    assert attempt.status_code == 404

    # It must still be there for Alice.
    still_there = await client.get(
        f"/conversations/{conversation_id}", headers=alice["headers"]
    )
    assert still_there.status_code == 200


async def test_listing_shows_only_your_own_conversations(client, alice, bob):
    """The list endpoint must filter by owner, not return the whole table."""
    await client.post("/conversations", json={"title": "Alice one"}, headers=alice["headers"])
    await client.post("/conversations", json={"title": "Alice two"}, headers=alice["headers"])
    await client.post("/conversations", json={"title": "Bob one"}, headers=bob["headers"])

    alice_list = (await client.get("/conversations", headers=alice["headers"])).json()
    bob_list = (await client.get("/conversations", headers=bob["headers"])).json()

    assert len(alice_list) == 2
    assert len(bob_list) == 1

    assert {item["title"] for item in alice_list} == {"Alice one", "Alice two"}
    assert {item["title"] for item in bob_list} == {"Bob one"}

    # Every row returned belongs to the caller.
    assert all(item["user_id"] == alice["user_id"] for item in alice_list)
    assert all(item["user_id"] == bob["user_id"] for item in bob_list)


async def test_owner_id_comes_from_the_token_not_the_request(client, alice, bob):
    """Trying to set someone else's user_id in the body must not work.

    ConversationCreate has no user_id field, so the extra key is simply ignored
    and the owner is taken from the token. If the API trusted the body, anyone
    could create rows inside another account.
    """
    created = await client.post(
        "/conversations",
        json={"title": "Trying to plant this on Bob", "user_id": bob["user_id"]},
        headers=alice["headers"],
    )
    assert created.status_code == 201
    assert created.json()["user_id"] == alice["user_id"]

    # Bob's list must be empty.
    bob_list = (await client.get("/conversations", headers=bob["headers"])).json()
    assert bob_list == []


async def test_alices_token_cannot_be_reused_after_her_conversation_is_deleted(
    client, alice
):
    """Sanity check that deletion really removes the row for the owner too."""
    created = await client.post(
        "/conversations", json={"title": "Temporary"}, headers=alice["headers"]
    )
    conversation_id = created.json()["id"]

    deleted = await client.delete(
        f"/conversations/{conversation_id}", headers=alice["headers"]
    )
    assert deleted.status_code == 204

    gone = await client.get(f"/conversations/{conversation_id}", headers=alice["headers"])
    assert gone.status_code == 404
