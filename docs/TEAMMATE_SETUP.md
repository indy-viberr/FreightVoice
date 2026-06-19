# Running FreightVoice on your own laptop

For a teammate who's cloning/pulling the repo on a different machine (e.g. to run
the live demo). The code travels through git; **credentials and the venv do
not** (`.insforge/project.json`, `.venv/`, and `.env` are all gitignored), so
there's a little local setup.

## Quickest path — SQLite (zero accounts)

```bash
git pull
make demo          # creates the venv on first run, boots both services
```
Open **http://127.0.0.1:5000** for the dashboard. In another terminal: `make simulate`.

That's the whole demo, running on a local SQLite TMS. No credentials needed.

## Running it on InsForge (the live sponsor backend)

You need two values from a teammate who set up the InsForge project (they're not
in git):

- **`FAKETMS_INSFORGE_URL`** — `https://5muhwi7r.us-west.insforge.app` (not secret)
- **`FAKETMS_INSFORGE_TOKEN`** — the `ik_…` project API key (secret — get it
  directly from a teammate; never commit it)

Create a **`.env`** file in the project root (it's gitignored, and `run.sh`
auto-loads it):

```bash
cat > .env <<'EOF'
FAKETMS_STORAGE=insforge
FAKETMS_INSFORGE_URL=https://5muhwi7r.us-west.insforge.app
FAKETMS_INSFORGE_TOKEN=ik_paste_the_real_token_here
EOF
```

Verify, then run:

```bash
./.venv/bin/python scripts/check_insforge.py     # expect: ✓ InsForge is working
make demo                                         # run.sh prints "▸ loading .env"
```

The tables already exist in the shared InsForge project, so there's nothing to
create — you're pointing at the same database the rest of the team uses.

## Two heads-ups

- **One shared InsForge project.** Booting faketms runs `init(reset=True)`,
  which wipes and reseeds the shared `loads`/`pods`/`discrepancies` tables. So
  **only one person boots the InsForge demo at a time** — otherwise you reset
  each other mid-run. (SQLite is per-machine, so no such conflict there.)
- **Fallback on stage:** if the network or creds get fiddly, delete/rename
  `.env` (or set `FAKETMS_STORAGE=sqlite`) and `make demo` runs on SQLite. The
  demo still works; it just isn't persisting to InsForge.

## What each piece is

| You'll run on the laptop | Why |
|---|---|
| `git pull` | get the code |
| `make demo` (first run) | auto-creates `.venv` + installs deps |
| `.env` with InsForge creds | `run.sh` auto-loads it; points the TMS at InsForge |
| `scripts/check_insforge.py` | confirms URL + token + tables before the demo |

For the voice side (Vapi) and the LLM (Nebius), see
[`VAPI_SETUP.md`](VAPI_SETUP.md) — those are configured in the Vapi dashboard,
not on the laptop.
