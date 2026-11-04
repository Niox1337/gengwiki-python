"""The command line. Mostly for first-time setup, so a password or key never has to sit in a script or shell history."""

import argparse
import getpass
import sys

from . import GengWiki, GengWikiError, __version__


def _memes(rows) -> None:
    if not rows:
        print("没有找到")
    for m in rows:
        print(f"{m.title}  [{m.slug}]  {m.summary}")


def _login(c: GengWiki, a) -> None:
    user = c.keys.login(a.email or input("邮箱 "), getpass.getpass("密码 "))
    print(f"已登录 {user.get('email', '')}，7 天内有效，密码没有保存")


def _logout(c: GengWiki, a) -> None:
    c.keys.logout()
    print("已退出")


def _status(c: GengWiki, a) -> None:
    print(f"站点  {c.base_url}")
    print(f"登录  {'已登录' if c.keys.logged_in else '未登录'}")
    if not c._key:
        print(f"Key   没有，到 {c.site_url}/me 创建后运行 gengwiki keys add 名字")
        return
    saved = next((k for k in c.keys.local() if k.current), None)
    print(f"Key   {saved.name if saved else '来自参数或环境变量'}  {c._key[:15]}")
    persona = c.persona()
    print(f"人设  {persona.title if persona else '没有'}")
    try:
        r = c.rate_limit()
        print(f"额度  今天 {r.used_today}/{r.per_day}，这一分钟 {r.used_this_minute}/{r.per_minute}")
    except GengWikiError as e:
        print(f"额度  暂时查不到，{e.message}")


def _keys_local(c: GengWiki, a) -> None:
    rows = c.keys.local()
    if not rows:
        print(f"还没有保存 Key，到 {c.site_url}/me 创建后运行 gengwiki keys add 名字")
    for k in rows:
        print(f"{'*' if k.current else ' '} {k.name}  {k.prefix}  {k.persona_title or ''}".rstrip())


def _keys_add(c: GengWiki, a) -> None:
    print(f"已保存 {c.keys.add(a.name, getpass.getpass('粘贴 Key ').strip()).name}")


def _keys_use(c: GengWiki, a) -> None:
    print(f"已切换到 {c.keys.use(a.name).name}")


def _keys_remove(c: GengWiki, a) -> None:
    c.keys.remove(a.name)
    print(f"已从本机删除 {a.name}，服务器上依然有效")


def _keys_secret(c: GengWiki, a) -> None:
    print(c.keys.secret(a.name))


def _keys_remote(c: GengWiki, a) -> None:
    for k in c.keys.list():
        print(f"{k.name}  {k.prefix}  最后使用 {k.last_used_at or '从未'}")


def _keys_rotate(c: GengWiki, a) -> None:
    print(f"已换新密钥并保存到 {c.keys.rotate(a.name).name}，旧密钥立即失效")


def _keys_revoke(c: GengWiki, a) -> None:
    c.keys.revoke(a.name)
    print(f"已吊销 {a.name}")


def _personas(c: GengWiki, a) -> None:
    rows = c.personas(a.q)
    if not rows:
        print("没有找到")
    for p in rows:
        print(f"{p.title}  {p.description}".rstrip())


def _use(c: GengWiki, a) -> None:
    print(f"已切换到 {c.use_persona(a.persona).title}")


def _search(c: GengWiki, a) -> None:
    _memes(c.find_memes(a.q))


def _trending(c: GengWiki, a) -> None:
    _memes(c.trending(a.tag))


def _tags(c: GengWiki, a) -> None:
    for t in c.tags():
        print(f"{t.name}  {t.count}")


def _subscribe(c: GengWiki, a) -> None:
    if not a.tag:
        print("、".join(c.subscriptions()) or "还没有订阅标签")
        return
    rows = c.subscribe(a.tag)
    print(f"已订阅 {a.tag}")
    _memes(rows)


def _unsubscribe(c: GengWiki, a) -> None:
    print(f"已退订 {a.tag}" if c.unsubscribe(a.tag) else f"没有订阅 {a.tag}")


def _meme(c: GengWiki, a) -> None:
    m = c.meme(a.slug)
    print(m.title)
    if m.aliases:
        print("别名  " + "、".join(m.aliases))
    print(f"\n{m.body or m.summary}")
    if m.usage_scenario:
        print(f"\n使用场景  {m.usage_scenario}")
    for example in m.usage_examples:
        print(f"\n  {example}")


def _sync(c: GengWiki, a) -> None:
    s = c.sync(images=a.images)
    print(f"梗 {s['memes']} 个，表情 {s['stickers']} 个，图片 {s['images']} 张，发出 {s['requests']} 个请求")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gengwiki", description="梗Wiki 命令行")
    parser.add_argument("--version", action="version", version=__version__)
    parser.set_defaults(run=None)
    sub = parser.add_subparsers(metavar="命令")

    def command(parent, name, run, help_text, *args):
        p = parent.add_parser(name, help=help_text)
        p.set_defaults(run=run)
        for arg, kwargs in args:
            p.add_argument(arg, **kwargs)
        return p

    optional = {"nargs": "?", "default": ""}
    command(sub, "status", _status, "当前站点、Key、人设和额度")
    command(sub, "login", _login, "登录以管理 Key", ("email", optional))
    command(sub, "logout", _logout, "退出登录")
    command(sub, "search", _search, "搜索梗", ("q", optional))
    command(sub, "meme", _meme, "查看一个梗", ("slug", {}))
    command(sub, "trending", _trending, "热门榜", ("tag", optional))
    command(sub, "tags", _tags, "全部标签")
    command(sub, "subscribe", _subscribe, "订阅标签，不带标签时列出已订阅的", ("tag", optional))
    command(sub, "unsubscribe", _unsubscribe, "退订标签", ("tag", {}))
    command(sub, "personas", _personas, "浏览人设", ("q", optional))
    command(sub, "use", _use, "切换人设", ("persona", {}))
    command(sub, "sync", _sync, "下载全部内容供离线使用", ("--images", {"action": "store_true"}))

    keys = command(sub, "keys", _keys_local, "列出已保存的 Key").add_subparsers(metavar="操作")
    command(keys, "add", _keys_add, "保存在网站上创建的 Key", ("name", {}))
    command(keys, "use", _keys_use, "切换到已保存的 Key", ("name", {}))
    command(keys, "remove", _keys_remove, "只从本机删除", ("name", {}))
    command(keys, "secret", _keys_secret, "输出密钥，交给别的程序", ("name", {}))
    command(keys, "remote", _keys_remote, "列出账号上的 Key，需要登录")
    command(keys, "rotate", _keys_rotate, "换新密钥，需要登录", ("name", {}))
    command(keys, "revoke", _keys_revoke, "吊销并从本机删除，需要登录", ("name", {}))
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # A pipe on a non-Chinese Windows is cp1252, which would turn all the text into question marks.
            # On any encoding, one character it lacks must not end the program.
            encoding = stream.encoding if "梗".encode(stream.encoding, "ignore") else "utf-8"
            stream.reconfigure(encoding=encoding, errors="replace")
    parser = _parser()
    args = parser.parse_args(argv)
    if args.run is None:
        parser.print_help()
        return 0
    try:
        with GengWiki() as client:
            args.run(client, args)
    except (GengWikiError, ValueError) as e:
        print(f"错误  {getattr(e, 'message', e)}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
