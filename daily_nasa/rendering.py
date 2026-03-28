from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from .common import (
    is_title_repetitive,
    normalize_cn_summary,
    normalize_cn_title,
    normalize_whitespace,
    title_similarity,
)
from .config import BOTTOM_BANNER_URL, TITLE_KEYWORDS, TOP_BANNER_URL


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    cards_html = ""
    for idx, article in enumerate(articles, start=1):
        image = article.get("cover_url", "") or article.get("image_url", "")
        meta = " · ".join(part for part in [article.get("channel", "NASA"), article.get("publish_time", "")] if part)
        card_title = normalize_cn_title(article.get("title", ""))
        summary = normalize_cn_summary(article.get("summary", ""), card_title)
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
            f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:#334155;'>"
            f"<strong>看点速读：</strong>{summary}</p>"
            "<p style='margin:0;font-size:14px;line-height:1.9;color:#475569;'><strong>价值判断：</strong>"
            "这条更新关系到 NASA 后续任务节奏和技术验证进度，适合持续追踪下一次官方通报。</p>"
            "</section>"
        )
        cards_html += card

    intro = (
        "今天这份 NASA 动态快报，聚焦阿尔忒弥斯计划、空间站任务与深空技术。"
        "你将看到每条消息的核心进展、关键节点和影响判断，便于快速获取高价值航天信息。"
    )
    return (
        "<section style='background:#f4f8fc;'>"
        f"<img src='{TOP_BANNER_URL}' style='width:100%;display:block;'>"
        "<section style='padding:24px 16px 8px 16px;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,"
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
        "<section style='margin:4px 0 20px 0;padding:16px;border-radius:12px;background:#fffaf0;border:1px solid #ffe4b8;'>"
        "<p style='margin:0;font-size:15px;color:#5f4b2f;line-height:1.9;'><strong>互动话题：</strong>"
        "今天这几条 NASA 动态里，你最想追踪哪个任务后续？为什么？</p>"
        "<p style='margin:8px 0 0 0;font-size:14px;color:#7b6543;line-height:1.9;'>"
        "欢迎在评论区留下你的观点，我们会优先跟进高关注任务。</p>"
        "</section>"
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


def fit_title_length(title: str) -> str:
    text = normalize_whitespace(title).strip("：:，,。 ")
    if len(text) > 28:
        text = text[:28]
    if len(text) < 14:
        text = f"{text}最新进展"
    if len(text) > 28:
        text = text[:28]
    return text


def score_title_candidate(title: str, signal: str, recent_titles: list[str]) -> float:
    score = 100.0
    if not re.search(r"[0-9一二三四五六七八九十]", title):
        score -= 12
    if not any(keyword.lower() in title.lower() for keyword in TITLE_KEYWORDS):
        score -= 10
    if not (14 <= len(title) <= 28):
        score -= 8
    if signal and signal in title:
        score += 5

    similarity_penalty = 0.0
    for recent in recent_titles[:12]:
        similarity_penalty = max(similarity_penalty, title_similarity(title, recent))
    score -= similarity_penalty * 35
    if is_title_repetitive(title, recent_titles):
        score -= 18
    return score


def build_wechat_fallback_title(
    date_str: str,
    articles: list[dict[str, Any]],
    recent_titles: list[str] | None = None,
) -> str:
    recent_titles = recent_titles or []
    count = len(articles)
    focus = pick_title_focus(articles)
    signal = infer_story_signal(articles)

    if count <= 1:
        templates = [
            f"NASA今日焦点：{signal}关键节点解读",
            f"NASA最新通报：{signal}影响有哪些",
            f"NASA这条更新值得看：{signal}进展速读",
            f"NASA刚发布新变化：{signal}后续怎么看",
            f"NASA一条重磅动态：{signal}时间点梳理",
        ]
    else:
        templates = [
            f"NASA今日{count}条动态：{signal}与{focus}新进展",
            f"NASA更新{count}个任务节点：{signal}进度速览",
            f"NASA最新{count}条看点：{focus}与{signal}进度",
            f"NASA一天释放{count}个信号：{signal}关键变化",
            f"NASA这{count}条最值得追踪：{signal}和{focus}",
        ]

    candidates = [fit_title_length(template) for template in templates]
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        candidates = [fit_title_length(f"NASA今日{max(1, count)}条关键进展：{focus}速读")]

    seed_source = f"{date_str}|{count}|{signal}|{focus}"
    seed = int(hashlib.md5(seed_source.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    rng.shuffle(candidates)

    best_title = max(candidates, key=lambda title: score_title_candidate(title, signal, recent_titles))
    if is_title_repetitive(best_title, recent_titles):
        for candidate in candidates:
            if not is_title_repetitive(candidate, recent_titles):
                best_title = candidate
                break
    return fit_title_length(best_title)


def build_default_payload(
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
    recent_titles: list[str] | None = None,
) -> dict[str, Any]:
    songs = [{"name": normalize_cn_title(article["title"]), "artist": article.get("channel", "NASA")} for article in articles]
    title = build_wechat_fallback_title(date_str, articles, recent_titles or [])
    return {
        "date": date_str,
        "title": title,
        "covers": cover_urls[:5],
        "songs": songs[:5],
        "weixin_html": build_fallback_html(date_str, title, articles, cover_urls),
    }


def build_article_blocks(articles: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for idx, article in enumerate(articles, start=1):
        blocks.append(
            "\n".join(
                [
                    f"Item {idx}",
                    f"- title: {article['title']}",
                    f"- channel: {article.get('channel', 'NASA')}",
                    f"- published_at: {article.get('publish_time', '')}",
                    f"- summary: {article.get('summary', '')}",
                    f"- url: {article['url']}",
                    f"- image: {article.get('cover_url', article.get('image_url', ''))}",
                ]
            )
        )
    return "\n\n".join(blocks)
