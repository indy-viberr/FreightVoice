#!/usr/bin/env python3
"""
InsForge connectivity smoke test.

Answers "is InsForge actually working?" before you point the demo at it. Checks,
in order: env config -> reachable -> auth OK -> the three tables exist. Read-only
by default; pass --seed to (re)seed the three demo loads through the real
InsForgeStore code path.

Usage:
    export FAKETMS_INSFORGE_URL=http://localhost:7130        # or https://<app>.insforge.app
    export FAKETMS_INSFORGE_TOKEN=your-insforge-bearer-token
    python scripts/check_insforge.py
    python scripts/check_insforge.py --seed      # also reseed loads/pods/discrepancies
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

URL = os.environ.get("FAKETMS_INSFORGE_URL", "http://localhost:7130").rstrip("/")
TOKEN = os.environ.get("FAKETMS_INSFORGE_TOKEN", "")
TABLES = ("loads", "pods", "discrepancies")

OK, BAD, INFO = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[2m·\033[0m"


def _records_url(table: str) -> str:
    return f"{URL}/api/database/records/{table}"


def check_table(table: str) -> bool:
    """One table: reachable, authorized, exists. Prints a specific diagnosis."""
    try:
        r = requests.get(_records_url(table),
                         headers={"Authorization": f"Bearer {TOKEN}"},
                         params={"limit": 1}, timeout=8)
    except requests.ConnectionError:
        print(f"  {BAD} {table}: cannot reach {URL} — is InsForge running at that URL?")
        return False
    except requests.RequestException as e:
        print(f"  {BAD} {table}: request failed — {type(e).__name__}")
        return False

    if r.status_code in (401, 403):
        print(f"  {BAD} {table}: auth rejected (HTTP {r.status_code}) — check FAKETMS_INSFORGE_TOKEN")
        return False
    if r.status_code == 404:
        print(f"  {BAD} {table}: table not found (HTTP 404) — run the DDL in docs/SPONSORS.md")
        return False
    if r.status_code >= 400:
        print(f"  {BAD} {table}: HTTP {r.status_code} — {r.text[:120]}")
        return False

    # 200: count rows for a friendly signal.
    try:
        rows = r.json() or []
    except ValueError:
        rows = []
    print(f"  {OK} {table}: reachable, authorized, exists")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true",
                    help="(re)seed demo data via InsForgeStore after the checks pass")
    args = ap.parse_args()

    print(f"\nInsForge check  →  {URL}")
    print(f"  {OK if TOKEN else BAD} token: "
          f"{'set (' + str(len(TOKEN)) + ' chars)' if TOKEN else 'MISSING — export FAKETMS_INSFORGE_TOKEN'}")
    if not TOKEN:
        print("\nSet the token and re-run.\n")
        return 1

    print(f"  {INFO} checking tables…")
    results = [check_table(t) for t in TABLES]
    if not all(results):
        print("\nNot ready. Fix the ✗ items above (DDL is in docs/SPONSORS.md).\n")
        return 1

    if args.seed:
        # Exercise the real integration end to end.
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from faketms.stores.insforge_store import InsForgeStore

        store = InsForgeStore()
        store.init(reset=True)
        state = store.dump_state()
        print(f"  {OK} seeded via InsForgeStore: {len(state['loads'])} loads "
              f"({', '.join(l['load_id'] for l in state['loads'])})")

    print(f"\n{OK} InsForge is working. "
          f"Run the demo with FAKETMS_STORAGE=insforge.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
