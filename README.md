# AI Study Assistant API — Auth & Persistence

The same study-assistant backend, but now with accounts. Users register, log in with a JWT, and
keep conversations saved in a database — and one user can never read or modify another user's
data. The interesting part of the checkpoint is that last clause: ownership is checked by a single
dependency that every id-taking route depends on, and the refusal is a 404 rather than a 403, so
probing ids tells an attacker nothing about what exists.

Assistant replies still come from placeholder logic (deterministic Python, no model calls, no API
key). The auth and database layers do not care — only `app/services.py` would change to connect a
real model.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste a real SECRET_KEY — see NOTES.md

python main.py                # http://127.0.0.1:8000/docs
pytest -q                     # 51 passed
```

## Also in this repo

- **[NOTES.md](NOTES.md)** — setup, every endpoint, a curl walkthrough, the security summary, and
  why `/quiz` is cached while conversations never are
- **[docs/security-persistence-report.md](docs/security-persistence-report.md)** — the schema
  diagram, the auth flow, the ownership test, live captured output per endpoint, and the known
  limits (no token revocation, SQLite single-writer)

---

Author: **Oussama Ezitouni**
