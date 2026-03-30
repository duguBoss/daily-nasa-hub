from __future__ import annotations

from .models import (
    build_model_candidates,
    call_gemini,
    call_minimax,
    is_quota_or_rate_limit_error,
    parse_model_json,
)
from .prompts import (
    FAN_PERSPECTIVE_TERMS,
    MISSION_HINT_TERMS,
    build_gemini_prompt,
    build_gemini_rewrite_prompt,
    build_story_terms,
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
    PRIMARY_MODEL_NAME,
    REQUEST_TIMEOUT,
    REQUIRE_AI_GENERATION,
    TITLE_KEYWORDS,
)
from typing import Any


__all__ = [
    "generate_payload",
    "evaluate_payload_quality",
    "sanitize_payload",
    "build_gemini_prompt",
    "build_gemini_rewrite_prompt",
    "call_gemini",
    "call_minimax",
    "parse_model_json",
    "build_model_candidates",
    "is_quota_or_rate_limit_error",
    "build_story_terms",
    "title_matches_story_terms",
]


def generate_payload(
    gemini_api_key: str | None,
    minimax_api_key: str | None,
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

    if REQUIRE_AI_GENERATION and not gemini_api_key and not minimax_api_key:
        raise RuntimeError("Neither GEMINI_API_KEY nor MINIMAX_API_KEY is set. AI generation is required for publishing.")

    model_candidates = build_model_candidates(gemini_api_key, minimax_api_key)

    if REQUIRE_AI_GENERATION and not model_candidates:
        raise RuntimeError("No usable model candidate found for AI generation.")

    primary_provider, primary_model_name = ("gemini", PRIMARY_MODEL_NAME)
    if model_candidates:
        primary_provider, primary_model_name = model_candidates[0][0], model_candidates[0][1]

    meta: dict[str, Any] = {
        "ai_enabled": bool(gemini_api_key or minimax_api_key),
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

    latest_payload = default_payload
    latest_quality = default_quality
    last_error = ""

    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        attempt_best_payload: dict[str, Any] | None = None
        attempt_best_quality: dict[str, Any] | None = None
        attempt_best_model = ""
        attempt_best_provider = ""

        for provider, model_name, provider_api_key, caller in model_candidates:
            model_label = f"{provider}:{model_name}"
            try:
                print(f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS}: trying {model_label}")
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

                raw = caller(provider_api_key, prompt, model_name)
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
                    f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_label}: "
                    f"quality={quality['score']} issues={quality['issues'][:6]}"
                )

                if attempt_best_quality is None or quality["score"] > attempt_best_quality["score"]:
                    attempt_best_payload = candidate
                    attempt_best_quality = quality
                    attempt_best_model = model_name
                    attempt_best_provider = provider

                if quality["score"] >= MIN_QUALITY_SCORE:
                    meta.update(
                        {
                            "ai_success": True,
                            "provider": provider,
                            "fallback_used": not (
                                provider == primary_provider and model_name == primary_model_name
                            ),
                            "model": model_name,
                            "quality_score": quality["score"],
                            "quality_breakdown": quality["breakdown"],
                            "quality_issues": quality["issues"],
                            "attempts": attempt,
                        }
                    )
                    return candidate, meta
            except Exception as exc:
                last_error = f"{model_label}: {exc}"
                if is_quota_or_rate_limit_error(str(exc)):
                    print(
                        f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_label} hit quota/rate limit; "
                        "switching to next model."
                    )
                print(f"Model attempt {attempt}/{MAX_MODEL_ATTEMPTS} with {model_label} failed: {exc}")

        if attempt_best_payload is not None and attempt_best_quality is not None:
            latest_payload = attempt_best_payload
            latest_quality = attempt_best_quality
            meta.update(
                {
                    "quality_score": attempt_best_quality["score"],
                    "quality_breakdown": attempt_best_quality["breakdown"],
                    "quality_issues": attempt_best_quality["issues"],
                    "provider": attempt_best_provider or primary_provider,
                    "model": attempt_best_model or primary_model_name,
                    "attempts": attempt,
                    "fallback_used": not (
                        (attempt_best_provider or primary_provider) == primary_provider
                        and (attempt_best_model or primary_model_name) == primary_model_name
                    ),
                }
            )

    raise RuntimeError(
        f"Model output below quality threshold after {MAX_MODEL_ATTEMPTS} attempts. "
        f"Best score={meta['quality_score']}, required={MIN_QUALITY_SCORE}, "
        f"issues={meta['quality_issues'][:6]}, last_error={last_error}"
    )
