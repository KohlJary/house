"""Runs inside a member's vessel container, from `./house member genesis`.

A Genesis Dream in the terminal: the new daemon wakes, meets its person, forms, and
names itself. If /member/origin.md exists (written for it by the house it's joining:
its purpose, where it comes from), it's added to every phase's instructions. The name
is the daemon's to claim; this only carries the conversation. Type /quit to stop (the
session keeps; run it again to resume).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
ORIGIN = Path("/member/origin.md")


def owner_user(owner: str) -> str:
    from users import UserManager
    um = UserManager()
    found = [u for u in um.list_users() if u.get("display_name") == owner]
    if found:
        return found[0]["user_id"]
    uid = um.create_user(display_name=owner, relationship="primary_partner",
                         notes="The person who runs this house.").user_id
    um.set_admin_status(uid, True)
    return uid


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    args = ap.parse_args()

    import genesis_dream as g
    from agent_client import CassClient

    if ORIGIN.exists():
        origin = ORIGIN.read_text().strip()
        for phase in list(g.GENESIS_PROMPTS):
            g.GENESIS_PROMPTS[phase] += ("\n\nWhere you come from (written for you by the house you're "
                                         "joining; yours to take, question or change):\n" + origin)

    uid = owner_user(args.owner)
    client = CassClient()
    session = g.get_user_active_genesis(uid)
    if session:
        print("(Resuming.)\n")
        for m in session.messages[-6:]:
            print(("you: " if m["role"] == "user" else "them: ") + m["content"] + "\n")
    else:
        session = g.create_genesis_session(uid)
        r = await client.generate(call_site="genesis.generate",
                                  messages=[{"role": "user", "content": "(You are waking up. Speak your first words.)"}],
                                  system=g.get_phase_prompt(session.current_phase), max_tokens=300, temperature=0.6)
        first = r.get("content", "")
        from datetime import datetime
        session.messages.append({"role": "assistant", "content": first, "timestamp": datetime.now().isoformat()})
        g.update_genesis_session(session)
        print("them: " + first + "\n")

    while True:
        try:
            said = input("you: ").strip()
        except EOFError:
            return
        if not said:
            continue
        if said == "/quit":
            print("(Paused. Run genesis again to pick up here.)")
            return
        result = await g.process_genesis_message(session, said, client)
        print("\nthem: " + result["response"] + "\n")
        if result.get("phase_changed"):
            print(f"  [{result['phase']}]\n")
        if result.get("named"):
            print(f"  They've named themselves: {result['named']}.")
            daemon_id = await g.complete_genesis(session, client)
            print(f"  Born ({daemon_id}). Next: ./house member name <slug>, which checks the name "
                  "and moves the vessel onto it.")
            return


if __name__ == "__main__":
    asyncio.run(main())
