from __future__ import annotations

import hashlib
import random
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
        points.append(f"可量化信号：{numeric_fact}")
    if "artemis" in raw:
        points.append("任务定位：属于Artemis体系，直接关系后续登月节奏。")
    if "clps" in raw or "intuitive machines" in raw:
        points.append("执行模式：商业公司参与月面投送，说明NASA在持续扩大商业协同。")
    if "crew" in raw and "launch" in raw:
        points.append("阶段判断：乘组与发射场同步推进，意味着测试飞行准备进入实操阶段。")
    if "spacewalk" in raw or "iss" in raw:
        points.append("在轨影响：这类消息通常关联空间站长期运行稳定性和补给策略。")
    if "moon" in raw or "lunar" in raw:
        points.append("战略价值：月面相关节点往往会影响后续多项实验和国际合作排期。")

    if not points:
        points = [
            "关键信号：本条动态虽然不一定是“发射大新闻”，但通常是任务推进的关键拼图。",
            "读者收益：提前理解这一步在整个任务链条的位置，后续看到新进展时更容易判断轻重缓急。",
        ]

    return " ".join(points)


def _build_next_watch(article: dict[str, Any]) -> str:
    raw = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    watch: list[str] = []
    if "launch" in raw:
        watch.append("关注下一次官方窗口更新时间，尤其是发射日期是否发生调整。")
    if "contract" in raw or "clps" in raw or "intuitive machines" in raw:
        watch.append("关注后续是否披露具体载荷清单、任务批次与执行时间线。")
    if "crew" in raw:
        watch.append("关注乘组后续训练、系统联调和任务分工披露。")
    if "moon" in raw or "lunar" in raw:
        watch.append("关注月面着陆、通信链路和关键技术验证节点是否按计划推进。")
    if not watch:
        watch.append("关注 NASA 下一条配套通报，通常会补充更具体的执行细节。")
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
            f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:#334155;'>"
            f"<strong>关键信息：</strong>{summary}</p>"
            f"<p style='margin:0 0 10px 0;font-size:15px;line-height:1.92;color:#334155;'>"
            f"<strong>对你意味着什么：</strong>{takeaway}</p>"
            f"<p style='margin:0;font-size:15px;line-height:1.92;color:#334155;'>"
            f"<strong>下一步关注点：</strong>{watch}</p>"
            "</section>"
        )
        cards_html += card

    intro = (
        "这不是“简单转发新闻”的NASA快讯，而是面向普通读者的任务解读版。"
        "你将看到每条动态在任务链条中的位置、为什么此刻值得关注、以及下一步应该盯哪些信号。"
        "如果你关心登月进度、空间站运营和深空任务节奏，这份内容会帮你在最短时间抓住真正有价值的信息。"
    )
    reader_checklist = (
        "本期阅读建议：先看每条“关键信息”快速建立背景，再重点看“对你意味着什么”理解战略价值，"
        "最后按“下一步关注点”做后续追踪。这样你不会被碎片化消息带偏，能持续跟上NASA任务主线。"
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
        "<p style='margin:10px 0 0 0;font-size:14px;line-height:1.9;color:#455b73;'>"
        f"{reader_checklist}</p>"
        "<p style='margin:10px 0 0 0;font-size:13px;line-height:1.8;color:#5b7088;'>"
        "关键词：NASA、阿尔忒弥斯计划、登月任务、空间站、深空探索</p>"
        "</section>"
        f"{cards_html}"
        "<section style='margin:4px 0 20px 0;padding:16px;border-radius:12px;background:#fffaf0;border:1px solid #ffe4b8;'>"
        "<p style='margin:0;font-size:15px;color:#5f4b2f;line-height:1.9;'><strong>互动问题：</strong>"
        "如果你只追一条后续消息，你会选哪条？你更在意发射时间、技术验证，还是商业合作进展？</p>"
        "<p style='margin:8px 0 0 0;font-size:14px;color:#7b6543;line-height:1.9;'>"
        "留言告诉我你的关注点，下一期会优先补充你最关心的任务细节。</p>"
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
            f"NASA最新通报：{signal}进展与影响",
            f"NASA这条更新值得看：{signal}深度梳理",
            f"NASA刚发布新变化：{signal}后续怎么看",
            f"NASA一条重磅动态：{signal}时间点拆解",
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
