"""处理错误。所有错误都继承自 GengWikiError。"""

from gengwiki import AuthError, ForbiddenError, GengWiki, GengWikiError, NotFoundError, RateLimitError

client = GengWiki()

try:
    print(client.meme("不存在的梗").body)
except NotFoundError as e:
    # 没找到，错误信息里会列出相近的结果
    print(e.message)
except AuthError:
    print("Key 无效或已吊销")
except ForbiddenError:
    print("Key 没有这项权限，或者配额用完了")
except RateLimitError as e:
    print(f"请求太多，{e.retry_after} 秒后再试")
except GengWikiError as e:
    # 其他错误，比如服务器故障或者断网
    print(e.status, e.code, e.message)
