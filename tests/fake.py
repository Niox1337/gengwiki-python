"""A stand-in for both gengwiki services on one port, written from api/src/main.rs and backend/src/main.rs.

It counts every request, because request counts are what these tests are about.
"""

import http.server
import json
import threading
import urllib.parse
import uuid

KEY_A = "gwk_live_aaaaaa" + "0" * 42
KEY_B = "gwk_live_bbbbbb" + "0" * 42
PERSONA_A = "11111111-1111-1111-1111-111111111111"
PERSONA_B = "22222222-2222-2222-2222-222222222222"
PACK = "33333333-3333-3333-3333-333333333333"
STICKER = "44444444-4444-4444-4444-444444444444"
LU_XUN = "55555555-5555-5555-5555-555555555555"
DU_FU = "66666666-6666-6666-6666-666666666666"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
ALL_SCOPES = ["memes:read", "trending:read", "persona:read", "stickers:read", "people:read", "lexicon:read:self", "lexicon:write:self"]
TOKEN = "jwt-token"


def meme(slug, title, heat=1, aliases=(), updated_at="2026-01-01T00:00:00Z"):
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, slug)),
        "slug": slug,
        "title": title,
        "aliases": list(aliases),
        "summary": f"{title}的释义",
        "usage_scenario": f"{title}的场景",
        "body": f"{title}的正文",
        "usage_examples": [f"{title}的例句"],
        "categories": ["网络"],
        "heat": heat,
        "first_seen": None,
        "updated_at": updated_at,
        "related": [],
        "contributors": [{"name": "鲸鱼", "edits": 1, "avatar_id": None}],
    }


SUMMARY = ("slug", "title", "aliases", "summary", "usage_scenario", "categories", "heat", "updated_at")


class _Replied(Exception):
    """A scope check already answered, stop routing."""


class Fake:
    def __init__(self):
        self.memes = {m["slug"]: m for m in [meme("tang-ping", "躺平", 9, ["摆烂"]), meme("yyds", "YYDS", 5, ["永远的神"])]}
        self.personas = {
            PERSONA_A: self._persona(PERSONA_A, "毒舌老哥", ["tang-ping"], [PACK]),
            PERSONA_B: self._persona(PERSONA_B, "温柔姐姐", ["yyds"], []),
        }
        self.packs = {
            PACK: {
                "id": PACK,
                "title": "猫猫",
                "description": "",
                "tags": ["可爱"],
                "stickers": [{"id": STICKER, "caption": "震惊"}],
            }
        }
        self.people = {
            LU_XUN: {"id": LU_XUN, "name": "鲁迅", "aliases": ["周树人"], "tags": ["作家"], "bio": "现代文学家", "quotes": ["我家门前有两棵树"]},
            DU_FU: {"id": DU_FU, "name": "杜甫", "aliases": [], "tags": ["诗人"], "bio": "唐代诗人", "quotes": []},
        }
        self.keys = {
            KEY_A: self._key(KEY_A, "a", PERSONA_A, ["tang-ping", "yyds"], [PACK], people=[LU_XUN]),
            KEY_B: self._key(KEY_B, "b", PERSONA_B, ["yyds"], []),
        }
        self.backup: list[dict] = []  # what the backup wiki has
        self.lexicons: dict[str, dict] = {}
        self.entries: dict[str, list] = {}
        self.hits: list[tuple[str, str]] = []
        self.status: int | None = None  # answer everything with this status
        self.html_ok = False  # answer everything with a 200 HTML page, like a captive portal
        self.json_ok = None  # answer everything with a 200 and this JSON, like a proxy that rewrites replies
        self.account_open = True  # False is what the public site does today
        self.lock = threading.Lock()

    @staticmethod
    def _persona(pid, title, memes, packs):
        return {
            "id": pid,
            "title": title,
            "description": "",
            "prompt": f"你是{title}",
            "tags": [],
            "author": "鲸鱼",
            "status": "published",
            "memes": [{"slug": s, "title": s, "summary": ""} for s in memes],
            "packs": [{"id": p, "title": "猫猫", "cover": STICKER} for p in packs],
            "people": [{"id": LU_XUN, "name": "鲁迅", "aliases": ["周树人"], "quotes": 1}] if packs else [],
        }

    def _key(self, token, name, persona, memes, packs, scopes=None, people=()):
        return {
            "id": str(uuid.uuid4()),
            "name": name,
            "prefix": token[:15],
            "scopes": scopes or list(ALL_SCOPES),
            "memes": memes,
            "persona": persona,
            "packs": packs,
            "people": list(people),
            "revoked": False,
        }

    def public_key(self, k):
        title = self.personas[k["persona"]]["title"] if k["persona"] else None
        return {
            "id": k["id"],
            "name": k["name"],
            "prefix": k["prefix"],
            "scopes": k["scopes"],
            "memes": [{"slug": s, "title": s} for s in k["memes"]],
            "persona": {"id": k["persona"], "title": title} if k["persona"] else None,
            "packs": [{"id": p, "title": "猫猫"} for p in k["packs"]],
            "people": [{"id": p, "name": self.people[p]["name"]} for p in k["people"]],
            "created_at": "2026-01-01T00:00:00Z",
            "last_used_at": None,
            "revoked_at": "2026-01-02T00:00:00Z" if k["revoked"] else None,
        }

    def count(self, prefix=""):
        return sum(1 for _, p in self.hits if p.startswith(prefix))


def serve(fake: Fake):
    """Returns (url, stop)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body=None, headers=()):
            data = b"" if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error_reply(self, status, code):
            self.reply(status, {"error": {"code": code, "message": code}})

        def token(self):
            return self.headers.get("Authorization", "").removeprefix("Bearer ")

        def body(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

        def route(self, method):
            url = urllib.parse.urlsplit(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
            path = urllib.parse.unquote(url.path)
            with fake.lock:
                fake.hits.append((method, path))
                if fake.html_ok:
                    return self.reply(200, "<html>登录 Wi-Fi</html>".encode(), [("Content-Type", "text/html")])
                if fake.json_ok is not None:
                    return self.reply(200, fake.json_ok)
                if fake.status == 429:
                    return self.reply(429, {"error": {"code": "rate_limited", "message": "x"}}, [("Retry-After", "3600")])
                if fake.status:
                    return self.error_reply(fake.status, "internal")
                if path == "/backup":
                    word = q.get("q", "").lower()
                    items = [i for i in fake.backup if any(word in s.lower() for s in [i["title"], *i["aliases"]])]
                    return self.reply(200, {"schema_version": 1, "items": items, "has_more": False})
                if path.startswith("/v1/"):
                    try:
                        return self.v1(method, path[3:], q)
                    except _Replied:
                        return
                if path.startswith("/api/"):
                    if not fake.account_open:
                        return self.reply(404, b"<html>not found</html>", [("Content-Type", "text/html")])
                    return self.account(method, path[4:])
                return self.reply(404, b"<html>")

        def v1(self, method, path, q):
            if path.startswith("/stickers/") and path.endswith("/image"):
                if path.split("/")[2] == STICKER:
                    return self.reply(200, PNG, [("Content-Type", "image/png")])
                return self.error_reply(404, "not_found")
            k = fake.keys.get(self.token())
            if k is None or k["revoked"]:
                return self.error_reply(401, "unauthorized")

            def need(scope):
                if scope in k["scopes"]:
                    return True
                self.error_reply(403, "forbidden")
                raise _Replied

            limit = max(1, min(int(q.get("limit", 20)), 100))
            scoped = sorted((fake.memes[s] for s in k["memes"] if s in fake.memes), key=lambda m: -m["heat"])
            if path == "/memes/search" and need("memes:read"):
                term = q.get("q", "").strip().lower()
                rows = [m for m in scoped if term in " ".join([m["title"], *m["aliases"], m["usage_scenario"]]).lower()]
                return self.reply(200, [{f: m[f] for f in SUMMARY} for m in rows[:limit]])
            if path.startswith("/memes/") and need("memes:read"):
                m = next((m for m in scoped if m["slug"] == path[7:]), None)
                return self.reply(200, m) if m else self.error_reply(404, "not_found")
            if path == "/tags" and need("trending:read"):
                counts = {}
                for m in fake.memes.values():
                    for c in m["categories"]:
                        counts[c] = counts.get(c, 0) + 1
                return self.reply(200, [{"name": c, "count": n} for c, n in sorted(counts.items(), key=lambda r: (-r[1], r[0]))])
            if path == "/trending" and need("trending:read"):
                tag = q.get("tag", "")
                rows = sorted((m for m in fake.memes.values() if not tag or tag in m["categories"]), key=lambda m: -m["heat"])
                if tag and "limit" not in q:
                    limit = 5
                return self.reply(200, [{f: m[f] for f in SUMMARY} for m in rows[:limit]])
            if path == "/persona" and need("persona:read"):
                p = fake.personas.get(k["persona"])
                if not p:
                    return self.error_reply(404, "not_found")
                return self.reply(200, {f: p[f] for f in ("id", "title", "description", "prompt", "tags")})
            base = f"http://{self.headers['Host']}"
            if path == "/sticker-packs" and need("stickers:read"):
                packs = []
                for pid in k["packs"]:
                    p = fake.packs[pid]
                    packs.append({**p, "stickers": [{**s, "url": f"{base}/v1/stickers/{s['id']}/image"} for s in p["stickers"]]})
                return self.reply(200, packs)
            if path == "/stickers/search" and need("stickers:read"):
                return self.reply(200, [])
            if path == "/people/linked" and need("people:read"):
                return self.reply(200, [fake.people[p] for p in k["people"]])
            if path == "/people" and need("people:read"):
                offset = int(q.get("offset", 0))
                return self.reply(200, list(fake.people.values())[offset : offset + limit])
            if path.startswith("/people/") and need("people:read"):
                wanted = path[8:].lower()
                p = next((p for p in fake.people.values() if wanted in (p["id"], p["name"].lower(), *map(str.lower, p["aliases"]))), None)
                return self.reply(200, {**p, "memes": [{"slug": "tang-ping", "title": "躺平", "summary": ""}]}) if p else self.error_reply(404, "not_found")
            if path == "/me/usage":
                return self.reply(200, {"per_day": 100000, "days": [{"day": "2026-01-01", "requests": 3}]})
            if path == "/me/rate-limit":
                return self.reply(200, {"per_minute": 600, "per_day": 100000, "used_this_minute": 1, "used_today": 2, "reset_secs": 30})
            if path == "/me/lexicons":
                if method == "POST":
                    if need("lexicon:write:self"):
                        lex = {"id": str(uuid.uuid4()), "visibility": "private", "entries": 0, "description": "", **self.body()}
                        fake.lexicons[lex["id"]] = lex
                        fake.entries[lex["id"]] = []
                        return self.reply(201, lex)
                    return
                if need("lexicon:read:self"):
                    return self.reply(200, list(fake.lexicons.values()))
                return
            if path.startswith("/me/lexicons/") and path.endswith("/entries"):
                lid = path.split("/")[3]
                if lid not in fake.lexicons:
                    return self.error_reply(404, "not_found")
                if method == "POST":
                    if need("lexicon:write:self"):
                        e = {"id": str(uuid.uuid4()), "aliases": [], "note": "", "tags": [], **self.body()}
                        fake.entries[lid].append(e)
                        fake.lexicons[lid]["entries"] += 1
                        return self.reply(201, e)
                    return
                if need("lexicon:read:self"):
                    return self.reply(200, fake.entries[lid])
                return
            return self.error_reply(404, "not_found")

        def account(self, method, path):
            if method == "GET" and path == "/personas":
                return self.reply(200, list(fake.personas.values()))
            if method == "POST" and path == "/auth/login":
                b = self.body()
                if b.get("password") != "correct horse":
                    return self.error_reply(401, "unauthorized")
                return self.reply(200, {"token": TOKEN, "expires_in": 604800, "user": {"email": b["email"]}})
            if self.token() != TOKEN:
                return self.error_reply(401, "unauthorized")
            if path == "/me/keys" and method == "GET":
                return self.reply(200, [fake.public_key(k) for k in fake.keys.values()])
            if path == "/me/keys" and method == "POST":
                b = self.body()
                token = f"gwk_live_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
                k = fake._key(token, b["name"], b.get("persona"), b.get("memes", []), b.get("packs", []), b.get("scopes"), b.get("people", []))
                fake.keys[token] = k
                return self.reply(201, {"key": token, "api_key": fake.public_key(k)})
            parts = path.split("/")  # ['', 'me', 'keys', id, 'rotate']
            old = next((k for k in fake.keys.values() if k["id"] == parts[3] and not k["revoked"]), None)
            if old is None:
                return self.error_reply(404, "not_found")
            old["revoked"] = True
            if method == "DELETE":
                return self.reply(204)
            token = f"gwk_live_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"
            k = fake._key(token, old["name"], old["persona"], old["memes"], old["packs"], old["scopes"], old["people"])
            fake.keys[token] = k
            return self.reply(200, {"key": token, "api_key": fake.public_key(k)})

        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

        def do_DELETE(self):
            self.route("DELETE")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True).start()

    def stop():
        server.shutdown()
        server.server_close()

    return f"http://127.0.0.1:{server.server_port}", stop
