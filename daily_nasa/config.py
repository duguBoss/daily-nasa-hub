from __future__ import annotations

import os
from pathlib import Path

import pytz


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
NVIDIA_OPENAI_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL_SERIES = (
    "moonshotai/kimi-k2.5",
    "nvidia/nemotron-3-super-120b-a12b",
    "minimaxai/minimax-m2.5",
    "z-ai/glm5",
)
MINIMAX_OPENAI_BASE_URL = "https://api.minimaxi.com/v1"
MINIMAX_MODEL_NAME = "MiniMax-M2.7"

REQUEST_TIMEOUT = 45
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
    "登月",
    "月球",
    "月面",
    "空间站",
    "深空",
    "火箭",
    "发射",
    "望远镜",
)
FORBIDDEN_TITLE_PATTERNS = (
    "nasa今日速递",
    "一次看懂",
    "今天最值得看的",
    "关键信息梳理",
    "原文直译",
    "看点清单",
    "倒计时",
    "里程碑",
    "追踪提醒",
)
GENERIC_TITLE_TOKENS = (
    "nasa",
    "今日",
    "今天",
    "最新",
    "动态",
    "盘点",
    "看点",
    "关键",
    "进展",
    "速读",
    "解读",
    "发布",
    "更新",
    "任务",
)
