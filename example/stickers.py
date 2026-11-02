"""搜索表情包并下载图片。"""

from gengwiki import GengWiki

client = GengWiki()

# 按配文、表情包名称或标签搜索
for sticker in client.search_stickers("震惊", limit=3):
    print(sticker.caption, sticker.pack_title, sticker.url)

    # 下载到本地并返回路径，第二次不再下载
    print(client.sticker_image(sticker.id))

# 列出这个 Key 能用的表情包
for pack in client.sticker_packs():
    print(pack.title, len(pack.stickers))
