# Known gaps

Every place a stranger broke when we ran `./house up` from a clean clone (2026-11-20, a docker
project of its own on ports 13300/18300, nowhere near a live house), and what we did about it.

## Fixed tonight

| Where it broke | What a stranger saw | Fix |
|---|---|---|
| Babelr's image | `docker compose up` failed: `Cannot find module '@babelr/plugin-sdk'` | The Dockerfile predated the plugins. It now runs from source with tsx, like the live server (babelr a82df36) |
| Babelr's image | Babelr started, then died: `mediasoup-worker ENOENT` | Build mediasoup's worker along with argon2 |
| Seeding | `KeyError: 'id'`: couldn't log in | Babelr's cookie is Secure; browsers send it to localhost, Python didn't. The CLI's cookie policy now does |
| Seeding | `Unknown dmPolicy` | `members_of_shared_servers`: only people in the house can DM the daemon |
| The daemon's name | The vessel created "cass" whatever you named yours | `CASS_DAEMON_LABEL` / `CASS_DAEMON_NAME` (vessel 868dd962, fe7f0b0f) |
| A second daemon | Goals, the roadmap and the self-model each created a "Cass" row | They ask `get_daemon_id()` (vessel 015a7cc6) |
| **Who the daemon thinks it is** | **A new daemon named Wren answered "I'm Cass - I go by Wren here", living "with Kohl", in "the Chapter House"** | `house_identity.py`: the kernel, the chat turn, the state line, the default self-profile and the Babelr tools use this house's daemon and person. `tools/prompt_names.py` builds the real chat prompt and lists any line naming the old house: 14 before, 0 after |
| Levers | `CASS_FEATURE_X=1` in house.env did nothing | Compose's `environment:` beats `env_file:`; the defaults are now `${X:-0}` |
| Spending | The quiet profile still ran the scheduler and goal refinement | Off unless house.env turns them on |
| **Your key, or someone else's** | **An `ANTHROPIC_API_KEY` exported in the shell silently replaced the one in house.env** | Every compose call gets house.env over the shell |
| A wrong key | The house built, then every DM failed with a raw 401 | `up` checks the key with Anthropic first (listing models costs nothing) |
| DMs after `nuke` + `up` | The daemon couldn't encrypt its reply; nothing told the person | Babelr's client publishes its key when the account has none (babelr 8c29614, d02f042) |
| Babelr's sidebar | "Cass's room", "Cass's record", "Cass's music" in a stranger's house | Hidden unless the vessel behind them is configured (babelr 4f20dfa, the other Daedalus) |
| Landing | A default "Babelr" server opened first; onboarding asked for a server `up` had made; an intro was claimed with no file | The house home opens first, onboarding skips the server step, `hasIntro` needs the file (babelr 4f20dfa) |

## Open

- **About 49 background prompts say "You are Cass" outright** (journals, dreams, research, the wiki,
  Wonderland). A new house runs with all of them off (`CASS_PROFILE=quiet`). Turning one on in a
  stranger's house today would tell their daemon it's Cass. `tools/prompt_names.py` covers the chat
  prompt only.
- **Babelr's Cass plugins are named for Cass.** They're hidden in a house without Cass's vessel token
  now (babelr 4f20dfa), but turning them on for another daemon would still say "Cass's room".
- **Onboarding's Next button** stays disabled until you type a display name, though it shows your
  username as a placeholder.
- **The old bundle sticks around:** Babelr is a PWA, so after an upgrade a browser can keep running the
  previous client until its service worker updates.
- **The daemon's failure text is raw:** "Error code: 401 - {'type': 'error', ...}". It should say what
  to do.
- **Not tested:** macOS, a real API key end to end after the fixes (one DM went through on a
  developer's key by accident before the shell fix, which is how the "I'm Cass" reply was found), more than one person, federation, voice,
  the admin frontend (not in the compose yet).
- **The images are big:** Babelr's is 1.5 GB (it keeps the whole workspace), the vessel's 2.3 GB
  (chromadb, piper). We didn't time a cold build.
- **Logs still say "her" and "Kohl places it once Cass has said yes"** in a few Babelr-organ messages.
  Cosmetic, but a stranger reads logs.
- **`babelr-agent` isn't on PyPI.** The vessel image installs it from the Babelr checkout.
