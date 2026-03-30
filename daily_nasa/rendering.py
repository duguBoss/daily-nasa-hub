from __future__ import annotations

import re
from html import escape
from typing import Any

from .common import (
    is_title_repetitive,
    normalize_cn_summary,
    normalize_cn_title,
    normalize_whitespace,
)
from .config import BOTTOM_BANNER_URL, TITLE_KEYWORDS, TOP_BANNER_URL


CARD_IMAGE_STYLE = "width:100%;display:block;border-radius:16px;margin:0 0 14px 0;object-fit:cover;"
ARTICLE_SKIP_TOKENS = {
    "nasa",
    "today",
    "daily",
    "update",
    "mission",
    "missions",
    "news",
    "story",
    "photo",
    "image",
    "article",
    "science",
    "space",
    "launch",
    "final",
    "preparations",
    "underway",
    "what",
    "read",
    "more",
    "and",
    "the",
}


def _plain_text_from_article(article: dict[str, Any]) -> str:
    parts = [
        normalize_whitespace(str(article.get("summary", ""))),
        normalize_whitespace(str(article.get("content", ""))),
    ]
    text = "\n\n".join(part for part in parts if part)
    return normalize_whitespace(text)


def _split_sentences(text: str) -> list[str]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    chunks = re.split(r"(?<=[。！？!?])\s+|\n+", normalized)
    sentences: list[str] = []
    for chunk in chunks:
        cleaned = normalize_whitespace(chunk)
        if len(cleaned) < 24:
            continue
        sentences.append(cleaned)
    return sentences


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = normalize_whitespace(item).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _article_paragraphs(article: dict[str, Any], max_paragraphs: int = 2) -> list[str]:
    title = normalize_cn_title(article.get("title", ""))
    summary = normalize_cn_summary(article.get("summary", ""), title)
    source_text = _plain_text_from_article(article)

    paragraphs: list[str] = []
    if summary:
        paragraphs.append(summary)
    paragraphs.extend(_split_sentences(source_text))
    paragraphs = _dedupe_preserve_order(paragraphs)

    trimmed: list[str] = []
    for paragraph in paragraphs:
        clean = normalize_whitespace(paragraph)
        if clean and clean != title:
            trimmed.append(clean[:260])
        if len(trimmed) >= max_paragraphs:
            break
    if trimmed:
        return trimmed
    return [title] if title else []


def _extract_fact_snippets(article: dict[str, Any], limit: int = 3) -> list[str]:
    text = _plain_text_from_article(article)
    sentences = _split_sentences(text)
    fact_like = [
        sentence
        for sentence in sentences
        if re.search(r"\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*(?:million|billion|%|km|kg|hours?|days?|payloads?)", sentence, flags=re.I)
        or re.search(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", sentence)
    ]
    if not fact_like:
        fact_like = sentences[:limit]
    return [item[:180] for item in _dedupe_preserve_order(fact_like)[:limit]]


def _article_label(article: dict[str, Any], *, science: bool, index: int = 0) -> str:
    if science:
        return "NASA每日科普"
    return f"NASA新闻 {index:02d}"


def _channel_meta(article: dict[str, Any]) -> str:
    parts = [article.get("channel", "NASA"), article.get("publish_time", "")]
    return " · ".join(part for part in parts if part)


def _render_paragraphs(paragraphs: list[str], color: str = "#31465f") -> str:
    return "".join(
        f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:{color};'>{escape(paragraph)}</p>"
        for paragraph in paragraphs
    )


def _render_fact_strip(article: dict[str, Any], accent: str) -> str:
    facts = _extract_fact_snippets(article, limit=2)
    if not facts:
        return ""
    facts_html = "".join(
        f"<p style='margin:0 0 6px 0;font-size:13px;line-height:1.75;color:#49617d;'>{escape(fact)}</p>"
        for fact in facts
    )
    return (
        f"<section style='margin:4px 0 14px 0;padding:12px 14px;border-left:3px solid {accent};"
        "border-radius:12px;background:#f6f9fc;'>"
        f"{facts_html}"
        "</section>"
    )


def _build_science_card(article: dict[str, Any]) -> str:
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=2)

    card = (
        "<section style='margin:0 0 24px 0;padding:18px;border-radius:20px;background:linear-gradient(180deg,#f5f9ff 0%,#ffffff 100%);"
        "border:1px solid #d9e7fb;box-shadow:0 12px 28px rgba(20,35,54,0.06);'>"
        "<section style='display:inline-block;margin:0 0 12px 0;padding:6px 12px;border-radius:999px;"
        "background:#0b3d91;color:#ffffff;font-size:12px;letter-spacing:0.08em;'>NASA每日科普</section>"
    )
    if image:
        card += f"<img src='{image}' style='{CARD_IMAGE_STYLE}'>"
    card += (
        f"<h3 style='margin:0 0 8px 0;font-size:22px;line-height:1.42;color:#11263f;'>{escape(title)}</h3>"
        f"<p style='margin:0 0 14px 0;font-size:13px;line-height:1.7;color:#5e738c;'>{escape(meta)}</p>"
        f"{_render_fact_strip(article, '#0b3d91')}"
        f"{_render_paragraphs(paragraphs, '#30485f')}"
        "</section>"
    )
    return card


def _build_news_card(article: dict[str, Any], idx: int) -> str:
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=3)

    card = (
        "<section style='margin:0 0 18px 0;padding:18px;border:1px solid #e4ebf2;border-radius:18px;"
        "background:#ffffff;box-shadow:0 8px 22px rgba(20,35,54,0.05);'>"
        "<section style='display:flex;align-items:center;justify-content:space-between;margin:0 0 12px 0;'>"
        f"<span style='display:inline-block;padding:5px 11px;border-radius:999px;background:#eef4fb;color:#24496f;font-size:12px;'>{_article_label(article, science=False, index=idx)}</span>"
        f"<span style='font-size:12px;color:#7f90a5;'>第 {idx} 条</span>"
        "</section>"
    )
    if image:
        card += f"<img src='{image}' style='{CARD_IMAGE_STYLE}'>"
    card += (
        f"<h3 style='margin:0 0 8px 0;font-size:20px;line-height:1.48;color:#172a43;'>{escape(title)}</h3>"
        f"<p style='margin:0 0 14px 0;font-size:13px;line-height:1.7;color:#61758a;'>{escape(meta)}</p>"
        f"{_render_fact_strip(article, '#3b82f6')}"
        f"{_render_paragraphs(paragraphs)}"
        "</section>"
    )
    return card


def _build_divider(label: str) -> str:
    return (
        "<section style='display:flex;align-items:center;gap:12px;margin:28px 0 22px 0;'>"
        "<section style='flex:1;height:1px;background:linear-gradient(to right,#d4dfeb,#eef3f8);'></section>"
        f"<span style='padding:0 2px;font-size:13px;letter-spacing:0.08em;color:#6c829a;'>{escape(label)}</span>"
        "<section style='flex:1;height:1px;background:linear-gradient(to left,#d4dfeb,#eef3f8);'></section>"
        "</section>"
    )


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    science_article = articles[0] if articles else {}
    news_articles = articles[1:3] if len(articles) > 1 else []

    lead_titles = [normalize_cn_title(article.get("title", "")) for article in articles[:3] if article.get("title")]
    if len(lead_titles) >= 3:
        intro = f"今天先从 {lead_titles[0]} 这条 NASA 每日科普切入，再看 {lead_titles[1]} 和 {lead_titles[2]} 两条最新任务新闻。"
    elif lead_titles:
        intro = f"今天这份 NASA 日报围绕 {lead_titles[0]} 展开，先看每日科普，再看后续新闻推进。"
    else:
        intro = "今天这份 NASA 日报分成两部分：先读一条每日科普，再追两条正在推进的任务新闻。"

    cards_html = ""
    if science_article:
        cards_html += _build_science_card(science_article)
    if news_articles:
        cards_html += _build_divider("今日NASA新闻")
        for idx, article in enumerate(news_articles, start=1):
            cards_html += _build_news_card(article, idx)

    return (
        "<section style='background:#f4f8fc;'>"
        f"<img src='{TOP_BANNER_URL}' style='width:100%;display:block;'>"
        "<section style='padding:24px 12px 8px 12px;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,"
        "Helvetica Neue,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;'>"
        "<section style='padding:20px 16px;border-radius:18px;background:linear-gradient(140deg,#f8fbff 0%,#eef5ff 100%);margin-bottom:22px;'>"
        f"<p style='margin:0 0 8px 0;font-size:13px;color:#61758a;line-height:1.7;'>NASA Daily · {escape(date_str)}</p>"
        f"<h1 style='margin:0;font-size:25px;line-height:1.38;color:#10243e;'>{escape(title)}</h1>"
        f"<p style='margin:12px 0 0 0;font-size:15px;line-height:1.9;color:#364a60;'>{escape(intro)}</p>"
        "</section>"
        f"{cards_html}"
        "</section>"
        f"<img src='{BOTTOM_BANNER_URL}' style='width:100%;display:block;'>"
        "</section>"
    )


def pick_title_focus(articles: list[dict[str, Any]]) -> str:
    text = " ".join(f"{a.get('title', '')} {a.get('summary', '')}" for a in articles).lower()
    rules = [
        (("artemis ii", "artemis", "moon", "launch"), "Artemis登月"),
        (("clps", "intuitive machines", "lunar"), "CLPS月面投送"),
        (("spacestation", "spacewalk", "crew", "iss", "space station"), "空间站任务"),
        (("webb", "hubble", "roman", "telescope"), "深空望远镜"),
        (("earth", "climate", "volcano", "nisar"), "地球观测"),
        (("image", "gallery", "photo", "apod", "comet"), "天文影像"),
    ]
    for keywords, focus in rules:
        if any(keyword in text for keyword in keywords):
            return focus
    return "NASA新动态"


def infer_story_signal(articles: list[dict[str, Any]]) -> str:
    text = " ".join(f"{a.get('title', '')} {a.get('summary', '')}" for a in articles).lower()
    if "artemis ii" in text:
        return "Artemis II"
    if "intuitive machines" in text or "clps" in text:
        return "CLPS月面投送"
    if "spacewalk" in text or "spacestation" in text or "iss" in text:
        return "空间站出舱"
    if "webb" in text or "hubble" in text or "roman" in text:
        return "太空望远镜"
    if "moon" in text or "lunar" in text:
        return "月面任务"
    return pick_title_focus(articles)


def _title_subject_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", text))
    candidates.extend(re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", text))
    candidates.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", text))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = normalize_whitespace(item).strip()
        key = clean.lower()
        if len(clean) < 2 or key in seen:
            continue
        seen.add(key)
        deduped.append(clean)
    return deduped


def extract_lead_subject(articles: list[dict[str, Any]]) -> str:
    lead_article = next((article for article in articles if not str(article.get("channel", "")).startswith("NASA APOD")), None)
    lead_text = normalize_whitespace(str((lead_article or (articles[0] if articles else {})).get("title", "")))
    for token in _title_subject_candidates(lead_text):
        if token.lower() not in ARTICLE_SKIP_TOKENS and token not in {"今日", "新闻", "科普", "动态", "进展", "任务"}:
            return token[:12]
    return "NASA任务线"


def fit_title_length(title: str) -> str:
    text = normalize_whitespace(title).strip(":：,，.。 ")
    if len(text) > 28:
        text = text[:28]
    if len(text) < 14:
        text = f"{text}最新进展"
    if len(text) > 28:
        text = text[:28]
    return text


def score_title_candidate(
    title: str,
    signal: str,
    lead_subject: str,
    recent_titles: list[str],
    preferred_style: str,
) -> int:
    score = 0
    text_lower = title.lower()
    if signal.lower() in text_lower:
        score += 10
    if any(kw in text_lower for kw in TITLE_KEYWORDS):
        score += 6
    if lead_subject.lower() in text_lower:
        score += 5
    if preferred_style and preferred_style.lower() in text_lower:
        score += 4
    if not is_title_repetitive(title, recent_titles):
        score += 3
    return score


def build_article_blocks(articles: list[dict[str, Any]]) -> str:
    blocks = []
    for idx, article in enumerate(articles, start=1):
        title = normalize_whitespace(article.get("title", ""))
        title_en = normalize_whitespace(article.get("title_en", ""))
        summary = normalize_whitespace(article.get("summary", ""))
        content = _plain_text_from_article(article)[:1200]
        channel = article.get("channel", "")
        publish_time = article.get("publish_time", "")
        image = article.get("cover_url", "") or article.get("image_url", "")
        url = article.get("url", "")
        role = "science_card" if idx == 1 else f"news_card_{idx - 1}"
        fact_snippets = _extract_fact_snippets(article, limit=3)

        block = [f"[News {idx}]", f"Role: {role}", f"Title: {title}"]
        if title_en and title_en != title:
            block.append(f"Original Title: {title_en}")
        if channel:
            block.append(f"Channel: {channel}")
        if publish_time:
            block.append(f"Time: {publish_time}")
        if summary:
            block.append(f"Summary: {summary}")
        if content:
            block.append(f"Content excerpt: {content}")
        if fact_snippets:
            block.append(f"Required grounding facts: {' | '.join(fact_snippets)}")
        if image:
            block.append(f"Image: {image}")
        if url:
            block.append(f"URL: {url}")
        block.append("Constraint: only use facts from this block when writing this card.")
        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


def build_default_payload(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> dict[str, Any]:
    fallback_title = build_wechat_fallback_title(date_str, articles, recent_titles)
    default_covers = [url for url in cover_urls if url][:5]

    songs = []
    for article in articles[:3]:
        name = normalize_whitespace(article.get("title", ""))[:60]
        channel = article.get("channel", "NASA")
        if name:
            songs.append({"name": name, "artist": channel})

    html = build_fallback_html(date_str, fallback_title, articles, default_covers)

    return {
        "date": date_str,
        "title": fallback_title,
        "covers": default_covers,
        "songs": songs,
        "weixin_html": html,
    }


def build_wechat_fallback_title(date_str: str, articles: list[dict[str, Any]], recent_titles: list[str]) -> str:
    signal = infer_story_signal(articles)
    lead_subject = extract_lead_subject(articles)
    candidates = [
        f"3条NASA动态：{signal}",
        f"3条NASA要闻：{signal}与{lead_subject}",
        f"从{lead_subject}看NASA今天在忙什么",
        f"今天这3条NASA内容，先看{signal}",
        f"NASA三条新动态：{lead_subject}与{signal}",
    ]

    best_title = "3条NASA动态：月面任务与天文影像"
    best_score = -1
    for candidate in candidates:
        fitted = fit_title_length(candidate)
        score = score_title_candidate(fitted, signal, lead_subject, recent_titles, "3条")
        if score > best_score:
            best_score = score
            best_title = fitted
    return best_title
