"""在终端里和人设聊天，这里用 DeepSeek。直接回车退出。需要 pip install openai。"""

import os

from openai import OpenAI

from gengwiki import GengWiki

client = GengWiki()
llm = OpenAI(base_url="https://api.deepseek.com", api_key=os.environ.get("DEEPSEEK_API_KEY"))

# 选一个人设，它决定了说话风格和能查到的梗
persona = client.use_persona("毒舌老哥")
# 人设只管性格，查梗和发表情的步骤由 guide 告诉模型
messages = [{"role": "system", "content": f"{persona.prompt}\n\n{client.tools.guide()}"}]

while question := input("你 "):
    messages.append({"role": "user", "content": question})

    # 模型要用工具就执行，然后把结果交还给它，直到它不再需要工具
    while True:
        reply = llm.chat.completions.create(model="deepseek-chat", messages=messages, tools=client.tools.openai()).choices[0].message
        messages.append(reply)
        results = client.tools.run(reply)
        if not results:
            break
        messages += results

    print(persona.title, reply.content)
