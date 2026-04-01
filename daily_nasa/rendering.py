from __future__ import annotations

import re
from html import escape
from typing import Any

from .common import is_title_repetitive, normalize_cn_summary, normalize_cn_title, normalize_whitespace
from .config import BOTTOM_BANNER_URL, TITLE_KEYWORDS, TOP_BANNER_URL


ARTICLE_SKIP_TOKENS = {
    "nasa", "today", "daily", "update", "mission", "missions", "news", "story", "photo", "image",
    "article", "science", "space", "launch", "final", "preparations", "underway", "what", "read", "more",
    "and", "the", "今日", "最新", "动态", "消息", "任务", "进展", "节点", "新闻", "科普", "发布", "相关",
}
GENERIC_SUBJECT_FRAGMENTS = (
    "任务更新", "相关进展", "最新进展", "最新节点", "关键节点", "阶段进展", "发射阶段进展", "发布最新节点", "发布发射阶段进展",
)
FORBIDDEN_TITLE_TOKENS = {"3条", "三条", "要闻", "盘点", "汇总", "速报", "冲刺", "开扯", "扒", "合集"}


# Modern light theme styles
LIGHT_BG = "#fafafa"
LIGHT_CARD_BG = "#ffffff"
BORDER_COLOR = "#e8e8e8"
TEXT_PRIMARY = "#1a1a1a"
TEXT_SECONDARY = "#4a4a4a"
TEXT_MUTED = "#6b7280"
TEXT_LABEL = "#9ca3af"
ACCENT_BLUE = "#3b82f6"
ACCENT_GRADIENT = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
CARD_SHADOW = "0 2px 8px rgba(0,0,0,0.08)"
CARD_SHADOW_HOVER = "0 4px 16px rgba(0,0,0,0.12)"

FONT_FAMILY = "-apple-system,BlinkMacSystemFont,Helvetica Neue,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif"


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


def _article_label(category: str) -> str:
    """Get article category label."""
    labels = {
        "science": "Daily Science",
        "station": "Space Station",
        "deep": "Deep Space",
        "mars": "Mars Exploration",
        "earth": "Earth Science",
        "tech": "Technology",
    }
    return labels.get(category, "NASA News")


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


def _channel_meta(article: dict[str, Any]) -> str:
    """Get article meta info."""
    parts = []
    channel = article.get("channel", "")
    if channel and channel != "NASA":
        parts.append(channel)
    pub_time = article.get("publish_time", "")
    if pub_time:
        parts.append(pub_time)
    return " · ".join(parts) if parts else "NASA"


def _build_article_section(article: dict[str, Any], category: str) -> str:
    """Build a modern article section with card design."""
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=2)
    label = _article_label(category)

    html = f"<div style='margin:16px;background:{LIGHT_CARD_BG};border-radius:12px;box-shadow:{CARD_SHADOW};overflow:hidden;'>"

    # Category label bar
    html += f"<div style='padding:12px 20px;background:{ACCENT_GRADIENT};'>"
    html += f"<p style='margin:0;font-size:11px;color:#fff;letter-spacing:1px;text-transform:uppercase;font-weight:500;'>{label}</p>"
    html += "</div>"

    # Image - full width within card, no padding
    if image:
        html += f"<div style='width:100%;height:220px;overflow:hidden;'>"
        html += f"<img src='{image}' style='display:block;width:100%;height:100%;object-fit:cover;'>"
        html += "</div>"

    # Content area - full width text
    html += f"<div style='padding:20px 0;'>"
    html += f"<h2 style='margin:0 16px 10px 16px;font-size:20px;font-weight:600;color:{TEXT_PRIMARY};line-height:1.4;'>{escape(title)}</h2>"
    html += f"<p style='margin:0 16px 16px 16px;font-size:12px;color:{TEXT_LABEL};'>{escape(meta)}</p>"

    # Divider
    html += f"<div style='width:40px;height:3px;background:{ACCENT_BLUE};border-radius:2px;margin:16px;'></div>"

    # Paragraphs - full width
    for para in paragraphs:
        html += f"<p style='margin:0 16px 12px 16px;font-size:14px;color:{TEXT_SECONDARY};line-height:1.8;'>{escape(para)}</p>"

    html += "</div></div>"
    return html


def _build_header(date_str: str, headline: str) -> str:
    """Build modern header with gradient background."""
    return (
        f"<div style='position:relative;width:100%;padding:40px 24px;background:{ACCENT_GRADIENT};text-align:center;'>"
        f"<div style='max-width:600px;margin:0 auto;'>"
        f"<p style='margin:0 0 12px 0;font-size:12px;color:rgba(255,255,255,0.8);letter-spacing:2px;text-transform:uppercase;'>{escape(date_str)}</p>"
        f"<h1 style='margin:0;font-size:26px;font-weight:600;color:#fff;line-height:1.4;letter-spacing:-0.3px;'>{escape(headline)}</h1>"
        f"<div style='width:60px;height:4px;background:rgba(255,255,255,0.5);border-radius:2px;margin:20px auto 0;'></div>"
        f"</div></div>"
    )


def _build_intro(text: str) -> str:
    """Build modern intro section with card design - full width text."""
    return (
        f"<div style='margin:16px;background:{LIGHT_CARD_BG};border-radius:12px;box-shadow:{CARD_SHADOW};overflow:hidden;'>"
        f"<div style='padding:16px 0;'>"
        f"<div style='display:flex;align-items:center;margin:0 16px 12px 16px;'>"
        f"<div style='width:4px;height:20px;background:{ACCENT_BLUE};border-radius:2px;margin-right:10px;'></div>"
        f"<p style='margin:0;font-size:13px;color:{TEXT_LABEL};letter-spacing:1px;text-transform:uppercase;font-weight:500;'>今日导读</p>"
        f"</div>"
        f"<p style='margin:0 16px;font-size:15px;color:{TEXT_SECONDARY};line-height:1.8;'>{escape(text)}</p>"
        f"</div></div>"
    )


def _build_footer() -> str:
    """Build modern footer with gradient."""
    return (
        f"<div style='margin-top:24px;padding:32px 24px;background:{ACCENT_GRADIENT};text-align:center;'>"
        f"<p style='margin:0 0 8px 0;font-size:14px;color:#fff;font-weight:600;letter-spacing:2px;'>NASA DAILY</p>"
        f"<p style='margin:0 0 16px 0;font-size:12px;color:rgba(255,255,255,0.8);'>探索宇宙，每日更新</p>"
        f"<div style='width:40px;height:2px;background:rgba(255,255,255,0.5);border-radius:1px;margin:0 auto;'></div>"
        f"</div>"
    )


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    """Build complete HTML with modern card-based design."""
    science_article = articles[0] if articles else {}
    news_articles = articles[1:4] if len(articles) > 1 else []

    # Build intro text
    lead_titles = [normalize_cn_title(article.get("title", "")) for article in articles[:3] if article.get("title")]
    if len(lead_titles) >= 3:
        intro = f"今日聚焦 {lead_titles[0]}，{lead_titles[1]}，以及 {lead_titles[2]}。"
    elif len(lead_titles) == 2:
        intro = f"今日聚焦 {lead_titles[0]} 和 {lead_titles[1]}。"
    elif lead_titles:
        intro = f"今日聚焦 {lead_titles[0]}。"
    else:
        intro = "今日 NASA 最新航天动态。"

    # Build headline from first article or default
    headline = build_headline_title(articles, date_str)

    # Build content with modern card-based design
    html_parts = [
        f"<div style='background:{LIGHT_BG};width:100%;font-family:{FONT_FAMILY};color:{TEXT_PRIMARY};padding-bottom:16px;'>",
        _build_header(date_str, headline),
        _build_intro(intro),
    ]

    # Science article (featured)
    if science_article:
        html_parts.append(_build_article_section(science_article, "science"))

    # Section divider for news
    if news_articles:
        html_parts.append(
            f"<div style='margin:24px 16px 16px;'>"
            f"<div style='display:flex;align-items:center;'>"
            f"<div style='flex:1;height:1px;background:{BORDER_COLOR};'></div>"
            f"<span style='margin:0 16px;font-size:13px;color:{TEXT_LABEL};font-weight:500;'>更多新闻</span>"
            f"<div style='flex:1;height:1px;background:{BORDER_COLOR};'></div>"
            f"</div></div>"
        )

    # News articles with alternating categories
    categories = ["station", "deep", "mars", "earth", "tech"]
    for idx, article in enumerate(news_articles):
        category = categories[idx % len(categories)]
        html_parts.append(_build_article_section(article, category))

    html_parts.append(_build_footer())
    html_parts.append("</div>")

    return "".join(html_parts)


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
