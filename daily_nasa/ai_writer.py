from __future__ import annotations

import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .common import (
    clean_english_artifacts,
    count_chinese_chars,
    ensure_follow_header,
    is_html_chinese_friendly,
    is_title_repetitive,
    normalize_whitespace,
    text_language_stats,
)
from .config import MAX_MODEL_ATTEMPTS, MAX_REWRITE_ROUNDS, MIN_QUALITY_SCORE, MODEL_NAME, REQUEST_TIMEOUT, TITLE_KEYWORDS
from .rendering import build_article_blocks, build_default_payload, build_fallback_html, build_wechat_fallback_title, fit_title_length
from .state import load_recent_titles


def call_gemini(api_key: str, prompt: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "topP": 0.9, "responseMimeType": "application/json"},
    }
    response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=REQUEST_TIMEOUT)
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


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    return f"""
You are a senior Chinese science editor for WeChat and an SEO strategist.
Turn the NASA updates into one detailed Chinese article with high information density.

Date: {date_str}
News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles to avoid style duplication:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

Output rules (MUST follow):
1) Output valid JSON only. No markdown fences, no explanations.
2) All user-facing body text must be Simplified Chinese (Artemis/ISS can remain in English names).
3) Title length: 14-28 Chinese chars, include number signal and one mission keyword.
4) weixin_html must NOT contain external links, anchor tags, source-jump CTA.
5) The article must be detailed: at least 500 Chinese characters in body text.
6) For each news card, include three explicit sections:
   - 关键信息
   - 对读者意味着什么
   - 下一步关注点
7) First screen must answer:
   - 今天发生了什么
   - 为什么值得普通读者看
   - 读者看完能得到什么
8) Keep factual tone. No fabrication, no vague filler.
9) Keep SEO keywords naturally: NASA, Artemis, 登月, 空间站, 深空探索.

JSON schema:
{{
  "date": "{date_str}",
  "title": "...",
  "covers": ["up to 5 image urls"],
  "songs": [{{"name": "news title", "artist": "channel"}}],
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
    issues = quality_report.get("issues", [])[:10]
    return f"""
Rewrite the JSON article to pass quality gate score >= {MIN_QUALITY_SCORE}.
This is rewrite attempt #{attempt}.

News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

Current draft JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Quality report:
{json.dumps(quality_report, ensure_ascii=False)}

Priority fixes:
{json.dumps(issues, ensure_ascii=False)}

Mandatory constraints:
- Keep JSON-only output.
- Keep all body text in Simplified Chinese.
- No external links / anchor tags / source-jump wording.
- Total body content >= 500 Chinese chars.
- Every card must have: 关键信息 / 对读者意味着什么 / 下一步关注点.
- Improve information density and keep factual precision.

Return full JSON with keys: date, title, covers, songs, weixin_html.
"""


def sanitize_payload(
    payload: Any,
    default_payload: dict[str, Any],
    date_str: str,
    cover_urls: list[str],
    articles: list[dict[str, Any]],
    recent_titles: list[str],
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
    title_invalid = (not title) or count_chinese_chars(title) < 6 or is_title_repetitive(title, recent_titles)
    if title_invalid:
        title = build_wechat_fallback_title(date_str, articles, recent_titles)
    normalized["title"] = fit_title_length(title)

    weixin_html = str(normalized.get("weixin_html", "")).strip()
    if not weixin_html.startswith("<section"):
        weixin_html = default_payload["weixin_html"]
    if not is_html_chinese_friendly(weixin_html):
        weixin_html = build_fallback_html(date_str, normalized["title"], articles, normalized["covers"])
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


def evaluate_payload_quality(
    payload: dict[str, Any],
    articles: list[dict[str, Any]],
    recent_titles: list[str] | None = None,
) -> dict[str, Any]:
    recent_titles = recent_titles or []
    title = normalize_whitespace(str(payload.get("title", "")))
    html = str(payload.get("weixin_html", ""))
    soup = BeautifulSoup(html or "<section></section>", "html.parser")
    plain_text = clean_english_artifacts(soup.get_text(" ", strip=True))

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
    if recent_titles and is_title_repetitive(title, recent_titles):
        title_score = max(0, title_score - 6)
        issues.append("title_similar_to_recent")
    breakdown["title"] = title_score

    chinese_chars, english_words, ratio = text_language_stats(plain_text)
    long_english_phrase = bool(re.search(r"(?:\b[A-Za-z]{3,}\b\s+){5,}", plain_text))
    target_articles = max(1, len(articles))
    min_chinese_chars = max(500, 320 + target_articles * 120)

    language_score = 0
    if chinese_chars >= min_chinese_chars:
        language_score += 10
    else:
        issues.append("body_below_500_chinese_chars")
    if ratio >= 0.84:
        language_score += 8
    elif ratio >= 0.75:
        language_score += 4
        issues.append("chinese_ratio_low")
    else:
        issues.append("chinese_ratio_too_low")
    if english_words <= 20:
        language_score += 4
    elif english_words <= 35:
        language_score += 2
        issues.append("too_much_english")
    else:
        issues.append("too_much_english")
    if long_english_phrase:
        issues.append("long_english_phrase_detected")
    if "your browser does not support the audio element" in plain_text.lower():
        issues.append("html_contains_browser_artifact")
    if not is_html_chinese_friendly(html):
        issues.append("html_not_chinese_friendly")
    breakdown["language"] = max(0, language_score)

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

    required_markers = ["关键信息", "对你意味着什么", "下一步关注点"]
    marker_hits = sum(1 for marker in required_markers if marker in plain_text)
    if marker_hits >= 3:
        structure_score += 8
    else:
        issues.append("missing_reader_oriented_sections")

    if any(token in plain_text for token in ["互动", "留言", "你会选哪条", "你最关心"]):
        structure_score += 4
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
    if keyword_hits >= 4:
        seo_score += 8
    elif keyword_hits >= 3:
        seo_score += 5
        issues.append("seo_keyword_coverage_medium")
    else:
        issues.append("seo_keyword_coverage_low")
    if any(token in html.lower() for token in ["<h2", "<h3", "<strong"]):
        seo_score += 4
    else:
        issues.append("seo_structure_tags_missing")
    if chinese_chars >= min_chinese_chars:
        seo_score += 3
    else:
        issues.append("content_depth_insufficient")
    breakdown["seo"] = seo_score

    total_score = title_score + breakdown["language"] + structure_score + compliance_score + seo_score
    hard_fail_issues = {
        "contains_external_link",
        "contains_source_jump_copy",
        "too_much_english",
        "long_english_phrase_detected",
        "html_contains_browser_artifact",
        "html_not_chinese_friendly",
        "title_similar_to_recent",
        "body_below_500_chinese_chars",
        "missing_reader_oriented_sections",
    }
    if any(issue in hard_fail_issues for issue in issues):
        total_score = min(total_score, MIN_QUALITY_SCORE - 1)

    return {"score": max(0, min(100, total_score)), "breakdown": breakdown, "issues": issues}


def generate_payload(
    api_key: str | None,
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    recent_titles = load_recent_titles()
    default_payload = build_default_payload(date_str, articles, cover_urls, recent_titles)
    default_payload = sanitize_payload(default_payload, default_payload, date_str, cover_urls, articles, recent_titles)
    default_quality = evaluate_payload_quality(default_payload, articles, recent_titles)

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
            candidate = sanitize_payload(parsed, default_payload, date_str, cover_urls, articles, recent_titles)
            quality = evaluate_payload_quality(candidate, articles, recent_titles)

            latest_payload = candidate
            latest_quality = quality
            print(
                f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS}: quality={quality['score']} "
                f"issues={quality['issues'][:5]}"
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
