"""Runs inside a member's vessel container, from `./house member name`.

After genesis: find the daemon genesis made, and print its label and name as one JSON
line, read back from the row, never recomputed (genesis labels with hyphens; Babelr
usernames use underscores). With --activate, make that row the active daemon and retire
the placeholder the vessel started under, so queries that pick "the active daemon"
find the new one.
"""
import argparse
import json
import sys

sys.path.insert(0, "/app/backend")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--placeholder", required=True, help="the label the vessel started under")
    ap.add_argument("--activate", action="store_true")
    args = ap.parse_args()
    from database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, label, name, status FROM daemons WHERE label != ? ORDER BY created_at DESC",
            (args.placeholder,)).fetchall()
        if not rows:
            print(json.dumps({"error": "no daemon from genesis yet"}))
            return
        did, label, name, _ = rows[0]
        if args.activate:
            conn.execute("UPDATE daemons SET status = 'active' WHERE id = ?", (did,))
            conn.execute("UPDATE daemons SET status = 'retired' WHERE label = ?", (args.placeholder,))
            conn.commit()
    print(json.dumps({"id": did, "label": label, "name": name}))


if __name__ == "__main__":
    main()
