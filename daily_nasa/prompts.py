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
    "spacex",
    "payload",
    "登月",
    "月球",
    "发射",
    "载荷",
    "空间站",
    "望远镜",
)
FAN_PERSPECTIVE_TERMS = (
    "如果你最近在关注",
    "真正值得注意的是",
    "先抓住一个关键信息",
    "换句话说",
    "对NASA粉丝来说",
)
FORBIDDEN_TITLE_TERMS = (
    "3条",
    "三条",
    "要闻",
    "速报",
    "汇总",
    "盘点",
    "合集",
    "冲刺",
    "开扯",
    "扒一扒",
    "扒",
    "盘",
)
TITLE_STYLE_HINT = "标题要像成熟中文科技自媒体，不要像栏目名或低信息量摘要"
_GENERIC_STORY_TOKENS = {
    "nasa",
    "today",
    "daily",
    "update",
    "mission",
    "missions",
    "news",
    "story",
    "article",
    "science",
    "space",
    "最新",
    "动态",
    "消息",
    "进展",
    "节点",
    "科普",
    "新闻",
    "任务",
    "发布",
}


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
3) Title length 14-28 Chinese chars. It must contain at least one concrete mission, entity, place, payload, date, or scientific fact from the materials.
4) The title must read like a strong Chinese self-media headline: specific, information-dense, and curiosity-inducing, but still truthful.
5) Do not write generic count headlines like “3条NASA要闻”, “三条动态”, “今日速报”, or any low-information title that hides the real subject.
6) Do not use slang or internet-black-talk words such as “冲刺”, “开扯”, “盘”, “扒一扒”.
7) Prefer direct information in the title: mission name, payload count, launch node, crew move, telescope image, or scientific finding.
8) Avoid repeating “NASA” when the subject can be made clearer by naming the mission, spacecraft, company, telescope, or destination.
9) No external links, no anchor tags, no source-jump wording, and no “点击原文/来源如下” style copy.
10) Body must have >= 500 Chinese characters.
11) The article structure must contain exactly 3 content cards when 3 materials are provided:
    - Card 1: fixed as “NASA每日科普”.
    - Card 2 and Card 3: fixed as news cards.
12) Never merge facts across cards. Each card may only use details from its corresponding source block.
13) Each card must contain at least 2 concrete source facts: mission name, agency/company, date, location, payload, quantity, milestone, or technical target.
14) Card 1 should explain what the reader is seeing或理解的对象，然后解释它为什么有科学意义。
15) Card 2 and Card 3 should each use 2-3 natural paragraphs: first explain what happened, then explain why this development matters.
16) Avoid templated phrases and newsroom cliches, especially: “值得持续关注”, “释放了一个信号”, “后续仍值得期待”, “对普通读者来说”.
17) Write like a knowledgeable aerospace fan explaining the day to other readers. Natural, direct, lively, but never exaggerated.
18) The body HTML must NOT repeat the article title. Assume the publishing platform already shows the title separately.
19) Keep strong WeChat visual hierarchy, but do not render a main title heading in weixin_html.
20) Each card must include its image at the top. Use the article Image field from the materials.
21) Preserve important English mission/entity names on first mention when needed, and explain them naturally in Chinese instead of forcing awkward translation.
22) HTML rule: no leading whitespace right after opening tags.
23) Side margin/padding must be 0 (or omitted) on the outer wrapper.
24) Card styling must be FULL-WIDTH with NO side padding/margin: use `margin:0;padding:0` on cards. Do NOT use `padding:1em` or `margin: 2em` that creates side whitespace. Cards should touch screen edges.
25) Images must be `width:100%` with no border-radius or side margins.

JSON schema:
{{
  "date": "{date_str}",
  "title": "...",
  "covers": ["up to 5 image urls"],
  "songs": [{{"name": "news title", "artist": "channel"}}],
  "weixin_html": "<section>...</section>"
}}
"""


def build_gemini_rewrite_prompt(date_str: str, articles: list[dict[str, Any]], previous_payload: dict[str, Any], quality_report: dict[str, Any], attempt: int) -> str:
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
- Title must be a self-media headline, not a generic summary label.
- Do not use weak count titles like “3条NASA要闻”, “三条动态”, “今日速报”.
- Do not use internet slang like “冲刺”, “盘”, “开扯”, “扒一扒”.
- Title must include at least one concrete mission/entity/fact from source materials.
- Keep exactly 3 clearly separated cards when 3 materials are provided.
- Card 1 must be labeled “NASA每日科普”; Card 2 and Card 3 must be news cards.
- Add a visible divider labeled “今日NASA新闻” between Card 1 and Card 2.
- The body HTML must not repeat the overall title as a heading or hero title.
- Each card must stay faithful to its own source. Do not borrow facts, names, dates, or conclusions from another card.
- No links or source jumps.
- No templated phrases such as “值得持续关注”, “释放了一个信号”, “后续仍值得期待”, “对普通读者来说”.
- Every card needs concrete source facts, not generic filler.
- Write from a NASA enthusiast perspective, but keep the tone grounded and readable.
- HTML must have no leading whitespace after opening tags.
- Side margin/padding must be 0 (or omitted).
"""


def _story_candidate_tokens(text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", text))
    candidates.extend(re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", text))
    candidates.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", text))
    return candidates


def build_story_terms(articles: list[dict[str, Any]]) -> list[str]:
    text = " ".join(normalize_whitespace(f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}") for article in articles)
    text_lower = text.lower()
    terms: list[str] = []

    for term in ["Artemis II", "Artemis", "CLPS", "Intuitive Machines", "ISS", "Kennedy", "Roman", "Webb", "Hubble", "NISAR", "Moon", "Lunar", "SpaceX"]:
        if term.lower() in text_lower:
            terms.append(term.lower())

    for token in _story_candidate_tokens(text):
        clean = normalize_whitespace(token).strip()
        key = clean.lower()
        if len(clean) < 2 or key in _GENERIC_STORY_TOKENS or clean in {"任务更新", "相关进展", "最新进展", "最新节点", "发射阶段", "关键节点"}:
            continue
        terms.append(key)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = normalize_whitespace(term).strip().lower()
        if len(clean_term) >= 2 and clean_term not in seen:
            seen.add(clean_term)
            deduped.append(clean_term)
    return deduped[:14]
