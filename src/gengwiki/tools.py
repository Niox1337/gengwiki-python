"""Tools for function calling, in OpenAI or Anthropic format. Replies are trimmed, because every field costs the model tokens."""

import json
from typing import TYPE_CHECKING, Any, Callable, Sequence

from .errors import GengWikiError

if TYPE_CHECKING:
    from .client import GengWiki

_LIMIT = {"type": "integer", "description": "返回条数"}

_DEFINITIONS = [
    {
        "name": "search_memes",
        "description": "搜索中文网络热梗，返回释义和使用场景。遇到不认识的网络用语时调用。",
        "parameters": {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "梗的关键词、别名或拼音缩写"}, "limit": _LIMIT},
            "required": ["q"],
        },
    },
    {
        "name": "get_meme",
        "description": "查看一个梗的完整解释和用法例句。搜索结果的释义和使用场景不够用时调用。",
        "parameters": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "search_memes 返回的 slug，也可以是梗的准确名称"}},
            "required": ["slug"],
        },
    },
    {
        "name": "trending_memes",
        "description": "查看全站最近流行的梗。想了解现在流行什么时调用。",
        "parameters": {
            "type": "object",
            "properties": {"tag": {"type": "string", "description": "分类，留空为全站榜"}, "limit": _LIMIT},
        },
    },
    {
        "name": "search_stickers",
        "description": "按含义搜索表情包，返回图片链接。想用表情回复时调用，链接可以直接放进 Markdown。",
        "parameters": {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "想表达的情绪或内容"}, "limit": _LIMIT},
            "required": ["q"],
        },
    },
    {
        "name": "search_lexicon",
        "description": "搜索用户的个人词库，里面是用户自己记录的词语和含义。",
        "parameters": {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "关键词"}, "limit": _LIMIT},
            "required": ["q"],
        },
    },
]


def _summary(m) -> dict:
    row = {"slug": m.slug, "title": m.title, "aliases": m.aliases, "summary": m.summary}
    # Most memes have none yet, and an empty field still costs tokens.
    return {**row, "usage_scenario": m.usage_scenario} if m.usage_scenario else row


def _handlers(c: "GengWiki") -> dict[str, Callable[..., Any]]:
    def get_meme(slug: str) -> dict:
        m = c.meme(slug)
        return {
            **_summary(m),
            "body": m.body,
            "usage_examples": m.usage_examples,
            "related": [{"slug": r.slug, "title": r.title} for r in m.related],
        }

    def search_memes(q: str, limit: int = 5) -> list[dict]:
        return [_summary(m) for m in c.search_memes(q, int(limit))]

    def trending_memes(tag: str = "", limit: int = 10) -> list[dict]:
        return [_summary(m) for m in c.trending(tag, int(limit))]

    def search_stickers(q: str, limit: int = 5) -> list[dict]:
        return [{"caption": s.caption, "url": s.url, "pack": s.pack_title} for s in c.search_stickers(q, int(limit))]

    def search_lexicon(q: str, limit: int = 10) -> list[dict]:
        return [{"term": e.term, "aliases": e.aliases, "note": e.note} for e in c.search_lexicons(q, int(limit))]

    return {
        "search_memes": search_memes,
        "get_meme": get_meme,
        "trending_memes": trending_memes,
        "search_stickers": search_stickers,
        "search_lexicon": search_lexicon,
    }


class Tools:
    def __init__(self, client: "GengWiki"):
        self._handlers = _handlers(client)

    def openai(self, names: Sequence[str] | None = None) -> list[dict]:
        """Definitions for OpenAI, DeepSeek and anything else that takes chat completions tools."""
        return [{"type": "function", "function": d} for d in self._pick(names)]

    def responses(self, names: Sequence[str] | None = None) -> list[dict]:
        """Definitions for the OpenAI Responses API."""
        return [{"type": "function", **d} for d in self._pick(names)]

    def anthropic(self, names: Sequence[str] | None = None) -> list[dict]:
        """Definitions for the Claude API."""
        return [{"name": d["name"], "description": d["description"], "input_schema": d["parameters"]} for d in self._pick(names)]

    @staticmethod
    def _pick(names: Sequence[str] | None) -> list[dict]:
        return [d for d in _DEFINITIONS if names is None or d["name"] in names]

    def call(self, name: str, arguments: str | dict | None = None) -> str:
        """Run one tool and return JSON for the model. Failures come back as JSON too, so the model can react instead of the loop crashing."""
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else (arguments or {})
            handler = self._handlers.get(name)
            if handler is None:
                raise ValueError(f"unknown tool {name!r}")
            result = handler(**args)
        except GengWikiError as e:
            result = {"error": {"code": e.code, "message": e.message}}
        except (TypeError, ValueError, AttributeError) as e:
            # The model passed bad arguments, tell it so it can try again.
            result = {"error": {"code": "bad_arguments", "message": str(e)}}
        return json.dumps(result, ensure_ascii=False)

    def run(self, message: Any) -> list[dict]:
        """Run every tool call in a model reply and return the messages to append. Takes SDK objects or plain dicts, from any of the three APIs."""
        choices = _get(message, "choices")
        if choices:
            message = _get(choices[0], "message")  # handed the whole chat completion
        output = _get(message, "output")
        if isinstance(output, list):
            return [
                {"type": "function_call_output", "call_id": _get(i, "call_id"), "output": self.call(_get(i, "name"), _get(i, "arguments"))}
                for i in output
                if _get(i, "type") == "function_call"
            ]
        calls = _get(message, "tool_calls")
        if calls:
            return [
                {
                    "role": "tool",
                    "tool_call_id": _get(call, "id"),
                    "content": self.call(_get(_get(call, "function"), "name"), _get(_get(call, "function"), "arguments")),
                }
                for call in calls
            ]
        content = _get(message, "content")
        blocks = [b for b in content if _get(b, "type") == "tool_use"] if isinstance(content, list) else []
        if not blocks:
            return []
        results = [
            {"type": "tool_result", "tool_use_id": _get(b, "id"), "content": self.call(_get(b, "name"), _get(b, "input"))}
            for b in blocks
        ]
        return [{"role": "user", "content": results}]


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
