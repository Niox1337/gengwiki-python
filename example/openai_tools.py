"""让 OpenAI 的模型自己查梗，用 Chat Completions 接口。需要 pip install openai。"""

from openai import OpenAI

from gengwiki import GengWiki

client = GengWiki()
llm = OpenAI()

messages = [{"role": "user", "content": "躺平是什么意思？"}]

# 模型要用工具就执行，然后把结果交还给它，直到它不再需要工具
while True:
    reply = llm.chat.completions.create(model="gpt-5", messages=messages, tools=client.tools.openai()).choices[0].message
    results = client.tools.run(reply)
    if not results:
        break
    messages += [reply, *results]

print(reply.content)
