"""Runs inside the vessel container, once, from `house up`.

Reads the daemon's Babelr token on stdin and puts it where the Babelr organ looks
(DATA_DIR/babelr/token, mode 600). Makes the owner a vessel user and links their
Babelr username to it, so a DM from them is their chat with the daemon (links.json).
Prints one line per thing it did. Never prints the token.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True, help="the owner's Babelr username")
    args = ap.parse_args()
    token = sys.stdin.readline().strip()
    if not token:
        sys.exit("No token on stdin.")

    from config import DATA_DIR
    from users import UserManager

    base = Path(os.getenv("BABELR_DIR") or Path(DATA_DIR) / "babelr")
    base.mkdir(parents=True, exist_ok=True)
    tok = base / "token"
    tok.write_text(token + "\n")
    os.chmod(tok, 0o600)
    print(f"  The daemon's Babelr token is in place ({tok}).")

    links_path = base / "links.json"
    links = json.loads(links_path.read_text()) if links_path.exists() else {}
    um = UserManager()
    uid = links.get(args.owner)
    if not uid:
        existing = [u for u in um.list_users() if u.get("display_name") == args.owner]
        uid = existing[0]["user_id"] if existing else um.create_user(
            display_name=args.owner, relationship="primary_partner",
            notes="The person who runs this house.").user_id
        um.set_admin_status(uid, True)
        links[args.owner] = uid
        links_path.write_text(json.dumps(links, indent=2) + "\n")
        print(f"  {args.owner} is the daemon's person here; their DMs are their chat with it.")
    terms = base / "terms.json"
    if not terms.exists():
        terms.write_text("{}\n")


if __name__ == "__main__":
    main()
