from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
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

DEFAULT_REPOSITORY = "duguBoss/daily-nasa-hub"
DEFAULT_BRANCH = "main"
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


def save_news(articles: list[dict[str, Any]], date_str: str) -> tuple[str, str]:
    if not articles:
        return "", ""

    json_file_name = f"Daily_NASA_{date_str}.json"
    markdown_file_name = f"Daily_NASA_{date_str}.md"

    cover_images = [a["image_path"] for a in articles if a.get("image_path")]

    json_data = {
        "title": f"NASA 每日新闻：{date_str}",
        "date": date_str,
        "cover": cover_images[:6],
        "articles": articles,
    }

    with open(json_file_name, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    markdown_content = f"# NASA 每日新闻：{date_str}\n\n"
    markdown_content += f"![Cover]({TOP_BANNER_URL})\n\n"

    for i, article in enumerate(articles):
        markdown_content += f"## {i+1}. {article['title']}\n\n"
        if article.get("image_path"):
            markdown_content += f"![Image]({article['image_path']})\n\n"
        markdown_content += f"{article.get('summary', article.get('content', ''))}\n\n"
        markdown_content += f"来源: {article.get('url', '')}\n\n"
        markdown_content += "---\n\n"

    markdown_content += f"\n![Bottom]({BOTTOM_BANNER_URL})\n"

    with open(markdown_file_name, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"Saved {len(articles)} articles to {json_file_name}")
    return json_file_name, markdown_file_name


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


def translate_with_gemini(api_key: str, title: str, content: str) -> dict[str, str]:
    prompt = f"""翻译以下NASA新闻为简体中文：

标题：{title}

内容：{content[:2000]}

要求：
1. 标题翻译简洁有力，适合SEO，20-35字
2. 内容摘要100-200字
3. 只返回JSON格式：
{{"title_cn":"中文标题","summary_cn":"中文摘要"}}
"""

    try:
        result = call_gemini(api_key, prompt)
        return json.loads(result)
    except Exception as e:
        print(f"Translation failed: {e}")
        return {
            "title_cn": title[:35],
            "summary_cn": content[:150] + "..." if len(content) > 150 else content
        }


def main() -> None:
    existing_ids = load_existing_news_ids()
    print(f"Found {len(existing_ids)} existing article IDs")

    target_date = datetime.datetime.now(SHANGHAI_TZ).date()
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"Fetching NASA news for {date_str}")

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

        api_key = ""
        try:
            api_key = require_api_key()
        except ValueError:
            pass

        if api_key and content_data.get("content"):
            try:
                translated = translate_with_gemini(api_key, content_data["title"], content_data["content"])
                title_cn = translated.get("title_cn", content_data["title"])
                summary_cn = translated.get("summary_cn", content_data["content"][:150])
            except Exception:
                title_cn = content_data["title"]
                summary_cn = content_data["content"][:150]
        else:
            title_cn = content_data["title"]
            summary_cn = content_data["content"][:150] if content_data.get("content") else ""

        new_articles.append({
            "id": article_id,
            "title": title_cn,
            "original_title": content_data["title"],
            "summary": summary_cn,
            "content": content_data["content"],
            "url": article_url,
            "image_url": content_data.get("image_url", ""),
            "image_path": image_path,
            "date": article.get("date", date_str),
        })

        time.sleep(1)

    if new_articles:
        json_file, md_file = save_news(new_articles, date_str)
        print(f"Successfully saved news to {json_file} and {md_file}")
    else:
        print("No new articles to save today.")


if __name__ == "__main__":
    main()