"""在异步程序里使用。放到线程里调用，就不会卡住事件循环。"""

import asyncio

from gengwiki import GengWiki

client = GengWiki()


async def main():
    # 同时查询多个词，可以共用同一个客户端
    results = await asyncio.gather(
        asyncio.to_thread(client.search_memes, "躺平"),
        asyncio.to_thread(client.search_memes, "摆烂"),
        asyncio.to_thread(client.trending),
    )
    print(results)


asyncio.run(main())
