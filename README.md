# gengwiki-python

梗Wiki 的 Python SDK。先读本地，网络只是兜底。不依赖任何第三方库，支持 Python 3.10 及以上。

```python
from gengwiki import GengWiki

client = GengWiki("gwk_live_xxx")          # 也可以用环境变量 GENGWIKI_API_KEY

client.search_memes("躺平")                 # 第一次发 1 个请求
client.search_memes("摆烂")                 # 不发请求
client.meme("tang-ping").body              # 取详情，之后不再请求
client.persona().as_message()              # {"role": "system", "content": "..."}
client.request_count                       # 实际发出的请求数
```

## 请求是怎么省下来的

| 数据 | 做法 | 请求数 |
| --- | --- | --- |
| 梗搜索 | 第一次拉取 Key 范围内的列表，之后在本地按服务器相同的规则搜索和排序 | 6 小时 1 次 |
| 梗详情 | 正文存本地，用列表里的 `updated_at` 判断是否过期，没改过就不重新下载，不同 Key 共用一份 | 每个梗每次改动 1 次 |
| 范围外的梗 | 列表完整时直接判定不存在 | 0 |
| 人设 | 服务器没有编辑人设的接口，所以缓存 7 天 | 7 天 1 次 |
| 表情搜索 | 表情包列表没有条数上限，所以总在本地搜索 | 6 小时 1 次 |
| 表情图片 | 图片内容不变，存到磁盘后永久复用，不占 Key 额度 | 每张 1 次 |
| 热门榜 | 总是拉满 100 条再截取，所有 Key 共用，缓存 15 分钟 | 15 分钟 1 次 |
| 词库 | 写入时同步更新本地缓存，不需要重新读取 | 1 小时 1 次 |
| 查询失败 | 不存在的结果也会记住 1 小时，避免模型反复查同一个词 | 1 小时 1 次 |
| 用量和限流 | 总是实时读取 | 每次 1 次 |

服务器宕机、网络断开或触发限流时，只要本地有旧数据就直接返回旧数据，并在 `gengwiki` 日志里记一条警告。Key 被吊销时不会这样处理，401 和 403 总是直接抛出。

```python
client.sync(images=True)   # 把这个 Key 能看到的内容全部下载下来，之后可以离线使用
client.refresh()           # 让下一次读取走网络，旧数据继续留作兜底
```

如果一个 Key 关联的梗超过 100 个，列表会被截断，因为接口没有分页。这时搜索改为按查询词请求服务器，每个查询词缓存 6 小时。

## API Key

Key 保存在 `~/.gengwiki/<API 域名>/keys.json`，权限是 0600。每个域名有独立的目录，所以一个域名的 Key 不会被发给另一个域名。可以用环境变量 `GENGWIKI_HOME` 改位置。优先级依次是参数 `api_key`、环境变量 `GENGWIKI_API_KEY`、最后选中的已保存 Key。

下面这些操作都不发请求，也不需要登录。

```python
client.keys.add("老哥", "gwk_live_xxx")     # 保存在网站上创建的 Key
client.keys.local()                         # 列出已保存的 Key，不含密钥
client.keys.use("老哥")                     # 切换，并设为以后的默认 Key
client.keys.secret("老哥")                  # 取出密钥交给别的程序
client.keys.remove("老哥")                  # 只从本机删除，服务器上依然有效
```

下面这些操作需要登录。密码不会保存，只保存 7 天有效的 token。

```python
client.keys.login("me@example.com", password)
client.keys.list()
client.keys.create("新 Key", persona="毒舌老哥", memes=["yyds"])   # 密钥只显示一次，所以会立即保存
client.keys.rotate("老哥")                                         # 换新密钥，本地缓存跟着迁移，不用重新下载
client.keys.revoke("老哥")                                         # 吊销并清除本地数据
client.keys.logout()
```

## 切换人设

一个 Key 终身绑定一个人设，所以切换人设就是切换到绑定了它的 Key。

```python
persona = client.use_persona("温柔姐姐")     # 按标题或 id
messages = [persona.as_message(), {"role": "user", "content": "你好"}]
```

SDK 依次这样查找。

1. 已保存的 Key 里已知绑定了这个人设的，直接切换。
2. 还没查过人设的已保存 Key，各查一次并记下来。
3. 如果已登录，从人设目录里找到它，创建一个新 Key 并保存，和网站一样带上它关联的梗和表情包。
4. 都没有就抛出 `NotFoundError`，说明可以怎么做。切换失败时当前人设不变。

切换过一次之后，来回切换不再发任何请求，选择也会在下次启动时恢复。`client.personas("关键词")` 可以浏览人设目录。

## 给大模型用的工具

```python
tools = client.tools.openai()        # OpenAI、DeepSeek 等
tools = client.tools.anthropic()     # Claude

while True:
    reply = llm.chat.completions.create(model=model, messages=messages, tools=tools).choices[0].message
    results = client.tools.run(reply)
    if not results:
        break
    messages += [reply, *results]
```

`run` 能处理两家 SDK 返回的对象，也能处理普通字典。Claude 的回复用法相同，只是追加时写成 `{"role": "assistant", "content": reply.content}`。

共有 5 个工具，分别是 `search_memes`、`get_meme`、`trending_memes`、`search_stickers` 和 `search_lexicon`。返回内容只留模型需要的字段，以节省 token。出错时返回 JSON 形式的错误而不是抛异常，模型可以看到错误并自己调整。可以用 `client.tools.openai(["search_memes"])` 只选其中几个。

## 错误

全部继承自 `GengWikiError`，都带 `status`、`code` 和 `message`。

| 异常 | 含义 |
| --- | --- |
| `AuthError` | Key 无效或已吊销，或登录已过期 |
| `ForbiddenError` | Key 缺少 scope，或配额用完 |
| `NotFoundError` | 不存在，或不在这个 Key 的范围内 |
| `RateLimitError` | 触发限流，且本地没有旧数据，`retry_after` 是要等的秒数 |
| `ServerError` `NetworkError` | 服务不可用，且本地没有旧数据 |
| `BadResponseError` | 响应状态正常但内容不对，比如公共 Wi-Fi 的登录页，且本地没有旧数据 |
| `AccountApiUnavailable` | 这个站点没有开放账号接口 |

## 开发

```bash
uv run python -m unittest discover -s tests -t .
```

`tests/fake.py` 是一个会统计请求数的假服务器。`tests/test_live.py` 用来对照真实服务，只有设置了 `GENGWIKI_LIVE_API` 和 `GENGWIKI_LIVE_SITE` 才会运行，需要指向一套载入了 `tests/live_seed.sql` 的临时环境，绝对不要指向生产环境。
