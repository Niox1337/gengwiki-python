# 更新日志

## 0.11.0

- 没有 Key 也能用，只有梗Wiki 热门的 20 个梗和 10 个人物。第一次调用 `client.turn()` 时返回的 `notice` 会提醒去哪里拿 Key。
- 新增 `guest_memes` 参数，设为 `False` 时没有 Key 就不玩梗，只保留这条提醒。
- 新增 `add_word`、`add_sticker`、`add_persona` 和 `add_person`，添加只有自己的 Key 能用的内容，不用审核。对应的 `remove_word`、`remove_sticker`、`remove_persona` 和 `remove_person` 用来删除。
- 用户的话里出现个人词库的词时，`client.turn()` 会把解释带给模型。
