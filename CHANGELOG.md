# 更新日志

## 0.12.0

- 新增 `semantic` 参数，默认 `False`。设为 `True` 后，`client.turn()` 掷中时会把用户的话发给梗Wiki，服务器挑出意思相近的梗和语录排在前面，其余位置仍然随机。需要 Key。请求最多等 1.5 秒，失败或服务器没有排序时照常用随机素材，并在 60 秒内不再请求。
- `search_stickers` 找不到字面匹配的表情时，服务器会按意思找相近的表情。

## 0.11.1

- 默认地址换成新域名 https://api.gengwiki.com 和 https://gengwiki.com。旧域名暂时还能用，会转到新地址。

## 0.11.0

- 没有 Key 也能用，只有梗Wiki 热门的 20 个梗和 10 个人物。第一次调用 `client.turn()` 时返回的 `notice` 会提醒去哪里拿 Key。
- 新增 `guest_memes` 参数，设为 `False` 时没有 Key 就不玩梗，只保留这条提醒。
- 新增 `add_word`、`add_sticker`、`add_persona` 和 `add_person`，添加只有自己的 Key 能用的内容，不用审核。对应的 `remove_word`、`remove_sticker`、`remove_persona` 和 `remove_person` 用来删除。
- 用户的话里出现个人词库的词时，`client.turn()` 会把解释带给模型。
