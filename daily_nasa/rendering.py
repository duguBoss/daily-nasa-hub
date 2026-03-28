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
        "这不是“搬运快讯”，而是一份航天迷视角的 NASA 任务带读。"
        "我会把今天最该追的一条先拎出来，再告诉你它在任务链条里处于哪一环、为什么这一刻值得盯。"
        "如果你本来就爱看登月、空间站和深空任务，这份内容会更像同好之间的高密度情报交换。"
    )
    reader_checklist = (
        "航天爱好者阅读建议：先看“关键信息”锁定事实，再看“对你意味着什么”判断轻重，"
        "最后按“下一步关注点”建立追踪清单。这样不会只看热闹，而是能持续跟踪任务主线。"
    )
    deep_dive = (
        "延伸解读：很多读者会把NASA动态当作“今天又发了什么消息”，但真正有价值的是识别每条消息在任务链条里的位置。"
        "例如合同类新闻通常对应资源配置和执行节奏变化，乘组与发射场消息对应任务进入实操阶段，技术验证消息则对应后续大节点是否按时推进。"
        "当你用“阶段定位 + 影响判断 + 下一步追踪”三步阅读法时，同样一条新闻的信息价值会明显提升。"
    )
    deep_dive_2 = (
        "建议把这份日报当成任务跟踪面板来用：先记住任务名称与当前阶段，再记录下一条需要验证的公开信号，"
        "例如发射窗口、载荷清单、在轨验证结果或时间表变动。这样连续看一周后，你会形成完整认知，而不是只看到零散新闻标题。"
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
        "<p style='margin:10px 0 0 0;font-size:14px;line-height:1.9;color:#455b73;'>"
        f"{reader_checklist}</p>"
        "<p style='margin:10px 0 0 0;font-size:14px;line-height:1.9;color:#455b73;'>"
        f"{deep_dive}</p>"
        "<p style='margin:10px 0 0 0;font-size:14px;line-height:1.9;color:#455b73;'>"
        f"{deep_dive_2}</p>"
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


def extract_lead_subject(articles: list[dict[str, Any]]) -> str:
    if not articles:
        return "任务主线"
    lead = normalize_whitespace(str(articles[0].get("title", "")))
    lead = re.sub(r"^No\.\d+\s*", "", lead, flags=re.I)
    lead = lead.replace("NASA", "").strip("：:，,。 ")
    if len(lead) > 10:
        lead = lead[:10]
    return lead or "任务主线"


def fit_title_length(title: str) -> str:
    text = normalize_whitespace(title).strip("：:，,。 ")
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
    style_tag: str,
) -> float:
    score = 100.0
    if not re.search(r"[0-9一二三四五六七八九十]", title):
        score -= 12
    if not any(keyword.lower() in title.lower() for keyword in TITLE_KEYWORDS):
        score -= 10
    if not (14 <= len(title) <= 28):
        score -= 8
    if signal and signal in title:
        score += 5
    if lead_subject and lead_subject in title:
        score += 7
    else:
        score -= 10
    if preferred_style and style_tag == preferred_style:
        score += 4

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
    title_count = max(1, count)
    focus = pick_title_focus(articles)
    signal = infer_story_signal(articles)
    lead_subject = extract_lead_subject(articles)

    style_packs = [
        (
            "倒计时",
            [
                f"NASA焦点1条：{lead_subject}进入倒计时",
                f"NASA通报1条：{lead_subject}窗口临近",
            ],
            [
                f"NASA今日{title_count}条：{lead_subject}倒计时信号",
                f"NASA速报{title_count}条：{lead_subject}窗口变化",
            ],
        ),
        (
            "里程碑",
            [
                f"NASA焦点1条：{lead_subject}里程碑节点",
                f"NASA更新1条：{lead_subject}关键里程碑",
            ],
            [
                f"NASA今日{title_count}条：{lead_subject}里程碑进展",
                f"NASA更新{title_count}节点：{lead_subject}与{signal}",
            ],
        ),
        (
            "看点清单",
            [
                f"NASA看点1条：{lead_subject}三件事",
                f"NASA任务追踪1条：{lead_subject}重点清单",
            ],
            [
                f"NASA最新{title_count}看点：{lead_subject}与{focus}",
                f"NASA这{title_count}条要点：{lead_subject}重点清单",
            ],
        ),
        (
            "变化判断",
            [
                f"NASA新动态1条：{lead_subject}关键变化",
                f"NASA通报1条：{lead_subject}进度变化",
            ],
            [
                f"NASA今日{title_count}条：{lead_subject}关键变化",
                f"NASA速报{title_count}条：{lead_subject}变化判断",
            ],
        ),
        (
            "追踪提醒",
            [
                f"NASA焦点1条：{lead_subject}下一步怎么盯",
                f"NASA更新1条：{lead_subject}后续看点",
            ],
            [
                f"NASA今日{title_count}条：{lead_subject}后续怎么盯",
                f"NASA这{title_count}条要点：{lead_subject}追踪提醒",
            ],
        ),
    ]

    seed_source = f"{date_str}|{count}|{signal}|{focus}|{lead_subject}"
    seed = int(hashlib.md5(seed_source.encode("utf-8")).hexdigest()[:8], 16)
    preferred_idx = seed % len(style_packs)

    candidates_with_style: list[tuple[str, str]] = []
    for offset in range(len(style_packs)):
        idx = (preferred_idx + offset) % len(style_packs)
        style_tag, single_templates, multi_templates = style_packs[idx]
        templates = single_templates if count <= 1 else multi_templates
        for template in templates:
            candidates_with_style.append((fit_title_length(template), style_tag))

    deduped_candidates: list[tuple[str, str]] = []
    seen_titles: set[str] = set()
    for title, style_tag in candidates_with_style:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        deduped_candidates.append((title, style_tag))

    if not deduped_candidates:
        deduped_candidates = [(fit_title_length(f"NASA今日{max(1, count)}条关键进展：{focus}速读"), "默认")]

    preferred_style = style_packs[preferred_idx][0]
    best_title, _ = max(
        deduped_candidates,
        key=lambda item: score_title_candidate(
            item[0],
            signal,
            lead_subject,
            recent_titles,
            preferred_style,
            item[1],
        ),
    )
    if is_title_repetitive(best_title, recent_titles):
        for candidate, _ in deduped_candidates:
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
