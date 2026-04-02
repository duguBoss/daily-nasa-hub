from __future__ import annotations

import re
from typing import Any

from .models import (
    build_model_candidates,
    call_gemini,
    call_groq,
    call_minimax,
    call_openrouter,
    is_quota_or_rate_limit_error,
    parse_model_json,
)
from .prompts import (
    FAN_PERSPECTIVE_TERMS,
    MISSION_HINT_TERMS,
    build_card_prompt,
    build_gemini_prompt,
    build_gemini_rewrite_prompt,
    build_story_terms,
    build_title_prompt,
)
from .quality import (
    evaluate_payload_quality,
    sanitize_payload,
    title_matches_story_terms,
)
from .rendering import (
    build_article_blocks,
    build_default_payload,
    build_fallback_html,
    build_wechat_fallback_title,
    fit_title_length,
)
from .state import load_recent_titles
from .config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    GEMINI_ADDITIONAL_FALLBACK_MODELS,
    MAX_MODEL_ATTEMPTS,
    MIN_QUALITY_SCORE,
    MINIMAX_MODEL_NAME,
    MINIMAX_OPENAI_BASE_URL,
    OPENROUTER_MODEL_SERIES,
    OPENROUTER_OPENAI_BASE_URL,
    PRIMARY_MODEL_NAME,
    REQUEST_TIMEOUT,
    REQUIRE_AI_GENERATION,
    TITLE_KEYWORDS,
)


__all__ = [
    "generate_payload",
    "evaluate_payload_quality",
    "sanitize_payload",
    "build_gemini_prompt",
    "build_gemini_rewrite_prompt",
    "call_gemini",
    "call_groq",
    "call_minimax",
    "call_openrouter",
    "parse_model_json",
    "build_model_candidates",
    "is_quota_or_rate_limit_error",
    "build_story_terms",
    "title_matches_story_terms",
]


def _is_valid_chinese_title(title: str) -> bool:
    """Check if title is valid Chinese title (20-30 chars, mostly Chinese)."""
    if not title:
        return False
    
    # Remove punctuation for length check
    title_no_punct = re.sub(r'[^\u4e00-\u9fff\w]', '', title)
    char_count = len(title_no_punct)
    
    # Must be 20-30 characters
    if not (20 <= char_count <= 30):
        return False
    
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", title))
    # At least 80% Chinese (allow some numbers/English names)
    return chinese_chars >= char_count * 0.8


def _generate_title_step(
    model_candidates: list,
    date_str: str,
    articles: list[dict[str, Any]],
    recent_titles: list[str],
) -> tuple[str, str, str]:
    """Step 1: Generate title only. Returns (title, provider, model).

    Strategy: For each model, keep retrying until success (valid title).
    Only switch to next model when API call fails (exception).
    """
    from .common import count_chinese_chars
    from .config import MAX_TITLE_RETRIES

    prompt = build_title_prompt(date_str, articles, recent_titles)

    for provider, model_name, provider_api_key, caller in model_candidates:
        print(f"[Step 1/4] Using {provider}:{model_name}")

        for attempt in range(MAX_TITLE_RETRIES):
            try:
                print(f"  Attempt {attempt + 1}/{MAX_TITLE_RETRIES}")
                raw = caller(provider_api_key, prompt, model_name)
                # Clean up the response - remove quotes and whitespace
                title = raw.strip().strip('"').strip("'")

                # Validate: must be Chinese title with 20-30 chars
                if _is_valid_chinese_title(title):
                    print(f"[Step 1/4] ✓ Title generated ({len(title)} chars): {title[:40]}...")
                    return title, provider, model_name
                else:
                    # Detailed rejection reason - but continue with same model
                    title_no_punct = re.sub(r'[^\u4e00-\u9fff\w]', '', title)
                    char_count = len(title_no_punct)
                    chinese_count = count_chinese_chars(title)
                    if not (20 <= char_count <= 30):
                        print(f"  ✗ Rejected (length {char_count}, need 20-30), retrying...")
                    else:
                        print(f"  ✗ Rejected (only {chinese_count}/{char_count} Chinese), retrying...")
                    # Continue to next attempt with same model
                    continue

            except Exception as e:
                print(f"  ✗ API failed: {e}")
                print(f"  Switching to next model...")
                break  # Break inner loop, switch to next model

    # No fallback - raise error if all models exhausted
    raise RuntimeError(
        f"Failed to generate valid title after trying all models. "
        "Title must be 20-30 Chinese characters. No default fallback allowed."
    )


def _has_chinese_content(text: str, min_chars: int = 20) -> bool:
    """Check if text has sufficient Chinese content."""
    if not text:
        return False
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return chinese_chars >= min_chars


def _generate_card_step(
    model_candidates: list,
    card_number: int,
    article: dict[str, Any],
    date_str: str,
) -> tuple[str, str, str]:
    """Step 2/3/4: Generate content for a single card. Returns (html, provider, model).

    Strategy: For each model, keep retrying until success (valid content).
    Only switch to next model when API call fails (exception).
    """
    from .config import MAX_MODEL_ATTEMPTS

    prompt = build_card_prompt(card_number, article, date_str)

    for provider, model_name, provider_api_key, caller in model_candidates:
        print(f"[Step {card_number+1}/4] Using {provider}:{model_name} for card {card_number}")

        for attempt in range(MAX_MODEL_ATTEMPTS):
            try:
                print(f"  Attempt {attempt + 1}/{MAX_MODEL_ATTEMPTS}")
                raw = caller(provider_api_key, prompt, model_name)
                html = raw.strip()

                # Validate: must have Chinese content
                if html and len(html) > 50 and _has_chinese_content(html, min_chars=20):
                    print(f"[Step {card_number+1}/4] Card {card_number} generated: {len(html)} chars")
                    return html, provider, model_name
                else:
                    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", html)) if html else 0
                    print(f"  ✗ Rejected (not enough Chinese: {chinese_count} chars), retrying...")
                    continue  # Retry with same model

            except Exception as e:
                print(f"  ✗ API failed: {e}")
                print(f"  Switching to next model...")
                break  # Switch to next model

    # Fallback to basic HTML using article's Chinese title and summary (light theme)
    print(f"[Step {card_number+1}/4] All models failed, using fallback HTML")
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = article.get("title", "")
    summary = article.get("summary", "")
    fallback_html = f'<img src="{image}" style="width:100%;display:block;"><p style="margin:1em 0;font-size:0.95em;line-height:1.7em;color:#333;">{title}</p><p style="margin:1em 0;font-size:0.95em;line-height:1.7em;color:#555;">{summary}</p>'
    return fallback_html, "fallback", "basic"


def _generate_card_content_step(
    model_candidates: list,
    card_number: int,
    article: dict[str, Any],
    date_str: str,
) -> tuple[dict[str, str], str, str]:
    """Step 2/3/4: Generate Chinese content for a single card. Returns (content_dict, provider, model).
    
    content_dict contains: title, summary, content (paragraphs)
    """
    from .config import MAX_MODEL_ATTEMPTS
    from .prompts import build_card_content_prompt

    prompt = build_card_content_prompt(card_number, article, date_str)

    for provider, model_name, provider_api_key, caller in model_candidates:
        print(f"[Step {card_number+1}/4] Using {provider}:{model_name} for card {card_number} content")

        for attempt in range(MAX_MODEL_ATTEMPTS):
            try:
                print(f"  Attempt {attempt + 1}/{MAX_MODEL_ATTEMPTS}")
                raw = caller(provider_api_key, prompt, model_name)
                raw = raw.strip()

                # Parse JSON response
                try:
                    content = json.loads(raw)
                    if isinstance(content, dict) and "title" in content and "paragraphs" in content:
                        # Validate: must have Chinese content
                        text_to_check = content.get("title", "") + "".join(content.get("paragraphs", []))
                        if _has_chinese_content(text_to_check, min_chars=20):
                            print(f"[Step {card_number+1}/4] Card {card_number} content generated: {len(text_to_check)} chars")
                            return content, provider, model_name
                        else:
                            chinese_count = len(re.findall(r"[\u4e00-\u9fff]", text_to_check))
                            print(f"  ✗ Rejected (not enough Chinese: {chinese_count} chars), retrying...")
                            continue
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code block
                    json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
                    if json_match:
                        try:
                            content = json.loads(json_match.group(1))
                            if isinstance(content, dict) and "title" in content and "paragraphs" in content:
                                text_to_check = content.get("title", "") + "".join(content.get("paragraphs", []))
                                if _has_chinese_content(text_to_check, min_chars=20):
                                    print(f"[Step {card_number+1}/4] Card {card_number} content generated: {len(text_to_check)} chars")
                                    return content, provider, model_name
                        except json.JSONDecodeError:
                            pass
                    
                    print(f"  ✗ Invalid JSON response, retrying...")
                    continue

            except Exception as e:
                print(f"  ✗ API failed: {e}")
                print(f"  Switching to next model...")
                break  # Switch to next model

    # Fallback to original article content
    print(f"[Step {card_number+1}/4] All models failed, using fallback content")
    return {
        "title": article.get("title", ""),
        "summary": article.get("summary", ""),
        "paragraphs": [article.get("summary", ""), article.get("content", "")[:200]]
    }, "fallback", "original"


def generate_payload(
    gemini_api_key: str | None,
    minimax_api_key: str | None,
    openrouter_api_key: str | None,
    groq_api_key: str | None,
    date_str: str,
    articles: list[dict[str, Any]],
    cover_urls: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate payload using step-by-step approach for better reliability."""
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

    if REQUIRE_AI_GENERATION and not gemini_api_key and not minimax_api_key and not openrouter_api_key and not groq_api_key:
        raise RuntimeError(
            "None of GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, or MINIMAX_API_KEY is set. AI generation is required for publishing."
        )

    model_candidates = build_model_candidates(gemini_api_key, minimax_api_key, openrouter_api_key, groq_api_key)

    if REQUIRE_AI_GENERATION and not model_candidates:
        raise RuntimeError("No usable model candidate found for AI generation.")

    primary_provider, primary_model_name = ("gemini", PRIMARY_MODEL_NAME)
    if model_candidates:
        primary_provider, primary_model_name = model_candidates[0][0], model_candidates[0][1]

    meta: dict[str, Any] = {
        "ai_enabled": bool(gemini_api_key or minimax_api_key or openrouter_api_key or groq_api_key),
        "ai_success": False,
        "provider": primary_provider,
        "model": primary_model_name,
        "error": "",
        "fallback_used": False,
        "quality_score": default_quality["score"],
        "quality_breakdown": default_quality["breakdown"],
        "quality_issues": default_quality["issues"],
        "attempts": 0,
    }

    # Step-by-step generation
    print("\n=== Starting Step-by-Step Generation ===\n")
    
    # Step 1: Generate title
    title, title_provider, title_model = _generate_title_step(model_candidates, date_str, articles, recent_titles)
    print(f"[Step 1/4] Complete: Title = '{title[:40]}...'\n")
    
    # Step 2-4: Generate Chinese content for cards (up to 3 cards)
    card_models = []
    processed_articles = []
    for i, article in enumerate(articles[:3]):
        card_num = i + 1
        chinese_content, card_provider, card_model = _generate_card_content_step(model_candidates, card_num, article, date_str)
        card_models.append(f"{card_provider}:{card_model}")
        
        # Update article with Chinese content
        processed_article = dict(article)
        processed_article["title"] = chinese_content.get("title", article.get("title", ""))
        processed_article["summary"] = chinese_content.get("summary", "")
        processed_article["content"] = chinese_content.get("content", "")
        processed_articles.append(processed_article)
        print(f"[Step {card_num+1}/4] Complete: Card {card_num} generated with Chinese content\n")
    
    # Build songs from processed article titles
    songs = []
    for article in processed_articles:
        songs.append({
            "name": article.get("title", "")[:30],
            "artist": article.get("channel", "NASA")
        })
    
    # Assemble final payload using template system
    from .rendering import _build_apod_from_article, _build_news_from_articles
    from . import template as tpl
    from .config import TOP_BANNER_URL
    
    # Build APOD section from first processed article (science content)
    apod_html = _build_apod_from_article(processed_articles[0], vol=date_str[:4])
    
    # Build news section from remaining processed articles
    news_html = _build_news_from_articles(processed_articles[1:])
    
    # Render full HTML using template
    weixin_html = tpl.render_full_html(
        banner_url=TOP_BANNER_URL,
        apod_html=apod_html,
        news_html=news_html,
        show_divider=len(processed_articles) > 1,
    )
    
    # Build final payload
    payload = {
        "date": date_str,
        "title": title,
        "covers": cover_urls[:5],
        "songs": songs,
        "weixin_html": weixin_html,
    }
    
    # Sanitize and evaluate
    payload = sanitize_payload(
        payload,
        default_payload,
        date_str,
        cover_urls,
        articles,
        recent_titles,
        allow_template_fallback=False,
    )
    quality = evaluate_payload_quality(payload, articles, recent_titles)
    
    print(f"\n=== Generation Complete ===")
    print(f"Title: {title[:50]}...")
    print(f"Quality Score: {quality['score']}")
    print(f"Issues: {quality['issues'][:3]}")
    print(f"Models used: title={title_model}, cards={card_models}")
    
    meta.update({
        "ai_success": True,
        "provider": title_provider,
        "model": title_model,
        "quality_score": quality["score"],
        "quality_breakdown": quality["breakdown"],
        "quality_issues": quality["issues"],
        "attempts": 1,
        "fallback_used": title_provider != primary_provider,
        "card_models": card_models,
    })
    
    return payload, meta
