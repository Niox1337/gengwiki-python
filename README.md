# gengwiki-python

梗Wiki 的 Python SDK，支持 Python 3.10 及以上。

```bash
pip install gengwiki
```

到[个人中心](https://gengwiki.niox.lol/me)创建 Key，然后保存到本机，之后的代码里就不用再写它了。

```bash
gengwiki keys add 老哥      # 粘贴时不显示，也不会留在命令历史里
gengwiki status            # 查看当前 Key、人设和额度
```

```python
from gengwiki import GengWiki

client = GengWiki()                        # 也可以传入 Key，或者设置环境变量 GENGWIKI_API_KEY

client.search_memes("躺平")
client.meme("tang-ping").body
client.persona().as_message()              # {"role": "system", "content": "..."}
```

更多用法见 [example/](https://github.com/Niox1337/gengwiki-python/tree/main/example)。

## 切换人设

一个 Key 终身绑定一个人设，所以切换人设就是切换到绑定了它的 Key。没有这样的 Key 时，登录后会自动创建一个并保存。

```python
persona = client.use_persona("温柔姐姐")     # 按标题或 id
messages = [persona.as_message(), {"role": "user", "content": "你好"}]
```

`client.personas("关键词")` 可以浏览人设目录。Claude 的系统提示不放在消息列表里，所以要写成 `system=persona.prompt`。

## 命令行

安装后可以用 `gengwiki`，也可以用 `python -m gengwiki`。

```bash
gengwiki login                # 登录，密码不会保存
gengwiki status               # 当前站点、Key、人设和额度
gengwiki search 躺平           # 也有 meme、trending、personas
gengwiki use 温柔姐姐           # 切换人设
gengwiki sync --images        # 下载全部内容供离线使用
gengwiki keys                 # 也有 add、use、remove、secret、remote、rotate、revoke
```

## 给大模型用的工具

```python
tools = client.tools.openai()        # OpenAI 和 DeepSeek 等的 Chat Completions
tools = client.tools.responses()     # OpenAI 的 Responses API
tools = client.tools.anthropic()     # Claude

while True:
    reply = llm.chat.completions.create(model=model, messages=messages, tools=tools).choices[0].message
    results = client.tools.run(reply)
    if not results:
        break
    messages += [reply, *results]
```

Claude 的回复用法相同，只是追加时写成 `{"role": "assistant", "content": reply.content}`。Responses API 把 `response` 传给 `run`，追加时写成 `input += [*response.output, *results]`。

想让模型不等提问就玩梗，把 `client.meme_prompt(用户的话)` 放进提示词。它会优先带上这句话提到的梗，再随机补一些 Key 范围内的梗和热门梗，并告诉模型只在非常贴切时才用。`client.match_memes(用户的话)` 返回这句话提到了哪些梗，可以用来决定机器人要不要插话。两个方法都不调用模型，缓存好之后也不发请求。

共有 5 个工具，分别是 `search_memes`、`get_meme`、`trending_memes`、`search_stickers` 和 `search_lexicon`。可以用 `client.tools.openai(["search_memes"])` 只选其中几个。

## 开发

```bash
uv run python -m unittest discover -s tests -t .
```

`tests/test_live.py` 用来对照真实服务，只有设置了 `GENGWIKI_LIVE_API` 和 `GENGWIKI_LIVE_SITE` 才会运行，需要指向一套载入了 `tests/live_seed.sql` 的临时环境，绝对不要指向生产环境。
