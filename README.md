# AI Study Assistant API — Auth & Persistence

A FastAPI backend where users register, log in, and keep **private** conversations saved in a
database. One user can never read or modify another user's data.

Assistant replies come from placeholder logic (deterministic Python, no model calls). Only
`app/services.py` would change to connect a real model — the auth and database layers are
independent of it.

## What it does

- **Register** with an email and password → only a bcrypt hash is stored
- **Log in** → receive a JWT access token
- **Create conversations** and **post messages**, all owned by the account that made them
- **Both turns are saved**: the user's message and the assistant's reply become separate rows
- **Ownership is enforced** on every read and write, with a 404 that does not reveal existence
- **An in-memory TTL cache** in front of the non-sensitive `/quiz` endpoint

## Project structure

```
fastapi-auth-backend/
├── app/
│   ├── main.py            app, routers, lifespan (creates tables)
│   ├── config.py          settings, limits, SECRET_KEY handling
│   ├── database.py        engine, session, get_db dependency
│   ├── models_db.py       SQLAlchemy tables: User, Conversation, Message
│   ├── schemas.py         Pydantic request/response models
│   ├── security.py        bcrypt hashing, JWT encode/decode
│   ├── dependencies.py    get_current_user, get_owned_conversation
│   ├── cache.py           TTL cache + why cache ≠ database
│   ├── services.py        placeholder AI logic
│   └── routers/           health, auth, conversations, quiz
├── tests/                 51 tests (pytest + httpx)
├── docs/
│   ├── security-persistence-report.md
│   └── screenshots/
├── main.py                run the server
├── .env.example
└── requirements.txt
```

## Setup

```bash
git clone https://github.com/ezitounioussama/fastapi-auth-backend.git
cd fastapi-auth-backend

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # paste into SECRET_KEY
```

`SECRET_KEY` is what signs the tokens — anyone holding it can mint a token for any account, so it
must never be committed. `.env` and `*.db` are both in `.gitignore`. If you skip this step the app
still runs, but it generates a random key at startup and warns you, and tokens stop working on
every restart.

## Running it

```bash
python main.py            # or: uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- The database file `app.db` is created automatically on first run.

### Trying it in Swagger UI

1. `POST /auth/register` — pick an email and password
2. `POST /auth/login` — copy the `access_token` from the response
3. Click **Authorize** (top right) and paste the token
4. The `/conversations` endpoints are now usable

## Testing

```bash
pytest -q      # 51 passed
```

Each test gets its own in-memory SQLite database, so nothing touches `app.db`. Expect ~18 seconds:
almost all of it is bcrypt being deliberately slow, which is the same property that makes password
cracking impractical.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | Index |
| GET | `/health` | — | Status, version, database reachability |
| POST | `/auth/register` | — | Create an account |
| POST | `/auth/login` | — | Get a JWT |
| GET | `/auth/me` | **token** | The current account |
| POST | `/conversations` | **token** | Start a conversation |
| GET | `/conversations` | **token** | List *my* conversations |
| GET | `/conversations/{id}` | **token + owner** | Read one, with messages |
| DELETE | `/conversations/{id}` | **token + owner** | Delete one, and its messages |
| POST | `/conversations/{id}/messages` | **token + owner** | Add a message, get a reply |
| GET | `/conversations/{id}/messages` | **token + owner** | List the messages |
| POST | `/quiz` | **token** | Generate a quiz (cached) |
| GET | `/cache/stats` | **token** | Cache hits, misses, size |

## Walkthrough with curl

```bash
# 1. Register
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"alice-password-123"}'
# → 201 {"id":1,"email":"alice@example.com","created_at":"..."}

# 2. Log in and keep the token
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"alice-password-123"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 3. Start a conversation
curl -X POST localhost:8000/conversations -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"title":"Learning Python"}'
# → 201 {"id":1,"title":"Learning Python","user_id":1,"message_count":0,...}

# 4. Post a message — both turns are stored
curl -X POST localhost:8000/conversations/1/messages -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"What is a Python list?"}'
```

```json
{
  "conversation_id": 1,
  "user_message": {
    "id": 1, "conversation_id": 1, "role": "user",
    "content": "What is a Python list?", "created_at": "2026-08-13T18:06:40.233201"
  },
  "assistant_message": {
    "id": 2, "conversation_id": 1, "role": "assistant",
    "content": "A list stores several values in order under one name, written with square brackets: scores = [10, 20, 30]. You reach an item by its position, counting from 0, so scores[0] is 10.",
    "created_at": "2026-08-13T18:06:40.233216"
  }
}
```

## Security summary

**Passwords** are hashed with bcrypt and never stored or returned. A byte scan of `app.db`
confirms the submitted passwords appear nowhere in the file, and two users with the same password
get different hashes — proof the salting works.

**Tokens** are JWTs signed with HS256 and expire after 60 minutes. Six rejection cases are tested:
missing header, tampered signature, forged signature, expired, deleted user, malformed header.

**Ownership** is one dependency, `get_owned_conversation`, that every id-taking route depends on —
so a new endpoint cannot forget the check. The owner is always taken from the token, never from
the request body.

**The refusal is 404, not 403.** A 403 would confirm that a conversation exists and belongs to
someone else, letting an attacker enumerate ids to map other people's data. With a 404, "not
yours" and "never existed" return byte-identical responses:

```
GET /conversations/1    (Bob's token, Alice's conversation) → 404 {"detail":"Conversation not found."}
GET /conversations/999  (Bob's token, nonexistent)          → 404 {"detail":"Conversation not found."}
```

**Login failures** are also identical for a wrong password and an unknown email, so account
addresses cannot be discovered by probing.

## Cache versus database

| | Cache | Database |
|---|---|---|
| Question it answers | "computed this recently?" | "what belongs to this user?" |
| Storage | process memory | file on disk |
| Survives restart | no | yes |
| Entry lifetime | 300s, then expires | until deleted |
| Cost of losing it | a recomputation | someone's data, permanently |

`/quiz` is cached because the result depends only on the topic, is identical for every user, and
holds nothing private — verified by Bob getting `cached: true` from an entry Alice created.
Conversations are **never** cached: they are user-owned, and a cross-user content-keyed cache is
exactly how one person's private text leaks into another's response.

## Full report

[`docs/security-persistence-report.md`](docs/security-persistence-report.md) has the schema
diagram, the auth flow, the ownership rule with the test that proves it, live captured output for
every endpoint, and the known limits (no token revocation, SQLite single-writer).

---

Author: **Oussama Ezitouni**
