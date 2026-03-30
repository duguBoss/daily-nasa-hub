from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

import requests

from .config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    GEMINI_ADDITIONAL_FALLBACK_MODELS,
    MINIMAX_MODEL_NAME,
    MINIMAX_OPENAI_BASE_URL,
    NVIDIA_MODEL_SERIES,
    NVIDIA_OPENAI_BASE_URL,
    PRIMARY_MODEL_NAME,
    REQUEST_TIMEOUT,
)


def is_quota_or_rate_limit_error(error_text: str) -> bool:
    text = error_text.lower()
    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "insufficient_quota" in text
        or "rate limit" in text
        or "too many requests" in text
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


def call_minimax(api_key: str, prompt: str, model_name: str) -> str:
    base_url = os.environ.get("MINIMAX_OPENAI_BASE_URL", "").strip() or MINIMAX_OPENAI_BASE_URL
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "stream": False,
    }
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"MINIMAX request failed ({response.status_code}): {response.text}")
    result_json = response.json()
    choices = result_json.get("choices", [])
    if not choices:
        raise RuntimeError("MINIMAX returned empty choices.")
    return extract_message_content(choices[0].get("message", {}).get("content", ""))


def call_nvidia(api_key: str, prompt: str, model_name: str) -> str:
    base_url = os.environ.get("NVIDIA_OPENAI_BASE_URL", "").strip() or NVIDIA_OPENAI_BASE_URL
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16384,
        "temperature": 1.0,
        "top_p": 1.0,
        "stream": False,
        "chat_template_kwargs": {"thinking": True},
    }
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"NVIDIA request failed ({response.status_code}): {response.text}")
    result_json = response.json()
    choices = result_json.get("choices", [])
    if not choices:
        raise RuntimeError("NVIDIA returned empty choices.")
    return extract_message_content(choices[0].get("message", {}).get("content", ""))


def extract_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            elif isinstance(item, str) and item.strip():
                parts.append(item)
        return "\n".join(parts)
    return str(content or "")


def parse_model_json(text: str) -> dict[str, Any]:
    text = normalize_whitespace(text)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_model_candidates(
    gemini_api_key: str | None,
    minimax_api_key: str | None,
    nvidia_api_key: str | None,
) -> list[tuple[str, str, str, Callable[[str, str, str], str]]]:
    model_candidates: list[tuple[str, str, str, Callable[[str, str, str], str]]] = []
    if gemini_api_key:
        gemini_models = [
            PRIMARY_MODEL_NAME,
            FALLBACK_MODEL_NAME,
            EXTRA_FALLBACK_MODEL_NAME,
            *list(GEMINI_ADDITIONAL_FALLBACK_MODELS),
        ]
        for model_name in gemini_models:
            if model_name:
                model_candidates.append(("gemini", model_name, gemini_api_key, call_gemini))
    if nvidia_api_key:
        nvidia_models = [model_name.strip() for model_name in NVIDIA_MODEL_SERIES if model_name.strip()]
        env_model = os.environ.get("NVIDIA_MODEL_NAME", "").strip()
        if env_model:
            nvidia_models = [env_model, *[name for name in nvidia_models if name != env_model]]
        for model_name in nvidia_models:
            model_candidates.append(("nvidia", model_name, nvidia_api_key, call_nvidia))
    if minimax_api_key:
        minimax_model_name = os.environ.get("MINIMAX_MODEL_NAME", "").strip() or MINIMAX_MODEL_NAME
        model_candidates.append(("minimax", minimax_model_name, minimax_api_key, call_minimax))
    return model_candidates
