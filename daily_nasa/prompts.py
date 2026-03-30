from __future__ import annotations

import json
import re
from typing import Any

from .common import normalize_whitespace
from .rendering import build_article_blocks


READER_MARKER_1 = "关键信息"
READER_MARKER_2 = "对你意味着什么"
READER_MARKER_3 = "下一步关注点"
MIN_CHINESE_CHARS = 500
MISSION_HINT_TERMS = (
    "artemis ii",
    "artemis",
    "clps",
    "intuitive machines",
    "iss",
    "kennedy",
    "阿尔忒弥斯",
    "登月",
    "月面",
    "月球",
    "空间站",
    "肯尼迪",
)
FAN_PERSPECTIVE_TERMS = (
    "航天迷",
    "太空爱好者",
    "追任务",
    "值得追踪",
    "我们最该盯",
)


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    return f"""
You are a NASA enthusiast and a senior Chinese science editor for WeChat.
Write a high-value Chinese NASA briefing from an aerospace fan perspective.

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
3) Title length 14-28 Chinese chars, with a number signal and mission keyword.
4) No external links, no anchor tags, no source-jump wording.
5) Body must have >= 500 Chinese characters.
6) Write news cards in a natural, direct style. No section labels like "关键信息"、"对你意味着什么"、"下一步关注点". Just write the content as flowing paragraphs or use visual hierarchy (bold/headings) to organize.
7) Prioritize factual density: include concrete mission names, stages, timelines, budgets, or technical targets.
8) Write like you're explaining to a friend who knows a bit about space. Be direct, skip the template phrases like "随着...临近"、"值得关注"、"帮助你了解"、"内容详细梳理"、"对你意味着什么"、"下一步关注点".
9) HTML rule: no leading whitespace after opening tags. Content must directly follow tags like <p>content</p> not <p> content</p>.
10) Visual rule: side margin/padding must be 0 (or omitted). Do not set custom left/right spacing.
11) Title must be tied to source stories, using at least one concrete mission/entity from materials (e.g. Artemis II / CLPS / Intuitive Machines). Title should be creative and content-driven, not templated. Never use: 倒计时 / 里程碑 / 看点清单 / 变化判断 / 追踪提醒.
12) Each news card should include at least 2 concrete facts from source (time, amount,机构,里程碑).
13) Tone: write as "航天爱好者带读" instead of neutral newswire. No templated section headers.
14) Keep rich WeChat visual style: cards, contrast blocks, and clear hierarchy (h1/h3/strong).

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
- No section labels like "关键信息"、"对你意味着什么"、"下一步关注点". Write flowing paragraphs or use visual hierarchy.
- No links or source jumps.
- Keep factual details and reader usefulness.
- HTML must have no leading whitespace after opening tags.
- Side margin/padding must be 0 (or omitted).
- Title must include at least one concrete mission/entity from source materials. Title should be creative and content-driven, not templated. Never use: 倒计时 / 里程碑 / 看点清单 / 变化判断 / 追踪提醒.
- Write from NASA enthusiast perspective ("航天爱好者带读"), not plain agency bulletin style.
- Keep strong visual hierarchy (h1 + card style + emphasized key lines).
"""


def build_story_terms(articles: list[dict[str, Any]]) -> list[str]:
    text = " ".join(
        normalize_whitespace(
            f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')}"
        )
        for article in articles
    ).lower()
    terms: list[str] = []
    if "artemis ii" in text:
        terms.extend(["artemis ii", "阿尔忒弥斯ii", "阿尔忒弥斯2号", "阿尔忒弥斯2"])
    if "intuitive machines" in text:
        terms.extend(["intuitive machines", "月面投送", "商业月面"])
    if "clps" in text:
        terms.extend(["clps", "月面载荷服务"])
    if "kennedy" in text:
        terms.extend(["肯尼迪", "发射场"])
    if "iss" in text or "space station" in text or "spacestation" in text:
        terms.extend(["iss", "空间站"])
    if "lunar" in text or "moon" in text:
        terms.extend(["登月", "月球", "月面"])
    if "artemis" in text:
        terms.extend(["artemis", "阿尔忒弥斯"])

    if not terms and articles:
        lead_title = normalize_whitespace(str(articles[0].get("title", "")))
        terms.extend([token.lower() for token in re.findall(r"[A-Za-z]{3,}(?:\s+[A-Za-z0-9]{2,})?", lead_title)[:3]])
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", lead_title):
            if token not in {"今日", "今天", "动态", "进展", "任务", "更新", "关键"}:
                terms.append(token.lower())

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = term.strip().lower()
        if len(clean_term) < 2 or clean_term in seen:
            continue
        seen.add(clean_term)
        deduped.append(clean_term)
    return deduped[:8]
