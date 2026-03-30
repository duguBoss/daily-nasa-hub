from __future__ import annotations

import os
from pathlib import Path

import pytz


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


NASA_NEWS_URLS = [
    "https://www.nasa.gov/news/recently-published/",
    "https://www.nasa.gov/2026-news-releases/",
]
IMAGE_OF_THE_DAY_URL = "https://www.nasa.gov/image-of-the-day/"
APOD_API_KEY = os.environ.get("NASA_APOD_API_KEY", "DEMO_KEY")
SFN_API_KEY = os.environ.get("SFN_API_KEY", "")
SFN_API_BASE = "https://api.spaceflightnewsapi.net/v4"

# Model policy requested by user:
# primary model -> fallback model -> extra fallback model.
PRIMARY_MODEL_NAME = "gemini-3.1-pro-preview"
FALLBACK_MODEL_NAME = "gemini-3-flash-preview"
EXTRA_FALLBACK_MODEL_NAME = "gemini-3.1-flash-lite-preview"
GEMINI_ADDITIONAL_FALLBACK_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
)
OPENROUTER_OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL_SERIES = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m2.5:free",
    "stepfun/step-3.5-flash:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
)
MINIMAX_OPENAI_BASE_URL = "https://api.minimaxi.com/v1"
MINIMAX_MODEL_NAME = "MiniMax-M2.7"

REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 45)
GEMINI_REQUEST_TIMEOUT = _env_int("GEMINI_REQUEST_TIMEOUT", REQUEST_TIMEOUT)
OPENROUTER_REQUEST_TIMEOUT = _env_int("OPENROUTER_REQUEST_TIMEOUT", max(REQUEST_TIMEOUT, 180))
MINIMAX_REQUEST_TIMEOUT = _env_int("MINIMAX_REQUEST_TIMEOUT", max(REQUEST_TIMEOUT, 120))
OPENROUTER_MAX_TOKENS = _env_int("OPENROUTER_MAX_TOKENS", 8192)
OPENROUTER_STREAM = _env_flag("OPENROUTER_STREAM", True)
LIST_TOP_N = 5
MERGE_TOP_N = 3
MAX_SEEN_URLS = 1200

# Quality and retry policy:
# - score threshold must pass
# - retry count capped at 2 attempts total
MIN_QUALITY_SCORE = 92
MAX_MODEL_ATTEMPTS = 2

# Strict mode: must use model output; no model means error.
REQUIRE_AI_GENERATION = True

ASSET_ROOT = Path("assets") / "generated"
STATE_FILE = Path("state") / "nasa_seen_urls.json"
SHANGHAI_TZ = pytz.timezone("Asia/Shanghai")

FOLLOW_HEADER_GIF = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "xm1dT1jCe8lIO3P2oFVtd1x040PKGCRPN033gUTrHQQz0Licdqug5X1QgUPQBRCicoTqdYMrpgk7etibXLkK9rwcg/0"
    "?wx_fmt=gif&from=appmsg"
)
TOP_BANNER_URL = FOLLOW_HEADER_GIF
BOTTOM_BANNER_URL = (
    "https://mmbiz.qpic.cn/mmbiz_gif/"
    "3hAJnwuyZuicicZkgJBUCCaricdibomDBrTzk57DCmhVC16o9ILH0Tn1YPEiarfLRRQSVFN2mJdeYibGnBPialPIzvojw/"
    "0?wx_fmt=gif"
)

TITLE_KEYWORDS = (
    "nasa",
    "artemis",
    "artemis ii",
    "clps",
    "moon",
    "lunar",
    "iss",
    "space station",
    "??",
    "??",
    "??",
    "???",
    "??",
    "??",
    "??",
    "???",
)
FORBIDDEN_TITLE_PATTERNS = (
    "nasa????",
    "????",
    "???????",
    "??????",
    "????",
    "????",
    "???",
    "???",
    "????",
)
GENERIC_TITLE_TOKENS = (
    "nasa",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
    "??",
)
