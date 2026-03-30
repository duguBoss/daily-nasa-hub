from __future__ import annotations

import json
import re
from typing import Any

from .common import normalize_whitespace
from .rendering import build_article_blocks


MIN_CHINESE_CHARS = 500
MISSION_HINT_TERMS = (
    "artemis",
    "artemis ii",
    "clps",
    "intuitive machines",
    "iss",
    "space station",
    "kennedy",
    "roman",
    "webb",
    "hubble",
    "nisar",
    "moon",
    "lunar",
    "launch",
    "月球",
    "月面",
    "登月",
    "空间站",
    "深空",
    "火箭",
    "发射",
    "望远镜",
    "彗星",
)
FAN_PERSPECTIVE_TERMS = (
    "航天迷",
    "航天爱好者",
    "太空迷",
    "如果你也在追",
    "抬头看天",
    "我最想先讲",
)


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    return f"""
You are a NASA enthusiast and a senior Chinese science editor for WeChat.
Write a polished Chinese NASA daily briefing that is vivid, accurate, and obviously grounded in the source materials.

Date: {date_str}
News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles to avoid duplication:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

MANDATORY OUTPUT RULES:
1) Output valid JSON only.
2) All user-facing body text must be Simplified Chinese.
3) Title length 14-28 Chinese chars, and it must include a number signal plus at least one concrete mission/entity from the materials.
4) No external links, no anchor tags, no source-jump wording, no "原文如下" style copy.
5) Body must have >= 500 Chinese characters.
6) The article structure must contain exactly 3 content cards when 3 materials are provided:
   - Card 1: fixed as "NASA每日科普". It should read like a science explainer based on the first material, usually APOD/image/science content.
   - Card 2 and Card 3: fixed as news cards. They must be based on the second and third source materials respectively.
7) Never merge facts across cards. Each card may only use details from its corresponding source block.
8) Each card must contain at least 2 concrete source facts: mission name, agency/company, date, location, payload, quantity, milestone, or technical target.
9) Card 1 should explain what the reader is seeing/understanding, then why it matters scientifically. It should feel like a daily NASA science read, not a news brief.
10) Card 2 and Card 3 should each use 2-3 natural paragraphs: first explain what happened, then explain why this development matters. Keep the interpretation tightly inferable from the source.
11) Avoid templated phrases and newsroom cliches, especially: "这条消息聚焦", "帮助你快速理解", "值得关注", "内容详细梳理", "对你意味着什么", "下一步关注点", "今天的NASA速报就到这里".
12) Write like a knowledgeable aerospace fan explaining the day to other readers. Natural, direct, lively, but never exaggerated.
13) Keep strong WeChat visual hierarchy. Use one H1 title, styled content cards, and a clear divider between Card 1 and Card 2 with the label "今日NASA新闻".
14) Each card must include its image at the top. Use the article Image field from the materials.
15) Preserve important English mission/entity names on first mention when needed, and explain them naturally in Chinese instead of forcing awkward translation.
16) HTML rule: no leading whitespace right after opening tags.
17) Side margin/padding must be 0 (or omitted) on the outer wrapper.

JSON schema:
{{
  "date": "{date_str}",
  "title": "...",
  "covers": ["up to 5 image urls"],
  "songs": [{{"name": "news title", "artist": "channel"}}],
  "weixin_html": "<section>...</section>"
}}
"""


def build_gemini_rewrite_prompt(
    date_str: str,
    articles: list[dict[str, Any]],
    previous_payload: dict[str, Any],
    quality_report: dict[str, Any],
    attempt: int,
) -> str:
    issues = quality_report.get("issues", [])[:12]
    return f"""
Rewrite the JSON article to pass quality gate score >= 80.
This is rewrite attempt #{attempt} (max 3 attempts total).

News materials:
{build_article_blocks(articles)}

Current draft JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Quality report:
{json.dumps(quality_report, ensure_ascii=False)}

Fix these issues first:
{json.dumps(issues, ensure_ascii=False)}

Hard constraints:
- JSON-only output.
- >= 500 Chinese chars in body.
- Keep exactly one H1 and 3 clearly separated cards when 3 materials are provided.
- Card 1 must be labeled "NASA每日科普"; Card 2 and Card 3 must be news cards.
- Add a visible divider labeled "今日NASA新闻" between Card 1 and Card 2.
- Each card must stay faithful to its own source. Do not borrow facts, names, dates, or conclusions from another card.
- No links or source jumps.
- No templated phrases such as "这条消息聚焦" / "帮助你快速理解" / "对你意味着什么" / "下一步关注点".
- Every card needs concrete source facts, not generic filler.
- Title must include at least one concrete mission/entity from source materials and must not use forbidden generic title patterns.
- Write from a NASA enthusiast perspective, but keep the tone grounded and readable.
- HTML must have no leading whitespace after opening tags.
- Side margin/padding must be 0 (or omitted).
"""


def build_story_terms(articles: list[dict[str, Any]]) -> list[str]:
    text = " ".join(
        normalize_whitespace(
            f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}"
        )
        for article in articles
    )
    text_lower = text.lower()
    terms: list[str] = []

    canonical_terms = [
        "Artemis II",
        "Artemis",
        "CLPS",
        "Intuitive Machines",
        "ISS",
        "Kennedy",
        "Roman",
        "Webb",
        "Hubble",
        "NISAR",
        "Moon",
        "Lunar",
    ]
    for term in canonical_terms:
        if term.lower() in text_lower:
            terms.append(term.lower())

    terms.extend(token.lower() for token in re.findall(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", text))
    terms.extend(token.lower() for token in re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", text))

    lead_title = normalize_whitespace(str(articles[0].get("title", ""))) if articles else ""
    for token in re.findall(r"[\u4e00-\u9fff]{2,8}", lead_title):
        if token not in {"今日", "动态", "进展", "任务", "更新", "焦点", "科普", "新闻"}:
            terms.append(token.lower())

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = normalize_whitespace(term).strip().lower()
        if len(clean_term) < 2 or clean_term in seen:
            continue
        seen.add(clean_term)
        deduped.append(clean_term)
    return deduped[:12]
