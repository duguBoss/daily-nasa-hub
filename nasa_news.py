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
ASSET_ROOT = Path("assets") / "generated"
STATE_FILE = Path("state") / "nasa_seen_urls.json"
SHANGHAI_TZ = pytz.timezone("Asia/Shanghai")

TOP_BANNER_URL = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzXgUR7FJnf11qGIo8nmKt6RxibXrb5s4RFb9UZ9UOHQy7fqQyI377Licw/"
    "0?wx_fmt=gif"
)
BOTTOM_BANNER_URL = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/"
    "0?wx_fmt=gif"
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
            f"<strong>看点速读：</strong>{article.get('summary', '')}</p>"
            f"<p style='margin:0;font-size:14px;line-height:1.8;'><a href='{article['url']}' "
            "style='color:#1565c0;text-decoration:none;'>查看 NASA 原文 ></a></p>"
            "</section>"
        )
        cards_html += card

    intro = (
        "今天的 NASA 动态集中在载人航天、深空任务和前沿技术验证。"
        "为了提高微信分发和完读率，我们按“强标题+关键信息卡片+互动提问”的结构整理了重点。"
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
        "</section>"
        f"{cards_html}"
        "<section style='margin:4px 0 20px 0;padding:16px;border-radius:12px;background:#fffaf0;border:1px solid #ffe4b8;'>"
        "<p style='margin:0;font-size:15px;color:#5f4b2f;line-height:1.9;'><strong>互动话题：</strong>"
        "今天这几条 NASA 动态里，你最想追踪哪一个任务后续？</p>"
        "<p style='margin:8px 0 0 0;font-size:14px;color:#7b6543;line-height:1.9;'>"
        "如果这篇合辑有帮助，欢迎点在看并转发给同样关注太空探索的朋友。</p>"
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
            "NASA今天放出关键画面：{focus}背后信息量太大",
            "别错过NASA这条重磅更新：{focus}细节首次看清",
            "今天NASA最值得看的内容：{focus}核心进展来了",
            "NASA刚更新一条关键信号：{focus}正在发生变化",
            "这张NASA新图刷屏了：{focus}到底透露了什么",
        ]
        return rng.choice(templates).format(focus=focus)

    templates = [
        "NASA今天连发{count}条重磅动态：{focus}出现关键变化",
        "今天的NASA有点猛：{count}条{focus}新进展一次看完",
        "别只看标题，NASA这{count}条更新正在改写{focus}节奏",
        "NASA一天抛出{count}个信号：{focus}进入新阶段",
        "今天NASA最有价值的{count}条：{focus}看点全梳理",
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


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    article_blocks = []
    for idx, article in enumerate(articles, start=1):
        block = (
            f"新闻{idx}\n"
            f"- 标题: {article['title']}\n"
            f"- 频道: {article.get('channel', 'NASA')}\n"
            f"- 时间: {article.get('publish_time', '')}\n"
            f"- 摘要: {article.get('summary', '')}\n"
            f"- 原文: {article['url']}\n"
            f"- 配图: {article.get('cover_url', article.get('image_url', ''))}\n"
        )
        article_blocks.append(block)

    return f"""
你是“NASA内容主编 + 微信增长编辑”。请将以下新闻合并为一篇高点击、高完读率的中文微信文章。

日期: {date_str}
新闻素材:
{chr(10).join(article_blocks)}

封面图候选:
{json.dumps(cover_urls, ensure_ascii=False)}

最近已使用标题（请避免相似表达）:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

输出必须是合法 JSON，且只能输出 JSON，不要加解释文字。结构必须是:
{{
  "date": "{date_str}",
  "title": "14-24字中文主标题，强调新鲜感和价值感",
  "covers": ["最多5个图片URL"],
  "songs": [
    {{"name":"新闻标题","artist":"栏目名"}}
  ],
  "weixin_html": "<section>...</section>"
}}

写作要求:
1) 明显体现 NASA 风格: 科学、任务、探索、工程细节。
2) 按微信推荐算法优化: 强信息密度、明确受众收益、避免空话；首屏需有“今天发生了什么+为什么值得看”。
3) weixin_html 用内联样式，结构完整，必须包含顶部和底部 banner 图。
4) cards 中每条新闻要有标题、摘要、图片(有则展示)和原文链接。
5) 不要杜撰事实，不要出现“可能/大概”等含糊措辞。
6) title 禁止使用以下重复句式: “NASA今日速递：X条太空前沿动态一次看懂”。
7) title 请尽量包含数字、任务关键词（如Artemis/空间站/火箭/深空）之一。
"""


def generate_payload(
    api_key: str | None,
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    default_payload = build_default_payload(date_str, articles, cover_urls)
    meta = {
        "ai_enabled": bool(api_key),
        "ai_success": False,
        "model": MODEL_NAME,
        "error": "",
        "fallback_used": True,
    }
    if not api_key:
        meta["error"] = "GEMINI_API_KEY not set"
        return default_payload, meta

    try:
        recent_titles = load_recent_titles()
        prompt = build_gemini_prompt(date_str, articles, cover_urls, recent_titles)
        raw = call_gemini(api_key, prompt)
        payload = parse_model_json(raw)
    except Exception as exc:
        meta["error"] = str(exc)
        return default_payload, meta

    payload_date = str(payload.get("date", "")).strip()
    payload["date"] = payload_date if payload_date else date_str

    covers = payload.get("covers", [])
    if not isinstance(covers, list):
        covers = []
    covers = [str(url).strip() for url in covers if isinstance(url, str) and url.strip()]
    payload["covers"] = (covers or cover_urls)[:5]

    songs = payload.get("songs", [])
    if not isinstance(songs, list) or not songs:
        songs = default_payload["songs"]
    fixed_songs: list[dict[str, str]] = []
    for song in songs[:5]:
        if not isinstance(song, dict):
            continue
        name = normalize_whitespace(str(song.get("name", "")))
        artist = normalize_whitespace(str(song.get("artist", ""))) or "NASA"
        if name:
            fixed_songs.append({"name": name, "artist": artist})
    payload["songs"] = fixed_songs or default_payload["songs"]

    title = normalize_whitespace(str(payload.get("title", "")))
    if not title or title == "NASA 今日速递：3 条太空前沿动态一次看懂":
        title = default_payload["title"]
    payload["title"] = title

    weixin_html = str(payload.get("weixin_html", "")).strip()
    if not weixin_html.startswith("<section"):
        weixin_html = default_payload["weixin_html"]
    payload["weixin_html"] = weixin_html
    meta["ai_success"] = True
    meta["fallback_used"] = False
    return payload, meta


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
