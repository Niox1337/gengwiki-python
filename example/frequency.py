"""用代码决定多少比例的回复可以玩梗、用语录和发表情，模型再按语境决定用不用、用哪个。"""

from gengwiki import GengWiki

client = GengWiki(meme_frequency=0.3, quote_frequency=0.2, sticker_frequency=0.5)

# guide 不随回复变化，放进系统提示词
system = client.tools.guide()

# 每条回复掷一次，prompt 放在用户的话后面
question = "今天又要加班"
turn = client.turn(question)
messages = [
    {"role": "system", "content": system},
    {"role": "user", "content": f"{question}\n\n{turn.prompt}"},
]
print(turn.memes, turn.quotes, turn.stickers)

# 这条回复没掷中时，可以把发表情的工具也拿掉
names = [t["function"]["name"] for t in client.tools.openai()]
tools = client.tools.openai([n for n in names if turn.stickers or n != "search_stickers"])
print(messages, len(tools))
