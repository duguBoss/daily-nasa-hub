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


# New dark theme styles
DARK_BG = "#0a0a0a"
DARK_CARD_BG = "#0a0a0a"
BORDER_COLOR = "#1a1a1a"
TEXT_PRIMARY = "#fff"
TEXT_SECONDARY = "#bbb"
TEXT_MUTED = "#666"
TEXT_LABEL = "#888"
ACCENT_BLUE = "#3b82f6"

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
    """Build a fallback title from articles when AI generation fails."""
    if articles:
        first_article = articles[0]
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
    """Build a full article section with dark theme."""
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = normalize_cn_title(article.get("title", ""))
    meta = _channel_meta(article)
    paragraphs = _article_paragraphs(article, max_paragraphs=2)
    label = _article_label(category)
    
    html = f"<div style='padding:28px 24px;border-bottom:1px solid {BORDER_COLOR};'>"
    html += f"<p style='margin:0 0 16px 0;font-size:10px;color:{TEXT_MUTED};letter-spacing:2px;text-transform:uppercase;'>{label}</p>"
    
    if image:
        html += f"<img src='{image}' style='width:100%;height:260px;object-fit:cover;border-radius:4px;margin:0 0 20px 0;'>"
    
    html += f"<h2 style='margin:0 0 12px 0;font-size:22px;font-weight:400;color:{TEXT_PRIMARY};line-height:1.4;'>{escape(title)}</h2>"
    html += f"<p style='margin:0 0 20px 0;font-size:13px;color:{TEXT_MUTED};'>{escape(meta)}</p>"
    
    for para in paragraphs:
        html += f"<p style='margin:0 0 14px 0;font-size:14px;color:{TEXT_SECONDARY};line-height:1.9;font-weight:300;'>{escape(para)}</p>"
    
    html += "</div>"
    return html


def _build_header(date_str: str, headline: str) -> str:
    """Build dark header with image overlay."""
    return (
        f"<div style='position:relative;width:100%;height:280px;overflow:hidden;'>"
        f"<img src='{TOP_BANNER_URL}' style='width:100%;height:100%;object-fit:cover;filter:brightness(0.7);'>"
        f"<div style='position:absolute;bottom:0;left:0;right:0;padding:30px;background:linear-gradient(transparent,rgba(0,0,0,0.8));'>"
        f"<p style='margin:0 0 8px 0;font-size:11px;color:{TEXT_LABEL};letter-spacing:2px;text-transform:uppercase;'>{escape(date_str)}</p>"
        f"<h1 style='margin:0;font-size:28px;font-weight:300;color:{TEXT_PRIMARY};line-height:1.3;letter-spacing:-0.5px;'>{escape(headline)}</h1>"
        f"</div></div>"
    )


def _build_intro(text: str) -> str:
    """Build intro section."""
    return (
        f"<div style='padding:28px 24px;border-bottom:1px solid {BORDER_COLOR};'>"
        f"<p style='margin:0;font-size:15px;color:#aaa;line-height:1.8;font-weight:300;'>{escape(text)}</p>"
        f"</div>"
    )


def _build_footer() -> str:
    """Build dark footer."""
    return (
        f"<div style='padding:32px 24px;background:#111;text-align:center;'>"
        f"<p style='margin:0 0 8px 0;font-size:11px;color:#444;letter-spacing:2px;'>NASA DAILY</p>"
        f"<p style='margin:0;font-size:12px;color:#333;'>Daily space exploration updates</p>"
        f"</div>"
    )


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    """Build complete HTML with new dark theme."""
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
    
    # Build headline from first article or default - must be Chinese and exactly 30 chars
    headline = build_headline_title(articles, date_str)
    
    # Build content
    html_parts = [
        f"<div style='background:{DARK_BG};width:100%;font-family:{FONT_FAMILY};'>",
        _build_header(date_str, headline),
        _build_intro(intro),
    ]
    
    # Science article
    if science_article:
        html_parts.append(_build_article_section(science_article, "science"))
    
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
    """Build headline title - Chinese only, exactly 30 characters."""
    if not articles:
        return "NASA每日航天动态精选报道"
    
    # Get first article title
    first_title = normalize_cn_title(articles[0].get("title", ""))
    if not first_title:
        return "NASA每日航天动态精选报道"
    
    # Ensure Chinese title with exactly 30 characters
    return fit_title_exact_length(first_title, 30)


def fit_title_exact_length(title: str, exact_len: int = 30) -> str:
    """Fit title to exact length with Chinese content."""
    title = normalize_cn_title(title)
    
    # If title is already exact length, return it
    if len(title) == exact_len:
        return title
    
    # If title is shorter, pad with suffix
    if len(title) < exact_len:
        suffixes = ["最新进展", "深度解析", "全面报道", "详细解读", "现场直击"]
        for suffix in suffixes:
            combined = title + suffix
            if len(combined) == exact_len:
                return combined
            if len(combined) < exact_len:
                # Add more padding
                padding = "报道"
                combined = title + suffix + padding
                if len(combined) >= exact_len:
                    return combined[:exact_len]
        # If still short, pad with generic text
        padding_needed = exact_len - len(title)
        if padding_needed > 0:
            generic = "航天动态最新进展详细报道"
            return title + generic[:padding_needed]
        return title
    
    # If title is longer, truncate intelligently
    # Try to find a natural break point
    breakpoints = ["，", ",", "：", ":", "；", ";", " ", "、", "的", "了", "在", "是"]
    for bp in breakpoints:
        if bp in title[:exact_len]:
            idx = title[:exact_len].rfind(bp)
            if idx > 10:
                truncated = title[:idx]
                # Pad to exact length
                padding_needed = exact_len - len(truncated)
                if padding_needed > 0:
                    suffixes = ["最新进展", "深度解析", "全面报道", "详细解读"]
                    for suffix in suffixes:
                        if len(truncated) + len(suffix) == exact_len:
                            return truncated + suffix
                    generic = "航天动态最新进展详细报道"
                    return truncated + generic[:padding_needed]
                return truncated
    
    # Hard truncate and pad
    truncated = title[:exact_len]
    return truncated


def build_final_title(articles: list[dict[str, Any]], date_str: str) -> str:
    """Build final article title."""
    return build_headline_title(articles, date_str)


def generate_html_content(articles: list[dict[str, Any]], date_str: str) -> str:
    """Generate complete HTML content for WeChat."""
    title = build_final_title(articles, date_str)
    cover_urls = [a.get("cover_url", "") or a.get("image_url", "") for a in articles[:3]]
    return build_fallback_html(date_str, title, articles, cover_urls)
