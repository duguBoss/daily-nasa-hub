from __future__ import annotations

import json
import re
from typing import Any

from .common import normalize_whitespace
from .rendering import build_article_blocks


MIN_CHINESE_CHARS = 500
MISSION_HINT_TERMS = (
    "artemis",
    "artemis ii",
    "clps",
    "intuitive machines",
    "iss",
    "space station",
    "kennedy",
    "roman",
    "webb",
    "hubble",
    "nisar",
    "moon",
    "lunar",
    "launch",
    "spacex",
    "payload",
    "登月",
    "月球",
    "发射",
    "载荷",
    "空间站",
    "望远镜",
)
FAN_PERSPECTIVE_TERMS = (
    "如果你最近在关注",
    "真正值得注意的是",
    "先抓住一个关键信息",
    "换句话说",
    "对NASA粉丝来说",
)
FORBIDDEN_TITLE_TERMS = (
    "3条",
    "三条",
    "要闻",
    "速报",
    "汇总",
    "盘点",
    "合集",
    "冲刺",
    "开扯",
    "扒一扒",
    "扒",
    "盘",
)
TITLE_STYLE_HINT = "标题要像成熟中文科技自媒体，不要像栏目名或低信息量摘要"
_GENERIC_STORY_TOKENS = {
    "nasa",
    "today",
    "daily",
    "update",
    "mission",
    "missions",
    "news",
    "story",
    "article",
    "science",
    "space",
    "最新",
    "动态",
    "消息",
    "进展",
    "节点",
    "科普",
    "新闻",
    "任务",
    "发布",
}


def build_gemini_prompt(date_str: str, articles: list[dict[str, Any]], cover_urls: list[str], recent_titles: list[str]) -> str:
    return f"""
You are a NASA enthusiast and a senior Chinese science editor for WeChat.
Write a polished Chinese NASA daily briefing that is vivid, accurate, and obviously grounded in the source materials.

Date: {date_str}
News materials:
{build_article_blocks(articles)}

Cover candidates:
{json.dumps(cover_urls, ensure_ascii=False)}

Recent titles to avoid duplication:
{json.dumps(recent_titles[:12], ensure_ascii=False)}

MANDATORY OUTPUT RULES:
1) Output valid JSON only.
2) All user-facing body text must be Simplified Chinese.
3) Title length 14-28 Chinese chars. It must contain at least one concrete mission, entity, place, payload, date, or scientific fact from the materials.
4) The title must read like a strong Chinese self-media headline: specific, information-dense, and curiosity-inducing, but still truthful.
5) Do not write generic count headlines like “3条NASA要闻”, “三条动态”, “今日速报”, or any low-information title that hides the real subject.
6) Do not use slang or internet-black-talk words such as “冲刺”, “开扯”, “盘”, “扒一扒”.
7) Prefer direct information in the title: mission name, payload count, launch node, crew move, telescope image, or scientific finding.
8) Avoid repeating “NASA” when the subject can be made clearer by naming the mission, spacecraft, company, telescope, or destination.
9) No external links, no anchor tags, no source-jump wording, and no “点击原文/来源如下” style copy.
10) Body must have >= 500 Chinese characters.
11) The article structure must contain exactly 3 content cards when 3 materials are provided:
    - Card 1: fixed as “NASA每日科普”.
    - Card 2 and Card 3: fixed as news cards.
12) Never merge facts across cards. Each card may only use details from its corresponding source block.
13) Each card must contain at least 2 concrete source facts: mission name, agency/company, date, location, payload, quantity, milestone, or technical target.
14) Card 1 should explain what the reader is seeing或理解的对象，然后解释它为什么有科学意义。
15) Card 2 and Card 3 should each use 2-3 natural paragraphs: first explain what happened, then explain why this development matters.
16) Avoid templated phrases and newsroom cliches, especially: “值得持续关注”, “释放了一个信号”, “后续仍值得期待”, “对普通读者来说”.
17) Write like a knowledgeable aerospace fan explaining the day to other readers. Natural, direct, lively, but never exaggerated.
18) The body HTML must NOT repeat the article title. Assume the publishing platform already shows the title separately.
19) Keep strong WeChat visual hierarchy, but do not render a main title heading in weixin_html.
20) Each card must include its image at the top. Use the article Image field from the materials.
21) Preserve important English mission/entity names on first mention when needed, and explain them naturally in Chinese instead of forcing awkward translation.
22) HTML rule: no leading whitespace right after opening tags.
23) Side margin/padding must be 0 (or omitted) on the outer wrapper.
24) Card styling must be FULL-WIDTH with NO side padding/margin: use `margin:0;padding:0` on cards. Do NOT use `padding:1em` or `margin: 2em` that creates side whitespace. Cards should touch screen edges.
25) Images must be `width:100%` with no border-radius or side margins.

JSON schema:
{{
  "date": "{date_str}",
  "title": "...",
  "covers": ["up to 5 image urls"],
  "songs": [{{"name": "news title", "artist": "channel"}}],
  "weixin_html": "<section>...</section>"
}}
"""


def build_gemini_rewrite_prompt(date_str: str, articles: list[dict[str, Any]], previous_payload: dict[str, Any], quality_report: dict[str, Any], attempt: int) -> str:
    issues = quality_report.get("issues", [])[:12]
    return f"""
Rewrite the JSON article to pass quality gate score >= 80.
This is rewrite attempt #{attempt} (max 3 attempts total).

News materials:
{build_article_blocks(articles)}

Current draft JSON:
{json.dumps(previous_payload, ensure_ascii=False)}

Quality report:
{json.dumps(quality_report, ensure_ascii=False)}

Fix these issues first:
{json.dumps(issues, ensure_ascii=False)}

Hard constraints:
- JSON-only output.
- >= 500 Chinese chars in body.
- Title must be a self-media headline, not a generic summary label.
- Do not use weak count titles like “3条NASA要闻”, “三条动态”, “今日速报”.
- Do not use internet slang like “冲刺”, “盘”, “开扯”, “扒一扒”.
- Title must include at least one concrete mission/entity/fact from source materials.
- Keep exactly 3 clearly separated cards when 3 materials are provided.
- Card 1 must be labeled “NASA每日科普”; Card 2 and Card 3 must be news cards.
- Add a visible divider labeled “今日NASA新闻” between Card 1 and Card 2.
- The body HTML must not repeat the overall title as a heading or hero title.
- Each card must stay faithful to its own source. Do not borrow facts, names, dates, or conclusions from another card.
- No links or source jumps.
- No templated phrases such as “值得持续关注”, “释放了一个信号”, “后续仍值得期待”, “对普通读者来说”.
- Every card needs concrete source facts, not generic filler.
- Write from a NASA enthusiast perspective, but keep the tone grounded and readable.
- HTML must have no leading whitespace after opening tags.
- Side margin/padding must be 0 (or omitted).
"""


def build_title_prompt(date_str: str, articles: list[dict[str, Any]], recent_titles: list[str]) -> str:
    """Generate title only - step 1."""
    # Extract key facts from articles for title guidance
    facts = []
    for art in articles[:3]:
        title = art.get('title', '')
        if title:
            facts.append(title)

    return f"""你是NASA中文科技媒体主编，为今日NASA新闻撰写微信推文标题。

【今日素材要点】
{chr(10).join(f"- {f}" for f in facts) if facts else "NASA最新航天动态"}

【近期已用标题】（严禁重复或雷同）
{json.dumps(recent_titles[:12], ensure_ascii=False)}

【标题撰写规范 - 严格遵守】

1. 字数要求（硬性要求）：
   - 必须严格控制在20-30个汉字之间（不含标点符号）
   - 少于20字或超过30字直接不合格
   - 最佳长度：24-28字

2. 中文表达要求（关键）：
   - 必须使用地道中文表达，禁止生硬翻译或直译英文
   - 句子必须通顺自然，符合中文阅读习惯
   - 主谓宾结构清晰，逻辑连贯
   - 禁止出现"飞行第二天获准"这类语义不清的表达
   - 技术术语要使用中文标准译法：
     * translunar injection burn → 地月转移轨道点火/地月转移入射
     * perigee raise → 近地点抬升
     * apogee raise → 远地点抬升
     * cryogenic test → 低温测试
     * launch window → 发射窗口

3. 标题结构公式（三选一）：
   
   类型A - 进展型：[主体] + [完成/达成] + [具体进展] + [状态/结果]
   例："阿尔忒弥斯2号完成地月转移点火，四名宇航员状态良好"（26字）
   
   类型B - 发现型：[探测器/望远镜] + [捕捉到/发现] + [目标] + [特征/意义]
   例："韦伯望远镜捕捉到110亿光年外星系的引力透镜畸变图像"（26字）
   
   类型C - 准备型：[任务/火箭] + [完成准备环节] + [进入/即将] + [下一阶段]
   例："阿尔忒弥斯2号火箭完成低温加注测试，进入发射倒计时"（26字）

4. 用词规范：
   - 使用"完成"、"实现"、"确认"、"进入"等明确动词
   - 时间表达用"今日"、"刚刚"、"任务第二天"等清晰说法
   - 地点用"休斯顿"、"肯尼迪中心"等具体名称
   - 禁止："重磅"、"来了"、"刚刚"、"揭秘"、"真相"、"震惊"
   - 禁止：数字概括（"3大看点"）、情绪煽动词、空洞形容词

5. 差异化原则：
   - 必须基于今日素材的独特事实
   - 每个标题应该是"只有今天才能这么写"
   - 避免通用句式如"NASA宣布..."、"SpaceX完成..."

【自查步骤 - 必须执行】
1. 写出标题草稿
2. 大声朗读一遍，检查是否通顺自然
3. 数汉字数量（不含标点），确认20-30字
4. 检查是否有生硬翻译或语义不清
5. 确认符合规范后输出

【输出要求】
- 只输出标题文字，无引号、无说明、无JSON
- 纯中文（专有名词如Artemis音译为"阿尔忒弥斯"）
- 必须是一句通顺、自然、专业的话

【合格示例】（通顺自然，20-30字）
✓ "阿尔忒弥斯2号完成地月转移点火，四名宇航员状态良好"（26字）
✓ "韦伯望远镜捕捉到110亿光年外星系的引力透镜畸变图像"（26字）
✓ "毅力号在耶泽罗陨石坑发现疑似古代河流三角洲沉积岩层"（26字）

【不合格示例】（生硬、不通顺）
✗ "阿尔忒弥斯2号飞行第二天获准，休斯顿确认地月注入燃烧"（语义不清）
✗ "NASA完成Artemis任务重要节点，实现重大突破进展"（空洞、有英文）

输出："""


def build_card_prompt(card_number: int, article: dict[str, Any], date_str: str) -> str:
    """Generate content for a single card - step 2/3/4."""
    is_science = card_number == 1
    
    article_block = f"""【文章】
标题：{article.get('title', '')}
来源：{article.get('channel', 'NASA')}
时间：{article.get('publish_time', '')}
摘要：{article.get('summary', '')}
内容：{article.get('content', '')[:800]}..."""
    
    if is_science:
        return f"""你是一个NASA爱好者，为中文读者撰写科学解释。
为"NASA每日科普"栏目撰写内容。

日期：{date_str}
素材：
{article_block}

要求：
1) 只输出HTML内容，不要JSON，不要任何额外文字。
2) 以图片开头：<img src="{article.get('cover_url', '') or article.get('image_url', '')}" style="width:100%;display:block;">
3) 然后写2-3段文字：
   - 第一段：解释读者看到的是什么（图片/主题）
   - 第二段：解释这在科学上为什么重要
4) 使用自然、直接的语言，避免模板化表达。
5) HTML标签后不要有前导空格。
6) 全宽布局：使用 margin:0;padding:0。
7) 文字样式（浅色主题）：font-size:0.95em; line-height:1.7em; color:#333333。
8) 所有文字必须是简体中文。

输出格式：纯HTML字符串。"""


def build_card_content_prompt(card_number: int, article: dict[str, Any], date_str: str) -> str:
    """Generate Chinese content for a single card - returns JSON with title and paragraphs."""
    is_science = card_number == 1
    
    article_block = f"""【原文素材】
标题：{article.get('title', '')}
英文标题：{article.get('title_en', '')}
来源：{article.get('channel', 'NASA')}
时间：{article.get('publish_time', '')}
摘要：{article.get('summary', '')}
内容：{article.get('content', '')[:1000]}..."""
    
    card_type = "NASA每日科普" if is_science else f"NASA新闻 #{card_number-1}"
    content_focus = "科学解释" if is_science else "新闻报道"
    
    return f"""你是NASA中文科技媒体编辑，为中文读者撰写{content_focus}内容。

【任务】
为"{card_type}"栏目撰写中文内容。

日期：{date_str}

{article_block}

【字数要求 - 必须严格遵守】
⚠️ 写2个段落，每段必须包含200-300个汉字（这是硬性要求）
⚠️ 每段少于200字或多于300字都是不合格的
⚠️ 写完后必须逐字统计，确保符合要求
⚠️ 最佳长度：每段250字左右，两段共500字左右

【内容结构要求】
第1段（200-300字）：事件/发现介绍
- 简要介绍这是什么事件/发现/技术
- 详细说明关键信息：时间、地点、参与方
- 技术细节、数据、背景信息

第2段（200-300字）：意义与影响
- 工作原理或科学概念解释
- 点明其重要性和影响
- 这个发现/事件的科学价值
- 可能带来的改变或启示

注意：内容本身要有价值和吸引力，不要写"这对读者很有意义"这类直白的话，让价值通过内容自然体现

【写作要求】
- 使用自然、直接的语言，像给朋友分享有趣的知识
- 保留重要的英文术语（首次出现时带中文解释）
- 所有文字必须是简体中文
- 避免模板化表达，像专业科普作家一样写作
- 确保内容对读者有实际价值，不要空洞的描述

【标题要求】
- 15-25字，信息丰富
- 包含具体任务名、发现或科学事实
- 不要"NASA最新消息"这类泛泛标题
- 不要用"盘"、"扒"、"开扯"等网络用语

【输出格式】
只输出JSON，不要任何其他文字：
{{"title": "中文标题", "paragraphs": ["第1段内容（200-300字）...", "第2段内容（200-300字）..."]}}

【参考示例】
标题：韦伯望远镜捕捉到创生之柱新细节：恒星诞生区的壮丽景象
第1段（约250字）：詹姆斯·韦伯空间望远镜（JWST）近日发布了著名的"创生之柱"最新图像，展示了恒星诞生区域的惊人细节。这张图像使用近红外相机拍摄，能够穿透尘埃云，揭示出此前从未见过的年轻恒星。图像中可以看到数十颗正在形成的恒星，它们被包裹在气体和尘埃云中，正在经历引力坍缩过程。这些恒星的年龄只有几十万年，是天文学研究的重要目标。创生之柱位于鹰星云（M16）内，距离地球约6500光年，是恒星形成区的典型代表。

第2段（约250字）：韦伯望远镜的红外观测能力使得科学家能够穿透厚厚的尘埃，直接观测到恒星形成的核心区域。这张图像的科学价值在于它帮助天文学家理解恒星形成的早期阶段。通过分析这些年轻恒星的光谱，科学家可以确定它们的温度、质量和化学成分。此外，图像还揭示了恒星形成过程中喷流和外流的现象，这些都是恒星演化理论的重要组成部分。这一发现将推动恒星演化模型的完善，并为研究行星系统的起源提供新的线索。
"""


def build_card_rewrite_prompt(card_number: int, article: dict[str, Any], date_str: str, previous_attempts: list) -> str:
    """Generate rewrite prompt based on previous attempts to fix length issues."""
    is_science = card_number == 1
    
    # Analyze previous attempt
    last_attempt = previous_attempts[-1] if previous_attempts else {}
    paragraph_lengths = last_attempt.get("paragraph_lengths", [])
    last_content = last_attempt.get("content", {})
    last_paragraphs = last_content.get("paragraphs", [])
    
    # Build feedback about what went wrong
    feedback_parts = []
    for i, length in enumerate(paragraph_lengths):
        if length < 200:
            feedback_parts.append(f"❌ 第{i+1}段：当前只有{length}字，严重不足！需要增加{200-length}字以上")
        elif length > 300:
            feedback_parts.append(f"❌ 第{i+1}段：当前有{length}字，太长了！需要减少{length-300}字")
    
    feedback = "\n".join(feedback_parts) if feedback_parts else "字数需要调整"
    
    # Include last generated content for reference - full content for better iteration
    last_content_text = ""
    if last_paragraphs:
        last_content_text = "\n\n【上次生成的完整内容 - 请在此基础上修改，不要从头重写】\n"
        for i, para in enumerate(last_paragraphs):
            length = paragraph_lengths[i] if i < len(paragraph_lengths) else len(para)
            last_content_text += f"\n第{i+1}段（当前{length}字）：\n{para}\n"
    
    article_block = f"""【原文素材】
标题：{article.get('title', '')}
英文标题：{article.get('title_en', '')}
来源：{article.get('channel', 'NASA')}
摘要：{article.get('summary', '')}
内容：{article.get('content', '')[:1000]}..."""
    
    card_type = "NASA每日科普" if is_science else f"NASA新闻 #{card_number-1}"
    content_focus = "科学解释" if is_science else "新闻报道"
    
    # Determine if we need to expand or shrink for each paragraph
    adjustment_parts = []
    for i, length in enumerate(paragraph_lengths):
        if length < 200:
            adjustment_parts.append(f"""【第{i+1}段如何增加字数（当前{length}字，需增加{200-length}字以上）】
- 在现有内容基础上扩展，不要删除已有内容
- 添加更多细节：具体时间、数据、背景信息
- 详细解释相关概念和科学原理
- 补充例子或对比说明""")
        elif length > 300:
            adjustment_parts.append(f"""【第{i+1}段如何减少字数（当前{length}字，需减少{length-300}字）】
- 精简表达，删除冗余词语
- 合并相似句子
- 保留核心信息，删除次要细节""")
    
    adjustment_guide = "\n\n".join(adjustment_parts) if adjustment_parts else "【字数调整指南】\n- 检查每段字数，确保在200-300字范围内"
    
    return f"""你是NASA中文科技媒体编辑，为中文读者撰写{content_focus}内容。

【任务】
为"{card_type}"栏目重新撰写中文内容。

日期：{date_str}

{article_block}

【上次生成的问题 - 必须修正】
{feedback}

{adjustment_guide}
{last_content_text}

【重写要求 - 必须严格遵守】
⚠️ 写2个段落，每段必须包含200-300个汉字（硬性要求）
⚠️ 写完后逐字统计，确保符合要求
⚠️ 重要：在上次生成的基础上修改，不要从头重写！保留好的内容，只调整字数。

1. 修改策略：
   - 如果某段字数太少：在现有内容基础上扩展，添加细节、数据、解释
   - 如果某段字数太多：精简表达，删除冗余词语，保留核心信息
   - 不要完全删除重写，而是在上次内容基础上调整

2. 内容结构保持不变：
   - 第1段：事件/发现介绍（200-300字）
   - 第2段：意义与影响（200-300字）

【输出格式】
只输出JSON：
{{"title": "中文标题", "paragraphs": ["第1段内容（200-300字）...", "第2段内容（200-300字）..."]}}
"""


def build_card_prompt(card_number: int, article: dict[str, Any], date_str: str) -> str:
    """Generate content for a single card - step 2/3/4."""
    is_science = card_number == 1
    
    article_block = f"""【文章】
标题：{article.get('title', '')}
来源：{article.get('channel', 'NASA')}
时间：{article.get('publish_time', '')}
摘要：{article.get('summary', '')}
内容：{article.get('content', '')[:800]}..."""
    
    if is_science:
        return f"""你是一个NASA爱好者，为中文读者撰写科学解释。
为"NASA每日科普"栏目撰写内容。

日期：{date_str}
素材：
{article_block}

要求：
1) 只输出HTML内容，不要JSON，不要任何额外文字。
2) 以图片开头：<img src="{article.get('cover_url', '') or article.get('image_url', '')}" style="width:100%;display:block;">
3) 然后写2-3段文字：
   - 第一段：解释读者看到的是什么（图片/主题）
   - 第二段：解释这在科学上为什么重要
4) 使用自然、直接的语言，避免模板化表达。
5) HTML标签后不要有前导空格。
6) 全宽布局：使用 margin:0;padding:0。
7) 文字样式（浅色主题）：font-size:0.95em; line-height:1.7em; color:#333333。
8) 所有文字必须是简体中文。

输出格式：纯HTML字符串。"""
    else:
        return f"""你是一个NASA爱好者，为中文读者撰写新闻报道。
为新闻卡片 #{card_number-1} 撰写内容。

日期：{date_str}
素材：
{article_block}

要求：
1) 只输出HTML内容，不要JSON，不要任何额外文字。
2) 以图片开头：<img src="{article.get('cover_url', '') or article.get('image_url', '')}" style="width:100%;display:block;">
3) 然后写2-3段文字：
   - 第一段：发生了什么（新闻事件）
   - 第二段：这一进展为什么重要
4) 使用自然、直接的语言，避免"值得持续关注"等模板化表达。
5) HTML标签后不要有前导空格。
6) 全宽布局：使用 margin:0;padding:0。
7) 文字样式（浅色主题）：font-size:0.95em; line-height:1.7em; color:#333333。
8) 所有文字必须是简体中文。

输出格式：纯HTML字符串。"""


def _story_candidate_tokens(text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"\b[A-Z]{2,}(?:-[0-9]+)?\b", text))
    candidates.extend(re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,}){0,2}\b", text))
    candidates.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", text))
    return candidates


def build_story_terms(articles: list[dict[str, Any]]) -> list[str]:
    text = " ".join(normalize_whitespace(f"{article.get('title_en', '')} {article.get('title', '')} {article.get('summary', '')} {article.get('content', '')}") for article in articles)
    text_lower = text.lower()
    terms: list[str] = []

    for term in ["Artemis II", "Artemis", "CLPS", "Intuitive Machines", "ISS", "Kennedy", "Roman", "Webb", "Hubble", "NISAR", "Moon", "Lunar", "SpaceX"]:
        if term.lower() in text_lower:
            terms.append(term.lower())

    for token in _story_candidate_tokens(text):
        clean = normalize_whitespace(token).strip()
        key = clean.lower()
        if len(clean) < 2 or key in _GENERIC_STORY_TOKENS or clean in {"任务更新", "相关进展", "最新进展", "最新节点", "发射阶段", "关键节点"}:
            continue
        terms.append(key)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean_term = normalize_whitespace(term).strip().lower()
        if len(clean_term) >= 2 and clean_term not in seen:
            seen.add(clean_term)
            deduped.append(clean_term)
    return deduped[:14]
