"""What the API returns, as dataclasses. Unknown fields are dropped so a newer server never breaks an older SDK."""

import dataclasses
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Model:
    @classmethod
    def of(cls, d: dict):
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class MemeSummary(Model):
    slug: str = ""
    title: str = ""
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    categories: list[str] = field(default_factory=list)
    heat: int = 0
    updated_at: str = ""


@dataclass(frozen=True)
class Contributor(Model):
    name: str = ""
    edits: int = 0
    avatar_id: str | None = None


@dataclass(frozen=True)
class Meme(MemeSummary):
    id: str = ""
    body: str = ""
    usage_examples: list[str] = field(default_factory=list)
    first_seen: str | None = None
    related: list[MemeSummary] = field(default_factory=list)
    contributors: list[Contributor] = field(default_factory=list)

    @classmethod
    def of(cls, d: dict):
        d = {
            **d,
            "related": [MemeSummary.of(r) for r in d.get("related", [])],
            "contributors": [Contributor.of(c) for c in d.get("contributors", [])],
        }
        return super().of(d)


@dataclass(frozen=True)
class Persona(Model):
    id: str = ""
    title: str = ""
    description: str = ""
    prompt: str = ""
    tags: list[str] = field(default_factory=list)
    # Only the catalog sends these, a key's own persona does not.
    author: str | None = None
    memes: list[dict] = field(default_factory=list)
    packs: list[dict] = field(default_factory=list)

    def as_message(self) -> dict[str, str]:
        """The system message for any chat completions style API."""
        return {"role": "system", "content": self.prompt}


@dataclass(frozen=True)
class Sticker(Model):
    id: str = ""
    caption: str = ""
    url: str = ""
    pack_id: str = ""
    pack_title: str = ""


@dataclass(frozen=True)
class StickerPack(Model):
    id: str = ""
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    stickers: list[Sticker] = field(default_factory=list)

    @classmethod
    def of(cls, d: dict):
        stickers = [Sticker.of({**s, "pack_id": d.get("id", ""), "pack_title": d.get("title", "")}) for s in d.get("stickers", [])]
        return super().of({**d, "stickers": stickers})


@dataclass(frozen=True)
class Lexicon(Model):
    id: str = ""
    name: str = ""
    description: str = ""
    visibility: str = ""
    entries: int = 0


@dataclass(frozen=True)
class LexiconEntry(Model):
    id: str = ""
    term: str = ""
    aliases: list[str] = field(default_factory=list)
    note: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RateLimit(Model):
    per_minute: int | None = None
    per_day: int | None = None
    used_this_minute: int = 0
    used_today: int = 0
    reset_secs: int = 0


@dataclass(frozen=True)
class ApiKey(Model):
    """A key as the account API describes it. The secret is never part of this."""

    id: str = ""
    name: str = ""
    prefix: str = ""
    scopes: list[str] = field(default_factory=list)
    memes: list[dict] = field(default_factory=list)
    persona: dict | None = None
    packs: list[dict] = field(default_factory=list)
    created_at: str = ""
    last_used_at: str | None = None
    revoked_at: str | None = None


@dataclass(frozen=True)
class LocalKey(Model):
    """A key saved on this machine. The secret stays in the keyring."""

    name: str = ""
    prefix: str = ""
    id: str | None = None
    persona_id: str | None = None
    persona_title: str | None = None
    current: bool = False
