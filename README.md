# gengwiki-python

梗Wiki 的 Python SDK，支持 Python 3.10 及以上。

```bash
pip install gengwiki
```

到[个人中心](https://gengwiki.niox.lol/me)创建 Key，然后保存到本机，之后的代码里就不用再写它了。

```bash
gengwiki keys add 老哥      # 粘贴时不显示，也不会留在命令历史里
gengwiki status            # 查看当前 Key、人设、内容和额度
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
gengwiki status               # 当前站点、Key、人设、内容、缺的权限和额度
gengwiki search 躺平           # 也有 meme、trending、personas
gengwiki use 温柔姐姐           # 切换人设
gengwiki tags                 # 全部标签
gengwiki subscribe 游戏         # 订阅标签，也有 unsubscribe，不带标签时列出已订阅的
gengwiki sync --images        # 下载全部内容供离线使用
gengwiki keys                 # 也有 add、use、remove、secret、remote、rotate、revoke
```

代码里用 `client.status()` 可以拿到同样的内容，包括人设名字，梗、表情、人物和语录的数量，Key 缺的权限，以及数据是不是旧的。Key 无效时会抛出 `AuthError`。

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

人设只需要写性格和说话方式。查梗和发表情的步骤放在 `client.tools.guide()` 里，它还列出了这个 Key 关联的人物和能用的全部表情说明，放在系统提示词里人设的后面就行。

```python
system = f"{client.persona().prompt}\n\n{client.tools.guide()}"
```

模型默认用 Markdown 图片发表情。如果你的程序能自己发图片，传入自己的规则，比如 `client.tools.guide("发送时调用 send_sticker，传入这条说明。")`。

想让模型不等提问就玩梗，把 `client.meme_prompt(用户的话)` 放进提示词。它会优先带上这句话提到的梗，再随机补一些 Key 范围内的梗和热门梗，并告诉模型只在非常贴切时才用。`client.match_memes(用户的话)` 返回这句话提到了哪些梗，可以用来决定机器人要不要插话。两个方法都不调用模型，缓存好之后也不发请求。

想让模型也用某个标签的热梗，就订阅这个标签。

```python
client.tags()                 # 全部标签，每个带 name 和 count，用得最多的在前
client.subscribe("游戏")      # 返回这个标签的前 5 名，标签不存在时抛出 NotFoundError
client.subscriptions()        # ["游戏"]
client.unsubscribe("游戏")
```

订阅存在本机，所有 Key 共用，需要 `trending:read`。`client.turn()`、`client.meme_prompt()` 和 `client.match_memes()` 都会带上每个订阅标签的前 5 名，它们在随机选梗时有保留名额，已经绑定在 Key 上的梗不会重复出现。要按聊天分别订阅的话，自己保存标签，再传入 `tags=["游戏"]`，它会代替保存的订阅。

`client.search_memes()` 只搜 Key 范围内的梗。`client.find_memes()` 还会搜订阅标签的前 5 名和热门榜，`search_memes` 工具和命令行的 `gengwiki search` 用的是它。Key 范围以外的梗只有释义和使用场景，完整解释和例句读不到。

共有 7 个工具，分别是 `search_memes`、`get_meme`、`trending_memes`、`search_stickers`、`search_people`、`get_person` 和 `search_lexicon`。可以用 `client.tools.openai(["search_memes"])` 只选其中几个。

## 人物

```python
client.person("鲁迅")        # 特定人物，按 id、名字或别名，附带提到他的梗
client.people("作家")        # 全部人物，可以搜索，不受 Key 范围限制
client.linked_people()       # 这个 Key 关联的人物
```

Key 关联的人物会自动进入 `client.tools.guide()`，模型不用查就认识他们。人物有语录时，用 `quotes` 选择模型怎么对待语录，这会改变提示词里的指令，也决定工具结果带不带语录。

| `quotes` | 含义 |
|---|---|
| `off` | 不使用。提示词和工具结果都不带语录，并要求模型不要引用 |
| `cite` | 引用，这是默认值。贴切时照抄原话并说明是谁说的 |
| `use` | 直接使用。语境合适时整条回复只发一句语录原话，不加其他文字，用户问起出处时如实说 |
| `both` | 引用和使用。两种都可以，优先只发语录原话 |

```python
client = GengWiki(quotes="both")
```

需要 Key 勾选了 `people:read`，旧 Key 没有这个权限，要新建一个。

## 频率

三个 0 到 1 的参数决定多少比例的回复可以主动玩梗、用语录和发表情。每条回复由代码掷一次，掷中了才把素材给模型，模型再按语境决定用不用、用哪个，所以实际比例不会超过这个数。

掷中后模型会尽量用上一个梗，认真求助或倾诉时除外。用 DeepSeek 和一个人设测试时，掷中的回复约一半用了梗，所以 `meme_frequency=0.2` 大约对应一成的回复。比例因模型和人设而异，也可能有硬凑的情况，觉得太多就调低。

```python
client = GengWiki(meme_frequency=0.3, quote_frequency=0.2, sticker_frequency=0.5)

system = client.tools.guide()      # 放进系统提示词，不随回复变化
turn = client.turn(用户的话)         # 每条回复调用一次，不调用模型
messages = [
    {"role": "system", "content": system},
    {"role": "user", "content": f"{用户的话}\n\n{turn.prompt}"},
]
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `meme_frequency` | 0.2 | 掷中时 `turn.prompt` 带上一批梗，并要求模型尽量用上一个。模型被问到时仍然可以查梗 |
| `quote_frequency` | 1 | 掷中时带上语录。`use` 和 `both` 掷中后这条回复可以只发语录原话，和梗同时掷中时二选一。Key 没有关联带语录的人物，或者 `quotes="off"` 时无效 |
| `sticker_frequency` | 1 | 掷中时带上表情说明 |

- 没掷中时不带素材，`turn.prompt` 里会写明这条回复不要主动用。`turn.memes`、`turn.quotes` 和 `turn.stickers` 是这次掷的结果，可以用来拿掉工具，比如没掷中时不给模型 `search_stickers`。
- 用户的话里提到“表情”“斗图”“来张图”“发张图”时算表情掷中，提到“语录”“名言”“金句”时算语录掷中，只有频率为 0 时例外。
- 频率为 0 时不带素材，`search_stickers` 工具也不再返回结果。直接调用 `client.search_stickers()` 不受频率影响。
- 频率为 1 时，表情说明和语录留在 `guide()` 里，方便模型服务的提示词缓存，这也是一直以来的行为。频率在 0 和 1 之间时，它们只在掷中的回复里出现，所以只调用 `guide()` 不调用 `turn()` 的话，模型拿不到它们。

`client.meme_prompt()` 不掷骰子，措辞也更谨慎，模型只在非常贴切时才用。想按频率来就用 `client.turn()`。

## Key 存在哪里

Key 和登录令牌默认存在 `~/.gengwiki/<站点>/keys.json`，是只有当前用户能读的明文文件，和 `~/.aws/credentials` 一样。想放进系统钥匙串（Windows 凭据管理器、macOS 钥匙串、Linux Secret Service），就装上下面这个可选依赖。

```bash
pip install "gengwiki[keychain]"
```

装好后，下一次保存时密钥就会移进钥匙串，文件里只留一个引用。没有钥匙串的环境（比如 Docker 容器）会继续用文件并记一条警告。之后卸载这个依赖时，文件里的引用读不出来，会明确报错，不会丢数据。

## 开发

```bash
uv run python -m unittest discover -s tests -t .
```

`tests/test_live.py` 用来对照真实服务，只有设置了 `GENGWIKI_LIVE_API` 和 `GENGWIKI_LIVE_SITE` 才会运行，需要指向一套载入了 `tests/live_seed.sql` 的临时环境，绝对不要指向生产环境。
