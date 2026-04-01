from __future__ import annotations

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
    """Step 1: Generate title only. Returns (title, provider, model)."""
    from .common import count_chinese_chars
    
    prompt = build_title_prompt(date_str, articles, recent_titles)
    
    for provider, model_name, provider_api_key, caller in model_candidates:
        try:
            print(f"[Step 1/4] Generating title with {provider}:{model_name}")
            raw = caller(provider_api_key, prompt, model_name)
            # Clean up the response - remove quotes and whitespace
            title = raw.strip().strip('"').strip("'")
            
            # Validate: must be Chinese title with 20-30 chars
            if _is_valid_chinese_title(title):
                print(f"[Step 1/4] Title generated ({len(title)} chars): {title[:40]}...")
                return title, provider, model_name
            else:
                # Detailed rejection reason
                title_no_punct = re.sub(r'[^\u4e00-\u9fff\w]', '', title)
                char_count = len(title_no_punct)
                chinese_count = count_chinese_chars(title)
                if not (20 <= char_count <= 30):
                    print(f"[Step 1/4] Title rejected (length {char_count}, need 20-30): {title[:40]}...")
                else:
                    print(f"[Step 1/4] Title rejected (only {chinese_count}/{char_count} Chinese): {title[:40]}...")
        except Exception as e:
            print(f"[Step 1/4] Failed with {provider}:{model_name}: {e}")
            continue
    
    # Fallback to first article title
    if articles:
        title = articles[0].get("title", "")
        if _is_valid_chinese_title(title):
            return title, "fallback", "article_title"
        print(f"[Step 1/4] Article title also not valid Chinese, using default")
    
    # Default fallback
    default_title = f"NASA每日航天动态精选报道"
    return default_title, "fallback", "default"


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
    """Step 2/3/4: Generate content for a single card. Returns (html, provider, model)."""
    prompt = build_card_prompt(card_number, article, date_str)
    
    for provider, model_name, provider_api_key, caller in model_candidates:
        try:
            print(f"[Step {card_number+1}/4] Generating card {card_number} with {provider}:{model_name}")
            raw = caller(provider_api_key, prompt, model_name)
            html = raw.strip()
            
            # Validate: must have Chinese content
            if html and len(html) > 50 and _has_chinese_content(html, min_chars=20):
                print(f"[Step {card_number+1}/4] Card {card_number} generated: {len(html)} chars")
                return html, provider, model_name
            else:
                chinese_count = len(re.findall(r"[\u4e00-\u9fff]", html)) if html else 0
                print(f"[Step {card_number+1}/4] Card rejected (not enough Chinese: {chinese_count} chars): {html[:60] if html else 'empty'}...")
        except Exception as e:
            print(f"[Step {card_number+1}/4] Failed with {provider}:{model_name}: {e}")
            continue
    
    # Fallback to basic HTML using article's Chinese title and summary
    image = article.get("cover_url", "") or article.get("image_url", "")
    title = article.get("title", "")
    summary = article.get("summary", "")
    fallback_html = f'<img src="{image}" style="width:100%;display:block;"><p style="margin:1em 0;font-size:0.95em;line-height:1.7em;color:#bbb;">{title}</p><p style="margin:1em 0;font-size:0.95em;line-height:1.7em;color:#bbb;">{summary}</p>'
    return fallback_html, "fallback", "basic"


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
    
    # Step 2-4: Generate cards (up to 3 cards)
    card_htmls = []
    card_models = []
    for i, article in enumerate(articles[:3]):
        card_num = i + 1
        html, card_provider, card_model = _generate_card_step(model_candidates, card_num, article, date_str)
        card_htmls.append(html)
        card_models.append(f"{card_provider}:{card_model}")
        print(f"[Step {card_num+1}/4] Complete: Card {card_num} generated\n")
    
    # Build songs from article titles
    songs = []
    for article in articles[:3]:
        songs.append({
            "name": article.get("title", "")[:30],
            "artist": article.get("channel", "NASA")
        })
    
    # Assemble final payload
    # Build weixin_html with dark theme styling
    header_gif = "https://mmbiz.qpic.cn/mmbiz_gif/xm1dT1jCe8lIO3P2oFVtd1x040PKGCRPN033gUTrHQQz0Licdqug5X1QgUPQBRCicoTqdYMrpgk7etibXLkK9rwcg/0?wx_fmt=gif&from=appmsg"
    
    weixin_html_parts = [
        f"<section data-side-margin='0' style='margin:0;padding:0;box-sizing:border-box;background:#0a0a0a;color:#eee;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif;'>"
    ]
    
    # Add header GIF
    weixin_html_parts.append(f"<section style='margin:0;padding:0;'><img src='{header_gif}' style='width:100%;display:block;'></section>")
    
    # Add cards
    for i, html in enumerate(card_htmls):
        if i == 1:  # Add divider before card 2
            weixin_html_parts.append("<section style='text-align:center;margin:2em 0;padding:10px;background:#1a1a1a;'><span style='font-weight:bold;color:#fff;'>今日NASA新闻</span></section>")
        weixin_html_parts.append(f"<section style='margin:0;padding:0;'>{html}</section>")
    
    weixin_html_parts.append("</section>")
    weixin_html = "".join(weixin_html_parts)
    
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
