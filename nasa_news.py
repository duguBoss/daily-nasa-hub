from __future__ import annotations

import datetime
import hashlib
import json
import os
import random
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import pytz
import requests
from bs4 import BeautifulSoup


NASA_NEWS_URLS = [
    "https://www.nasa.gov/news/recently-published/",
    "https://www.nasa.gov/2026-news-releases/",
]
IMAGE_OF_THE_DAY_URL = "https://www.nasa.gov/image-of-the-day/"

MODEL_NAME = "gemini-3.1-flash-lite-preview"
REQUEST_TIMEOUT = 30
LIST_TOP_N = 5
MERGE_TOP_N = 3
MAX_SEEN_URLS = 1200
MIN_QUALITY_SCORE = 90
MAX_MODEL_ATTEMPTS = 3
MAX_REWRITE_ROUNDS = 2
ASSET_ROOT = Path("assets") / "generated"
STATE_FILE = Path("state") / "nasa_seen_urls.json"
SHANGHAI_TZ = pytz.timezone("Asia/Shanghai")

FOLLOW_HEADER_GIF = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "xm1dT1jCe8lIO3P2oFVtd1x040PKGCRPN033gUTrHQQz0Licdqug5X1QgUPQBRCicoTqdYMrpgk7etibXLkK9rwcg/0"
    "?wx_fmt=gif&from=appmsg"
)
TOP_BANNER_URL = (
    FOLLOW_HEADER_GIF
)
BOTTOM_BANNER_URL = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/"
    "0?wx_fmt=gif"
)

TITLE_KEYWORDS = (
    "NASA",
    "Artemis",
    "阿尔忒弥斯",
    "登月",
    "空间站",
    "火箭",
    "深空",
    "月球",
    "探测",
)
FORBIDDEN_TITLE_PATTERNS = (
    "NASA今日速递",
    "一次看懂",
    "原文",
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def count_chinese_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def normalize_cn_summary(summary: str, title: str) -> str:
    text = normalize_whitespace(summary)
    if count_chinese_chars(text) >= 18:
        return text

    clean_title = normalize_whitespace(title)
    return (
        f"NASA 最新动态聚焦“{clean_title}”。本文提炼任务目标、关键进展与后续节点，"
        "帮助你用一分钟看懂这条消息为什么值得持续关注。"
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


def is_nasa_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"www.nasa.gov", "nasa.gov", "science.nasa.gov"}:
        return False

    path = parsed.path.lower().strip("/")
    if not path:
        return False

    blocked_prefixes = {
        "news",
        "events",
        "missions",
        "learning-resources",
        "a-to-z-topics-listing",
        "a-to-z-of-nasa-missions",
        "nasa-brand-center",
        "social-media",
        "podcasts-and-audio",
    }
    if path in blocked_prefixes:
        return False

    blocked_keywords = (
        "search=",
        "wp-content",
        "tag/",
        "category/",
        "page/",
        "topic/",
        "multimedia/",
    )
    if any(keyword in url.lower() for keyword in blocked_keywords):
        return False

    allowed_markers = (
        "/news-release/",
        "/blogs/",
        "/article/",
        "/image-article/",
        "/missions/",
        "/centers-and-facilities/",
        "/science.nasa.gov/",
        "/feature/",
    )
    if any(marker in url.lower() for marker in allowed_markers):
        return True

    return bool(re.search(r"/20\d{2}/\d{2}/\d{2}/", url))


def fetch_page(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()
    return response.text


def parse_card_title(card: Any) -> str:
    heading_link = card.find("a", class_="hds-content-item-heading")
    if heading_link:
        heading_text = normalize_whitespace(heading_link.get_text(" ", strip=True))
        if len(heading_text) >= 8:
            return heading_text

    for selector in ["h2", "h3", "h4"]:
        tag = card.find(selector)
        if not tag:
            continue
        text = normalize_whitespace(tag.get_text(" ", strip=True))
        if len(text) >= 8:
            return text

    text = normalize_whitespace(card.get_text(" ", strip=True))
    read_time_match = re.search(r"\b\d+\s+min read\b", text, flags=re.I)
    if read_time_match:
        text = text[: read_time_match.start()]
    text = re.sub(r"\b(article|blog)\b.*$", "", text, flags=re.I)
    return normalize_whitespace(text)


def parse_nasa_news_list(html: str, source_url: str, top_n: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.hds-content-item")
    items: list[dict[str, Any]] = []

    for card in cards:
        link = card.find("a", class_="hds-content-item-heading", href=True) or card.find("a", href=True)
        if not link:
            continue
        full_url = canonicalize_url(link["href"])
        if not is_nasa_article_url(full_url):
            continue

        title = parse_card_title(card)
        if len(title) < 8:
            continue

        items.append({"title": title, "url": full_url, "source": source_url})

    if not items:
        for link in soup.find_all("a", href=True):
            full_url = canonicalize_url(link["href"])
            if not is_nasa_article_url(full_url):
                continue
            title = normalize_whitespace(link.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            items.append({"title": title, "url": full_url, "source": source_url})

    deduped: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in items:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        deduped.append(item)
        if len(deduped) >= top_n:
            break

    return deduped


def fetch_top_n_articles(top_n: int = LIST_TOP_N) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_url in NASA_NEWS_URLS:
        print(f"Fetching list page: {source_url}")
        try:
            html = fetch_page(source_url)
            source_items = parse_nasa_news_list(html, source_url, top_n)
            print(f"List extracted {len(source_items)} candidates from {source_url}")
        except Exception as exc:
            print(f"Failed to parse list page {source_url}: {exc}")
            continue

        for item in source_items:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            merged.append(item)
            if len(merged) >= top_n:
                return merged

    return merged[:top_n]


def fetch_image_of_the_day_candidate() -> dict[str, Any] | None:
    try:
        html = fetch_page(IMAGE_OF_THE_DAY_URL)
    except Exception as exc:
        print(f"Failed to fetch image-of-the-day page: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        url = canonicalize_url(link["href"])
        if "/image-article/" not in url.lower():
            continue
        if not is_nasa_article_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)

        title = normalize_whitespace(link.get_text(" ", strip=True))
        if not title:
            title = normalize_whitespace(link.get("aria-label", ""))
        if not title:
            title = "NASA Image of the Day"
        return {"title": title, "url": url, "source": IMAGE_OF_THE_DAY_URL}

    print("No image-of-the-day article link found.")
    return None


def infer_channel_name(url: str) -> str:
    url_lower = url.lower()
    if "/news-release/" in url_lower:
        return "NASA News"
    if "/blogs/spacestation/" in url_lower:
        return "ISS Blog"
    if "science.nasa.gov" in url_lower:
        return "NASA Science"
    if "/image-article/" in url_lower:
        return "NASA Gallery"
    return "NASA"


def pick_publish_time(soup: BeautifulSoup) -> str:
    for selector in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "publish_date"}),
    ]:
        tag = soup.find(selector[0], attrs=selector[1])
        if tag and tag.get("content"):
            return tag.get("content", "")

    time_tag = soup.find("time")
    if time_tag:
        return time_tag.get("datetime", "") or normalize_whitespace(time_tag.get_text(" ", strip=True))
    return ""


def fetch_article_content(url: str) -> dict[str, Any]:
    html = fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = normalize_whitespace(h1.get_text(" ", strip=True))
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = normalize_whitespace(og_title.get("content", ""))

    content_root = soup.find("article") or soup.find("main") or soup.find("div", id="content")
    paragraphs: list[str] = []
    if content_root:
        for bad in content_root.find_all(["script", "style", "nav", "footer", "aside"]):
            bad.decompose()
        for p in content_root.find_all("p"):
            text = normalize_whitespace(p.get_text(" ", strip=True))
            if len(text) >= 40:
                paragraphs.append(text)

    content = "\n\n".join(paragraphs[:8])
    if not content:
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        if og_desc:
            content = normalize_whitespace(og_desc.get("content", ""))

    image_url = ""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image.get("content", "")
    if not image_url:
        img = soup.find("img", src=re.compile(r"\.(jpg|jpeg|png|webp)", re.I))
        if img and img.get("src"):
            image_url = img.get("src", "")
    if image_url:
        image_url = canonicalize_url(image_url)

    summary_source = paragraphs[:2] if paragraphs else [content]
    summary = normalize_whitespace(" ".join(summary_source))
    summary = summary[:220]

    return {
        "title": title,
        "content": content,
        "summary": summary,
        "image_url": image_url,
        "publish_time": pick_publish_time(soup),
    }


def build_processed_articles(candidates: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    processed_articles: list[dict[str, Any]] = []

    for idx, candidate in enumerate(candidates, start=1):
        url = candidate["url"]
        print(f"Processing article {idx}/{len(candidates)}: {candidate['title']}")
        try:
            detail = fetch_article_content(url)
        except Exception as exc:
            print(f"Failed to fetch article detail: {exc}")
            detail = {"title": candidate["title"], "summary": "", "content": "", "image_url": "", "publish_time": ""}

        article_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
        article_id = f"nasa-{article_hash}"
        image_path = ""
        cover_url = detail.get("image_url", "")

        image_url = detail.get("image_url", "")
        if image_url:
            slug = slugify(candidate["title"])[:40]
            suffix_match = re.search(r"\.(jpg|jpeg|png|webp)(?:$|[?#])", image_url, re.I)
            image_ext = "." + suffix_match.group(1).lower() if suffix_match else ".jpg"
            file_name = f"{article_hash}-{slug}{image_ext}"
            local_path = ASSET_ROOT / date_str / file_name
            if download_image(image_url, local_path):
                image_path = str(local_path).replace("\\", "/")
                cover_url = github_asset_url(image_path)

        processed_articles.append(
            {
                "id": article_id,
                "title": detail.get("title") or candidate["title"],
                "summary": detail.get("summary", ""),
                "content": detail.get("content", ""),
                "url": url,
                "publish_time": detail.get("publish_time", ""),
                "channel": infer_channel_name(url),
                "image_url": image_url,
                "image_path": image_path,
                "cover_url": cover_url,
            }
        )
        time.sleep(0.8)

    return processed_articles


def download_image(image_url: str, file_path: Path) -> bool:
    if not image_url:
        return False
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(image_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(response.content)
        return True
    except Exception as exc:
        print(f"Failed to download image {image_url}: {exc}")
        return False


def cleanup_old_files(target_date: datetime.date, keep_days: int = 10) -> None:
    cutoff = target_date - datetime.timedelta(days=keep_days)

    for pattern in ["Daily_NASA_*.json", "Daily_NASA_*.md"]:
        for file_path in Path(".").glob(pattern):
            try:
                file_date = datetime.date.fromisoformat(file_path.stem.replace("Daily_NASA_", ""))
                if file_date < cutoff:
                    file_path.unlink()
                    print(f"Deleted old file: {file_path}")
            except ValueError:
                continue

    if ASSET_ROOT.exists():
        for child in ASSET_ROOT.iterdir():
            if not child.is_dir():
                continue
            try:
                folder_date = datetime.date.fromisoformat(child.name)
            except ValueError:
                continue
            if folder_date < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                print(f"Deleted old folder: {child}")


def seed_seen_urls_from_history() -> list[str]:
    seeded: list[str] = []
    for json_file in sorted(Path(".").glob("Daily_NASA_*.json"), reverse=True)[:14]:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        for key in ("source_top_urls", "new_urls"):
            values = data.get(key, [])
            if isinstance(values, list):
                seeded.extend([canonicalize_url(u) for u in values if isinstance(u, str) and u])

        for article in data.get("articles", []):
            if isinstance(article, dict) and article.get("url"):
                seeded.append(canonicalize_url(article["url"]))

    ordered: list[str] = []
    seen: set[str] = set()
    for url in seeded:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered[:MAX_SEEN_URLS]


def load_seen_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        seeded = seed_seen_urls_from_history()
        return {"seen_urls": seeded, "last_fetch_urls": [], "updated_at": ""}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        seen_urls = data.get("seen_urls", [])
        if not isinstance(seen_urls, list):
            seen_urls = []
        last_fetch_urls = data.get("last_fetch_urls", [])
        if not isinstance(last_fetch_urls, list):
            last_fetch_urls = []
        return {
            "seen_urls": [canonicalize_url(u) for u in seen_urls if isinstance(u, str) and u][:MAX_SEEN_URLS],
            "last_fetch_urls": [canonicalize_url(u) for u in last_fetch_urls if isinstance(u, str) and u][:LIST_TOP_N],
            "updated_at": data.get("updated_at", ""),
        }
    except Exception as exc:
        print(f"Failed to load state file, fallback to history seed: {exc}")
        return {"seen_urls": seed_seen_urls_from_history(), "last_fetch_urls": [], "updated_at": ""}


def save_seen_state(state: dict[str, Any], latest_urls: list[str], new_urls: list[str], date_str: str) -> None:
    normalized_latest = [canonicalize_url(u) for u in latest_urls if u]
    normalized_new = [canonicalize_url(u) for u in new_urls if u]
    merged = normalized_latest + state.get("seen_urls", [])
    ordered: list[str] = []
    seen: set[str] = set()
    for url in merged:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)

    state_payload = {
        "updated_at": datetime.datetime.now(SHANGHAI_TZ).isoformat(),
        "date": date_str,
        "last_fetch_urls": normalized_latest[:LIST_TOP_N],
        "last_new_urls": normalized_new[:LIST_TOP_N],
        "seen_urls": ordered[:MAX_SEEN_URLS],
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_payload, f, ensure_ascii=False, indent=2)
    print(f"State updated: {STATE_FILE} (seen={len(state_payload['seen_urls'])})")


def call_gemini(api_key: str, prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "topP": 0.9,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gemini request failed ({response.status_code}): {response.text}")

    result_json = response.json()
    candidate = (result_json.get("candidates") or [{}])[0]
    content = candidate.get("content", {})
    parts = content.get("parts") or []
    if not parts:
        raise RuntimeError("Gemini returned empty content.")
    return parts[0].get("text", "")


def parse_model_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def build_fallback_html(date_str: str, title: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> str:
    cards_html = ""
    for idx, article in enumerate(articles, start=1):
        image = article.get("cover_url", "") or article.get("image_url", "")
        meta = " · ".join(part for part in [article.get("channel", "NASA"), article.get("publish_time", "")] if part)
        summary = normalize_cn_summary(article.get("summary", ""), article["title"])
        card = (
            "<section style='margin:0 0 18px 0;padding:16px;border:1px solid #e8eef5;border-radius:14px;"
            "background:#ffffff;box-shadow:0 6px 16px rgba(20,35,54,0.06);'>"
            f"<h3 style='margin:0 0 8px 0;font-size:19px;line-height:1.45;color:#1b2c45;'>No.{idx} {article['title']}</h3>"
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


def build_wechat_fallback_title(date_str: str, articles: list[dict[str, Any]]) -> str:
    count = len(articles)
    focus = pick_title_focus(articles)
    seed = int(hashlib.md5(date_str.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed + count)

    if count <= 1:
        templates = [
            "NASA今日关键更新：{focus}最新进度与影响",
            "NASA刚发布重要动态：{focus}有哪些新变化",
            "NASA今天最值得看的一条：{focus}关键信息梳理",
            "NASA释出最新信号：{focus}任务节奏正在变化",
            "NASA最新通报来了：{focus}后续看点一文说清",
        ]
        return rng.choice(templates).format(focus=focus)

    templates = [
        "NASA今日{count}条关键进展：{focus}最新时间表和看点",
        "NASA连发{count}条重要更新：{focus}进入新阶段",
        "NASA今天这{count}条最具价值：{focus}、节点与影响",
        "NASA一天释放{count}个任务信号：{focus}进度速读",
        "NASA最新{count}条动态盘点：{focus}为什么值得关注",
    ]
    return rng.choice(templates).format(count=count, focus=focus)

def build_default_payload(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str]) -> dict[str, Any]:
    songs = [{"name": article["title"], "artist": article.get("channel", "NASA")} for article in articles]
    title = build_wechat_fallback_title(date_str, articles)
    return {
        "date": date_str,
        "title": title,
        "covers": cover_urls[:5],
        "songs": songs[:5],
        "weixin_html": build_fallback_html(date_str, title, articles, cover_urls),
    }


def load_recent_titles(limit: int = 20) -> list[str]:
    titles: list[str] = []
    for json_file in sorted(Path(".").glob("Daily_NASA_*.json"), reverse=True)[:limit]:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        title = normalize_whitespace(str(data.get("title", "")))
        if title:
            titles.append(title)
    # unique and keep order
    ordered: list[str] = []
    seen: set[str] = set()
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        ordered.append(title)
    return ordered


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


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    return f"""
You are an editor-in-chief for a Chinese WeChat science account and an SEO strategist.
Your task is to turn the NASA updates into one high-retention Chinese article.

Date: {date_str}
News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles to avoid repeating style:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

Output rules (MUST follow):
1) Output valid JSON only. No markdown fences, no explanations.
2) All body content must be Simplified Chinese (mission names like Artemis/ISS can stay in English).
3) Create a title with 14-28 Chinese characters, include number signals and one mission keyword.
4) Do not include external links, anchor tags, or "view source" CTA in weixin_html.
5) Build weixin_html as a complete section with inline styles and include top and bottom banner images.
6) Structure: opening value paragraph, 3 content cards (title + summary + why it matters), interaction question.
7) Make it WeChat-feed friendly: high information density, clear user value in first screen, avoid empty adjectives.
8) Make it SEO-friendly: naturally include keywords like NASA, Artemis, lunar mission, space station, deep space.
9) Avoid duplicated paragraphs or repeated full blocks.

JSON schema:
{{
  "date": "{date_str}",
  "title": "...",
  "covers": ["up to 5 image urls"],
  "songs": [
    {{"name": "news title", "artist": "channel"}}
  ],
  "weixin_html": "<section>...</section>"
}}
"""


def build_gemini_rewrite_prompt(
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
    recent_titles: list[str],
    previous_payload: dict[str, Any],
    quality_report: dict[str, Any],
    attempt: int,
) -> str:
    issues = quality_report.get("issues", [])[:8]
    return f"""
Rewrite the JSON article to pass the quality gate with score >= {MIN_QUALITY_SCORE}.
This is rewrite attempt #{attempt}.

News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

Current draft JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Quality score:
{json.dumps(quality_report, ensure_ascii=False)}

Priority fixes:
{json.dumps(issues, ensure_ascii=False)}

Mandatory constraints:
- Keep output as valid JSON only.
- Keep all user-facing text in Simplified Chinese.
- No external links, no anchor tags, no source jump prompts.
- Keep style engaging but factual and non-clickbait.
- Remove duplication and improve readability for WeChat feed.
- Maintain SEO keyword coverage naturally.

Return the full JSON with keys: date, title, covers, songs, weixin_html.
"""


def sanitize_payload(
    payload: Any,
    default_payload: dict[str, Any],
    date_str: str,
    cover_urls: list[str],
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
    if not title:
        title = default_payload["title"]
    if len(title) > 32:
        title = title[:32]
    normalized["title"] = title

    weixin_html = str(normalized.get("weixin_html", "")).strip()
    if not weixin_html.startswith("<section"):
        weixin_html = default_payload["weixin_html"]
    normalized["weixin_html"] = ensure_follow_header(weixin_html)
    return normalized


def has_repeated_sentences(text: str) -> bool:
    parts = [normalize_whitespace(p) for p in re.split(r"[\u3002\uff01\uff1f!?\n]", text) if normalize_whitespace(p)]
    long_parts = [p for p in parts if len(p) >= 18]
    if len(long_parts) <= 1:
        return False

    seen: dict[str, int] = {}
    for part in long_parts:
        seen[part] = seen.get(part, 0) + 1
        if seen[part] >= 2:
            return True
    return False


def evaluate_payload_quality(payload: dict[str, Any], articles: list[dict[str, Any]]) -> dict[str, Any]:
    title = normalize_whitespace(str(payload.get("title", "")))
    html = str(payload.get("weixin_html", ""))
    soup = BeautifulSoup(html or "<section></section>", "html.parser")
    plain_text = normalize_whitespace(soup.get_text(" ", strip=True))

    issues: list[str] = []
    breakdown: dict[str, int] = {}

    title_score = 0
    if 14 <= len(title) <= 28:
        title_score += 8
    else:
        issues.append("title_length_not_14_28")

    if re.search(r"[0-9一二三四五六七八九十]", title):
        title_score += 4
    else:
        issues.append("title_missing_number_signal")

    if any(keyword.lower() in title.lower() for keyword in TITLE_KEYWORDS):
        title_score += 7
    else:
        issues.append("title_missing_mission_keyword")

    if not any(bad in title for bad in FORBIDDEN_TITLE_PATTERNS):
        title_score += 6
    else:
        issues.append("title_contains_forbidden_pattern")
    breakdown["title"] = title_score

    chinese_chars = count_chinese_chars(plain_text)
    english_words = len(re.findall(r"[A-Za-z]{2,}", plain_text))
    ratio = chinese_chars / max(chinese_chars + english_words * 2, 1)

    target_articles = max(1, len(articles))
    min_chinese_chars = 140 + target_articles * 40

    language_score = 0
    if chinese_chars >= min_chinese_chars:
        language_score += 8
    else:
        issues.append("body_too_short_or_not_enough_chinese")

    if ratio >= 0.70:
        language_score += 8
    elif ratio >= 0.55:
        language_score += 4
        issues.append("chinese_ratio_low")
    else:
        issues.append("chinese_ratio_too_low")

    if english_words <= 50:
        language_score += 4
    else:
        issues.append("too_much_english")
    breakdown["language"] = language_score

    structure_score = 0
    if "<h1" in html.lower():
        structure_score += 5
    else:
        issues.append("missing_h1")

    card_count = len(re.findall(r"No\.\d+", html))
    if card_count == 0:
        card_count = len(re.findall(r"<h3", html.lower()))

    if card_count >= max(1, len(articles)):
        structure_score += 8
    else:
        issues.append("news_card_count_insufficient")

    if any(token in plain_text for token in ["互动", "评论", "你最想", "为什么"]):
        structure_score += 7
    else:
        issues.append("missing_interaction_prompt")
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
    breakdown["compliance"] = compliance_score

    seo_score = 0
    keyword_hits = sum(1 for keyword in TITLE_KEYWORDS if keyword.lower() in plain_text.lower())
    if keyword_hits >= 3:
        seo_score += 8
    elif keyword_hits >= 2:
        seo_score += 5
        issues.append("seo_keyword_coverage_medium")
    else:
        issues.append("seo_keyword_coverage_low")

    if any(token in html.lower() for token in ["<h2", "<h3", "<strong"]):
        seo_score += 4
    else:
        issues.append("seo_structure_tags_missing")

    min_content_depth = 180 + target_articles * 70
    if len(plain_text) >= min_content_depth:
        seo_score += 3
    else:
        issues.append("content_depth_insufficient")
    breakdown["seo"] = seo_score

    total_score = title_score + language_score + structure_score + compliance_score + seo_score
    if "contains_external_link" in issues or "contains_source_jump_copy" in issues:
        total_score = min(total_score, MIN_QUALITY_SCORE - 1)

    return {
        "score": max(0, min(100, total_score)),
        "breakdown": breakdown,
        "issues": issues,
    }


def generate_payload(
    api_key: str | None,
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    default_payload = build_default_payload(date_str, articles, cover_urls)
    default_payload = sanitize_payload(default_payload, default_payload, date_str, cover_urls)
    default_quality = evaluate_payload_quality(default_payload, articles)

    meta = {
        "ai_enabled": bool(api_key),
        "ai_success": False,
        "model": MODEL_NAME,
        "error": "",
        "fallback_used": True,
        "quality_score": default_quality["score"],
        "quality_breakdown": default_quality["breakdown"],
        "quality_issues": default_quality["issues"],
        "attempts": 0,
    }

    if not api_key:
        meta["error"] = "GEMINI_API_KEY not set"
        return default_payload, meta

    recent_titles = load_recent_titles()
    best_payload = default_payload
    best_quality = default_quality
    latest_payload = default_payload
    latest_quality = default_quality

    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        if attempt > 1 and (attempt - 1) > MAX_REWRITE_ROUNDS:
            break

        try:
            if attempt == 1:
                prompt = build_gemini_prompt(date_str, articles, cover_urls, recent_titles)
            else:
                prompt = build_gemini_rewrite_prompt(
                    date_str,
                    articles,
                    cover_urls,
                    recent_titles,
                    latest_payload,
                    latest_quality,
                    attempt,
                )

            raw = call_gemini(api_key, prompt)
            parsed = parse_model_json(raw)
            candidate = sanitize_payload(parsed, default_payload, date_str, cover_urls)
            quality = evaluate_payload_quality(candidate, articles)

            latest_payload = candidate
            latest_quality = quality

            print(
                f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS}: quality={quality['score']} "
                f"issues={quality['issues'][:3]}"
            )

            if quality["score"] > best_quality["score"]:
                best_payload = candidate
                best_quality = quality

            if quality["score"] >= MIN_QUALITY_SCORE:
                meta.update(
                    {
                        "ai_success": True,
                        "fallback_used": False,
                        "quality_score": quality["score"],
                        "quality_breakdown": quality["breakdown"],
                        "quality_issues": quality["issues"],
                        "attempts": attempt,
                    }
                )
                return candidate, meta

        except Exception as exc:
            meta["error"] = str(exc)
            print(f"Model attempt {attempt} failed: {exc}")

    chosen_payload = best_payload if best_quality["score"] >= default_quality["score"] else default_payload
    chosen_quality = best_quality if chosen_payload is best_payload else default_quality

    meta.update(
        {
            "quality_score": chosen_quality["score"],
            "quality_breakdown": chosen_quality["breakdown"],
            "quality_issues": chosen_quality["issues"],
            "attempts": MAX_MODEL_ATTEMPTS,
        }
    )

    if chosen_quality["score"] < MIN_QUALITY_SCORE:
        meta["error"] = (
            f"Quality score {chosen_quality['score']} below threshold {MIN_QUALITY_SCORE}. "
            "Use deterministic fallback payload."
        )
        meta["quality_score"] = default_quality["score"]
        meta["quality_breakdown"] = default_quality["breakdown"]
        meta["quality_issues"] = default_quality["issues"]
        return default_payload, meta

    if chosen_payload is not default_payload:
        meta["ai_success"] = True
        meta["fallback_used"] = False

    return chosen_payload, meta


def save_news(
    articles: list[dict[str, Any]],
    payload: dict[str, Any],
    generation_meta: dict[str, Any],
    date_str: str,
    source_top_urls: list[str],
    new_urls: list[str],
) -> tuple[str, str]:
    json_file_name = f"Daily_NASA_{date_str}.json"
    markdown_file_name = f"Daily_NASA_{date_str}.md"

    json_data = {
        "date": payload["date"],
        "title": payload["title"],
        "covers": payload["covers"],
        "songs": payload["songs"],
        "weixin_html": payload["weixin_html"],
        "generation": generation_meta,
        "source_top_urls": source_top_urls,
        "new_urls": new_urls,
        "articles": [
            {
                "id": article["id"],
                "title": article["title"],
                "channel": article.get("channel", "NASA"),
                "summary": article.get("summary", ""),
                "url": article["url"],
                "publish_time": article.get("publish_time", ""),
                "image_url": article.get("image_url", ""),
                "image_path": article.get("image_path", ""),
                "cover_url": article.get("cover_url", ""),
            }
            for article in articles
        ],
    }

    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    lines = [f"# {payload['title']}", "", f"- 日期: {date_str}", ""]
    for idx, article in enumerate(articles, start=1):
        lines.extend(
            [
                f"## {idx}. {article['title']}",
                "",
                f"- 频道: {article.get('channel', 'NASA')}",
                f"- 链接: {article['url']}",
                "",
                article.get("summary", ""),
                "",
            ]
        )
    with open(markdown_file_name, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Saved merged output to {json_file_name} and {markdown_file_name}")
    return json_file_name, markdown_file_name


def get_optional_api_key() -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    return api_key or None


def main() -> None:
    target_date = datetime.datetime.now(SHANGHAI_TZ).date()
    date_str = target_date.isoformat()
    print(f"Running NASA daily pipeline for {date_str}")

    cleanup_old_files(target_date, keep_days=10)

    state = load_seen_state()
    seen_urls = set(state.get("seen_urls", []))
    print(f"Loaded state: seen_urls={len(seen_urls)}")

    top_list = fetch_top_n_articles(LIST_TOP_N)
    top_urls = [item["url"] for item in top_list]
    selected: list[dict[str, Any]] = []

    if top_list:
        print("Top list URLs:")
        for idx, url in enumerate(top_urls, start=1):
            print(f"  {idx}. {url}")

        new_candidates = [item for item in top_list if item["url"] not in seen_urls]
        print(f"New candidates after dedupe check: {len(new_candidates)}")
        for idx, item in enumerate(new_candidates, start=1):
            print(f"  NEW {idx}. {item['title']}")

        if new_candidates:
            selected = new_candidates[:MERGE_TOP_N]
        else:
            print("No new URL in top list, fallback to NASA Image of the Day.")
            iotd_candidate = fetch_image_of_the_day_candidate()
            if iotd_candidate:
                selected = [iotd_candidate]
                if iotd_candidate["url"] not in top_urls:
                    top_urls = [iotd_candidate["url"]] + top_urls
    else:
        print("No list items found, fallback to NASA Image of the Day.")
        iotd_candidate = fetch_image_of_the_day_candidate()
        if iotd_candidate:
            selected = [iotd_candidate]
            top_urls = [iotd_candidate["url"]]

    if not selected:
        print("No available candidate after fallback, only update state and exit.")
        save_seen_state(state, latest_urls=top_urls, new_urls=[], date_str=date_str)
        return

    processed_articles = build_processed_articles(selected, date_str)
    if not processed_articles:
        print("No processed article generated, only update state and exit.")
        save_seen_state(state, latest_urls=top_urls, new_urls=[], date_str=date_str)
        return

    cover_urls = [a.get("cover_url", "") for a in processed_articles if a.get("cover_url", "")]
    api_key = get_optional_api_key()
    print(f"AI model: {MODEL_NAME}")
    payload, generation_meta = generate_payload(api_key, date_str, processed_articles, cover_urls)
    if generation_meta["ai_success"]:
        print(f"AI generation succeeded with model {generation_meta['model']}.")
    else:
        print(
            "AI generation fallback used. "
            f"reason={generation_meta.get('error', 'unknown error')}"
        )

    selected_urls = [item["url"] for item in selected]

    save_news(
        processed_articles,
        payload,
        generation_meta,
        date_str,
        source_top_urls=top_urls,
        new_urls=selected_urls,
    )
    save_seen_state(state, latest_urls=top_urls, new_urls=selected_urls, date_str=date_str)
    print("Daily NASA pipeline completed.")


if __name__ == "__main__":
    main()
