"""Runs every file in example/ against the fake server, with the LLM SDKs stubbed, so the examples cannot drift from the SDK."""

import contextlib
import io
import runpy
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

from tests.fake import KEY_A, KEY_B
from tests.test_memes import Base

EXAMPLES = sorted((Path(__file__).parent.parent / "example").glob("*.py"))
ARGS = '{"q": "躺平"}'


def chat_replies():
    call = NS(id="1", function=NS(name="search_memes", arguments=ARGS))
    return [
        NS(choices=[NS(message=NS(content=None, tool_calls=[call]))]),
        NS(choices=[NS(message=NS(content="回答", tool_calls=None))]),
    ]


def llm_sdks():
    openai = mock.MagicMock()
    llm = openai.OpenAI.return_value
    llm.chat.completions.create.side_effect = chat_replies()
    llm.responses.create.side_effect = [
        NS(output=[NS(type="function_call", call_id="1", name="search_memes", arguments=ARGS)]),
        NS(output=[NS(type="message")], output_text="回答"),
    ]
    anthropic = mock.MagicMock()
    anthropic.Anthropic.return_value.messages.create.side_effect = [
        NS(content=[NS(type="tool_use", id="1", name="search_memes", input={"q": "躺平"})]),
        NS(content=[NS(type="text", text="回答")]),
    ]
    return {"openai": openai, "anthropic": anthropic}


class ExampleTest(Base):
    def run_example(self, path):
        saved = self.client(key=None)
        saved.keys.add("a", KEY_A)
        saved.keys.add("b", KEY_B)
        env = {"GENGWIKI_API_URL": self.url, "GENGWIKI_SITE_URL": self.url, "GENGWIKI_HOME": self.dir.name, "GENGWIKI_API_KEY": ""}
        out = io.StringIO()
        with (
            mock.patch.dict("os.environ", env),
            mock.patch.dict("sys.modules", llm_sdks()),
            mock.patch("getpass.getpass", return_value="correct horse"),
            mock.patch("builtins.input", side_effect=["躺平是什么？", ""]),
            contextlib.redirect_stdout(out),
        ):
            runpy.run_path(str(path), run_name="__main__")
        if path.stem != "api_keys":  # the only one that stays on this machine
            self.assertTrue(self.fake.hits, "this example never reached the server")
        self.assertTrue(out.getvalue())


for _path in EXAMPLES:
    setattr(ExampleTest, f"test_{_path.stem}", lambda self, path=_path: self.run_example(path))
