# Security and Persistence Report

**Project:** AI Study Assistant API v2.0.0
**Date:** 13 August 2026
**Stack:** FastAPI 0.141.1, SQLAlchemy 2.0.52, SQLite, PyJWT 2.13.0, bcrypt 5.0.0

Every response and database dump quoted below was captured from a real run against the server on
`127.0.0.1:8020`, not written by hand.

---

## 1. Database schema

Three tables, in a straight chain of ownership:

```
users                    conversations                 messages
─────────                ─────────────                 ────────
id          PK  ◄──┐     id            PK  ◄──┐        id               PK
email       UNIQUE │     title                │        conversation_id  FK ──┘
hashed_password    └──── user_id       FK     └─────── role
created_at               created_at                    content
                                                       created_at
```

| Table | Column | Type | Notes |
|---|---|---|---|
| `users` | `id` | INTEGER PK | |
| | `email` | VARCHAR(255) | **UNIQUE**, indexed — the database itself blocks duplicates |
| | `hashed_password` | VARCHAR(255) | bcrypt hash. **There is no password column** |
| | `created_at` | DATETIME | UTC, timezone-aware |
| `conversations` | `id` | INTEGER PK | |
| | `title` | VARCHAR(120) | |
| | `user_id` | INTEGER FK → `users.id` | **The ownership link.** Indexed, `ON DELETE CASCADE` |
| | `created_at` | DATETIME | |
| `messages` | `id` | INTEGER PK | |
| | `conversation_id` | INTEGER FK → `conversations.id` | Indexed, `ON DELETE CASCADE` |
| | `role` | VARCHAR(20) | `"user"` or `"assistant"` |
| | `content` | TEXT | TEXT, not VARCHAR(n) — a reply has no useful length limit |
| | `created_at` | DATETIME | |

Design choices worth naming:

- **`user_id` on `conversations` is the whole security model.** Every check in the API reduces to
  "does this row's `user_id` match the id in the token".
- **Cascades are declared in both places** — SQLAlchemy's `cascade="all, delete-orphan"` and the
  FK's `ON DELETE CASCADE` — so deleting a conversation cannot leave orphaned message rows behind.
- **`email` is unique at the database level**, not just checked in Python. Two registrations
  arriving at the same instant can both pass an application-level check; only the constraint can
  settle it, and the route catches the resulting `IntegrityError` and returns the same 409.

Verified row counts after the demo session:

```
users           2 rows
conversations   1 rows
messages        2 rows      (one user turn + one assistant turn)
```

---

## 2. Authentication flow

```
   ┌── POST /auth/register ──────────────────────────────────────┐
   │  email + password                                           │
   │      ↓                                                      │
   │  bcrypt.hashpw(password, gensalt())   ← the raw password is  │
   │      ↓                                  never stored         │
   │  INSERT INTO users (email, hashed_password)                 │
   │      ↓                                                      │
   │  201 { id, email, created_at }        ← no password field    │
   └─────────────────────────────────────────────────────────────┘

   ┌── POST /auth/login ─────────────────────────────────────────┐
   │  email + password                                           │
   │      ↓                                                      │
   │  SELECT … WHERE email = ?                                   │
   │      ↓                                                      │
   │  bcrypt.checkpw(password, row.hashed_password)               │
   │      ↓ valid                                                │
   │  JWT signed with SECRET_KEY (HS256), exp = now + 60 min      │
   │      ↓                                                      │
   │  200 { access_token, token_type, expires_in_minutes, user }  │
   └─────────────────────────────────────────────────────────────┘

   ┌── any protected request ────────────────────────────────────┐
   │  Authorization: Bearer <token>                              │
   │      ↓                                                      │
   │  get_current_user()                                         │
   │    • header present?          no → 401                      │
   │    • signature + exp valid?   no → 401                      │
   │    • sub parses to an int?    no → 401                      │
   │    • user row still exists?   no → 401                      │
   │      ↓ yes                                                  │
   │  the route receives a real User object                       │
   └─────────────────────────────────────────────────────────────┘
```

### Passwords are hashed, not stored

bcrypt rather than a plain hash like SHA-256, for two reasons: it is deliberately slow, so
guessing candidates in bulk is impractical; and it salts every hash, so identical passwords
produce different stored values.

What is actually in the `users` table after registering two accounts:

```
id=1  email=alice@example.com
  stored: $2b$12$U5DzQnaG3ZUQpY9223QrCOT22Oxa5JXOGJvw/SEiV2duHys6lhJU6
id=2  email=bob@example.com
  stored: $2b$12$9Irbwex4wKBZuGolbD64ee7SOw.ZsaGhroWDb3y2aSI9xCGRGpGcy
```

And a byte-level scan of the whole `app.db` file for the passwords that were submitted:

```
raw password 'alice-password-123' present in app.db: False
raw password 'bob-password-456'   present in app.db: False
```

A test also registers two users with the *same* password and asserts the two hashes differ,
which is what proves the salting rather than assuming it.

### Login failures are deliberately indistinguishable

```
POST /auth/login  {"email": "alice@example.com", "password": "WRONG"}   → 401
{"detail":"Incorrect email or password."}

POST /auth/login  {"email": "ghost@example.com", "password": "WRONG"}   → 401
{"detail":"Incorrect email or password."}
```

Identical bodies. A message like "no such user" would let someone test a list of addresses to
discover which have accounts. The login route also runs a throwaway `verify_password` when the
email is unknown, so that path takes roughly as long as a real check — returning instantly for an
unknown email is itself a measurable signal.

### Token rejection cases, all tested

| Case | Result |
|---|---|
| No `Authorization` header | 401 |
| Token with a flipped character (broken signature) | 401 |
| Token signed with a different secret (forged) | 401 |
| Token whose `exp` is in the past | 401 |
| Valid token whose user row has since been deleted | 401 |
| `Bearer` with no value, or a non-bearer scheme | 401 |

A JWT is **signed, not encrypted** — anyone holding one can read its payload. So the payload
carries only the user id, the email and the timestamps, and nothing secret.

---

## 3. The ownership rule

One dependency enforces it, and every route that takes a `conversation_id` depends on it:

```python
def get_owned_conversation(conversation_id, current_user=Depends(get_current_user), db=...):
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    return conversation
```

Three properties matter here:

**1. The rule lives in one place.** A new endpoint that declares
`conversation: Conversation = Depends(get_owned_conversation)` is protected automatically. There
is no per-route check to forget.

**2. The owner comes from the token, never from the request.** `ConversationCreate` has no
`user_id` field, so a client cannot claim to be someone else. A test posts
`{"title": "...", "user_id": <bob's id>}` using Alice's token and asserts the row still comes
back owned by Alice, with Bob's list left empty.

**3. The refusal is 404, not 403.** This is the subtle part. A 403 means "this exists but is not
yours", which confirms the row exists — an attacker could walk `/conversations/1`,
`/conversations/2`, … and map out how much data other people have. A 404 makes "not yours" and
"never existed" indistinguishable:

```
GET /conversations/1    (Alice's real conversation, Bob's token)   → 404 {"detail":"Conversation not found."}
GET /conversations/999  (has never existed,        Bob's token)    → 404 {"detail":"Conversation not found."}
```

Same status, byte-identical body. A test asserts `response_a.json() == response_b.json()` so this
cannot regress into a helpful-but-leaky error message.

---

## 4. The test that proves private data is protected

`tests/test_ownership.py::test_bob_cannot_read_alices_conversation`

```python
async def test_bob_cannot_read_alices_conversation(client, alice, bob):
    """The headline test: User A's conversation is invisible to User B."""
    created = await client.post(
        "/conversations", json={"title": "Alice's private notes"}, headers=alice["headers"]
    )
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
```

Two details make this a real proof rather than a formality. Bob holds a **valid** token — this is
not testing anonymous access, it is testing that authentication alone is not authorisation. And
the last assertion checks the response *text*, so a leak through an unexpected field would fail
the test too.

### Confirmed live, on every verb

```
GET    /conversations/1            (Bob) → 404   Alice's conversation, unreadable
POST   /conversations/1/messages   (Bob) → 404   cannot write into it
DELETE /conversations/1            (Bob) → 404   cannot delete it
GET    /conversations              (Bob) → 200   []      ← his own list is empty
GET    /conversations/1            (Alice) → 200 "Alice private notes", 2 messages intact
```

Alice's conversation still had both its messages after Bob's delete attempt, so the refusal is
real and not a silent partial write.

The suite covers the rest of the surface too: Bob cannot list Alice's messages, the list endpoint
returns only rows belonging to the caller (2 for Alice, 1 for Bob, never 3), and all six
conversation routes return 401 with no token at all.

**Test results:** `pytest -q` → **51 passed**, no warnings.

| File | Tests | Focus |
|---|---|---|
| `tests/test_ownership.py` | 8 | cross-user isolation on read, write, delete, list |
| `tests/test_auth.py` | 19 | hashing, salting, duplicate email, login failures, six token rejections |
| `tests/test_conversations.py` | 13 | route protection, persistence of both turns, ordering, cascade |
| `tests/test_cache_and_health.py` | 11 | cache hit/miss/expiry, health, public vs protected |

The suite takes about 18 seconds, almost all of it bcrypt. That is the algorithm working as
intended — the same cost that makes a test slow makes brute-forcing impractical.

---

## 5. Cache versus database

An in-memory TTL cache sits in front of `/quiz` only. Verified working:

```
POST /quiz {"topic":"Python lists","num_questions":2}  (Alice)  → cached: false   ← computed
POST /quiz {"topic":"Python lists","num_questions":2}  (Alice)  → cached: true    ← from memory
POST /quiz {"topic":"Python lists","num_questions":2}  (Bob)    → cached: true    ← shared entry

GET /cache/stats → {"entries":1,"hits":2,"misses":1,"ttl_seconds":300}
```

### Why the cache is temporary and the database is permanent

They answer different questions, so they have different lifetimes.

| | Cache | Database |
|---|---|---|
| Answers | "have I computed this recently?" | "what belongs to this user?" |
| Lives in | process memory | a file on disk |
| Survives a restart | no | yes |
| Entry lifetime | 300 seconds, then expires | until explicitly deleted |
| Cost of losing it | one recomputation | someone's data, permanently |
| Holds | shared, derivable results | accounts, conversations, messages |

The cache is a speed optimisation for work that can always be redone. Wiping it costs nothing but
CPU. The database is the record of what happened; a lost row cannot be recreated by recomputing
anything. That difference is why user data must never live only in a cache, and why derived
results should not be permanently stored as if they were facts.

### Why conversations are deliberately not cached

**Privacy.** The quiz cache key is `quiz:<topic>:<count>` — no user id — so one entry serves
everybody. That is safe here only because a quiz for "Python lists" is identical for every user
and contains nothing personal. Caching conversations on a content-keyed, cross-user cache is
precisely how one user's private text ends up in another user's response, which would undo the
ownership rule the rest of this project enforces.

**Correctness.** A conversation changes on every turn, so a cached copy would be stale almost
immediately, and stale history is worse than slow history.

Redis would be the next step when several server processes need to share one cache. The interface
in `app/cache.py` is deliberately just `get`/`set` with a TTL, which is the same shape Redis
offers, so swapping the implementation would mean rewriting that one file and nothing else.

---

## 6. Notes and known limits

**`SECRET_KEY` must be set in production.** When it is absent the app generates a random key at
startup and prints a warning to stderr. That is intentionally inconvenient: tokens stop working on
every restart, which makes the missing setting obvious instead of shipping a hard-coded secret.

**There is no token revocation.** A JWT stays valid until it expires, so "log out everywhere"
would need either short-lived tokens plus refresh tokens, or a server-side deny list. The 60
minute expiry limits the damage window. Deleting the account does invalidate its tokens
immediately, because `get_current_user` re-reads the user row on every request.

**Passwords are truncated to 72 bytes** before hashing, because that is bcrypt's own limit —
anything past it is ignored by the algorithm regardless. Doing it explicitly makes the behaviour
visible rather than silent.

**SQLite is a single-writer database.** Fine for this project and for development; a
multi-process deployment would want PostgreSQL, which is a change to `DATABASE_URL` and nothing
else since all access goes through SQLAlchemy.

## Screenshots

| File | Shows |
|---|---|
| [`screenshots/01-swagger-overview.png`](screenshots/01-swagger-overview.png) | The Authorize button, and lock icons on all 9 protected endpoints while `/health`, `/`, `/auth/register` and `/auth/login` stay open |
| [`screenshots/02-swagger-ownership-404.png`](screenshots/02-swagger-ownership-404.png) | Bob's token in the request header, `GET /conversations/1`, and the 404 refusal |
