"""The server's search, run locally, so a synced key answers without a request."""

import re


def _trigrams(text: str) -> set[str]:
    """What pg_trgm's show_trgm returns: lowercased alphanumeric words, padded with two spaces in front and one behind."""
    grams: set[str] = set()
    for word in re.findall(r"[^\W_]+", text.lower()):
        padded = f"  {word} "
        grams.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return grams


def similarity(a: str, b: str) -> float:
    ga, gb = _trigrams(a), _trigrams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def search_memes(q: str, rows: list[dict], limit: int) -> list[dict]:
    """Same match and order as common::memes::search. The title and aliases are scored, the usage scenario only has to contain q."""
    q = q.strip()
    if not q:
        return rows[:limit]
    scored = []
    for r in rows:
        text = " ".join([r["title"], *r["aliases"]])
        sim = similarity(text, q)
        if q.lower() in f"{text} {r.get('usage_scenario', '')}".lower() or sim > 0.2:
            scored.append((sim, r))
    scored.sort(key=lambda x: (-x[0], -x[1]["heat"]))
    return [r for _, r in scored[:limit]]


def match_memes(text: str, rows: list[dict], limit: int) -> list[dict]:
    """The reverse of search_memes, the memes whose title or alias is written in the text. The longest name wins."""
    text = text.lower()
    scored = []
    for r in rows:
        # One character aliases would match nearly any sentence.
        longest = max((len(n) for n in [r["title"], *r["aliases"]] if len(n) >= 2 and n.lower() in text), default=0)
        if longest:
            scored.append((longest, r))
    scored.sort(key=lambda x: (-x[0], -x[1]["heat"]))
    return [r for _, r in scored[:limit]]


def search_stickers(q: str, packs: list[dict], limit: int) -> list[dict]:
    """Same match as the API's strpos over the caption, the pack title and the pack tags.

    A host asking for one sticker by caption wants that sticker, so the exact caption comes first, then captions containing q, then the rest, each in pack order.
    Runs of whitespace count as one space, a model copying a caption tends to flatten them.
    """
    q = " ".join(q.split()).lower()
    found = []
    for p in packs:
        for s in p["stickers"]:
            caption = " ".join(s["caption"].split()).lower()
            if q in " ".join([caption, p["title"], *p["tags"]]).lower():
                rank = 0 if caption == q else 1 if q in caption else 2
                found.append((rank, {**s, "pack_id": p["id"], "pack_title": p["title"]}))
    found.sort(key=lambda x: x[0])
    return [s for _, s in found[:limit]]


def search_personas(q: str, rows: list[dict]) -> list[dict]:
    """Same match as the catalog's strpos over the title, the description and the tags."""
    q = q.strip().lower()
    return [r for r in rows if q in " ".join([r["title"], r.get("description", ""), *r.get("tags", [])]).lower()]


def search_people(q: str, rows: list[dict]) -> list[dict]:
    """Same match as the API's strpos over the name, aliases, tags, bio and quotes."""
    q = q.strip().lower()
    return [r for r in rows if q in " ".join([r["name"], *r["aliases"], *r["tags"], r["bio"], *r["quotes"]]).lower()]


def search_entries(q: str, entries: list[dict], limit: int) -> list[dict]:
    q = q.strip().lower()
    return [e for e in entries if q in " ".join([e["term"], *e["aliases"], e["note"], *e["tags"]]).lower()][:limit]
