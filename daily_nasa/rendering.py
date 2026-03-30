from __future__ import annotations

import hashlib
import re
from typing import Any

from .common import (
    extract_numeric_fact,
    is_title_repetitive,
    normalize_cn_summary,
    normalize_cn_title,
    normalize_whitespace,
    title_similarity,
)
from .config import BOTTOM_BANNER_URL, TITLE_KEYWORDS, TOP_BANNER_URL


def _build_reader_takeaway(article: dict[str, Any]) -> str:
    raw = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    points: list[str] = []

    numeric_fact = extract_numeric_fact(article.get("summary", ""))
    if numeric_fact:
        points.append(numeric_fact)
    if "artemis" in raw:
        points.append("属于Artemis体系，直接影响后续登月节奏。")
    if "clps" in raw or "intuitive machines" in raw:
        points.append("商业公司参与月面投送，NASA在扩大商业协同模式。")
    if "crew" in raw and "launch" in raw:
        points.append("乘组与发射场同步推进，测试飞行进入实操阶段。")
    if "spacewalk" in raw or "iss" in raw:
        points.append("关联空间站长期运行稳定性和补给策略。")
    if "moon" in raw or "lunar" in raw:
        points.append("月面节点通常影响后续实验和国际合作排期。")

    if not points:
        points = ["这条动态是任务推进中的关键拼图。"]

    return " ".join(points)


def _build_next_watch(article: dict[str, Any]) -> str:
    raw = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    watch: list[str] = []
    if "launch" in raw:
        watch.append("下一条官方通报，重点看发射日期是否调整。")
    if "contract" in raw or "clps" in raw or "intuitive machines" in raw:
        watch.append("后续载荷清单和执行时间线披露。")
    if "crew" in raw:
        watch.append("乘组训练进展和任务分工披露。")
    if "moon" in raw or "lunar" in raw:
        watch.append("月面着陆、通信链路和关键技术验证节点。")
    if not watch:
        watch.append("NASA下一条配套通报，通常会补充执行细节。")
    return " ".join(watch[:2])


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    cards_html = ""
    for idx, article in enumerate(articles, start=1):
        image = article.get("cover_url", "") or article.get("image_url", "")
        meta = " · ".join(part for part in [article.get("channel", "NASA"), article.get("publish_time", "")] if part)
        card_title = normalize_cn_title(article.get("title", ""))
        summary = normalize_cn_summary(article.get("summary", ""), card_title)
        takeaway = _build_reader_takeaway(article)
        watch = _build_next_watch(article)

        card = (
            "<section style='margin:0 0 18px 0;padding:16px;border:1px solid #e8eef5;border-radius:14px;"
            "background:#ffffff;box-shadow:0 6px 16px rgba(20,35,54,0.06);'>"
            f"<h3 style='margin:0 0 8px 0;font-size:19px;line-height:1.45;color:#1b2c45;'>No.{idx} {card_title}</h3>"
            f"<p style='margin:0 0 12px 0;font-size:13px;color:#64748b;line-height:1.7;'>{meta}</p>"
        )
        if image:
            card += (
                f"<img src='{image}' style='width:100%;display:block;border-radius:12px;margin:0 0 12px 0;"
                "object-fit:cover;'>"
            )
        card += (
            f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:#334155;'>{summary}</p>"
            f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:#334155;'>{takeaway}</p>"
            f"<p style='margin:0;font-size:15px;line-height:1.92;color:#334155;'>{watch}</p>"
            "</section>"
        )
        cards_html += card

    intro = (
        "航天迷视角的NASA日报。不做简单搬运，只挑今天最值得追的那条，"
        "说清楚它在任务链条里卡在哪一环、为什么这个节点值得盯。"
    )

    return (
        "<section style='background:#f4f8fc;'>"
        f"<img src='{TOP_BANNER_URL}' style='width:100%;display:block;'>"
        "<section style='padding:24px 12px 8px 12px;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,"
        "Helvetica Neue,PingFang SC,Hiragino Sans GB,Microsoft YaHei,sans-serif;'>"
        "<section style='padding:18px 14px;border-radius:14px;background:linear-gradient(140deg,#f7fbff 0%,#eef5ff 100%);"
        "margin-bottom:22px;'>"
        f"<p style='margin:0 0 8px 0;font-size:13px;color:#61758a;line-height:1.7;'>NASA Daily · {date_str}</p>"
        f"<h1 style='margin:0;font-size:24px;line-height:1.38;color:#10243e;'>{title}</h1>"
        f"<p style='margin:12px 0 0 0;font-size:15px;line-height:1.9;color:#364a60;'>{intro}</p>"
        "<p style='margin:10px 0 0 0;font-size:13px;line-height:1.8;color:#5b7088;'>"
        "关键词：NASA、阿尔忒弥斯计划、登月任务、空间站、深空探索</p>"
        "</section>"
        f"{cards_html}"
        "</section>"
        f"<img src='{BOTTOM_BANNER_URL}' style='width:100%;display:block;'>"
        "</section>"
    )


def pick_title_focus(articles: list[dict[str, Any]]) -> str:
    text = " ".join([f"{a.get('title', '')} {a.get('summary', '')}" for a in articles]).lower()
    rules = [
        (("artemis", "moon", "launch"), "Artemis登月"),
        (("spacestation", "spacewalk", "crew", "iss"), "空间站任务"),
        (("asteroid", "mars", "moon"), "深空探索"),
        (("earth", "climate", "volcano"), "地球观测"),
        (("rocket", "engine", "propulsion"), "火箭工程"),
        (("image", "gallery", "photo"), "航天影像"),
    ]
    for keywords, focus in rules:
        if any(keyword in text for keyword in keywords):
            return focus
    return "太空前沿"


def infer_story_signal(articles: list[dict[str, Any]]) -> str:
    text = " ".join([f"{a.get('title', '')} {a.get('summary', '')}" for a in articles]).lower()
    if "intuitive machines" in text or "clps" in text:
        return "CLPS月面投送"
    if "artemis ii" in text and ("crew" in text or "launch" in text):
        return "Artemis II发射前准备"
    if "spacewalk" in text or "spacestation" in text or "iss" in text:
        return "空间站任务窗口"
    if "moon" in text or "lunar" in text:
        return "登月任务节点"
    return pick_title_focus(articles)


def extract_lead_subject(articles: list[dict[str, Any]]) -> str:
    if not articles:
        return "任务主线"
    lead = normalize_whitespace(str(articles[0].get("title", "")))
    lead = re.sub(r"^No\.\d+\s*", "", lead, flags=re.I)
    lead = lead.replace("NASA", "").strip(":：,，.。 ")
    if len(lead) > 10:
        lead = lead[:10]
    return lead or "任务主线"


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
    if signal in text_lower:
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
        summary = normalize_whitespace(article.get("summary", ""))
        channel = article.get("channel", "")
        publish_time = article.get("publish_time", "")
        image = article.get("cover_url", "") or article.get("image_url", "")
        url = article.get("url", "")

        block = f"[News {idx}]\nTitle: {title}"
        if channel:
            block += f"\nChannel: {channel}"
        if publish_time:
            block += f"\nTime: {publish_time}"
        block += f"\nSummary: {summary}"
        if image:
            block += f"\nImage: {image}"
        if url:
            block += f"\nURL: {url}"
        blocks.append(block)

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
    styles = ["倒计时", "关键节点", "里程碑", "进展", "追踪"]
    candidates = []

    for style in styles:
        for suffix in ["", f":{lead_subject}", f":{signal}"]:
            candidate = f"{style}{suffix}" if suffix else style
            if 14 <= len(candidate) <= 28:
                candidates.append(candidate)

    candidates.extend([
        f"{signal}最新进展",
        f"{lead_subject}有动静",
        "Artemis相关任务更新",
    ])

    best_title = "NASA今日任务动态"
    best_score = -1
    for candidate in candidates:
        score = score_title_candidate(candidate, signal, lead_subject, recent_titles, "")
        if score > best_score:
            best_score = score
            best_title = candidate

    return fit_title_length(best_title)
