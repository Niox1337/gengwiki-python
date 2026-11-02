"""自己挑选和执行工具，适合接入其他框架。不需要安装大模型的 SDK。"""

from gengwiki import GengWiki

client = GengWiki()

# 只给模型其中两个工具
print(client.tools.openai(["search_memes", "get_meme"]))

# 自己执行一次，参数可以是字典，也可以是 JSON 字符串，返回 JSON 字符串
print(client.tools.call("search_memes", {"q": "躺平", "limit": 3}))
print(client.tools.call("get_meme", '{"slug": "tang-ping"}'))

# 出错时不抛异常，而是把错误返回给模型
print(client.tools.call("get_meme", {"slug": "不存在的梗"}))
