import json
import unittest
from types import SimpleNamespace as NS

from tests.fake import KEY_A
from tests.test_memes import Base


class ToolsTest(Base):
    def test_formats(self):
        c = self.client()
        names = {t["function"]["name"] for t in c.tools.openai()}
        self.assertEqual(names, {"search_memes", "get_meme", "trending_memes", "search_stickers", "search_lexicon"})
        self.assertEqual(c.tools.openai()[0]["type"], "function")
        claude = c.tools.anthropic(["get_meme"])
        self.assertEqual([t["name"] for t in claude], ["get_meme"])
        self.assertIn("slug", claude[0]["input_schema"]["properties"])

    def test_every_definition_has_a_handler_that_runs(self):
        c = self.client()
        args = {"q": "躺平", "slug": "tang-ping"}
        for t in c.tools.openai():
            f = t["function"]
            call = {k: args[k] for k in f["parameters"].get("required", [])}
            self.assertNotIn("error", json.loads(c.tools.call(f["name"], call)), f["name"])

    def test_reply_is_trimmed_and_readable_chinese(self):
        text = self.client().tools.call("search_memes", '{"q": "躺平"}')
        self.assertIn("躺平", text)
        self.assertEqual(set(json.loads(text)[0]), {"slug", "title", "aliases", "summary"})

    def test_get_meme_has_the_full_text(self):
        got = json.loads(self.client().tools.call("get_meme", {"slug": "摆烂"}))
        self.assertEqual((got["slug"], got["body"]), ("tang-ping", "躺平的正文"))

    def test_string_limit_from_a_model_works(self):
        self.assertEqual(len(json.loads(self.client().tools.call("trending_memes", {"limit": "1"}))), 1)

    def test_failures_come_back_as_json(self):
        c = self.client()
        cases = [
            ("get_meme", {"slug": "nope"}, "not_found"),
            ("no_such_tool", {}, "bad_arguments"),
            ("search_memes", "{not json", "bad_arguments"),
            ("search_memes", {"wrong": 1}, "bad_arguments"),
            ("search_memes", {"q": "x", "limit": "many"}, "bad_arguments"),
        ]
        for name, args, code in cases:
            self.assertEqual(json.loads(c.tools.call(name, args))["error"]["code"], code, (name, args))
        self.fake.keys[KEY_A]["scopes"] = []
        c.refresh()
        self.assertEqual(json.loads(c.tools.call("search_memes", {"q": "x"}))["error"]["code"], "forbidden")

    def test_html_with_a_200_is_not_blamed_on_the_arguments(self):
        self.fake.html_ok = True
        got = json.loads(self.client().tools.call("search_memes", {"q": "躺平"}))
        self.assertEqual(got["error"]["code"], "bad_response")

    def test_run_openai_objects_and_dicts(self):
        c = self.client()
        args = '{"q": "躺平"}'
        as_object = NS(content=None, tool_calls=[NS(id="1", function=NS(name="search_memes", arguments=args))])
        as_dict = {"tool_calls": [{"id": "1", "function": {"name": "search_memes", "arguments": args}}]}
        for message in (as_object, as_dict):
            [reply] = c.tools.run(message)
            self.assertEqual((reply["role"], reply["tool_call_id"]), ("tool", "1"))
            self.assertIn("tang-ping", reply["content"])

    def test_run_anthropic_objects_and_dicts(self):
        c = self.client()
        text = {"type": "text", "text": "查一下"}
        call = {"type": "tool_use", "id": "t", "name": "search_memes", "input": {"q": "躺平"}}
        for message in ({"content": [text, call]}, NS(content=[NS(**text), NS(**call)])):
            [reply] = c.tools.run(message)
            self.assertEqual(reply["role"], "user")
            self.assertEqual(reply["content"][0]["tool_use_id"], "t")
            self.assertIn("tang-ping", reply["content"][0]["content"])

    def test_run_with_no_calls(self):
        c = self.client()
        self.assertEqual(c.tools.run({"content": "你好"}), [])
        self.assertEqual(c.tools.run(NS(content="你好", tool_calls=None)), [])

    def test_a_conversation_costs_one_list_request(self):
        c = self.client()
        for q in ("躺平", "永远的神", "上班味"):
            c.tools.call("search_memes", {"q": q})
        self.assertEqual(c.request_count, 1)


if __name__ == "__main__":
    unittest.main()
