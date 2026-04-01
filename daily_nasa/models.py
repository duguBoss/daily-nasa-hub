from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Iterable

import requests

from .config import (
    EXTRA_FALLBACK_MODEL_NAME,
    FALLBACK_MODEL_NAME,
    GEMINI_ADDITIONAL_FALLBACK_MODELS,
    GEMINI_REQUEST_TIMEOUT,
    GROQ_MAX_TOKENS,
    GROQ_MODEL_SERIES,
    GROQ_REQUEST_TIMEOUT,
    MINIMAX_MODEL_NAME,
    MINIMAX_OPENAI_BASE_URL,
    MINIMAX_REQUEST_TIMEOUT,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODEL_SERIES,
    OPENROUTER_OPENAI_BASE_URL,
    OPENROUTER_REQUEST_TIMEOUT,
    OPENROUTER_STREAM,
    PRIMARY_MODEL_NAME,
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


def _request_timeout(read_timeout: int) -> tuple[int, int]:
    return (20, read_timeout)


def _response_excerpt(response: requests.Response, limit: int = 400) -> str:
    try:
        body = response.text
    except Exception:
        body = ""
    return normalize_whitespace(body)[:limit]


def _parse_json_response(response: requests.Response, provider_label: str) -> dict[str, Any]:
    """Parse JSON response with proper UTF-8 encoding handling."""
    try:
        # Ensure proper encoding - force UTF-8
        response.encoding = 'utf-8'
        return response.json()
    except ValueError as exc:
        excerpt = _response_excerpt(response)
        if excerpt:
            raise RuntimeError(
                f"{provider_label} returned non-JSON body ({response.status_code}): {excerpt}"
            ) from exc
        raise RuntimeError(f"{provider_label} returned empty response body ({response.status_code}).") from exc


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
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=_request_timeout(GEMINI_REQUEST_TIMEOUT),
    )
    if response.status_code != 200:
        raise RuntimeError(f"{model_name} request failed ({response.status_code}): {_response_excerpt(response)}")

    result_json = _parse_json_response(response, model_name)
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
        timeout=_request_timeout(MINIMAX_REQUEST_TIMEOUT),
    )
    if response.status_code != 200:
        raise RuntimeError(f"MINIMAX request failed ({response.status_code}): {_response_excerpt(response)}")
    result_json = _parse_json_response(response, "MINIMAX")
    choices = result_json.get("choices", [])
    if not choices:
        raise RuntimeError("MINIMAX returned empty choices.")
    return extract_message_content(choices[0].get("message", {}).get("content", ""))


def _iter_sse_data(lines: Iterable[str]) -> Iterable[str]:
    for raw_line in lines:
        if not raw_line:
            continue
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            yield line[5:].strip()
        elif line.startswith("{"):
            yield line


def _collect_stream_text(response: requests.Response, provider_label: str) -> str:
    chunks: list[str] = []
    for data in _iter_sse_data(response.iter_lines(decode_unicode=True)):
        if data == "[DONE]":
            break
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = event.get("choices", [])
        for choice in choices:
            delta = choice.get("delta") or choice.get("message") or {}
            content = extract_message_content(delta.get("content", ""))
            if content:
                chunks.append(content)
    text = "".join(chunks).strip()
    if text:
        return text
    raise RuntimeError(f"{provider_label} stream returned no content.")


def call_openrouter(api_key: str, prompt: str, model_name: str) -> str:
    """Call OpenRouter API using OpenAI client."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    base_url = os.environ.get("OPENROUTER_OPENAI_BASE_URL", "").strip() or OPENROUTER_OPENAI_BASE_URL

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    # Build messages
    messages = [{"role": "user", "content": prompt}]

    # Create completion
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=OPENROUTER_MAX_TOKENS,
        temperature=0.55,
        top_p=0.9,
        extra_headers={
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://github.com/duguBoss/daily-nasa-hub"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "daily-nasa-hub"),
        },
    )

    # Extract content from response
    if not completion.choices:
        raise RuntimeError("OpenRouter returned empty choices.")

    return extract_message_content(completion.choices[0].message.content)


def extract_message_content(content: Any) -> str:
    """Extract text content from various response formats with UTF-8 handling."""
    if isinstance(content, str):
        # Ensure proper UTF-8 handling
        if isinstance(content, bytes):
            return content.decode('utf-8', errors='replace')
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


def call_groq(api_key: str, prompt: str, model_name: str) -> str:
    """Call Groq API using OpenAI-compatible interface."""
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq package not installed. Run: pip install groq")
    
    client = Groq(api_key=api_key)
    
    # Build messages
    messages = [{"role": "user", "content": prompt}]
    
    # Create completion with streaming
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.55,
        max_completion_tokens=GROQ_MAX_TOKENS,
        top_p=0.9,
        stream=True,
        stop=None,
    )
    
    # Collect streamed content
    chunks: list[str] = []
    for chunk in completion:
        content = chunk.choices[0].delta.content
        if content:
            chunks.append(content)
    
    result = "".join(chunks).strip()
    if not result:
        raise RuntimeError(f"Groq:{model_name} returned empty content")
    
    return result


def parse_model_json(text: str) -> dict[str, Any]:
    """Parse JSON from model response with error handling for incomplete JSON."""
    text = normalize_whitespace(text)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    # Try to parse as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to fix common JSON issues
        # 1. Remove trailing commas before } or ]
        fixed_text = re.sub(r',(\s*[}\]])', r'\1', text)
        # 2. Try to close unclosed strings by finding the last complete key-value pair
        # Find the last complete property and truncate there
        last_complete = re.search(r'("[^"]*"\s*:\s*(?:"[^"]*"|[^,{}\[\]]*))\s*$', fixed_text)
        if last_complete:
            # Try to find a good truncation point
            truncated = fixed_text[:last_complete.end()]
            # Close any open structures
            open_braces = truncated.count('{') - truncated.count('}')
            open_brackets = truncated.count('[') - truncated.count(']')
            truncated += '}' * open_braces + ']' * open_brackets
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass
        
        # 3. If all else fails, try to extract just the title and weixin_html fields
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', text)
        html_match = re.search(r'"weixin_html"\s*:\s*"([^"]*)"', text, re.DOTALL)
        
        if title_match or html_match:
            result: dict[str, Any] = {}
            if title_match:
                result["title"] = title_match.group(1)
            if html_match:
                result["weixin_html"] = html_match.group(1)
            return result
        
        # Re-raise the original error if we can't fix it
        raise e


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_model_candidates(
    gemini_api_key: str | None,
    minimax_api_key: str | None,
    openrouter_api_key: str | None,
    groq_api_key: str | None,
) -> list[tuple[str, str, str, Callable[[str, str, str], str]]]:
    model_candidates: list[tuple[str, str, str, Callable[[str, str, str], str]]] = []
    
    # OpenRouter first (user preference - highest priority)
    if openrouter_api_key:
        openrouter_models = [model_name.strip() for model_name in OPENROUTER_MODEL_SERIES if model_name.strip()]
        env_model = os.environ.get("OPENROUTER_MODEL_NAME", "").strip()
        if env_model:
            openrouter_models = [env_model, *[name for name in openrouter_models if name != env_model]]
        for model_name in openrouter_models:
            model_candidates.append(("openrouter", model_name, openrouter_api_key, call_openrouter))
    
    # Groq second
    if groq_api_key:
        groq_models = [model_name.strip() for model_name in GROQ_MODEL_SERIES if model_name.strip()]
        env_model = os.environ.get("GROQ_MODEL_NAME", "").strip()
        if env_model:
            groq_models = [env_model, *[name for name in groq_models if name != env_model]]
        for model_name in groq_models:
            model_candidates.append(("groq", model_name, groq_api_key, call_groq))
    
    # Gemini as fallback
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
    
    return model_candidates
