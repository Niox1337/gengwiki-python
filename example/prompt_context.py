"""不用工具调用，先查好梗再放进提示词。适合不支持工具调用的模型。"""

from gengwiki import GengWiki

client = GengWiki()

# 这句话提到的梗排在最前面，再随机补一些，模型只在非常贴切时才用
question = "同事说他要躺平，是什么意思？"
context = client.meme_prompt(question)

# 有人设时用人设，没有时用默认的说法
persona = client.persona()
role = persona.prompt if persona else "你是一个懂网络用语的助手。"

messages = [
    {"role": "system", "content": f"{role}\n\n{context}"},
    {"role": "user", "content": question},
]
print(messages)
