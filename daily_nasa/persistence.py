from __future__ import annotations

import json
import os
from typing import Any


def save_news(
    articles: list[dict[str, Any]],
    payload: dict[str, Any],
    generation_meta: dict[str, Any],
    date_str: str,
    source_top_urls: list[str],
    new_urls: list[str],
) -> tuple[str, str]:
    json_file_name = f"Daily_NASA_{date_str}.json"
    markdown_file_name = f"Daily_NASA_{date_str}.md"

    json_data = {
        "date": payload["date"],
        "title": payload["title"],
        "covers": payload["covers"],
        "songs": payload["songs"],
        "weixin_html": payload["weixin_html"],
        "generation": generation_meta,
        "source_top_urls": source_top_urls,
        "new_urls": new_urls,
        "articles": [
            {
                "id": article["id"],
                "title": article["title"],
                "title_en": article.get("title_en", ""),
                "channel": article.get("channel", "NASA"),
                "summary": article.get("summary", ""),
                "url": article["url"],
                "publish_time": article.get("publish_time", ""),
                "image_url": article.get("image_url", ""),
                "image_path": article.get("image_path", ""),
                "cover_url": article.get("cover_url", ""),
            }
            for article in articles
        ],
    }

    with open(json_file_name, "w", encoding="utf-8") as file:
        json.dump(json_data, file, ensure_ascii=False, indent=2)

    lines = [f"# {payload['title']}", "", f"- 日期: {date_str}", ""]
    for idx, article in enumerate(articles, start=1):
        lines.extend(
            [
                f"## {idx}. {article['title']}",
                "",
                f"- 频道: {article.get('channel', 'NASA')}",
                f"- 链接: {article['url']}",
                "",
                article.get("summary", ""),
                "",
            ]
        )
    with open(markdown_file_name, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))

    print(f"Saved merged output to {json_file_name} and {markdown_file_name}")
    return json_file_name, markdown_file_name


def get_optional_api_key() -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    return api_key or None
