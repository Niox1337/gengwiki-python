"""搜索梗，查看详情和热门榜。运行前先用 gengwiki keys add 保存 Key。"""

from gengwiki import GengWiki

client = GengWiki()

# 搜索，标题和别名都能搜到
for meme in client.search_memes("躺平", limit=5):
    print(meme.title, meme.summary)

# 查看详情，可以用 slug，也可以用标题或别名
meme = client.meme("躺平")
print(meme.body)
print(meme.usage_scenario)
print(meme.usage_examples)

# 全站热门榜
for meme in client.trending(limit=10):
    print(meme.title, meme.heat)
