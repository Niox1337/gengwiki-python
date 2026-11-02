"""不用工具调用，先查好梗再放进提示词。适合不支持工具调用的模型。"""

from gengwiki import GengWiki

client = GengWiki()

# 把搜索结果拼成一段参考资料
memes = client.search_memes("躺平", limit=3)
context = "\n".join(f"{meme.title}，{meme.summary}" for meme in memes)

# 有人设时用人设，没有时用默认的说法
persona = client.persona()
role = persona.prompt if persona else "你是一个懂网络用语的助手。"

messages = [
    {"role": "system", "content": f"{role}\n\n可以参考这些梗\n{context}"},
    {"role": "user", "content": "同事说他要躺平，是什么意思？"},
]
print(messages)
