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
    enforce_outer_side_margin,
    is_html_chinese_friendly,
    is_title_repetitive,
    normalize_whitespace,
    text_language_stats,
)
from .config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    FORBIDDEN_TITLE_PATTERNS,
    MAX_MODEL_ATTEMPTS,
    MIN_QUALITY_SCORE,
    PRIMARY_MODEL_NAME,
    REQUEST_TIMEOUT,
    REQUIRE_AI_GENERATION,
    TITLE_KEYWORDS,
)
from .rendering import (
    build_article_blocks,
    build_default_payload,
    build_fallback_html,
    build_wechat_fallback_title,
    fit_title_length,
)
from .state import load_recent_titles


READER_MARKER_1 = "关键信息"
READER_MARKER_2 = "对你意味着什么"
READER_MARKER_3 = "下一步关注点"
MIN_CHINESE_CHARS = 500
LOW_VALUE_PATTERNS = [
    r"随着.{0,12}临近",
    r"值得关注",
    r"提供.{0,20}建议",
    r"帮助.{0,20}了解",
    r"内容详细梳理",
]
GENERIC_TITLE_PATTERNS = [
    r"今天最值得看的一条",
    r"关键信息梳理",
    r"一次看完",
    r"最新动态",
]
MISSION_HINT_TERMS = (
    "artemis ii",
    "artemis",
    "clps",
    "intuitive machines",
    "iss",
    "kennedy",
    "阿尔忒弥斯",
    "登月",
    "月面",
    "月球",
    "空间站",
    "肯尼迪",
)


def build_story_terms(articles: list[dict[str, Any]]) -> list[str]:
    text = " ".join(
        normalize_whitespace(
            f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')}"
        )
        for article in articles
    ).lower()
    terms: list[str] = []
    if "artemis ii" in text:
        terms.extend(["artemis ii", "阿尔忒弥斯ii", "阿尔忒弥斯2号", "阿尔忒弥斯2"])
    if "intuitive machines" in text:
        terms.extend(["intuitive machines", "月面投送", "商业月面"])
    if "clps" in text:
        terms.extend(["clps", "月面载荷服务"])
    if "kennedy" in text:
        terms.extend(["肯尼迪", "发射场"])
    if "iss" in text or "space station" in text or "spacestation" in text:
        terms.extend(["iss", "空间站"])
    if "lunar" in text or "moon" in text:
        terms.extend(["登月", "月球", "月面"])
    if "artemis" in text:
        terms.extend(["artemis", "阿尔忒弥斯"])

    if not terms and articles:
        lead_title = normalize_whitespace(str(articles[0].get("title", "")))
        terms.extend([token.lower() for token in re.findall(r"[A-Za-z]{3,}(?:\s+[A-Za-z0-9]{2,})?", lead_title)[:3]])
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", lead_title):
            if token not in {"今日", "今天", "动态", "进展", "任务", "更新", "关键"}:
                terms.append(token.lower())

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = term.strip().lower()
        if len(clean_term) < 2 or clean_term in seen:
            continue
        seen.add(clean_term)
        deduped.append(clean_term)
    return deduped[:8]


def title_matches_story_terms(title: str, articles: list[dict[str, Any]]) -> bool:
    story_terms = build_story_terms(articles)
    if not story_terms:
        return True
    title_norm = title.lower().replace(" ", "")
    for term in story_terms:
        term_norm = term.replace(" ", "")
        if term_norm and term_norm in title_norm:
            return True
    return False


def is_quota_or_rate_limit_error(error_text: str) -> bool:
    text = error_text.lower()
    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "rate limit" in text
        or "(429)" in text
        or " 429" in text
    )


def call_gemini(api_key: str, prompt: str, model_name: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.55,
            "topP": 0.9,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"{model_name} request failed ({response.status_code}): {response.text}")

    result_json = response.json()
    candidate = (result_json.get("candidates") or [{}])[0]
    content = candidate.get("content", {})
    parts = content.get("parts") or []
    if not parts:
        raise RuntimeError(f"{model_name} returned empty content.")
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
Write a high-value Chinese NASA briefing for serious readers.

Date: {date_str}
News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles to avoid duplication:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

MANDATORY OUTPUT RULES:
1) Output valid JSON only.
2) All user-facing body text must be Simplified Chinese.
3) Title length 14-28 Chinese chars, with a number signal and mission keyword.
4) No external links, no anchor tags, no source-jump wording.
5) Body must have >= {MIN_CHINESE_CHARS} Chinese characters.
6) Every news card must include exactly these three labeled sections:
   - {READER_MARKER_1}
   - {READER_MARKER_2}
   - {READER_MARKER_3}
7) First screen must explain:
   - what happened today
   - why it matters to normal readers
   - what reader can track next
8) Prioritize factual density: include concrete mission names, stages, timelines, budgets, or technical targets when available.
9) Avoid filler phrases and generic motivational language.
10) Visual rule: side margin/padding must be 0 (or omitted). Do not set custom left/right spacing.
11) Title must be tied to source stories, using at least one concrete mission/entity from materials (e.g. Artemis II / CLPS / Intuitive Machines).
12) Each news card should include at least 2 concrete facts from source (time, amount,机构,里程碑).

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
    previous_payload: dict[str, Any],
    quality_report: dict[str, Any],
    attempt: int,
) -> str:
    issues = quality_report.get("issues", [])[:12]
    return f"""
Rewrite the JSON article to pass quality gate score >= {MIN_QUALITY_SCORE}.
This is rewrite attempt #{attempt} (max {MAX_MODEL_ATTEMPTS} attempts total).

News materials:
{build_article_blocks(articles)}

Current draft JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Quality report:
{json.dumps(quality_report, ensure_ascii=False)}

Fix these issues first:
{json.dumps(issues, ensure_ascii=False)}

Hard constraints:
- JSON-only output.
- >= {MIN_CHINESE_CHARS} Chinese chars in body.
- Keep labels: {READER_MARKER_1} / {READER_MARKER_2} / {READER_MARKER_3}
- No links or source jumps.
- Keep factual details and reader usefulness.
- Side margin/padding must be 0 (or omitted).
- Title must include at least one concrete mission/entity from source materials.
"""


def sanitize_payload(
    payload: Any,
    default_payload: dict[str, Any],
    date_str: str,
    cover_urls: list[str],
    articles: list[dict[str, Any]],
    recent_titles: list[str],
    allow_template_fallback: bool,
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
        weixin_html = default_payload["weixin_html"] if allow_template_fallback else ""
    if allow_template_fallback and not is_html_chinese_friendly(weixin_html):
        weixin_html = build_fallback_html(date_str, normalized["title"], articles, normalized["covers"])

    weixin_html = ensure_follow_header(weixin_html)
    weixin_html = enforce_outer_side_margin(weixin_html, side_px=0)
    normalized["weixin_html"] = weixin_html
    return normalized


def has_repeated_sentences(text: str) -> bool:
    parts = [normalize_whitespace(p) for p in re.split(r"[。！？!?\n]", text) if normalize_whitespace(p)]
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
    if any(keyword in title.lower() for keyword in TITLE_KEYWORDS):
        title_score += 7
    else:
        issues.append("title_missing_mission_keyword")
    if any(pattern in title.lower() for pattern in FORBIDDEN_TITLE_PATTERNS):
        issues.append("title_contains_forbidden_pattern")
    if any(re.search(pattern, title) for pattern in GENERIC_TITLE_PATTERNS):
        issues.append("title_too_generic")
    if title_matches_story_terms(title, articles):
        title_score += 8
    else:
        issues.append("title_not_specific_to_story")
    if recent_titles and is_title_repetitive(title, recent_titles):
        title_score = max(0, title_score - 8)
        issues.append("title_similar_to_recent")
    breakdown["title"] = title_score

    chinese_chars, english_words, ratio = text_language_stats(plain_text)
    long_english_phrase = bool(re.search(r"(?:\b[A-Za-z]{3,}\b\s+){5,}", plain_text))
    target_articles = max(1, len(articles))
    min_chinese_chars = max(MIN_CHINESE_CHARS, 320 + target_articles * 120)

    language_score = 0
    if chinese_chars >= min_chinese_chars:
        language_score += 10
    else:
        issues.append("body_below_500_chinese_chars")
    if ratio >= 0.85:
        language_score += 8
    elif ratio >= 0.76:
        language_score += 4
        issues.append("chinese_ratio_low")
    else:
        issues.append("chinese_ratio_too_low")
    if english_words <= 20:
        language_score += 4
    else:
        issues.append("too_much_english")
    if long_english_phrase:
        issues.append("long_english_phrase_detected")
    if "your browser does not support the audio element" in plain_text.lower():
        issues.append("html_contains_browser_artifact")
    if not is_html_chinese_friendly(html):
        issues.append("html_not_chinese_friendly")
    if "data-side-margin='0'" not in html and 'data-side-margin="0"' not in html:
        issues.append("side_spacing_not_zero")

    factual_signal_count = len(
        re.findall(
            r"\b(?:19|20)\d{2}\b|\d+(?:\.\d+)?\s*(?:million|billion|%|km|kg|亿美元|百万美元|月|日|天|小时|次)",
            plain_text,
            flags=re.I,
        )
    ) + len(re.findall(r"\d+月\d+日", plain_text))
    required_facts = max(4, len(articles) * 2)
    if factual_signal_count >= required_facts:
        language_score += 6
    else:
        issues.append("factual_density_low")

    mission_term_hits = sum(1 for term in MISSION_HINT_TERMS if term in plain_text.lower())
    if mission_term_hits >= max(2, len(articles)):
        language_score += 3
    else:
        issues.append("mission_terms_insufficient")

    low_value_hits = 0
    for pattern in LOW_VALUE_PATTERNS:
        if re.search(pattern, plain_text):
            low_value_hits += 1
    if low_value_hits >= 2:
        issues.append("low_information_density_style")
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

    required_markers = [READER_MARKER_1, READER_MARKER_2, READER_MARKER_3]
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
    keyword_hits = sum(1 for keyword in TITLE_KEYWORDS if keyword in plain_text.lower())
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
        "title_contains_forbidden_pattern",
        "title_too_generic",
        "title_not_specific_to_story",
        "body_below_500_chinese_chars",
        "factual_density_low",
        "missing_reader_oriented_sections",
        "low_information_density_style",
        "side_spacing_not_zero",
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
    default_payload = sanitize_payload(
        default_payload,
        default_payload,
        date_str,
        cover_urls,
        articles,
        recent_titles,
        allow_template_fallback=True,
    )
    default_quality = evaluate_payload_quality(default_payload, articles, recent_titles)

    if REQUIRE_AI_GENERATION and not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. AI generation is required for publishing.")

    meta = {
        "ai_enabled": bool(api_key),
        "ai_success": False,
        "model": PRIMARY_MODEL_NAME,
        "error": "",
        "fallback_used": False,
        "quality_score": default_quality["score"],
        "quality_breakdown": default_quality["breakdown"],
        "quality_issues": default_quality["issues"],
        "attempts": 0,
    }

    models = [PRIMARY_MODEL_NAME, FALLBACK_MODEL_NAME, EXTRA_FALLBACK_MODEL_NAME]
    # Keep order stable while avoiding duplicates.
    models = list(dict.fromkeys([model for model in models if model]))
    latest_payload = default_payload
    latest_quality = default_quality
    last_error = ""

    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        attempt_best_payload: dict[str, Any] | None = None
        attempt_best_quality: dict[str, Any] | None = None
        attempt_best_model = ""

        for model_name in models:
            try:
                print(f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS}: trying {model_name}")
                if attempt == 1:
                    prompt = build_gemini_prompt(date_str, articles, cover_urls, recent_titles)
                else:
                    prompt = build_gemini_rewrite_prompt(
                        date_str,
                        articles,
                        latest_payload,
                        latest_quality,
                        attempt,
                    )

                raw = call_gemini(api_key, prompt, model_name)
                parsed = parse_model_json(raw)
                candidate = sanitize_payload(
                    parsed,
                    default_payload,
                    date_str,
                    cover_urls,
                    articles,
                    recent_titles,
                    allow_template_fallback=False,
                )
                quality = evaluate_payload_quality(candidate, articles, recent_titles)

                print(
                    f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_name}: "
                    f"quality={quality['score']} issues={quality['issues'][:6]}"
                )

                if attempt_best_quality is None or quality["score"] > attempt_best_quality["score"]:
                    attempt_best_payload = candidate
                    attempt_best_quality = quality
                    attempt_best_model = model_name

                if quality["score"] >= MIN_QUALITY_SCORE:
                    meta.update(
                        {
                            "ai_success": True,
                            "fallback_used": model_name != PRIMARY_MODEL_NAME,
                            "model": model_name,
                            "quality_score": quality["score"],
                            "quality_breakdown": quality["breakdown"],
                            "quality_issues": quality["issues"],
                            "attempts": attempt,
                        }
                    )
                    return candidate, meta
            except Exception as exc:
                last_error = f"{model_name}: {exc}"
                if is_quota_or_rate_limit_error(str(exc)):
                    print(
                        f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_name} hit quota/rate limit; "
                        "switching to next model."
                    )
                print(f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_name} failed: {exc}")

        if attempt_best_payload is not None and attempt_best_quality is not None:
            latest_payload = attempt_best_payload
            latest_quality = attempt_best_quality
            meta.update(
                {
                    "quality_score": attempt_best_quality["score"],
                    "quality_breakdown": attempt_best_quality["breakdown"],
                    "quality_issues": attempt_best_quality["issues"],
                    "model": attempt_best_model or PRIMARY_MODEL_NAME,
                    "attempts": attempt,
                    "fallback_used": (attempt_best_model or PRIMARY_MODEL_NAME) != PRIMARY_MODEL_NAME,
                }
            )

    raise RuntimeError(
        f"Model output below quality threshold after {MAX_MODEL_ATTEMPTS} attempts. "
        f"Best score={meta['quality_score']}, required={MIN_QUALITY_SCORE}, "
        f"issues={meta['quality_issues'][:6]}, last_error={last_error}"
    )
