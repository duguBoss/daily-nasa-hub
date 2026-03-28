from __future__ import annotations

import datetime
import os
from typing import Any

from daily_nasa.ai_writer import generate_payload
from daily_nasa.config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    IMAGE_OF_THE_DAY_URL,
    LIST_TOP_N,
    MERGE_TOP_N,
    MINIMAX_MODEL_NAME,
    PRIMARY_MODEL_NAME,
    SHANGHAI_TZ,
)
from daily_nasa.fetching import build_processed_articles, fetch_image_of_the_day_candidate, fetch_top_n_articles
from daily_nasa.persistence import get_optional_api_key, get_optional_minimax_api_key, save_news
from daily_nasa.state import cleanup_old_files, load_previous_day_candidates, load_seen_state, save_seen_state


def main() -> None:
    target_date = datetime.datetime.now(SHANGHAI_TZ).date()
    date_str = target_date.isoformat()
    print(f"Running NASA daily pipeline for {date_str}")

    cleanup_old_files(target_date, keep_days=10)

    state = load_seen_state()
    seen_urls = set(state.get("seen_urls", []))
    print(f"Loaded state: seen_urls={len(seen_urls)}")

    top_list = fetch_top_n_articles(LIST_TOP_N)
    top_urls = [item["url"] for item in top_list]
    selected: list[dict[str, Any]] = []
    reused_source_date = ""

    if top_list:
        print("Top list URLs:")
        for idx, url in enumerate(top_urls, start=1):
            print(f"  {idx}. {url}")

        new_candidates = [item for item in top_list if item["url"] not in seen_urls]
        print(f"New candidates after dedupe check: {len(new_candidates)}")
        for idx, item in enumerate(new_candidates, start=1):
            print(f"  NEW {idx}. {item['title']}")

        if new_candidates:
            selected = new_candidates[:MERGE_TOP_N]
        else:
            print("No new URL today, fallback to latest historical daily content.")
            history_candidates, history_date = load_previous_day_candidates(target_date, MERGE_TOP_N)
            if history_candidates:
                selected = history_candidates
                reused_source_date = history_date
                print(f"Reuse historical content from {history_date}, candidates={len(history_candidates)}")
            else:
                print("No historical content found, fallback to NASA Image of the Day.")
                iotd_candidate = fetch_image_of_the_day_candidate(IMAGE_OF_THE_DAY_URL)
                if iotd_candidate:
                    selected = [iotd_candidate]
                    if iotd_candidate["url"] not in top_urls:
                        top_urls = [iotd_candidate["url"]] + top_urls
    else:
        print("No list items found, fallback to latest historical daily content.")
        history_candidates, history_date = load_previous_day_candidates(target_date, MERGE_TOP_N)
        if history_candidates:
            selected = history_candidates
            reused_source_date = history_date
            print(f"Reuse historical content from {history_date}, candidates={len(history_candidates)}")
            if not top_urls:
                top_urls = [item["url"] for item in history_candidates]
        else:
            print("No historical content found, fallback to NASA Image of the Day.")
            iotd_candidate = fetch_image_of_the_day_candidate(IMAGE_OF_THE_DAY_URL)
            if iotd_candidate:
                selected = [iotd_candidate]
                top_urls = [iotd_candidate["url"]]

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
    minimax_model_name = os.environ.get("MINIMAX_MODEL_NAME", "").strip() or MINIMAX_MODEL_NAME
    print(
        "AI models: "
        f"primary={PRIMARY_MODEL_NAME}, fallback={FALLBACK_MODEL_NAME}, extra_fallback={EXTRA_FALLBACK_MODEL_NAME}, "
        f"minimax={minimax_model_name}"
    )

    payload, generation_meta = generate_payload(gemini_api_key, minimax_api_key, date_str, processed_articles, cover_urls)
    if reused_source_date:
        generation_meta["reused_previous_day"] = True
        generation_meta["reused_source_date"] = reused_source_date

    if generation_meta["ai_success"]:
        print(f"AI generation succeeded with model {generation_meta['model']}.")
    else:
        print("AI generation fallback used. " f"reason={generation_meta.get('error', 'unknown error')}")

    selected_urls = [] if reused_source_date else [item["url"] for item in selected]

    save_news(
        processed_articles,
        payload,
        generation_meta,
        date_str,
        source_top_urls=top_urls,
        new_urls=selected_urls,
    )
    save_seen_state(state, latest_urls=top_urls, new_urls=selected_urls, date_str=date_str)
    print("Daily NASA pipeline completed.")


if __name__ == "__main__":
    main()
