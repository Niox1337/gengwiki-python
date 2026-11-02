"""个人词库，记录自己的词语和含义。"""

from gengwiki import GengWiki

client = GengWiki()

# 新建词库
lexicon = client.create_lexicon("职场黑话", "工作里常听到的词")

# 添加词条
client.add_lexicon_entry(lexicon.id, "对齐", aliases=["拉齐"], note="统一大家的想法", tags=["职场"])

# 在所有词库里搜索
for entry in client.search_lexicons("拉齐"):
    print(entry.term, entry.note)

# 列出我的词库
for item in client.lexicons():
    print(item.name, item.entries)
