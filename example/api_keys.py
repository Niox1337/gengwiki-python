"""管理保存在本机的 Key，这些操作不需要登录。"""

from gengwiki import GengWiki

client = GengWiki()

# 保存在网站上创建的 Key
client.keys.add("工作", "gwk_live_xxx")

# 列出已保存的 Key，这里不含密钥
for key in client.keys.local():
    print(key.name, key.prefix, key.current)

# 切换，以后新建的客户端也会用它
client.keys.use("工作")

# 取出密钥，交给别的程序
secret = client.keys.secret("工作")

# 只从本机删除，服务器上依然有效
client.keys.remove("工作")

# 不想保存时，直接传入
other = GengWiki("gwk_live_yyy")
