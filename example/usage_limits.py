"""查看额度和用量，这两个总是读取最新数据。"""

from gengwiki import GengWiki

client = GengWiki()

# 当前额度
limit = client.rate_limit()
print(f"今天 {limit.used_today}/{limit.per_day}，这一分钟 {limit.used_this_minute}/{limit.per_minute}")

# 最近 30 天每天的请求数
for day in client.usage()["days"]:
    print(day["day"], day["requests"])
