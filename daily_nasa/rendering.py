from __future__ import annotations

import re
from html import escape
from typing import Any

from .common import is_title_repetitive, normalize_cn_summary, normalize_cn_title, normalize_whitespace
from .config import BOTTOM_BANNER_URL, TITLE_KEYWORDS, TOP_BANNER_URL


CARD_IMAGE_STYLE = "width:100%;display:block;border-radius:16px;margin:0 0 14px 0;object-fit:cover;"
ARTICLE_SKIP_TOKENS = {
    "nasa", "today", "daily", "update", "mission", "missions", "news", "story", "photo", "image",
    "article", "science", "space", "launch", "final", "preparations", "underway", "what", "read", "more",
    "and", "the", "今日", "最新", "动态", "消息", "任务", "进展", "节点", "新闻", "科普", "发布", "相关",
}
GENERIC_SUBJECT_FRAGMENTS = (
    "任务更新", "相关进展", "最新进展", "最新节点", "关键节点", "阶段进展", "发射阶段进展", "发布最新节点", "发布发射阶段进展",
)
FORBIDDEN_TITLE_TOKENS = {"3条", "三条", "要闻", "盘点", "汇总", "速报", "冲刺", "开扯", "扒", "合集"}


def _plain_text_from_article(article: dict[str, Any]) -> str:
    parts = [normalize_whitespace(str(article.get("summary", ""))), normalize_whitespace(str(article.get("content", "")))]
    return normalize_whitespace("\n\n".join(part for part in parts if part))


def _split_sentences(text: str) -> list[str]:
    normalized = normalize_whitespace(text)
    if not normalized:
        return []
    chunks = re.split(r"(?<=[。！？!?])\s+|\n+", normalized)
    return [clean for chunk in chunks if (clean := normalize_whitespace(chunk)) and len(clean) >= 18]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = normalize_whitespace(item).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _article_paragraphs(article: dict[str, Any], max_paragraphs: int = 2) -> list[str]:
    title = normalize_cn_title(article.get("title", ""))
    summary = normalize_cn_summary(article.get("summary", ""), title)
    paragraphs = []
    if summary:
        paragraphs.append(summary)
    paragraphs.extend(_split_sentences(_plain_text_from_article(article)))
    trimmed: list[str] = []
    for paragraph in _dedupe_preserve_order(paragraphs):
        clean = normalize_whitespace(paragraph)
        if clean and clean != title:
            trimmed.append(clean[:260])
        if len(trimmed) >= max_paragraphs:
            break
    return trimmed or ([title] if title else [])


def _extract_fact_snippets(article: dict[str, Any], limit: int = 3) -> list[str]:
    sentences = _split_sentences(_plain_text_from_article(article))
    fact_like = [
        sentence for sentence in sentences
        if re.search(r"\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*(?:million|billion|%|km|kg|hours?|days?|payloads?)", sentence, flags=re.I)
        or re.search(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", sentence)
        or re.search(r"\d+", sentence)
    ]
    if not fact_like:
        fact_like = sentences[:limit]
    return [item[:180] for item in _dedupe_preserve_order(fact_like)[:limit]]


def _article_label(science: bool, index: int = 0) -> str:
    return "NASA每日科普" if science else f"NASA新闻 {index:02d}"


def _channel_meta(article: dict[str, Any]) -> str:
    return " · ".join(part for part in [article.get("channel", "NASA"), article.get("publish_time", "")] if part)


def _render_paragraphs(paragraphs: list[str], color: str = "#31465f") -> str:
    return "".join(f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:{color};'>{escape(paragraph)}</p>" for paragraph in paragraphs)


def _render_fact_strip(article: dict[str, Any], accent: str) -> str:
    facts = _extract_fact_snippets(article, limit=2)
    if not facts:
        return ""
    facts_html = "".join(f"<p style='margin:0 0 6px 0;font-size:13px;line-height:1.75;color:#49617d;'>{escape(fact)}</p>" for fact in facts)
    return f"<section style='margin:4px 0 14px 0;padding:12px 14px;border-left:3px solid {accent};border-radius:12px;background:#f6f9fc;'>{facts_html}</section>"


def _build_science_card(article: dict[str, Any]) -> str:
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=3)
    card = (
        "<section style='margin:0 0 24px 0;padding:18px;border-radius:20px;background:linear-gradient(180deg,#f5f9ff 0%,#ffffff 100%);border:1px solid #d9e7fb;box-shadow:0 12px 28px rgba(20,35,54,0.06);'>"
        "<section style='display:inline-block;margin:0 0 12px 0;padding:6px 12px;border-radius:999px;background:#0b3d91;color:#ffffff;font-size:12px;letter-spacing:0.08em;'>NASA每日科普</section>"
    )
    if image:
        card += f"<img src='{image}' style='{CARD_IMAGE_STYLE}'>"
    card += f"<h3 style='margin:0 0 8px 0;font-size:22px;line-height:1.42;color:#11263f;'>{escape(title)}</h3><p style='margin:0 0 14px 0;font-size:13px;line-height:1.7;color:#5e738c;'>{escape(meta)}</p>{_render_fact_strip(article, '#0b3d91')}{_render_paragraphs(paragraphs, '#30485f')}</section>"
    return card


def _build_news_card(article: dict[str, Any], idx: int) -> str:
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=3)
    card = (
        "<section style='margin:0 0 18px 0;padding:18px;border:1px solid #e4ebf2;border-radius:18px;background:#ffffff;box-shadow:0 8px 22px rgba(20,35,54,0.05);'>"
        "<section style='display:flex;align-items:center;justify-content:space-between;margin:0 0 12px 0;'>"
        f"<span style='display:inline-block;padding:5px 11px;border-radius:999px;background:#eef4fb;color:#24496f;font-size:12px;'>{_article_label(False, idx)}</span>"
        f"<span style='font-size:12px;color:#7f90a5;'>新闻 {idx:02d}</span></section>"
    )
    if image:
        card += f"<img src='{image}' style='{CARD_IMAGE_STYLE}'>"
    card += f"<h3 style='margin:0 0 8px 0;font-size:20px;line-height:1.48;color:#172a43;'>{escape(title)}</h3><p style='margin:0 0 14px 0;font-size:13px;line-height:1.7;color:#61758a;'>{escape(meta)}</p>{_render_fact_strip(article, '#3b82f6')}{_render_paragraphs(paragraphs)}</section>"
    return card


def _build_divider(label: str) -> str:
    return f"<section style='display:flex;align-items:center;gap:12px;margin:28px 0 22px 0;'><section style='flex:1;height:1px;background:linear-gradient(to right,#d4dfeb,#eef3f8);'></section><span style='padding:0 2px;font-size:13px;letter-spacing:0.08em;color:#6c829a;'>{escape(label)}</span><section style='flex:1;height:1px;background:linear-gradient(to left,#d4dfeb,#eef3f8);'></section></section>"


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    science_article = articles[0] if articles else {}
    news_articles = articles[1:3] if len(articles) > 1 else []
    lead_titles = [normalize_cn_title(article.get("title", "")) for article in articles[:3] if article.get("title")]
    if len(lead_titles) >= 3:
        intro = f"今天这份 NASA 日报先带你看懂 {lead_titles[0]}，再快速补上 {lead_titles[1]} 和 {lead_titles[2]} 的关键信息。"
    elif lead_titles:
        intro = f"今天先把 {lead_titles[0]} 这条线索讲明白，再带你把 NASA 当天最值得看的进展顺一遍。"
    else:
        intro = "今天这份 NASA 日报会先讲清一条值得细看的科普内容，再补上当天最重要的两条航天动态。"
    cards_html = _build_science_card(science_article) if science_article else ""
    if news_articles:
        cards_html += _build_divider("今日NASA新闻") + "".join(_build_news_card(article, idx) for idx, article in enumerate(news_articles, start=1))
    return (
        "<section style='background:#f4f8fc;'>"
        f"<img src='{TOP_BANNER_URL}' style='width:100%;display:block;'>"
        "<section style='padding:24px 12px 8px 12px;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,Helvetica Neue,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;'>"
        f"<section style='padding:16px 16px 0 16px;margin-bottom:22px;'><p style='margin:0;font-size:15px;line-height:1.9;color:#364a60;'>{escape(intro)}</p></section>{cards_html}</section>"
        f"<img src='{BOTTOM_BANNER_URL}' style='width:100%;display:block;'>"
        "</section>"
    )


def pick_title_focus(articles: list[dict[str, Any]]) -> str:
    text = " ".join(f"{a.get('title_en', '')} {a.get('title', '')} {a.get('summary', '')}" for a in articles).lower()
    rules = [
        (("artemis ii", "artemis", "moon", "launch"), "Artemis"),
        (("clps", "intuitive machines", "lunar"), "CLPS月球任务"),
        (("spacewalk", "crew", "iss", "space station"), "国际空间站"),
        (("webb", "hubble", "roman", "telescope"), "太空望远镜"),
        (("earth", "climate", "volcano", "nisar"), "地球观测"),
        (("image", "gallery", "photo", "apod", "comet"), "NASA每日科普"),
    ]
    for keywords, focus in rules:
        if any(keyword in text for keyword in keywords):
            return focus
    return "NASA航天任务"


def infer_story_signal(articles: list[dict[str, Any]]) -> str:
    text = " ".join(f"{a.get('title_en', '')} {a.get('title', '')} {a.get('summary', '')}" for a in articles).lower()
    if "artemis ii" in text:
        return "Artemis II"
    if "intuitive machines" in text or "clps" in text:
        return "CLPS"
    if "spacewalk" in text or "iss" in text or "space station" in text:
        return "国际空间站"
    if "webb" in text or "hubble" in text or "roman" in text:
        return "太空望远镜"
    if "moon" in text or "lunar" in text:
        return "月球任务"
    return pick_title_focus(articles)


def _title_subject_candidates(text: str) -> list[str]:
    candidates = []
    candidates.extend(re.findall(r"[A-Z]{2,}(?:-[0-9]+)?", text))
    candidates.extend(re.findall(r"[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}", text))
    candidates.extend(re.findall(r"[\u4e00-\u9fff]{2,12}", text))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = normalize_whitespace(item).strip("：:，,。 ")
        key = clean.lower()
        if len(clean) >= 2 and key not in seen:
            seen.add(key)
            deduped.append(clean)
    return deduped


def _clean_subject(token: str) -> str:
    clean = normalize_whitespace(token).strip(":, ")
    clean = re.sub(r"^NASA", "", clean, flags=re.I).strip(":, ")
    for fragment in GENERIC_SUBJECT_FRAGMENTS:
        clean = clean.replace(fragment, "")
    clean = re.sub("^(\u4eca\u65e5|\u6700\u65b0|NASA)", "", clean).strip(":, ")
    clean = re.sub("(\u4eca\u5929|\u8fdb\u5c55|\u8282\u70b9|\u52a8\u6001|\u6d88\u606f|\u53d1\u5e03)$", "", clean).strip(":, ")
    clean = re.sub("(\u4efb\u52a1\u53d1\u5e03)$", "\u4efb\u52a1", clean).strip(":, ")
    if clean.lower().startswith(("final preparations", "here comes", "live coverage", "live ", "this ")):
        return ""
    return clean


def _first_meaningful_subject(article: dict[str, Any]) -> str:
    for text in [normalize_whitespace(str(article.get("title", ""))), normalize_whitespace(str(article.get("title_en", ""))), normalize_whitespace(str(article.get("summary", "")))]:
        for token in _title_subject_candidates(text):
            clean = _clean_subject(token)
            if clean and clean.lower() not in ARTICLE_SKIP_TOKENS and clean not in {"登月任务发布", "NASA任务更新", "相关进展", "最新进展", "最新节点", "关键节点"}:
                return clean[:14]
    return ""


def extract_lead_subject(articles: list[dict[str, Any]]) -> str:
    for article in articles[1:]:
        if subject := _first_meaningful_subject(article):
            return subject
    if articles and (subject := _first_meaningful_subject(articles[0])):
        return subject
    return infer_story_signal(articles)


def _secondary_subject(articles: list[dict[str, Any]]) -> str:
    used = {extract_lead_subject(articles).lower()}
    for article in articles[1:]:
        subject = _first_meaningful_subject(article)
        if subject and subject.lower() not in used:
            return subject[:14]
    for article in articles:
        subject = _first_meaningful_subject(article)
        if subject and subject.lower() not in used:
            return subject[:14]
    return infer_story_signal(articles)


def fit_title_length(title: str) -> str:
    text = normalize_whitespace(title).strip("：:，,。.!！？? ")
    # If title is too long, try to find a natural break point
    if len(text) > 28:
        # Look for natural break points: comma, period, or space before position 28
        for i in range(27, 14, -1):
            if text[i] in "，,、。！？；":
                return text[:i+1].rstrip("，,、 ")
        # If no natural break, keep the first 28 chars but ensure it ends with a complete word
        truncated = text[:28]
        # Don't cut in the middle of a word if possible
        if len(text) > 28 and text[28] not in "，,、。！？； ":
            # Find last space or punctuation before position 28
            for i in range(27, 14, -1):
                if text[i] in " ":
                    return text[:i].rstrip()
        return truncated.rstrip("，,、 ")
    if len(text) < 14:
        text = f"{text}迎来关键进展"
    return text


def score_title_candidate(title: str, signal: str, lead_subject: str, recent_titles: list[str], preferred_style: str) -> int:
    text_lower = title.lower()
    score = 4 if signal.lower() in text_lower else 0
    score += 6 if any(kw in text_lower for kw in TITLE_KEYWORDS) else 0
    score += 5 if lead_subject.lower() in text_lower else 0
    score += 4 if preferred_style and preferred_style.lower() in text_lower else 0
    score += 6 if lead_subject.lower() in text_lower and preferred_style and preferred_style.lower() in text_lower else 0
    score += 5 if not any(token in title for token in FORBIDDEN_TITLE_TOKENS) else 0
    score += 3 if not is_title_repetitive(title, recent_titles) else 0
    score += 3 if any(mark in title for mark in ["关键", "节点", "发射", "登月", "载荷", "图像"]) else 0
    return score


def build_article_blocks(articles: list[dict[str, Any]]) -> str:
    blocks = []
    for idx, article in enumerate(articles, start=1):
        fact_snippets = _extract_fact_snippets(article, limit=3)
        block = [f"[News {idx}]", f"Role: {'science_card' if idx == 1 else f'news_card_{idx - 1}'}", f"Title: {normalize_whitespace(article.get('title', ''))}"]
        if title_en := normalize_whitespace(article.get("title_en", "")):
            if title_en != normalize_whitespace(article.get("title", "")):
                block.append(f"Original Title: {title_en}")
        for label, value in [("Channel", article.get("channel", "")), ("Time", article.get("publish_time", "")), ("Summary", normalize_whitespace(article.get("summary", ""))), ("Content excerpt", _plain_text_from_article(article)[:1200]), ("Image", article.get("cover_url", "") or article.get("image_url", "")), ("URL", article.get("url", ""))]:
            if value:
                block.append(f"{label}: {value}")
        if fact_snippets:
            block.append(f"Required grounding facts: {' | '.join(fact_snippets)}")
        block.append("Constraint: only use facts from this block when writing this card.")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def build_default_payload(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> dict[str, Any]:
    fallback_title = build_wechat_fallback_title(date_str, articles, recent_titles)
    default_covers = [url for url in cover_urls if url][:5]
    songs = [{"name": normalize_whitespace(article.get("title", ""))[:60], "artist": article.get("channel", "NASA")} for article in articles[:3] if normalize_whitespace(article.get("title", ""))]
    return {"date": date_str, "title": fallback_title, "covers": default_covers, "songs": songs, "weixin_html": build_fallback_html(date_str, fallback_title, articles, default_covers)}


def build_wechat_fallback_title(date_str: str, articles: list[dict[str, Any]], recent_titles: list[str]) -> str:
    signal = infer_story_signal(articles)
    lead_subject = extract_lead_subject(articles)
    secondary = _secondary_subject(articles)
    candidates = [
        f"{lead_subject}迎来关键进展，{secondary}也有新消息",
        f"{lead_subject}时间表更新，{secondary}同步出现关键变化",
        f"{signal}之外，{secondary}也带来新节点",
        f"{lead_subject}这次先有新进展，{secondary}也放出信号",
        f"{lead_subject}推进到哪一步了，{secondary}今天说清楚",
    ]
    filtered = [candidate for candidate in candidates if not any(token in candidate for token in FORBIDDEN_TITLE_TOKENS)] or [f"{lead_subject}迎来关键进展，{secondary}也有更新"]
    best_title = fit_title_length(filtered[0])
    best_score = -1
    for candidate in filtered:
        fitted = fit_title_length(candidate)
        score = score_title_candidate(fitted, signal, lead_subject, recent_titles, secondary)
        if score > best_score:
            best_score = score
            best_title = fitted
    return best_title
