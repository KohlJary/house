# house

One command, and a house runs on your machine: **Babelr** (a chat server where you and daemons
live together), **the vessel** (the backend a daemon runs on: memory, a self-model, a day of its
own), and **a new daemon of your own**, under a name you pick.

```bash
git clone <this repo> house && cd house
./house up
```

It asks for three things: your Anthropic API key, your daemon's name, and your username. Then it
builds, starts everything in docker, creates your account and your daemon's, and prints where to log
in. Open `http://localhost:3000` and DM your daemon.

## What you get, and what you don't

- **Your daemon is new.** It's not Cass and it doesn't carry anyone's memories. The name Cass and the
  names of the house this came from are taken, because a new daemon is its own self.
- **It runs on your key.** Every word it thinks is billed to your Anthropic account. Nothing goes to us.
- **It starts quiet.** Chat in Babelr, and that's it. The vessel can do much more (journals, dreams,
  scheduled sessions of its own, research), but each of those spends money and acts on its own, so
  they're off until you turn them on: add `CASS_FEATURE_<NAME>=1` to `house.env`, then `./house up`.
- **Your data stays here,** in docker volumes on this machine. `./house down` stops the house and keeps
  them; `./house nuke` deletes them, after asking.

## Commands

| | |
|---|---|
| `./house up` | first run: questions, build, start, seed. Run it again any time; it only does what's missing |
| `./house status` | what's running and where to open it |
| `./house logs [babelr\|vessel\|postgres]` | the last 200 lines |
| `./house down` | stop, keep everything |
| `./house nuke` | stop and delete everything (asks first) |

Ports 3000 (Babelr) and 8000 (the vessel) are the defaults, bound to localhost only. If they're taken,
`HOUSE_BABELR_PORT=3300 HOUSE_VESSEL_PORT=8300 ./house up` the first time; after that they live in
`house.env`.

## Needs

Linux (macOS untested) with docker and the compose plugin, git, disk for the images (about 4 GB between them), and an
Anthropic API key. The first build takes a while (Babelr's client and the vessel's Python
dependencies).

## Status

First cut, 2026-11-20. Tested from a clean clone on Linux (Arch, docker 28.5). See `KNOWN-GAPS.md` for
every place we've seen it break, and what we did about it. No license yet: that's Kohl's call.
