from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .common import (
    clean_english_artifacts,
    count_chinese_chars,
    ensure_follow_header,
    enforce_outer_side_margin,
    is_html_chinese_friendly,
    is_title_repetitive,
    normalize_whitespace,
    strip_html_leading_whitespace,
    text_language_stats,
)
from .config import FORBIDDEN_TITLE_PATTERNS, MIN_QUALITY_SCORE, TITLE_KEYWORDS
from .rendering import build_fallback_html, build_wechat_fallback_title, fit_title_length
from .prompts import FAN_PERSPECTIVE_TERMS, MIN_CHINESE_CHARS, MISSION_HINT_TERMS, build_story_terms


TEMPLATE_PHRASES = (
    "这条消息聚焦",
    "帮助你快速理解",
    "内容详细梳理",
    "对你意味着什么",
    "下一步关注点",
    "今天的NASA速报就到这里",
    "准备好了吗",
    "让我们一起深入",
)
ARTICLE_STOPWORDS = {
    "nasa",
    "news",
    "daily",
    "today",
    "mission",
    "missions",
    "article",
    "story",
    "science",
    "image",
    "photo",
    "launch",
    "final",
    "preparations",
    "underway",
    "what",
    "read",
    "more",
    "from",
}


def sanitize_payload(
    payload: Any,
    default_payload: dict[str, Any],
    date_str: str,
    cover_urls: list[str],
    articles: list[dict[str, Any]],
    recent_titles: list[str],
    allow_template_fallback: bool,
) -> dict[str, Any]:
    normalized: dict[str, Any] = payload if isinstance(payload, dict) else {}
    normalized = dict(normalized)

    payload_date = str(normalized.get("date", "")).strip()
    normalized["date"] = payload_date if payload_date else date_str

    covers = normalized.get("covers", [])
    if not isinstance(covers, list):
        covers = []
    clean_covers = [str(url).strip() for url in covers if isinstance(url, str) and url.strip()]
    normalized["covers"] = (clean_covers or cover_urls or default_payload.get("covers", []))[:5]

    songs = normalized.get("songs", [])
    if not isinstance(songs, list) or not songs:
        songs = default_payload.get("songs", [])
    fixed_songs: list[dict[str, str]] = []
    for song in songs[:5]:
        if not isinstance(song, dict):
            continue
        name = normalize_whitespace(str(song.get("name", "")))
        artist = normalize_whitespace(str(song.get("artist", ""))) or "NASA"
        if name:
            fixed_songs.append({"name": name, "artist": artist})
    normalized["songs"] = fixed_songs or default_payload.get("songs", [])

    title = normalize_whitespace(str(normalized.get("title", "")))
    title_invalid = (not title) or count_chinese_chars(title) < 6 or is_title_repetitive(title, recent_titles)
    if title_invalid:
        title = build_wechat_fallback_title(date_str, articles, recent_titles)
    normalized["title"] = fit_title_length(title)

    weixin_html = str(normalized.get("weixin_html", "")).strip()
    if not weixin_html.startswith("<section"):
        weixin_html = default_payload["weixin_html"] if allow_template_fallback else ""
    if allow_template_fallback and not is_html_chinese_friendly(weixin_html):
        weixin_html = build_fallback_html(date_str, normalized["title"], articles, normalized["covers"])

    weixin_html = ensure_follow_header(weixin_html)
    weixin_html = enforce_outer_side_margin(weixin_html, side_px=0)
    weixin_html = strip_html_leading_whitespace(weixin_html)
    normalized["weixin_html"] = weixin_html
    return normalized


def has_repeated_sentences(text: str) -> bool:
    parts = [normalize_whitespace(p) for p in re.split(r"[。！？!?\n]", text) if normalize_whitespace(p)]
    long_parts = [p for p in parts if len(p) >= 18]
    if len(long_parts) <= 1:
        return False
    seen: dict[str, int] = {}
    for part in long_parts:
        seen[part] = seen.get(part, 0) + 1
        if seen[part] >= 2:
            return True
    return False


def title_matches_story_terms(title: str, articles: list[dict[str, Any]]) -> bool:
    story_terms = build_story_terms(articles)
    if not story_terms:
        return True
    title_norm = title.lower().replace(" ", "")
    for term in story_terms:
        term_norm = term.replace(" ", "")
        if term_norm and term_norm in title_norm:
            return True
    return False


def _template_phrase_hits(text: str) -> list[str]:
    return [phrase for phrase in TEMPLATE_PHRASES if phrase in text]


def _article_terms(article: dict[str, Any]) -> list[str]:
    source = normalize_whitespace(
        f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}"
    )
    terms: list[str] = []
    terms.extend(re.findall(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", source))
    terms.extend(re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", source))
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", source))
    terms.extend(re.findall(r"\b(?:19|20)\d{2}\b", source))

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean = normalize_whitespace(term).strip()
        key = clean.lower()
        if len(clean) < 2 or key in seen:
            continue
        if key in ARTICLE_STOPWORDS or clean in {"今日", "动态", "进展", "新闻", "任务", "科普"}:
            continue
        seen.add(key)
        deduped.append(clean)
    return deduped[:12]


def _grounded_article_count(plain_text: str, articles: list[dict[str, Any]]) -> int:
    normalized_plain = plain_text.lower().replace(" ", "")
    grounded = 0
    for article in articles:
        terms = _article_terms(article)
        if not terms:
            grounded += 1
            continue
        if any(term.lower().replace(" ", "") in normalized_plain for term in terms[:8]):
            grounded += 1
    return grounded


def evaluate_payload_quality(
    payload: dict[str, Any],
    articles: list[dict[str, Any]],
    recent_titles: list[str] | None = None,
) -> dict[str, Any]:
    recent_titles = recent_titles or []
    title = normalize_whitespace(str(payload.get("title", "")))
    html = str(payload.get("weixin_html", ""))
    soup = BeautifulSoup(html or "<section></section>", "html.parser")
    plain_text = clean_english_artifacts(soup.get_text(" ", strip=True))

    issues: list[str] = []
    breakdown: dict[str, int] = {}

    title_score = 0
    if 14 <= len(title) <= 28:
        title_score += 8
    else:
        issues.append("title_length_not_14_28")
    if re.search(r"[0-9一二三四五六七八九十两3]", title):
        title_score += 4
    else:
        issues.append("title_missing_number_signal")
    if any(keyword in title.lower() for keyword in TITLE_KEYWORDS):
        title_score += 7
    else:
        issues.append("title_missing_mission_keyword")
    if any(pattern in title.lower() for pattern in FORBIDDEN_TITLE_PATTERNS):
        issues.append("title_contains_forbidden_pattern")
    if title_matches_story_terms(title, articles):
        title_score += 8
    else:
        issues.append("title_not_specific_to_story")
    if recent_titles and is_title_repetitive(title, recent_titles):
        title_score = max(0, title_score - 8)
        issues.append("title_similar_to_recent")
    breakdown["title"] = title_score

    chinese_chars, english_words, ratio = text_language_stats(plain_text)
    long_english_phrase = bool(re.search(r"(?:\b[A-Za-z]{3,}\b\s+){5,}", plain_text))
    target_articles = max(1, len(articles))
    min_chinese_chars = max(MIN_CHINESE_CHARS, 320 + target_articles * 120)

    language_score = 0
    if chinese_chars >= min_chinese_chars:
        language_score += 10
    else:
        issues.append("body_below_500_chinese_chars")
    if ratio >= 0.85:
        language_score += 8
    elif ratio >= 0.76:
        language_score += 4
        issues.append("chinese_ratio_low")
    else:
        issues.append("chinese_ratio_too_low")
    if english_words <= 40:
        language_score += 4
    elif english_words <= 70:
        language_score += 2
        issues.append("english_words_medium")
    else:
        issues.append("too_much_english")
    if long_english_phrase:
        issues.append("long_english_phrase_detected")
    if "your browser does not support the audio element" in plain_text.lower():
        issues.append("html_contains_browser_artifact")
    if not is_html_chinese_friendly(html):
        issues.append("html_not_chinese_friendly")
    if "data-side-margin='0'" not in html and 'data-side-margin="0"' not in html:
        issues.append("side_spacing_not_zero")

    factual_signal_count = len(
        re.findall(
            r"\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*(?:million|billion|%|km|kg|hours?|days?|payloads?|missions?)",
            plain_text,
            flags=re.I,
        )
    ) + len(re.findall(r"\d+月\d+日", plain_text))
    required_facts = max(4, len(articles) * 2)
    if factual_signal_count >= required_facts:
        language_score += 6
    else:
        issues.append("factual_density_low")

    grounded_articles = _grounded_article_count(plain_text, articles)
    if grounded_articles >= len(articles):
        language_score += 6
    elif grounded_articles >= max(1, len(articles) - 1):
        language_score += 3
        issues.append("article_grounding_partial")
    else:
        issues.append("article_grounding_missing")

    mission_term_hits = sum(1 for term in MISSION_HINT_TERMS if term in plain_text.lower())
    if mission_term_hits >= max(2, len(articles)):
        language_score += 3
    else:
        issues.append("mission_terms_insufficient")
    if any(term in plain_text for term in FAN_PERSPECTIVE_TERMS):
        language_score += 2
    breakdown["language"] = max(0, language_score)

    structure_score = 0
    if "<h1" in html.lower():
        structure_score += 5
    else:
        issues.append("missing_h1")
    card_count = len(re.findall(r"NASA新闻\s*\d{2}", plain_text))
    if "NASA每日科普" in plain_text:
        card_count += 1
    if card_count >= max(1, len(articles)):
        structure_score += 10
    else:
        issues.append("news_card_count_insufficient")
    style_attr_count = html.lower().count("style=")
    if style_attr_count >= 10 and "<section" in html.lower():
        structure_score += 4
    else:
        issues.append("layout_style_too_plain")
    if "NASA每日科普" in plain_text:
        structure_score += 4
    else:
        issues.append("missing_science_card_label")
    if "今日NASA新闻" in plain_text:
        structure_score += 4
    else:
        issues.append("missing_news_divider")
    breakdown["structure"] = structure_score

    compliance_score = 0
    if "<a " not in html.lower():
        compliance_score += 10
    else:
        issues.append("contains_external_link")
    if "原文" not in plain_text and "source" not in plain_text.lower():
        compliance_score += 5
    else:
        issues.append("contains_source_jump_copy")
    if not has_repeated_sentences(plain_text):
        compliance_score += 5
    else:
        issues.append("repeated_content_detected")
    template_hits = _template_phrase_hits(plain_text)
    if not template_hits:
        compliance_score += 5
    else:
        issues.append("templated_phrases_detected")
    breakdown["compliance"] = compliance_score

    seo_score = 0
    keyword_hits = sum(1 for keyword in TITLE_KEYWORDS if keyword in plain_text.lower())
    if keyword_hits >= 4:
        seo_score += 8
    elif keyword_hits >= 3:
        seo_score += 5
        issues.append("seo_keyword_coverage_medium")
    else:
        issues.append("seo_keyword_coverage_low")
    if any(token in html.lower() for token in ["<h2", "<h3", "<strong"]):
        seo_score += 4
    else:
        issues.append("seo_structure_tags_missing")
    if chinese_chars >= min_chinese_chars:
        seo_score += 3
    else:
        issues.append("content_depth_insufficient")
    breakdown["seo"] = seo_score

    total_score = title_score + breakdown["language"] + breakdown["structure"] + compliance_score + seo_score
    hard_fail_issues = {
        "contains_external_link",
        "contains_source_jump_copy",
        "too_much_english",
        "long_english_phrase_detected",
        "html_contains_browser_artifact",
        "html_not_chinese_friendly",
        "title_similar_to_recent",
        "title_contains_forbidden_pattern",
        "title_not_specific_to_story",
        "body_below_500_chinese_chars",
        "factual_density_low",
        "article_grounding_missing",
        "layout_style_too_plain",
        "side_spacing_not_zero",
        "templated_phrases_detected",
        "missing_science_card_label",
        "missing_news_divider",
    }
    if any(issue in hard_fail_issues for issue in issues):
        total_score = min(total_score, MIN_QUALITY_SCORE - 1)

    return {"score": max(0, min(100, total_score)), "breakdown": breakdown, "issues": issues}
