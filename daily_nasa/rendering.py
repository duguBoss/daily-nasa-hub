from __future__ import annotations

import re
from html import escape
from typing import Any

from .common import is_title_repetitive, normalize_cn_summary, normalize_cn_title, normalize_whitespace
from .config import TOP_BANNER_URL
from . import template as tpl


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


def _article_paragraphs(article: dict[str, Any], max_paragraphs: int = 3) -> list[str]:
    """Extract paragraphs for article body."""
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
            trimmed.append(clean[:280])
        if len(trimmed) >= max_paragraphs:
            break
    return trimmed or ([title] if title else [])


def _extract_tag_from_title(title_en: str) -> str:
    """Extract mission tag from English title."""
    title_lower = title_en.lower()
    tags = [
        ("artemis", "Artemis"),
        ("orion", "Orion"),
        ("webb", "Webb"),
        ("hubble", "Hubble"),
        ("perseverance", "Perseverance"),
        ("curiosity", "Curiosity"),
        ("ingenuity", "Ingenuity"),
        ("spacex", "SpaceX"),
        ("falcon", "Falcon"),
        ("starship", "Starship"),
        ("iss", "ISS"),
        ("spacewalk", "Spacewalk"),
        ("mars", "Mars"),
        ("moon", "Moon"),
        ("lunar", "Lunar"),
        ("jupiter", "Jupiter"),
        ("saturn", "Saturn"),
        ("neptune", "Neptune"),
        ("uranus", "Uranus"),
        ("pluto", "Pluto"),
        ("asteroid", "Asteroid"),
        ("comet", "Comet"),
        ("galaxy", "Galaxy"),
        ("nebula", "Nebula"),
    ]
    for keyword, tag in tags:
        if keyword in title_lower:
            return tag
    return "NASA"


def build_wechat_fallback_title(date_str: str, articles: list[dict[str, Any]], recent_titles: list[str]) -> str:
    """Build a fallback title from articles when AI generation fails.

    Uses Chinese title (title field) not English title (title_en).
    """
    if articles:
        first_article = articles[0]
        # Use Chinese title (already normalized), not title_en
        title = first_article.get("title", "")
        if title:
            return fit_title_length(title)

    return f"NASA 每日动态 {date_str}"


def build_default_payload(
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
    recent_titles: list[str],
) -> dict[str, Any]:
    """Build default payload when AI generation fails or as fallback."""
    title = build_wechat_fallback_title(date_str, articles, recent_titles)
    weixin_html = build_fallback_html(date_str, title, articles, cover_urls)

    return {
        "title": title,
        "weixin_html": weixin_html,
        "covers": cover_urls,
        "date": date_str,
        "songs": [],
    }


def build_article_blocks(articles: list[dict[str, Any]]) -> str:
    """Build article blocks for AI prompt context."""
    blocks = []
    for i, article in enumerate(articles[:5], 1):
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")
        channel = article.get("channel", "NASA")
        pub_time = article.get("publish_time", "")

        block_parts = [f"【文章{i}】"]
        if title:
            block_parts.append(f"标题：{title}")
        if channel:
            block_parts.append(f"来源：{channel}")
        if pub_time:
            block_parts.append(f"时间：{pub_time}")
        if summary:
            block_parts.append(f"摘要：{summary}")
        if content:
            block_parts.append(f"内容：{content[:500]}...")

        blocks.append("\n".join(block_parts))

    return "\n\n".join(blocks)


def _build_apod_from_article(article: dict[str, Any], vol: str) -> str:
    """Build APOD section from first article."""
    title_cn = normalize_cn_title(article.get("title", ""))
    title_en = article.get("title_en", "")
    image_url = article.get("cover_url", "") or article.get("image_url", "")

    # Extract optics and object from content or summary
    content = f"{article.get('summary', '')} {article.get('content', '')}"

    # Try to extract optics info
    optics_match = re.search(r'(JWST|Hubble|Spitzer|Chandra|NIRCam|MIRI|WFC3)[\s\w]*', content, re.I)
    optics = optics_match.group(1).upper() if optics_match else "NASA"

    # Try to extract object name
    obj_match = re.search(r'([A-Z]{1,2}\d{1,4}|M\d{1,3}|NGC\s*\d{1,4}|Eagle|Orion|Crab|Andromeda|Milky Way)', content)
    obj = obj_match.group(1) if obj_match else "DEEP SPACE"

    # Get paragraphs
    paragraphs = _article_paragraphs(article, max_paragraphs=3)

    return tpl.render_apod_section(
        vol=vol,
        image_url=image_url or TOP_BANNER_URL,
        image_alt=title_cn or "NASA Image",
        optics=optics,
        obj=obj.upper(),
        title_cn=title_cn or "NASA每日天文图",
        title_en=title_en or "NASA Astronomy Picture",
        paragraphs=paragraphs,
    )


def _build_news_from_articles(articles: list[dict[str, Any]]) -> str:
    """Build news section from remaining articles."""
    news_items = []
    for idx, article in enumerate(articles, 1):
        title = normalize_cn_title(article.get("title", ""))
        title_en = article.get("title_en", "")
        tag = _extract_tag_from_title(title_en)
        image_url = article.get("cover_url", "") or article.get("image_url", "")
        paragraphs = _article_paragraphs(article, max_paragraphs=3)

        news_items.append(tpl.render_news_item(
            index=idx,
            title=title,
            tag=tag,
            image_url=image_url or TOP_BANNER_URL,
            image_alt=title,
            paragraphs=paragraphs,
        ))

    return tpl.render_news_section(''.join(news_items))


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    """Build complete HTML using template system."""
    if not articles:
        # Fallback when no articles
        apod_html = tpl.render_apod_section(
            vol=date_str[:4],
            image_url=TOP_BANNER_URL,
            image_alt="NASA",
            optics="NASA",
            obj="SPACE",
            title_cn="NASA每日航天动态",
            title_en="NASA Daily Space Updates",
            paragraphs=["今日暂无最新航天动态，请持续关注NASA官方发布。"],
        )
        news_html = tpl.render_news_section('')
        return tpl.render_full_html(
            banner_url=TOP_BANNER_URL,
            apod_html=apod_html,
            news_html=news_html,
        )

    # First article as APOD
    apod_html = _build_apod_from_article(articles[0], vol=date_str[:4])

    # Remaining articles as news
    news_html = _build_news_from_articles(articles[1:4])

    return tpl.render_full_html(
        banner_url=TOP_BANNER_URL,
        apod_html=apod_html,
        news_html=news_html,
        show_divider=len(articles) > 1,
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


def _is_repetitive_title(title: str) -> bool:
    return is_title_repetitive(title)


def fit_title_length(title: str, max_len: int = 30) -> str:
    """Fit title to max length while preserving meaning."""
    title = normalize_cn_title(title)
    if len(title) <= max_len:
        return title
    # Try to find a natural break point
    breakpoints = ["，", ",", "：", ":", "；", ";", " ", "、"]
    for bp in breakpoints:
        if bp in title[:max_len]:
            idx = title[:max_len].rfind(bp)
            if idx > 10:
                return title[:idx]
    # If no breakpoint, truncate at max_len
    return title[:max_len]


def build_headline_title(articles: list[dict[str, Any]], date_str: str) -> str:
    """Build headline title - Chinese only, 20-30 characters, naturally complete."""
    if not articles:
        return "NASA每日航天动态精选报道"

    # Get first article title
    first_title = normalize_cn_title(articles[0].get("title", ""))
    if not first_title:
        return "NASA每日航天动态精选报道"

    # Ensure Chinese title within 20-30 characters, naturally complete
    return fit_title_exact_length(first_title, min_len=20, max_len=30)


def fit_title_exact_length(title: str, min_len: int = 20, max_len: int = 30) -> str:
    """Fit title to length range with Chinese content - must be naturally complete.

    Title must be between min_len and max_len characters.
    If title is too short, return it as-is (AI should generate better title).
    If title is too long, truncate at natural break point.
    """
    title = normalize_cn_title(title)

    # If title is within range, return it
    if min_len <= len(title) <= max_len:
        return title

    # If title is shorter than min_len, return as-is (don't pad artificially)
    if len(title) < min_len:
        return title

    # If title is longer than max_len, truncate intelligently at natural break
    breakpoints = ["，", ",", "：", ":", "；", ";", " ", "、"]
    for bp in breakpoints:
        if bp in title[:max_len]:
            idx = title[:max_len].rfind(bp)
            if idx >= min_len:
                return title[:idx]

    # If no good breakpoint, hard truncate at max_len
    return title[:max_len]


def build_final_title(articles: list[dict[str, Any]], date_str: str) -> str:
    """Build final article title."""
    return build_headline_title(articles, date_str)


def generate_html_content(articles: list[dict[str, Any]], date_str: str) -> str:
    """Generate complete HTML content for WeChat."""
    title = build_final_title(articles, date_str)
    cover_urls = [a.get("cover_url", "") or a.get("image_url", "") for a in articles[:3]]
    return build_fallback_html(date_str, title, articles, cover_urls)
