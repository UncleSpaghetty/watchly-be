import email.utils
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape

import httpx
from defusedxml import ElementTree

from app.providers.base import USER_AGENT


@dataclass
class FeedItem:
    url: str
    title: str
    published_at: datetime | None
    excerpt: str | None
    image_url: str | None


@dataclass
class FeedResult:
    items: list[FeedItem]
    etag: str | None
    last_modified: str | None
    not_modified: bool = False


def _text(element: object, tag: str) -> str | None:
    found = element.find(tag)  # type: ignore[attr-defined]
    return (found.text or "").strip() or None if found is not None else None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _clean_excerpt(value: str | None, limit: int = 280) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _safe_url(value: str | None) -> str | None:
    return value if value and value.startswith(("http://", "https://")) else None


class RssProvider:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FeedResult:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = self._client.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        if response.status_code == 304:
            return FeedResult([], etag, last_modified, not_modified=True)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        items: list[FeedItem] = []
        for node in root.iter("item"):
            link = _safe_url(_text(node, "link"))
            title = _text(node, "title")
            if not link or not title:
                continue
            image = None
            for child in node:
                tag = child.tag.rsplit("}", 1)[-1]
                if tag in {"content", "thumbnail", "enclosure"}:
                    image = _safe_url(child.get("url"))
                    if image:
                        break
            items.append(
                FeedItem(
                    url=link,
                    title=unescape(title),
                    published_at=_parse_date(_text(node, "pubDate")),
                    excerpt=_clean_excerpt(_text(node, "description")),
                    image_url=image,
                )
            )
        return FeedResult(
            items, response.headers.get("ETag"), response.headers.get("Last-Modified")
        )
