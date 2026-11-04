"""查询人物，并选择模型怎么对待他们的语录。"""

from gengwiki import GengWiki

# off 不使用、cite 引用、use 直接使用、both 引用和使用
# quote_frequency 决定模型多主动地用语录，可选 low、medium、high
client = GengWiki(quotes="both", quote_frequency="medium")

for person in client.linked_people():
    print(person.name, person.bio)

for person in client.people("作家"):
    print(person.name, person.quotes[:1])

print(client.person("鲁迅").memes)

# Key 关联的人物和语录用法都在 guide 里，放在人设后面就行
print(client.tools.guide())
