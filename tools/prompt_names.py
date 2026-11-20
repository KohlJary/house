"""Build a house's chat system prompt (no model call) and show every line naming someone
from the house this came from. Run inside the vessel container:
  docker compose exec -T vessel python /house/tools/prompt_names.py --owner <username>
Exit 1 if any such line is found."""
import argparse, json, os, re, sys
from pathlib import Path
sys.path.insert(0, "/app/backend")

NAMES = re.compile(r"\b(Cass|Cassandra|Kohl|Kohlbern|RoboKohl|Daedalus|Chapter House|Solenne|Hearthweave)\b")

ap = argparse.ArgumentParser(); ap.add_argument("--owner", required=True); ap.add_argument("--show", action="store_true")
a = ap.parse_args()
from config import DATA_DIR
from database.daemon import get_daemon_id, get_daemon_entity_name
from users import UserManager
from conversations import ConversationManager
from memory import ThreadManager, OpenQuestionManager
from continuous_context import build_continuous_context
links = json.loads((Path(os.getenv("BABELR_DIR") or Path(DATA_DIR) / "babelr") .joinpath("links.json").read_text()))
did = get_daemon_id()
name = get_daemon_entity_name(did)
ctx = build_continuous_context(user_id=links[a.owner], conversation_id=None, user_manager=UserManager(),
                               thread_manager=ThreadManager(did), question_manager=OpenQuestionManager(did),
                               conversation_manager=ConversationManager(), daemon_name=name, daemon_id=did)
p = ctx.system_prompt
if a.show:
    print(p)
hits = [(i, l) for i, l in enumerate(p.splitlines(), 1) if NAMES.search(l)]
print(f"daemon: {name}; prompt: {len(p)} chars; lines naming the old house: {len(hits)}")
for i, l in hits:
    print(f"{i:4}: {l[:220]}")
sys.exit(1 if hits else 0)
