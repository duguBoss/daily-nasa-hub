from __future__ import annotations

import datetime
import os
from typing import Any

from daily_nasa.ai_writer import generate_payload
from daily_nasa.config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    GEMINI_ADDITIONAL_FALLBACK_MODELS,
    IMAGE_OF_THE_DAY_URL,
    LIST_TOP_N,
    MERGE_TOP_N,
    MINIMAX_MODEL_NAME,
    OPENROUTER_MODEL_SERIES,
    PRIMARY_MODEL_NAME,
    SHANGHAI_TZ,
)
from daily_nasa.fetching import build_processed_articles, fetch_apod_candidates, fetch_image_of_the_day_candidate, fetch_spaceflight_news_today, fetch_top_n_articles
from daily_nasa.persistence import get_optional_api_key, get_optional_groq_api_key, get_optional_minimax_api_key, get_optional_openrouter_api_key, save_news
from daily_nasa.state import cleanup_old_files, load_previous_day_candidates, load_seen_state, save_seen_state


def main() -> None:
    target_date = datetime.datetime.now(SHANGHAI_TZ).date()
    date_str = target_date.isoformat()
    print(f"Running NASA daily pipeline for {date_str}")

    cleanup_old_files(target_date, keep_days=10)

    state = load_seen_state()
    seen_urls = set(state.get("seen_urls", []))
    print(f"Loaded state: seen_urls={len(seen_urls)}")

    todays_apod = fetch_apod_candidates(1)
    if todays_apod:
        print(f"Today's APOD: {todays_apod[0]['title']}")

    sfn_news = fetch_spaceflight_news_today()
    if sfn_news:
        print(f"SpaceFlight News: {len(sfn_news)} articles available")

    top_list = fetch_top_n_articles(LIST_TOP_N)
    top_urls = [item["url"] for item in top_list]
    new_candidates = [item for item in top_list if item["url"] not in seen_urls]
    print(f"New NASA candidates after dedupe check: {len(new_candidates)}")
    for idx, item in enumerate(new_candidates, start=1):
        print(f"  NEW {idx}. {item['title']}")

    selected: list[dict[str, Any]] = []
    selected_url_set: set[str] = set()
    reused_source_date = ""

    if todays_apod:
        selected.append(todays_apod[0])
        print(f"Selected APOD: {todays_apod[0]['title']}")

    primary_news_pool = new_candidates or top_list
    if primary_news_pool:
        primary_news = primary_news_pool[0]
        selected.append(primary_news)
        if primary_news.get("url"):
            selected_url_set.add(primary_news["url"])
        if new_candidates:
            print(f"Selected NASA news: {primary_news['title']}")
        else:
            print(f"No new NASA news, using top: {primary_news['title']}")

    if sfn_news and len(selected) < 3:
        selected.append(sfn_news[0])
        print(f"Added SpaceFlight news: {sfn_news[0]['title']}")

    if len(selected) < 3:
        backup_news_pool = new_candidates[1:] if len(new_candidates) > 1 else []
        if not backup_news_pool:
            backup_news_pool = [item for item in top_list if item.get("url") not in selected_url_set]
        for candidate in backup_news_pool:
            url = candidate.get("url", "")
            if url and url in selected_url_set:
                continue
            selected.append(candidate)
            if url:
                selected_url_set.add(url)
            print(f"Filled missing slot with NASA news: {candidate['title']}")
            if len(selected) >= 3:
                break

    if len(selected) < 3:
        history_candidates, history_date = load_previous_day_candidates(target_date, max(1, 3 - len(selected)))
        for candidate in history_candidates:
            url = candidate.get("url", "")
            if url and url in selected_url_set:
                continue
            selected.append(candidate)
            if url:
                selected_url_set.add(url)
            reused_source_date = history_date
            print(f"Fallback to historical from {history_date}: {candidate['title']}")
            if len(selected) >= 3:
                break

    if top_list:
        print("Top list URLs:")
        for idx, url in enumerate(top_urls, start=1):
            print(f"  {idx}. {url}")

    if not selected:
        print("No available candidate after fallback, only update state and exit.")
        save_seen_state(state, latest_urls=top_urls, new_urls=[], date_str=date_str)
        return

    processed_articles = build_processed_articles(selected, date_str)
    if not processed_articles:
        print("No processed article generated, only update state and exit.")
        save_seen_state(state, latest_urls=top_urls, new_urls=[], date_str=date_str)
        return

    cover_urls = [article.get("cover_url", "") for article in processed_articles if article.get("cover_url", "")]
    gemini_api_key = get_optional_api_key()
    minimax_api_key = get_optional_minimax_api_key()
    openrouter_api_key = get_optional_openrouter_api_key()
    groq_api_key = get_optional_groq_api_key()
    minimax_model_name = os.environ.get("MINIMAX_MODEL_NAME", "").strip() or MINIMAX_MODEL_NAME
    openrouter_models = [model_name for model_name in OPENROUTER_MODEL_SERIES if model_name]
    gemini_fallbacks = [FALLBACK_MODEL_NAME, EXTRA_FALLBACK_MODEL_NAME, *list(GEMINI_ADDITIONAL_FALLBACK_MODELS)]
    print(
        "AI models: "
        f"primary={PRIMARY_MODEL_NAME}, gemini_fallbacks={gemini_fallbacks}, "
        f"openrouter_series={openrouter_models}, minimax={minimax_model_name}"
    )

    payload, generation_meta = generate_payload(
        gemini_api_key,
        minimax_api_key,
        openrouter_api_key,
        groq_api_key,
        date_str,
        processed_articles,
        cover_urls,
    )
    if reused_source_date:
        generation_meta["reused_previous_day"] = True
        generation_meta["reused_source_date"] = reused_source_date

    if generation_meta["ai_success"]:
        print(f"AI generation succeeded with model {generation_meta['model']}.")
    else:
        print("AI generation fallback used. " f"reason={generation_meta.get('error', 'unknown error')}")

    if reused_source_date:
        selected_urls = []
    else:
        selected_urls = [
            item["url"]
            for item in selected
            if item.get("url") and not item.get("is_apod") and not item.get("is_sfn")
        ]

    save_news(
        processed_articles,
        payload,
        generation_meta,
        date_str,
        top_urls,
        selected_urls,
    )

    save_seen_state(
        state,
        latest_urls=top_urls,
        new_urls=selected_urls,
        date_str=date_str,
    )

    print("Pipeline finished.")


if __name__ == "__main__":
    main()
