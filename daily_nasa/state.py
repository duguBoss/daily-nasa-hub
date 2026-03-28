from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import Any

from .common import canonicalize_url, normalize_whitespace
from .config import ASSET_ROOT, LIST_TOP_N, MAX_SEEN_URLS, MERGE_TOP_N, SHANGHAI_TZ, STATE_FILE


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
            with open(json_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            continue

        for key in ("source_top_urls", "new_urls"):
            values = data.get(key, [])
            if isinstance(values, list):
                seeded.extend([canonicalize_url(url) for url in values if isinstance(url, str) and url])

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
        return {"seen_urls": seed_seen_urls_from_history(), "last_fetch_urls": [], "updated_at": ""}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        seen_urls = data.get("seen_urls", [])
        if not isinstance(seen_urls, list):
            seen_urls = []
        last_fetch_urls = data.get("last_fetch_urls", [])
        if not isinstance(last_fetch_urls, list):
            last_fetch_urls = []
        return {
            "seen_urls": [canonicalize_url(url) for url in seen_urls if isinstance(url, str) and url][:MAX_SEEN_URLS],
            "last_fetch_urls": [canonicalize_url(url) for url in last_fetch_urls if isinstance(url, str) and url][
                :LIST_TOP_N
            ],
            "updated_at": data.get("updated_at", ""),
        }
    except Exception as exc:
        print(f"Failed to load state file, fallback to history seed: {exc}")
        return {"seen_urls": seed_seen_urls_from_history(), "last_fetch_urls": [], "updated_at": ""}


def save_seen_state(state: dict[str, Any], latest_urls: list[str], new_urls: list[str], date_str: str) -> None:
    normalized_latest = [canonicalize_url(url) for url in latest_urls if url]
    normalized_new = [canonicalize_url(url) for url in new_urls if url]
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
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state_payload, file, ensure_ascii=False, indent=2)
    print(f"State updated: {STATE_FILE} (seen={len(state_payload['seen_urls'])})")


def load_recent_titles(limit: int = 20) -> list[str]:
    titles: list[str] = []
    for json_file in sorted(Path(".").glob("Daily_NASA_*.json"), reverse=True)[:limit]:
        try:
            with open(json_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            continue
        title = normalize_whitespace(str(data.get("title", "")))
        if title:
            titles.append(title)

    ordered: list[str] = []
    seen: set[str] = set()
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        ordered.append(title)
    return ordered


def load_previous_day_candidates(target_date: datetime.date, top_n: int = MERGE_TOP_N) -> tuple[list[dict[str, Any]], str]:
    for json_file in sorted(Path(".").glob("Daily_NASA_*.json"), reverse=True):
        try:
            file_date = datetime.date.fromisoformat(json_file.stem.replace("Daily_NASA_", ""))
        except ValueError:
            continue
        if file_date >= target_date:
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            continue

        articles = data.get("articles", [])
        if not isinstance(articles, list):
            continue

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for article in articles:
            if not isinstance(article, dict):
                continue
            raw_url = str(article.get("url", "")).strip()
            if not raw_url:
                continue
            url = canonicalize_url(raw_url)
            if url in seen:
                continue
            seen.add(url)
            title = normalize_whitespace(str(article.get("title", ""))) or "NASA历史动态回顾"
            candidates.append({"title": title, "url": url, "source": f"history:{file_date.isoformat()}"})
            if len(candidates) >= top_n:
                break

        if candidates:
            return candidates, file_date.isoformat()

    return [], ""
