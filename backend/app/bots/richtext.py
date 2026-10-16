"""Keeps owner-written copy valid for Telegram's HTML parse mode.

The editor toolbar wraps text in a few tags (bold, italic, spoiler...). Anything
else, and any tag left open or closed out of order, would make Telegram reject
the whole message, so we rebuild the text with only balanced, allowed tags and
escape everything else.
"""

import html
from html.parser import HTMLParser

_ALIASES = {"strong": "b", "em": "i", "ins": "u", "strike": "s", "del": "s"}
_ALLOWED = {"b", "i", "u", "s", "code", "pre", "blockquote", "tg-spoiler", "a"}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _ALIASES.get(tag, tag)
        if tag == "span" and ("class", "tg-spoiler") in attrs:
            tag = "tg-spoiler"
        if tag not in _ALLOWED:
            return
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if not href.startswith(("https://", "http://", "tg://")):
                return
            self.out.append(f'<a href="{html.escape(href, quote=True)}">')
        else:
            self.out.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = _ALIASES.get(tag, tag)
        if tag == "span" and "tg-spoiler" in self.stack:
            tag = "tg-spoiler"
        if tag not in self.stack:
            return
        # Close anything opened inside it first so the nesting stays valid.
        while self.stack:
            current = self.stack.pop()
            self.out.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        self.close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def sanitize(text: str | None) -> str:
    if not text:
        return ""
    parser = _Sanitizer()
    parser.feed(text)
    return parser.result()
