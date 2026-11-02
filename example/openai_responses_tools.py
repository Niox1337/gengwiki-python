"""让 OpenAI 的模型自己查梗，用 Responses 接口。需要 pip install openai。"""

from openai import OpenAI

from gengwiki import GengWiki

client = GengWiki()
llm = OpenAI()

items = [{"role": "user", "content": "躺平是什么意思？"}]

# 模型要用工具就执行，然后把结果交还给它，直到它不再需要工具
while True:
    response = llm.responses.create(model="gpt-5", input=items, tools=client.tools.responses())
    results = client.tools.run(response)
    if not results:
        break
    items += [*response.output, *results]

print(response.output_text)
