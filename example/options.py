"""客户端的常用选项。"""

from gengwiki import GengWiki

# 自建服务时可以传入 base_url 和 site_url，或者设置环境变量 GENGWIKI_API_URL 和 GENGWIKI_SITE_URL
# 想改数据目录可以传入 home，或者设置环境变量 GENGWIKI_HOME

# 用 with 写法时，结束后会自动关闭本地缓存
with GengWiki(timeout=5) as client:
    print(client.search_memes("躺平"))
