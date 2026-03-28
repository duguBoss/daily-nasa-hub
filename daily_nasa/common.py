from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from .config import FOLLOW_HEADER_GIF, GENERIC_TITLE_TOKENS


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def count_chinese_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def clean_english_artifacts(text: str) -> str:
    clean_text = normalize_whitespace(text)
    clean_text = re.sub(r"your browser does not support the audio element\.?", "", clean_text, flags=re.I)
    return normalize_whitespace(clean_text)


def parse_en_date_to_cn(text: str) -> str:
    month_map = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b",
        text,
        flags=re.I,
    )
    if not match:
        return ""
    month = month_map.get(match.group(1).lower())
    if not month:
        return ""
    day = int(match.group(2))
    return f"{month}月{day}日"


def extract_numeric_fact(text: str) -> str:
    amount = re.search(r"\$([0-9][0-9,.]*)\s*(million|billion)?", text, flags=re.I)
    if amount:
        value = amount.group(1).replace(",", "")
        unit = (amount.group(2) or "").lower()
        try:
            num = float(value)
        except Exception:
            num = None

        if unit == "million" and num is not None:
            return f"金额约{num:g}百万美元"
        if unit == "billion" and num is not None:
            return f"金额约{num:g}十亿美元"
        return f"金额约{amount.group(1)}美元"

    date_cn = parse_en_date_to_cn(text)
    if date_cn:
        return f"关键时间点在{date_cn}"
    return ""


def normalize_cn_title(title: str) -> str:
    text = normalize_whitespace(title)
    if count_chinese_chars(text) >= 4:
        return text

    lower = text.lower()
    exact_rules = [
        (
            "artemis ii crew arrives at launch site, shares moon mascot",
            "Artemis II乘组抵达发射场并公布月球吉祥物",
        ),
        (
            "nasa selects intuitive machines to deliver artemis science, tech to moon",
            "NASA选定Intuitive Machines执行Artemis月面科学与技术投送",
        ),
        ("i am artemis", "Artemis人物故事：一线岗位与任务协同"),
    ]
    for key, cn in exact_rules:
        if key in lower:
            return cn

    keyword_rules = [
        (("artemis", "launch"), "Artemis任务发布发射阶段进展"),
        (("intuitive machines", "clps"), "CLPS月面投送新增商业合同"),
        (("spacestation", "spacewalk"), "空间站舱外任务窗口开启"),
        (("moon", "lunar"), "NASA登月任务发布最新节点"),
        (("rocket", "launch"), "NASA火箭任务发布关键里程碑"),
        (("image", "gallery"), "NASA航天影像发布今日重点"),
    ]
    for keys, cn in keyword_rules:
        if any(key in lower for key in keys):
            return cn

    proper_nouns = re.findall(r"[A-Z][A-Za-z0-9-]{2,}", text)
    if proper_nouns:
        return f"NASA任务更新：{proper_nouns[0]}相关进展"
    return "NASA任务更新：关键任务节点发布"


def normalize_cn_summary(summary: str, title: str) -> str:
    text = clean_english_artifacts(summary)
    if count_chinese_chars(text) >= 28:
        return text[:260]

    lower = (f"{title} {summary}").lower()
    mission = normalize_cn_title(title).replace("NASA任务更新：", "")
    facts: list[str] = []

    numeric_fact = extract_numeric_fact(summary)
    if numeric_fact:
        facts.append(numeric_fact)
    if "crew" in lower and "launch" in lower:
        facts.append("乘组状态已进入发射前协同准备")
    if "clps" in lower or "intuitive machines" in lower:
        facts.append("任务属于NASA商业月面载荷服务体系")
    if "moon" in lower or "lunar" in lower:
        facts.append("核心目标围绕月面能力验证")
    if "spacewalk" in lower or "iss" in lower or "spacestation" in lower:
        facts.append("与空间站长期在轨运营相关")

    fact_text = "；".join(dict.fromkeys(facts))
    if fact_text:
        return f"这条消息聚焦{mission}。{fact_text}。值得关注任务目标、执行节点与后续验证安排。"

    return (
        f"这条消息聚焦{mission}。本文提炼任务目标、关键进展与后续节点，"
        "帮助你快速理解这条NASA动态为什么值得持续关注。"
    )


def ensure_follow_header(weixin_html: str) -> str:
    if FOLLOW_HEADER_GIF in weixin_html:
        return weixin_html
    header = (
        "<section style='margin:0;padding:0;'>"
        f"<img src='{FOLLOW_HEADER_GIF}' style='width:100%;display:block;'>"
        "</section>"
    )
    return header + weixin_html


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:60] or "news"


def github_asset_url(asset_path: str, repo: str = "duguBoss/daily-nasa-hub", branch: str = "main") -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{asset_path}".replace("\\", "/")


def canonicalize_url(raw_url: str, base_url: str = "https://www.nasa.gov") -> str:
    absolute = urljoin(base_url, raw_url)
    parsed = urlparse(absolute)
    cleaned = parsed._replace(query="", fragment="")
    normalized_path = re.sub(r"/{2,}", "/", cleaned.path).rstrip("/")
    if not normalized_path:
        normalized_path = "/"
    cleaned = cleaned._replace(path=normalized_path)
    return urlunparse(cleaned)


def title_skeleton(title: str) -> str:
    text = normalize_whitespace(title).lower()
    text = re.sub(r"[0-9一二三四五六七八九十条个篇：:，,。.!！?？·\-\s]", "", text)
    for token in GENERIC_TITLE_TOKENS:
        text = text.replace(token, "")
    return text


def title_similarity(left: str, right: str) -> float:
    a = title_skeleton(left)
    b = title_skeleton(right)
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def is_title_repetitive(title: str, recent_titles: Iterable[str], threshold: float = 0.72) -> bool:
    skeleton = title_skeleton(title)
    for recent in list(recent_titles)[:12]:
        if not recent:
            continue
        recent_skeleton = title_skeleton(recent)
        if skeleton and skeleton == recent_skeleton:
            return True
        if title_similarity(title, recent) >= threshold:
            return True
    return False


def text_language_stats(text: str) -> tuple[int, int, float]:
    chinese_chars = count_chinese_chars(text)
    english_words = len(re.findall(r"[A-Za-z]{2,}", text))
    ratio = chinese_chars / max(chinese_chars + english_words * 2, 1)
    return chinese_chars, english_words, ratio


def is_html_chinese_friendly(weixin_html: str) -> bool:
    soup = BeautifulSoup(weixin_html or "<section></section>", "html.parser")
    plain_text = clean_english_artifacts(soup.get_text(" ", strip=True))
    chinese_chars, english_words, ratio = text_language_stats(plain_text)
    long_english_phrase = bool(re.search(r"(?:\b[A-Za-z]{3,}\b\s+){5,}", plain_text))

    if "your browser does not support the audio element" in plain_text.lower():
        return False
    return chinese_chars >= 300 and ratio >= 0.80 and english_words <= 30 and not long_english_phrase
