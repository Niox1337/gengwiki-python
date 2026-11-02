"""浏览和切换人设。一个 Key 绑定一个人设，所以切换人设就是切换 Key。"""

from gengwiki import GengWiki

client = GengWiki()

# 当前 Key 绑定的人设，没有绑定时是 None
current = client.persona()
if current:
    print(current.title, current.prompt)

# 浏览人设目录
for persona in client.personas():
    print(persona.title, persona.description)

# 切换，之后的搜索也会换成这个 Key 的范围
persona = client.use_persona("温柔姐姐")

# 直接放进消息列表
messages = [persona.as_message(), {"role": "user", "content": "你好"}]
print(messages)
