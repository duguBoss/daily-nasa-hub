from __future__ import annotations

import hashlib
import io
import re
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from .common import (
    canonicalize_url,
    github_asset_url,
    normalize_cn_summary,
    normalize_cn_title,
    normalize_whitespace,
    slugify,
)
from .config import APOD_API_KEY, ASSET_ROOT, LIST_TOP_N, NASA_NEWS_URLS, REQUEST_TIMEOUT, SFN_API_BASE, SFN_API_KEY

# Optional PIL import for webp to jpg conversion
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def is_nasa_article_url(url: str) -> bool:
    parsed = requests.utils.urlparse(url)
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

    blocked_keywords = ("search=", "wp-content", "tag/", "category/", "page/", "topic/", "multimedia/")
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


def fetch_image_of_the_day_candidate(image_of_the_day_url: str) -> dict[str, Any] | None:
    try:
        html = fetch_page(image_of_the_day_url)
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
        return {"title": title, "url": url, "source": image_of_the_day_url}

    print("No image-of-the-day article link found.")
    return None


def fetch_apod_candidates(count: int = 3) -> list[dict[str, Any]]:
    try:
        url = f"https://api.nasa.gov/planetary/apod?api_key={APOD_API_KEY}&count={count}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        items = response.json()
    except Exception as exc:
        print(f"Failed to fetch APOD: {exc}")
        return []

    if not isinstance(items, list):
        items = [items]

    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_whitespace(item.get("title", ""))
        explanation = normalize_whitespace(item.get("explanation", ""))
        date = item.get("date", "")
        media_type = item.get("media_type", "")
        image_url = item.get("url", "")
        hdurl = item.get("hdurl", "")

        if not title or media_type != "image":
            continue
        candidates.append(
            {
                "title": title,
                "url": "",
                "source": "NASA APOD",
                "summary": explanation[:300],
                "cover_url": hdurl or image_url,
                "hdurl": hdurl,
                "image_url": image_url,
                "apod_date": date,
                "is_apod": True,
            }
        )
    return candidates


def fetch_spaceflight_news_today() -> list[dict[str, Any]]:
    try:
        url = f"{SFN_API_BASE}/articles/?limit=10&ordering=-published_at&format=json"
        headers = {"Authorization": f"Token {SFN_API_KEY}"} if SFN_API_KEY else {}
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(f"SpaceFlight News API: fetched {len(data.get('results', []))} articles")
    except Exception as exc:
        print(f"Failed to fetch SpaceFlight News: {exc}")
        return []

    results = data.get("results", []) if isinstance(data, dict) else []
    candidates: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = normalize_whitespace(item.get("title", ""))
        summary = normalize_whitespace(item.get("summary", ""))
        url_out = item.get("url", "")
        image_url = item.get("image_url", "")
        published_at = item.get("published_at", "")
        if not title or not url_out:
            continue
        candidates.append(
            {
                "title": title,
                "url": url_out,
                "source": "SpaceFlight News",
                "summary": summary[:300] if summary else "",
                "cover_url": image_url if image_url else "",
                "publish_time": published_at,
                "is_sfn": True,
            }
        )
    return candidates


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
    summary = normalize_whitespace(" ".join(summary_source))[:220]
    return {
        "title": title,
        "content": content,
        "summary": summary,
        "image_url": image_url,
        "publish_time": pick_publish_time(soup),
    }


def _convert_webp_to_jpg(image_data: bytes) -> bytes | None:
    """Convert webp image data to jpg format. Returns None if conversion fails."""
    if not PIL_AVAILABLE:
        return None
    try:
        img = Image.open(io.BytesIO(image_data))
        # Convert to RGB if necessary (remove alpha channel)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=95)
        return output.getvalue()
    except Exception as exc:
        print(f"WebP to JPG conversion failed: {exc}")
        return None


def _compress_image(image_data: bytes, max_size_mb: float = 5.0, quality: int = 85) -> bytes:
    """Compress image if it exceeds max_size_mb. Returns compressed image data."""
    if not PIL_AVAILABLE:
        return image_data
    
    max_size_bytes = int(max_size_mb * 1024 * 1024)
    
    # If already small enough, return as-is
    if len(image_data) <= max_size_bytes:
        return image_data
    
    try:
        img = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # Try different quality levels and resize if needed
        current_quality = quality
        min_quality = 60
        
        while current_quality >= min_quality:
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=current_quality, optimize=True)
            compressed = output.getvalue()
            
            if len(compressed) <= max_size_bytes:
                print(f"  Compressed image: {len(image_data)/1024/1024:.2f}MB -> {len(compressed)/1024/1024:.2f}MB (quality={current_quality})")
                return compressed
            
            # Reduce quality and try again
            current_quality -= 10
        
        # If quality reduction alone isn't enough, resize the image
        width, height = img.size
        scale = 0.9
        while scale > 0.5:
            new_width = int(width * scale)
            new_height = int(height * scale)
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            output = io.BytesIO()
            resized.save(output, format='JPEG', quality=min_quality, optimize=True)
            compressed = output.getvalue()
            
            if len(compressed) <= max_size_bytes:
                print(f"  Resized and compressed image: {len(image_data)/1024/1024:.2f}MB -> {len(compressed)/1024/1024:.2f}MB (scale={scale:.1f})")
                return compressed
            
            scale -= 0.1
        
        # Last resort: return the smallest we could get
        print(f"  Warning: Could not compress below {max_size_mb}MB, returning best effort")
        return compressed
        
    except Exception as exc:
        print(f"Image compression failed: {exc}, using original")
        return image_data


def download_image(image_url: str, file_path: Path) -> bool:
    if not image_url:
        return False
    # Clean URL - remove surrounding whitespace/quotes
    image_url = image_url.strip().strip("'\"")
    if not image_url:
        return False
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading image: {image_url[:80]}...")
        response = requests.get(image_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        image_data = response.content
        original_size = len(image_data)

        # Check if it's webp and convert to jpg
        is_webp = image_url.lower().endswith('.webp') or image_url.lower().endswith('.web')
        if is_webp and PIL_AVAILABLE:
            converted = _convert_webp_to_jpg(image_data)
            if converted:
                image_data = converted
                # Update file path to use .jpg extension
                file_path = file_path.with_suffix('.jpg')
                print(f"  Converted WebP to JPG: {original_size/1024/1024:.2f}MB -> {len(image_data)/1024/1024:.2f}MB")

        # Compress if image is larger than 5MB
        if PIL_AVAILABLE and len(image_data) > 5 * 1024 * 1024:
            image_data = _compress_image(image_data, max_size_mb=5.0)
            # Update file path to jpg if compressed
            file_path = file_path.with_suffix('.jpg')

        with open(file_path, "wb") as file:
            file.write(image_data)
        print(f"Image saved: {file_path} ({len(image_data)/1024/1024:.2f}MB)")
        return True
    except Exception as exc:
        print(f"Failed to download image {image_url[:80]}: {exc}")
        return False


def build_processed_articles(candidates: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    processed_articles: list[dict[str, Any]] = []
    for idx, candidate in enumerate(candidates, start=1):
        url = candidate["url"]
        is_apod = candidate.get("is_apod", False)
        is_sfn = candidate.get("is_sfn", False)
        print(f"Processing article {idx}/{len(candidates)}: {candidate['title']}")

        if is_apod:
            detail = {
                "title": candidate["title"],
                "summary": candidate.get("summary", ""),
                "content": candidate.get("summary", ""),
                "image_url": candidate.get("cover_url", "") or candidate.get("hdurl", ""),
                "publish_time": candidate.get("apod_date", ""),
            }
        elif is_sfn:
            detail = {
                "title": candidate["title"],
                "summary": candidate.get("summary", ""),
                "content": candidate.get("summary", ""),
                "image_url": candidate.get("cover_url", ""),
                "publish_time": candidate.get("publish_time", ""),
            }
        else:
            try:
                detail = fetch_article_content(url)
            except Exception as exc:
                print(f"Failed to fetch article detail: {exc}")
                detail = {"title": candidate["title"], "summary": "", "content": "", "image_url": "", "publish_time": ""}

        hash_input = url if url else candidate.get("title", "") + candidate.get("apod_date", "")
        article_hash = hashlib.md5(hash_input.encode("utf-8")).hexdigest()[:12]
        article_id = f"nasa-{article_hash}"
        image_path = ""
        cover_url = detail.get("image_url", "")
        image_url = detail.get("image_url", "")

        if image_url:
            slug = slugify(candidate["title"])[:40]
            # Check if it's webp - if so, we'll convert to jpg
            is_webp = bool(re.search(r'\.webp(?:$|[?#])', image_url, re.I))
            suffix_match = re.search(r"\.(jpg|jpeg|png|webp)(?:$|[?#])", image_url, re.I)
            image_ext = "." + suffix_match.group(1).lower() if suffix_match else ".jpg"
            # Force jpg extension for webp images
            if is_webp:
                image_ext = ".jpg"
            file_name = f"{article_hash}-{slug}{image_ext}"
            local_path = ASSET_ROOT / date_str / file_name
            if download_image(image_url, local_path):
                # download_image may have changed the path to .jpg if webp was converted
                if not local_path.exists() and local_path.with_suffix('.jpg').exists():
                    local_path = local_path.with_suffix('.jpg')
                image_path = str(local_path).replace("\\", "/")
                cover_url = github_asset_url(image_path)

        raw_title = detail.get("title") or candidate["title"]
        processed_articles.append(
            {
                "id": article_id,
                "title": normalize_cn_title(raw_title),
                "title_en": raw_title,
                "summary": normalize_cn_summary(detail.get("summary", ""), raw_title),
                "content": detail.get("content", ""),
                "url": url,
                "publish_time": detail.get("publish_time", ""),
                "channel": "NASA APOD" if is_apod else ("SpaceFlight News" if is_sfn else infer_channel_name(url)),
                "image_url": image_url,
                "image_path": image_path,
                "cover_url": cover_url,
            }
        )
        if not is_apod:
            time.sleep(0.8)
    return processed_articles
