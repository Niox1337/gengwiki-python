"""让 Claude 自己查梗，并带上人设。需要 pip install anthropic。"""

from anthropic import Anthropic

from gengwiki import GengWiki

client = GengWiki()
llm = Anthropic()

# Claude 的系统提示不放在消息列表里
persona = client.persona()
system = persona.prompt if persona else "你是一个懂网络用语的助手。"

messages = [{"role": "user", "content": "躺平是什么意思？"}]

# 模型要用工具就执行，然后把结果交还给它，直到它不再需要工具
while True:
    reply = llm.messages.create(model="claude-opus-5-5", max_tokens=1024, system=system, messages=messages, tools=client.tools.anthropic())
    results = client.tools.run(reply)
    if not results:
        break
    messages += [{"role": "assistant", "content": reply.content}, *results]

print(reply.content[0].text)
