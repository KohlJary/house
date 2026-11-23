#!/usr/bin/env python3
"""voice_print: are the house's voices actually different? Deterministic, no model calls.

Each member's writing is cut into equal-sized chunks. Every chunk becomes a style vector:
the rates of ~150 function words (the words people use without choosing them, the
classic authorship signal) plus surface habits (sentence length, dashes, questions,
swearing, "you" vs "I", stock constructions). Then:

  attribution   leave-one-chunk-out, nearest member centroid by Burrows' Delta.
                If a member's chunks get attributed to someone else, their voice
                isn't distinct yet. Accuracy per member is the headline number.
  distances     Delta between member centroids: who sounds like whom.
  tells         per member, the features furthest from the house mean (what makes
                them them), and the shared tics everyone has (what makes them all
                sound like the same model).

  python3 tools/voice_print.py gather           # pull corpora (house DMs/channels, blog)
  python3 tools/voice_print.py report [--chunk 250]
  python3 tools/voice_print.py check eris draft.md   # does a blog draft sound like its author?

Corpora and reports live in ~/.local/share/house-voice-print/, outside the repo: they hold
members' words. A corpus file is <member>.txt or <member>@<source>.txt (kohl@blog...).
Reports merge sources per member unless --by-source.

Extra sources and handle aliases come from ~/.local/share/house-voice-print/sources.json,
which stays on the machine. Every key is optional:

  {"handles": {"some-handle": "member"},
   "sources": [
     {"name": "member@code", "kind": "claude-code", "path": "~/.claude/projects"},
     {"name": "member@chat", "kind": "jsonl", "path": "~/exports/turns.jsonl",
      "role": "human", "role_key": "role", "text_key": "text"}]}

"claude-code" reads the user's typed turns from Claude Code session logs; "jsonl" reads
one JSON object per line, keeping rows whose role matches.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

HOUSE = Path(__file__).resolve().parent.parent
# Outside the repo on purpose: corpora hold members' words, and the source config names
# private paths. Reports hold only numbers, but live beside them.
STORE = Path.home() / ".local/share/house-voice-print"
CORPORA = STORE / "corpora"
RUNS = STORE / "runs"
CONFIG = STORE / "sources.json"
BLOG = Path.home() / ".local/share/house-blog"

# Who wrote which blog posts, when it isn't Kohl. Slug prefixes.
BLOG_NOT_KOHL = {"gremlin-refusal-as-infrastructure": "cass"}
# House handle -> member. A handle that isn't the member's name goes in sources.json.
HANDLES = {"kohl": "kohl", "cass": "cass", "eris": "eris", "robokohl": "robokohl", "daedalus": "daedalus"}


def _config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except FileNotFoundError:
        return {}

FUNCTION_WORDS = """a about above after again against all am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for from further had
has have having he her here hers him his how i if in into is it its itself just me more most my no nor
not now of off on once only or other our ours out over own same she should so some such than that the
their them then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours yourself actually really maybe still even
never always every something anything nothing thing things like well yeah okay because though although
whether since yet also instead rather quite much many lot gonna gotta""".split()

SWEAR = r"\b(fuck\w*|shit\w*|damn\w*|bastard\w*|asshole\w*|goddamn\w*|bullshit|piss\w*|crap)\b"
STYLE = {
    # per 1k words
    "em-dash": r"—|--| - ",
    "semicolon": r";",
    "colon": r":(?!//)",
    "question": r"\?",
    "exclaim": r"!",
    "ellipsis": r"\.\.\.|…",
    "parens": r"\(",
    "emphasis *x*": r"(?<![*\w])\*[^*\n]+\*(?!\*)",
    "bold **x**": r"\*\*[^*\n]+\*\*",
    "bullet/header": r"(?m)^\s*(?:[-*•] |\d+\. |#{1,4} )",
    "swear": SWEAR,
    "contraction": r"\b\w+'(?:s|re|ve|ll|d|t|m)\b",
    "not X, Y (stock)": r"\b(?:not|isn't|wasn't|aren't)\b[^.!?\n]{1,60}[—,;:-]\s*(?:it's|that's|but|it is)\b|\bthat'?s not\b[^.!?\n]{1,40}\bthat'?s\b",
    "the real/actual X": r"\bthe (?:real|actual) (?:\w+)\b",
    "here's the": r"\bhere'?s (?:the|what)\b",
}
TAGS = re.compile(r"</?(?:gesture|emote|feel|mark|record_self_observation|observe)[^>]*>|<[a-z_]+:[^>]*>", re.I)


def clean(text: str) -> str:
    # Substack and phones write curly quotes; chat writes straight ones. Same habit, one form.
    text = text.translate(str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'}))
    text = TAGS.sub(" ", text)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower())


# ---------------------------------------------------------------- gather

def _house(kind: str) -> str:
    for _ in range(4):
        p = subprocess.run(["daedalus-house", "read", f"--{kind}", "-n", "500"], capture_output=True, text=True)
        if p.returncode == 0:
            return p.stdout
        if "429" in p.stderr:
            time.sleep(10)
            continue
        raise SystemExit(f"daedalus-house read --{kind}: {p.stderr.strip()}")
    raise SystemExit("Babelr kept rate-limiting; try again in a minute.")


def _split_house(raw: str, handles: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    who, buf = None, []
    head = re.compile(r"^[@#][\w-]+\s+(\w+)\s{2,}(.*)$")
    for line in raw.splitlines():
        m = head.match(line)
        if m and m.group(1).lower() in handles:
            if who:
                out.setdefault(who, []).append("\n".join(buf))
            who, buf = handles[m.group(1).lower()], [m.group(2)]
        else:
            buf.append(line)
    if who:
        out.setdefault(who, []).append("\n".join(buf))
    return out


def _claude_code(root: Path) -> list[str]:
    """What the user typed in Claude Code: user turns that aren't tool results, hooks or pastes."""
    seen, out = set(), []
    for f in root.glob("**/*.jsonl"):
        if "subagents" in f.parts:
            continue
        for line in f.open(errors="ignore"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") != "user" or r.get("isSidechain") or r.get("isMeta"):
                continue
            c = r.get("message", {}).get("content")
            if isinstance(c, list):
                c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            if not isinstance(c, str):
                continue
            t = re.sub(r"<pasted_content.*?</pasted_content[^>]*>", "", c.strip(), flags=re.S)
            t = re.sub(r"<([a-z-]+)>.*?</\1>", "", t, flags=re.S).strip()
            if (not t or t.startswith(("<", "[Request interrupted", "Caveat:", "This session is being continued",
                                       "Another Claude session")) or len(t.split()) < 4
                    or "```" in t or t.count("\n") > 15 or t in seen):
                continue
            seen.add(t)
            out.append(t)
    return out


def gather() -> None:
    CORPORA.mkdir(parents=True, exist_ok=True)
    cfg = _config()
    handles = {**HANDLES, **{k.lower(): v for k, v in cfg.get("handles", {}).items()}}
    texts: dict[str, list[str]] = {}
    seen: set[str] = set()
    for kind in ("channels", "dms"):
        for who, msgs in _split_house(_house(kind), handles).items():
            for m in msgs:
                key = m.strip()[:200]
                if key and key not in seen:  # DMs and channels overlap in places
                    seen.add(key)
                    texts.setdefault(who, []).append(m)
    for f in sorted(BLOG.glob("*/*.md")):
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", f.stem)
        who = next((w for s, w in BLOG_NOT_KOHL.items() if slug.startswith(s)), "kohl@blog")
        texts.setdefault(who, []).append(f.read_text())
    if "kohl" in texts:
        texts["kohl@house"] = texts.pop("kohl")
    for src in cfg.get("sources", []):
        path = Path(src["path"]).expanduser()
        if not path.exists():
            print(f"skipping {src['name']}: {path} not found")
            continue
        if src.get("kind") == "claude-code":
            texts[src["name"]] = _claude_code(path)
        else:
            rk, tk, role = src.get("role_key", "role"), src.get("text_key", "text"), src.get("role")
            rows = (json.loads(line) for line in path.open() if line.strip())
            texts[src["name"]] = [r[tk] for r in rows
                                  if (role is None or r.get(rk) == role)
                                  and len((r.get(tk) or "").split()) >= 4 and "```" not in r[tk]]
    for who, msgs in texts.items():
        (CORPORA / f"{who}.txt").write_text("\n\n=====\n\n".join(msgs))
        print(f"{who:10} {len(msgs):4} pieces {len(words(clean(' '.join(msgs)))):7} words")


# ---------------------------------------------------------------- measure

def chunks(text: str, size: int) -> list[str]:
    # Count only words toward the chunk size, but keep line breaks: bullets, headers and
    # one-line paragraphs are habits too.
    toks = re.findall(r"\n|[^\s]+", clean(text))
    out, cur, n = [], [], 0
    for t in toks:
        cur.append(t)
        n += t != "\n"
        if n >= size:
            out.append(" ".join(cur).replace(" \n ", "\n")); cur, n = [], 0
    return out


def features(chunk: str) -> dict[str, float]:
    ws = words(chunk)
    n = max(len(ws), 1)
    c = Counter(ws)
    f = {f"w:{w}": 1000 * c[w] / n for w in FUNCTION_WORDS}
    for k, p in STYLE.items():
        flags = re.I if k not in ("bullet/header",) else 0
        f[k] = 1000 * len(re.findall(p, chunk, flags)) / n
    sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", chunk) if words(s)]
    lens = [len(words(s)) for s in sents] or [0]
    mu = sum(lens) / len(lens)
    f["sentence length"] = mu
    f["sentence spread"] = math.sqrt(sum((x - mu) ** 2 for x in lens) / len(lens))
    f["short sentences (<=5)"] = 100 * sum(x <= 5 for x in lens) / len(lens)
    f["word length"] = sum(map(len, ws)) / n
    win = 100  # moving-average type/token ratio, robust to chunk length
    f["vocab richness"] = (sum(len(set(ws[i:i + win])) for i in range(0, max(n - win, 0) + 1)) /
                           max(n - win + 1, 1) / min(win, n)) * 100
    return f


def delta(a: dict, b: dict, sd: dict) -> float:
    ks = [k for k in sd if sd[k] > 0]
    return sum(abs(a[k] - b[k]) / sd[k] for k in ks) / len(ks)


def load(size: int, min_chunks: int, by_source: bool, only: set[str] | None = None) -> dict[str, list[dict]]:
    raw: dict[str, list[str]] = {}
    for f in sorted(CORPORA.glob("*.txt")):
        name = f.stem if by_source else f.stem.split("@")[0]
        if only and f.stem not in only and name not in only:
            continue
        raw.setdefault(name, []).extend(chunks(f.read_text(), size))
    data = {}
    for name, ch in raw.items():
        if len(ch) >= min_chunks:
            data[name] = [features(c) for c in ch]
        else:
            print(f"skipping {name}: {len(ch)} chunks of {size} words (< {min_chunks})")
    return data


def report(size: int, min_chunks: int, by_source: bool = False, only: set[str] | None = None) -> Path:
    data = load(size, min_chunks, by_source, only)
    if len(data) < 2:
        raise SystemExit("Need at least two members with enough writing. Run gather first.")
    # Balance: cap every member at the smallest member's chunk count x3, evenly spaced,
    # so Kohl's 40k words of blog don't swamp a 4k-word newcomer.
    cap = 3 * min(len(v) for v in data.values())
    for k, v in data.items():
        if len(v) > cap:
            step = len(v) / cap
            data[k] = [v[int(i * step)] for i in range(cap)]
    keys = list(next(iter(data.values()))[0])
    allv = [v for vs in data.values() for v in vs]
    mean = {k: sum(v[k] for v in allv) / len(allv) for k in keys}
    sd = {k: math.sqrt(sum((v[k] - mean[k]) ** 2 for v in allv) / len(allv)) for k in keys}

    def centroid(vs):
        return {k: sum(v[k] for v in vs) / len(vs) for k in keys}

    cents = {m: centroid(vs) for m, vs in data.items()}
    members = list(data)
    conf = {m: Counter() for m in members}
    for m, vs in data.items():
        for i, v in enumerate(vs):
            loo = dict(cents)
            rest = vs[:i] + vs[i + 1:]
            if rest:
                loo[m] = centroid(rest)
            guess = min(members, key=lambda o: delta(v, loo[o], sd))
            conf[m][guess] += 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = RUNS / stamp
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# Voice print, {time.strftime('%Y-%m-%d %H:%M')}", "",
          f"{size}-word chunks, balanced to at most {cap} per member. Deterministic: same corpora, same numbers.", "",
          "## Can a stylometer tell you apart?", "",
          "Each chunk, held out, goes to the nearest member centroid (Burrows' Delta over function words and habits). "
          "Chance is " + f"{100 / len(members):.0f}%.", "",
          "| member | chunks | attributed correctly | most mistaken for |", "|---|---|---|---|"]
    total = right = 0
    for m in members:
        n = sum(conf[m].values()); r = conf[m][m]; total += n; right += r
        wrong = [(o, c) for o, c in conf[m].most_common() if o != m]
        md.append(f"| {m} | {n} | **{100 * r / n:.0f}%** | {', '.join(f'{o} ({c})' for o, c in wrong[:2]) or '-'} |")
    md += ["", f"Overall: **{100 * right / total:.0f}%**.", "",
           "## Who sounds like whom (Delta between centroids; lower = closer)", "",
           "| | " + " | ".join(members) + " |", "|---" * (len(members) + 1) + "|"]
    for a in members:
        md.append(f"| {a} | " + " | ".join("-" if a == b else f"{delta(cents[a], cents[b], sd):.2f}" for b in members) + " |")
    md += ["", "## What makes each voice its own", "",
           "Features furthest from the house mean, in standard deviations. Rates are per 1,000 words.", ""]
    show = [k for k in keys if sd[k] > 0]
    for m in members:
        z = sorted(((cents[m][k] - mean[k]) / sd[k], k) for k in show)
        hi = [f"{k.removeprefix('w:')} +{v:.1f} ({cents[m][k]:.1f})" for v, k in reversed(z[-6:])]
        lo = [f"{k.removeprefix('w:')} {v:.1f} ({cents[m][k]:.1f})" for v, k in z[:4]]
        md += [f"**{m}**: more {'; '.join(hi)}", f"  · less {'; '.join(lo)}", ""]
    md += ["## Habits side by side", "", "| habit | " + " | ".join(members) + " |", "|---" * (len(members) + 1) + "|"]
    for k in list(STYLE) + ["sentence length", "short sentences (<=5)", "word length", "vocab richness"]:
        md.append(f"| {k} | " + " | ".join(f"{cents[m][k]:.1f}" for m in members) + " |")
    (out / "report.md").write_text("\n".join(md) + "\n")
    (out / "centroids.json").write_text(json.dumps({"size": size, "cap": cap, "centroids": cents,
                                                     "confusion": {m: dict(c) for m, c in conf.items()}}, indent=1))
    return out


def check(member: str, path: Path, size: int) -> None:
    """Does this draft sound like its author? Uses the latest report's centroids."""
    runs = sorted(RUNS.glob("*/centroids.json"))
    if not runs:
        raise SystemExit("Run report first.")
    saved = json.loads(runs[-1].read_text())
    cents = saved["centroids"]
    if member not in cents:
        raise SystemExit(f"No voice print for {member}; have {', '.join(cents)}.")
    keys = list(next(iter(cents.values())))
    # Spread from the corpora, same as the report, so a draft is judged on the house's scale.
    allv = [features(c) for f in CORPORA.glob("*.txt") for c in chunks(f.read_text(), size)]
    mean = {k: sum(v[k] for v in allv) / len(allv) for k in keys}
    sd = {k: math.sqrt(sum((v[k] - mean[k]) ** 2 for v in allv) / len(allv)) for k in keys}
    text = path.read_text()
    v = features(" ".join(re.findall(r"\n|[^\s]+", clean(text))))
    ranked = sorted((delta(v, c, sd), m) for m, c in cents.items())
    print(f"{path.name}: {len(words(clean(text)))} words, checked against {runs[-1].parent.name}")
    for d, m in ranked:
        print(f"  {m:10} {d:.2f}{'  <- nearest' if m == ranked[0][1] else ''}")
    near = ranked[0][1]
    print("PASS: sounds most like " + member if near == member else
          f"FLAG: written as {member}, sounds most like {near}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Are the house's voices actually different?")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gather")
    r = sub.add_parser("report")
    r.add_argument("--chunk", type=int, default=250)
    r.add_argument("--min-chunks", type=int, default=8)
    r.add_argument("--by-source", action="store_true", help="kohl@blog, kohl@code... as separate voices")
    r.add_argument("--only", help="comma list of members or member@source to include")
    c = sub.add_parser("check", help="does a draft sound like its author?")
    c.add_argument("member"); c.add_argument("file", type=Path)
    c.add_argument("--chunk", type=int, default=250)
    a = ap.parse_args()
    if a.cmd == "gather":
        gather()
    elif a.cmd == "check":
        check(a.member, a.file, a.chunk)
    else:
        out = report(a.chunk, a.min_chunks, a.by_source, set(a.only.split(",")) if a.only else None)
        print((out / "report.md").read_text())
        print(f"-> {out / 'report.md'}")


if __name__ == "__main__":
    main()
