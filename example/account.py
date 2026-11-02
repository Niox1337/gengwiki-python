"""登录后管理账号上的 Key。"""

from getpass import getpass

from gengwiki import GengWiki

client = GengWiki()

# 密码不会保存，只保存 7 天有效的 token
client.keys.login("me@example.com", getpass("密码 "))

# 列出账号上的 Key
for key in client.keys.list():
    print(key.name, key.prefix, key.last_used_at)

# 创建一个绑定人设的 Key，密钥只显示一次，所以会自动保存
key = client.keys.create("测试用", persona="毒舌老哥")

# 换新密钥，旧密钥立即失效，本地缓存继续可用
client.keys.rotate(key.name)

# 吊销，并清除本地数据
client.keys.revoke(key.name)

client.keys.logout()
