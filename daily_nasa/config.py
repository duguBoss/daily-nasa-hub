from __future__ import annotations

from pathlib import Path

import pytz


NASA_NEWS_URLS = [
    "https://www.nasa.gov/news/recently-published/",
    "https://www.nasa.gov/2026-news-releases/",
]
IMAGE_OF_THE_DAY_URL = "https://www.nasa.gov/image-of-the-day/"

MODEL_NAME = "gemini-3.1-flash-lite-preview"
REQUEST_TIMEOUT = 30
LIST_TOP_N = 5
MERGE_TOP_N = 3
MAX_SEEN_URLS = 1200
MIN_QUALITY_SCORE = 90
MAX_MODEL_ATTEMPTS = 3
MAX_REWRITE_ROUNDS = 2

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
    "NASA",
    "Artemis",
    "阿尔忒弥斯",
    "登月",
    "空间站",
    "火箭",
    "深空",
    "月球",
    "探测",
)
FORBIDDEN_TITLE_PATTERNS = (
    "NASA今日速递",
    "一次看懂",
    "原文",
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
