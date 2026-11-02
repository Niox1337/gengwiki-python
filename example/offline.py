"""提前下载内容，之后断网也能用。"""

from gengwiki import GengWiki

client = GengWiki()

# 下载这个 Key 能看到的全部内容，中断后再运行会接着下载
print(client.sync(images=True))

# 这些读取都来自本地
print(client.search_memes("躺平"))
print(client.persona())

# 想看最新内容时，让下一次读取走网络
client.refresh()
print(client.search_memes("躺平"))

# 这个客户端实际发出的请求数
print(client.request_count)
