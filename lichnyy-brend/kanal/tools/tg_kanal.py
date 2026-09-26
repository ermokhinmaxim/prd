#!/usr/bin/env python3
"""Выгрузка публичного Telegram-канала в Markdown через веб-превью t.me/s/<канал>.

Работает только с публичными каналами. Закрытые каналы и чаты так не читаются.

    python3 lichnyy-brend/kanal/tools/tg_kanal.py ermokhinpr               # все посты в stdout
    python3 lichnyy-brend/kanal/tools/tg_kanal.py prkonorova --limit 20    # последние 20
    python3 lichnyy-brend/kanal/tools/tg_kanal.py ermokhinpr --out DIR     # по файлу на пост
"""
import argparse
import html
import os
import re
import sys
import urllib.request

POST_RE = re.compile(r'(?=<div class="tgme_widget_message_wrap)')


def fetch(channel, before=None):
    url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def to_md(fragment):
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = re.sub(r'<i class="emoji"[^>]*><b>(.*?)</b></i>', r"\1", s, flags=re.S)
    s = re.sub(r"<(b|strong)>(.*?)</\1>", r"**\2**", s, flags=re.S)
    s = re.sub(r"<(i|em)>(.*?)</\1>", r"_\2_", s, flags=re.S)
    s = re.sub(r"<(s|del)>(.*?)</\1>", r"~~\2~~", s, flags=re.S)
    s = re.sub(r"<tg-spoiler>(.*?)</tg-spoiler>", r"||\1||", s, flags=re.S)
    s = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>",
               lambda m: "\n".join("> " + l for l in m.group(1).split("\n")), s, flags=re.S)

    def link(m):
        href, label = m.group(1), m.group(2)
        plain = re.sub(r"<[^>]+>|\*", "", label).strip()
        if plain == href or plain.startswith(("http", "@", "#")):
            return label
        return f"[{label}]({href})"

    s = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', link, s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse(page, channel):
    posts = []
    for block in POST_RE.split(page):
        m = re.search(rf'data-post="{re.escape(channel)}/(\d+)"', block, re.I)
        if not m:
            continue
        text = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        date = re.search(r'<time datetime="([^"]+)"', block)
        views = re.search(r'tgme_widget_message_views">([^<]+)<', block)
        fwd = re.search(r'tgme_widget_message_forwarded_from_name"[^>]*>(.*?)</', block, re.S)
        preview = re.search(r'tgme_widget_message_link_preview"[^>]*href="([^"]+)"', block)
        reactions = re.findall(r'<span class="tgme_reaction">.*?<b>(.*?)</b>.*?</i>([^<]+)</span>', block, re.S)
        posts.append({
            "id": int(m.group(1)),
            "date": date.group(1)[:10] if date else "",
            "views": views.group(1) if views else "",
            "forwarded": to_md(fwd.group(1)) if fwd else "",
            "photos": block.count("tgme_widget_message_photo_wrap"),
            "videos": block.count("tgme_widget_message_video_player"),
            "preview": preview.group(1) if preview else "",
            "reactions": " ".join(f"{e}{n}" for e, n in reactions),
            "text": to_md(text.group(1)) if text else "",
        })
    return posts


def collect(channel, limit):
    seen, before = {}, None
    while len(seen) < limit:
        batch = parse(fetch(channel, before), channel)
        fresh = [p for p in batch if p["id"] not in seen]
        if not fresh:
            break
        for p in fresh:
            seen[p["id"]] = p
        before = min(p["id"] for p in fresh)
    return sorted(seen.values(), key=lambda p: p["id"])[-limit:]


def render(p, channel):
    meta = [f"Дата: {p['date']}", f"Ссылка: https://t.me/{channel}/{p['id']}"]
    if p["views"]:
        meta.append(f"Просмотры: {p['views']}")
    if p["reactions"]:
        meta.append(f"Реакции: {p['reactions']}")
    media = []
    if p["photos"]:
        media.append(f"фото: {p['photos']}")
    if p["videos"]:
        media.append(f"видео: {p['videos']}")
    if media:
        meta.append("Медиа: " + ", ".join(media))
    if p["forwarded"]:
        meta.append(f"Репост из: {p['forwarded']}")
    if p["preview"]:
        meta.append(f"Превью ссылки: {p['preview']}")
    return f"# Пост {p['id']}\n\n" + "\n".join(meta) + "\n\n---\n\n" + p["text"] + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("channel", help="имя канала без @, например ermokhinpr")
    ap.add_argument("--limit", type=int, default=200, help="сколько последних постов взять")
    ap.add_argument("--out", help="папка: по файлу на пост вместо вывода в stdout")
    args = ap.parse_args()

    channel = args.channel.lstrip("@").split("/")[-1]
    posts = [p for p in collect(channel, args.limit) if p["text"] or p["photos"] or p["videos"]]
    if not posts:
        sys.exit(f"Постов не найдено: канал {channel} закрыт, пуст или недоступен")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        for p in posts:
            path = os.path.join(args.out, f"{p['date']}-{p['id']:04d}.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(render(p, channel))
        print(f"{len(posts)} постов → {args.out}")
    else:
        print("\n\n".join(render(p, channel) for p in posts))


if __name__ == "__main__":
    main()
