from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import requests
import pytz
from bs4 import BeautifulSoup


NASA_NEWS_URLS = [
    "https://www.nasa.gov/2026-news-releases/",
    "https://www.nasa.gov/news/recently-published/",
]

MODEL_NAME = "gemini-3.1-flash-lite-preview"
REQUEST_TIMEOUT = 30
ASSET_ROOT = Path("assets") / "generated"
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


def require_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY. Set it in the environment or GitHub Secrets.")
    return api_key


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:60] or "news"


def github_asset_url(asset_path: str, repo: str = "duguBoss/daily-nasa-hub", branch: str = "main") -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{asset_path}".replace("\\", "/")


def fetch_page(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    response.raise_for_status()
    return response.text


def parse_nasa_news_list(html: str, target_date: datetime.date) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not href or "/2026/" not in href and "/2025/" not in href:
            continue

        title = normalize_whitespace(link.get_text())
        if not title or len(title) < 15:
            parent = link.find_parent(["article", "div", "li"])
            if parent:
                h_tag = parent.find(["h2", "h3", "h4"])
                if h_tag:
                    title = normalize_whitespace(h_tag.get_text())

        if title and len(title) > 15:
            full_url = href if href.startswith("http") else f"https://www.nasa.gov{href}"

            date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
            article_date = target_date
            if date_match:
                try:
                    article_date = datetime.date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                except ValueError:
                    pass

            if article_date == target_date:
                articles.append({
                    "title": title,
                    "url": full_url,
                    "date": article_date.isoformat(),
                })

    seen_urls = set()
    unique_articles = []
    for article in articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique_articles.append(article)

    return unique_articles


def fetch_article_content(url: str) -> dict[str, Any]:
    html = fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = normalize_whitespace(title_tag.get_text())

    if not title:
        title_tag = soup.find("meta", property="og:title")
        if title_tag:
            title = title_tag.get("content", "")

    content_div = soup.find("div", class_=lambda x: x and "article" in x.lower() if x else False)
    if not content_div:
        content_div = soup.find("main")
    if not content_div:
        content_div = soup.find("article")
    if not content_div:
        content_div = soup.find("div", {"id": "content"})
    if not content_div:
        content_div = soup.find("div", class_=lambda x: x and "entry" in x.lower() if x else False)
    if not content_div:
        content_div = soup.find("div", class_=lambda x: x and "post" in x.lower() if x else False)

    content = ""
    if content_div:
        for tag in content_div.find_all(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        paragraphs = content_div.find_all("p")
        content = "\n\n".join(normalize_whitespace(p.get_text()) for p in paragraphs if p.get_text(strip=True))

    if not content:
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc:
            content = meta_desc.get("content", "")
        if not content:
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc:
                content = meta_desc.get("content", "")

    image_url = ""
    og_image = soup.find("meta", property="og:image")
    if og_image:
        image_url = og_image.get("content", "")

    if not image_url:
        img_tag = soup.find("img", src=re.compile(r"\.jpg|\.jpeg|\.png|\.webp", re.I))
        if img_tag:
            image_url = img_tag.get("src", "")

    if image_url and not image_url.startswith("http"):
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        elif image_url.startswith("/"):
            image_url = "https://www.nasa.gov" + image_url

    return {
        "title": title,
        "content": content,
        "image_url": image_url,
    }


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
    except Exception as e:
        print(f"Failed to download image {image_url}: {e}")
        return False


def cleanup_old_files(target_date: datetime.date, keep_days: int = 7) -> None:
    cutoff = target_date - datetime.timedelta(days=keep_days)

    for pattern in ["Daily_NASA_*.json", "Daily_NASA_*.md"]:
        for file_path in Path(".").glob(pattern):
            try:
                date_str = file_path.stem.replace("Daily_NASA_", "")
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff:
                    file_path.unlink()
                    print(f"Deleted old file: {file_path}")
            except (ValueError, IndexError):
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


def load_existing_news_ids() -> set[str]:
    json_files = list(Path(".").glob("Daily_NASA_*.json"))
    existing_ids = set()
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "articles" in data:
                    for article in data["articles"]:
                        existing_ids.add(article.get("id", ""))
        except Exception:
            continue
    return existing_ids


def call_gemini(api_key: str, prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
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
        raise RuntimeError(f"Gemini API request failed with status {response.status_code}: {response.text}")

    result_json = response.json()
    candidate = (result_json.get("candidates") or [{}])[0]
    content = candidate.get("content", {})
    parts = content.get("parts") or []

    return parts[0]["text"]


def build_gemini_prompt(articles: list[dict[str, Any]], date_str: str) -> str:
    articles_text = "\n\n".join([
        f"文章 {i+1}: {a['title']}\n内容: {a.get('content', '')[:1500]}"
        for i, a in enumerate(articles)
    ])

    return f"""你是一个科技新闻编辑，需要为NASA每日新闻生成微信格式的HTML内容。

日期：{date_str}

文章列表：
{articles_text}

要求：
1. 生成一个JSON对象，包含以下字段：
   - "title": 主标题，20-35字，简短有力
   - "summary": 摘要，50-80字，概括当日NASA新闻要点
   - "covers": 图片URL数组，最多6张
   - "wxhtml": 微信HTML内容，使用section标签，包含所有文章的标题、摘要和配图

微信HTML格式要求：
- 顶部banner图片
- 每个文章条目用卡片样式展示
- 包含文章标题、图片、摘要
- 底部banner图片
- 使用内联样式，简洁美观

只返回JSON格式：
{{"title":"标题","summary":"摘要","covers":["url1","url2"],"wxhtml":"<section>...</section>"}}
"""


def generate_wxhtml(api_key: str, articles: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    prompt = build_gemini_prompt(articles, date_str)
    try:
        result = call_gemini(api_key, prompt)
        return json.loads(result)
    except Exception as e:
        print(f"Gemini API call failed: {e}")
        return {
            "title": f"NASA 每日新闻：{date_str}",
            "summary": "NASA最新太空探索、科技与应用动态。",
            "covers": [],
            "wxhtml": ""
        }


def save_news(articles: list[dict[str, Any]], wxhtml_data: dict[str, Any], date_str: str) -> tuple[str, str]:
    if not articles:
        return "", ""

    covers = wxhtml_data.get("covers", [])
    cover_urls = []
    for a in articles:
        if a.get("image_path"):
            cover_urls.append(github_asset_url(a["image_path"]))

    json_data = {
        "title": wxhtml_data.get("title", f"NASA 每日新闻：{date_str}"),
        "summary": wxhtml_data.get("summary", ""),
        "covers": cover_urls[:6],
        "wxhtml": wxhtml_data.get("wxhtml", ""),
        "articles": [
            {
                "id": a["id"],
                "title": a["title"],
                "original_title": a.get("original_title", ""),
                "summary": a.get("summary", ""),
                "url": a["url"],
                "image_url": a.get("image_url", ""),
                "image_path": a.get("image_path", ""),
            }
            for a in articles
        ],
    }

    json_file_name = f"Daily_NASA_{date_str}.json"
    markdown_file_name = f"Daily_NASA_{date_str}.md"

    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    markdown_content = f"# NASA 每日新闻：{date_str}\n\n"
    markdown_content += f"![Cover]({TOP_BANNER_URL})\n\n"
    markdown_content += f"## {wxhtml_data.get('title', 'NASA News')}\n\n"
    markdown_content += f"*{wxhtml_data.get('summary', '')}*\n\n"

    for i, article in enumerate(articles):
        markdown_content += f"### {i+1}. {article['title']}\n\n"
        if article.get("image_path"):
            markdown_content += f"![Image]({github_asset_url(article['image_path'])})\n\n"
        markdown_content += f"{article.get('summary', article.get('content', ''))}\n\n"
        markdown_content += f"[来源]({article['url']})\n\n"
        markdown_content += "---\n\n"

    markdown_content += f"\n![Bottom]({BOTTOM_BANNER_URL})\n"

    with open(markdown_file_name, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"Saved {len(articles)} articles to {json_file_name}")
    return json_file_name, markdown_file_name


def main() -> None:
    target_date = datetime.datetime.now(SHANGHAI_TZ).date()
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"Fetching NASA news for {date_str}")

    cleanup_old_files(target_date, keep_days=7)

    existing_ids = load_existing_news_ids()
    print(f"Found {len(existing_ids)} existing article IDs")

    all_articles = []
    seen_urls = set()

    for url in NASA_NEWS_URLS:
        print(f"Fetching from {url}")
        try:
            html = fetch_page(url)
            articles = parse_nasa_news_list(html, target_date)
            print(f"Found {len(articles)} articles from {url}")

            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    all_articles.append(article)
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")

    print(f"Total unique articles: {len(all_articles)}")

    if not all_articles:
        print("No articles found for today.")
        return

    new_articles = []
    for i, article in enumerate(all_articles):
        article_url = article["url"]
        article_hash = hashlib.md5(article_url.encode()).hexdigest()[:12]
        article_id = f"nasa-{article_hash}"

        if article_id in existing_ids:
            print(f"Skipping duplicate: {article['title']}")
            continue

        print(f"Processing article {i+1}/{len(all_articles)}: {article['title']}")

        try:
            content_data = fetch_article_content(article_url)
        except Exception as e:
            print(f"Failed to fetch article content: {e}")
            content_data = {"title": article["title"], "content": "", "image_url": ""}

        image_path = ""
        if content_data.get("image_url"):
            slug = slugify(article["title"])[:40]
            image_ext = Path(content_data["image_url"]).suffix or ".jpg"
            image_file_name = f"{article_hash}-{slug}{image_ext}"
            image_path = ASSET_ROOT / date_str / image_file_name

            if download_image(content_data["image_url"], image_path):
                image_path = str(image_path)
            else:
                image_path = ""

        summary = content_data["content"][:150] if content_data.get("content") else ""

        new_articles.append({
            "id": article_id,
            "title": content_data["title"],
            "original_title": content_data["title"],
            "summary": summary,
            "content": content_data["content"],
            "url": article_url,
            "image_url": content_data.get("image_url", ""),
            "image_path": image_path,
            "date": article.get("date", date_str),
        })

        time.sleep(1)

    if not new_articles:
        print("No new articles to save today.")
        return

    api_key = ""
    try:
        api_key = require_api_key()
    except ValueError:
        print("GEMINI_API_KEY not set, skipping wxhtml generation")

    wxhtml_data = {
        "title": f"NASA 每日新闻：{date_str}",
        "summary": f"NASA太空探索与科技最新动态 ({date_str})",
        "covers": [],
        "wxhtml": ""
    }

    if api_key:
        wxhtml_data = generate_wxhtml(api_key, new_articles, date_str)

    json_file, md_file = save_news(new_articles, wxhtml_data, date_str)
    print(f"Successfully saved news to {json_file} and {md_file}")


if __name__ == "__main__":
    main()