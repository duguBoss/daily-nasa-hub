"""HTML Template for NASA Daily News.

Templates preserve the full styling from template.html.
Content and images are parameterized for dynamic filling.
"""

from __future__ import annotations

from html import escape
from typing import List, Tuple, Optional


def _minify_html(html: str) -> str:
    """Minify HTML to single line, preserving spaces inside tags."""
    lines = html.strip().split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            result.append(stripped)
    return ''.join(result)


# Main page template
PAGE_TEMPLATE = _minify_html('''
<section style="max-width: 100%; margin: 0 auto; box-sizing: border-box; padding: 0 1px; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei UI', 'Microsoft YaHei', Arial, sans-serif; background-color: #ffffff; overflow: hidden; font-size: 15px; color: #333;">
    {header}
    {apod_section}
    {divider}
    {news_section}
    {footer}
</section>
''')


# Header with banner
HEADER_TEMPLATE = _minify_html('''
<section style="width: 100%; margin-bottom: 30px;">
    <img src="{banner_url}" style="width: 100%; display: block; margin: 0; padding: 0;" alt="顶部引导关注GIF" />
</section>
''')


# APOD section template
APOD_TEMPLATE = _minify_html('''
<section style="margin-bottom: 40px; background-color: #fcfcfd; box-shadow: 0 4px 15px rgba(11,61,145,0.06);">
    <section style="background-color: #0B3D91; padding: 16px; display: flex; justify-content: space-between; align-items: flex-end;">
        <section>
            <section style="color: #FC3D21; font-size: 11px; font-weight: bold; font-family: Arial, sans-serif; letter-spacing: 2px; margin-bottom: 4px;">
                ASTRONOMY PICTURE OF THE DAY
            </section>
            <section style="color: #ffffff; font-size: 18px; font-weight: bold; letter-spacing: 1px;">
                NASA 每日天文图
            </section>
        </section>
        <section style="color: #94a3b8; font-size: 11px; font-family: Arial, sans-serif; text-align: right;">
            <span style="display: block; border-bottom: 1px solid #475569; padding-bottom: 3px; margin-bottom: 3px; letter-spacing: 1px;">VOL. {vol}</span>
            <span style="letter-spacing: 1px;">ISSUE</span>
        </section>
    </section>
    {image_section}
    <section style="background-color: #000000; color: #a1a1aa; padding: 8px 16px; font-size: 11px; font-family: Consolas, 'Courier New', monospace; display: flex; justify-content: space-between; letter-spacing: 0.5px;">
        <span><span style="color:#FC3D21;">OPTICS:</span> {optics}</span>
        <span><span style="color:#FC3D21;">OBJ:</span> {obj}</span>
    </section>
    <section style="padding: 25px 16px 20px 16px;">
        <section style="text-align: center; margin-bottom: 25px;">
            <section style="display: inline-block; font-size: 19px; font-weight: bold; color: #0B3D91; border-bottom: 2px solid #FC3D21; padding-bottom: 5px; letter-spacing: 1px;">
                {title_cn}
            </section>
            <section style="font-size: 12px; color: #94a3b8; margin-top: 8px; text-transform: uppercase; letter-spacing: 1.5px; font-family: Arial, sans-serif;">
                {title_en}
            </section>
        </section>
        <section style="display: flex; align-items: center; margin-bottom: 15px;">
            <span style="background-color: #0B3D91; width: 4px; height: 14px; display: inline-block; margin-right: 8px;"></span>
            <span style="font-size: 13px; font-weight: bold; color: #0B3D91; letter-spacing: 1px;">影像解析 EXPLANATION</span>
        </section>
        <section style="font-size: 15px; color: #475569; line-height: 1.8; text-align: justify; word-wrap: break-word;">
            {content}
        </section>
    </section>
</section>
''')


# Divider between sections
DIVIDER_TEMPLATE = '<section style="width: 85%; height: 1px; border-top: 1px dashed #cbd5e1; margin: 0 auto 35px auto;"></section>'


# News section wrapper
NEWS_WRAPPER_TEMPLATE = _minify_html('''
<section style="margin-bottom: 30px;">
    <section style="text-align: center; margin-bottom: 30px;">
        <section style="display: inline-block; padding: 4px 15px; border: 1px solid #0B3D91; color: #0B3D91; font-size: 18px; font-weight: bold; letter-spacing: 2px;">
            NASA 航天新闻快报
        </section>
        <section style="font-size: 12px; color: #94a3b8; margin-top: 4px; letter-spacing: 1px; text-transform: uppercase;">
            Mission Updates & Discoveries
        </section>
    </section>
    {news_items}
</section>
''')


# Single news item template - first item (margin-bottom: 35px)
NEWS_ITEM_FIRST_TEMPLATE = _minify_html('''
<section style="margin-bottom: 35px;">
    <section style="background: linear-gradient(90deg, #f0f4f9 0%, #ffffff 100%); border-left: 4px solid #FC3D21; padding: 12px 16px; margin-bottom: 0;">
        <section style="color: #FC3D21; font-size: 14px; font-family: Arial, sans-serif; font-weight: 900; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">
            <span>NEWS / {index}</span>
            <span style="font-size: 11px; background-color: #e2e8f0; color: #475569; padding: 2px 6px; border-radius: 2px; font-weight: normal;">{tag}</span>
        </section>
        <section style="color: #0B3D91; font-size: 17px; font-weight: bold; line-height: 1.5;">
            {title}
        </section>
    </section>
    {image_section}
    <section style="padding: 20px 16px 10px 16px; line-height: 1.8; text-align: justify; word-wrap: break-word;">
        {paragraphs}
    </section>
</section>
''')


# Single news item template - subsequent items (margin-bottom: 20px)
NEWS_ITEM_TEMPLATE = _minify_html('''
<section style="margin-bottom: 20px;">
    <section style="background: linear-gradient(90deg, #f0f4f9 0%, #ffffff 100%); border-left: 4px solid #FC3D21; padding: 12px 16px; margin-bottom: 0;">
        <section style="color: #FC3D21; font-size: 14px; font-family: Arial, sans-serif; font-weight: 900; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;">
            <span>NEWS / {index}</span>
            <span style="font-size: 11px; background-color: #e2e8f0; color: #475569; padding: 2px 6px; border-radius: 2px; font-weight: normal;">{tag}</span>
        </section>
        <section style="color: #0B3D91; font-size: 17px; font-weight: bold; line-height: 1.5;">
            {title}
        </section>
    </section>
    {image_section}
    <section style="padding: 20px 16px 10px 16px; line-height: 1.8; text-align: justify; word-wrap: break-word;">
        {paragraphs}
    </section>
</section>
''')


# Footer template
FOOTER_TEMPLATE = _minify_html('''
<section style="text-align: center; padding: 30px 0 20px 0; background-color: #f8fafc; border-top: 2px solid #0B3D91;">
    <section style="color: #0B3D91; font-size: 14px; font-family: Arial, sans-serif; font-weight: 900; letter-spacing: 2px; margin-bottom: 5px;">
        EXPLORE THE UNIVERSE
    </section>
    <section style="color: #94a3b8; font-size: 12px; letter-spacing: 1px;">
        {subtitle}
    </section>
</section>
''')


# Paragraph with first-letter drop cap (for APOD)
DROP_CAP_PARAGRAPH_TEMPLATE = '<p style="margin: 0 0 15px 0;"><span style="float: left; font-size: 38px; font-weight: bold; color: #0B3D91; line-height: 1; margin: 4px 8px 0 0; font-family: Georgia, serif;">{first_char}</span>{rest_text}</p>'

# Regular paragraph with color #475569 (for news content)
PARAGRAPH_TEMPLATE = '<p style="margin: 0 0 15px 0; color: #475569;">{text}</p>'

# Last paragraph (no bottom margin) with color #475569
PARAGRAPH_LAST_TEMPLATE = '<p style="margin: 0; color: #475569;">{text}</p>'

# Highlighted text (blue)
HIGHLIGHT_BLUE_TEMPLATE = '<span style="color: #0B3D91; font-weight: bold;">{text}</span>'

# Highlighted text (red)
HIGHLIGHT_RED_TEMPLATE = '<span style="color: #FC3D21; font-weight: bold;">{text}</span>'


def render_paragraph(text: str, is_first: bool = False, is_last: bool = False) -> str:
    """Render a paragraph. First paragraph gets drop cap styling.
    
    Args:
        text: Paragraph text
        is_first: Whether this is the first paragraph (gets drop cap)
        is_last: Whether this is the last paragraph (no bottom margin)
    """
    if is_first and text:
        first_char = text[0]
        rest_text = escape(text[1:])
        return DROP_CAP_PARAGRAPH_TEMPLATE.format(first_char=escape(first_char), rest_text=rest_text)
    
    if is_last:
        return PARAGRAPH_LAST_TEMPLATE.format(text=escape(text))
    
    return PARAGRAPH_TEMPLATE.format(text=escape(text))


def render_highlighted_paragraph(text: str, highlights: Optional[List[Tuple[str, str]]] = None, is_last: bool = False) -> str:
    """Render paragraph with highlighted keywords.
    
    Args:
        text: Paragraph text
        highlights: list of (keyword, color) tuples, color can be 'blue' or 'red'
        is_last: Whether this is the last paragraph (no bottom margin)
    """
    if not highlights:
        if is_last:
            return PARAGRAPH_LAST_TEMPLATE.format(text=escape(text))
        return PARAGRAPH_TEMPLATE.format(text=escape(text))
    
    # Apply highlights
    result = escape(text)
    for keyword, color in highlights:
        escaped_keyword = escape(keyword)
        if color == 'red':
            replacement = HIGHLIGHT_RED_TEMPLATE.format(text=escaped_keyword)
        else:
            replacement = HIGHLIGHT_BLUE_TEMPLATE.format(text=escaped_keyword)
        result = result.replace(escaped_keyword, replacement)
    
    if is_last:
        return PARAGRAPH_LAST_TEMPLATE.format(text=result)
    
    return PARAGRAPH_TEMPLATE.format(text=result)


def render_apod_content(paragraphs: List[str], highlights: Optional[List[List[Tuple[str, str]]]] = None) -> str:
    """Render APOD content section with paragraphs.
    
    paragraphs: list of paragraph texts
    highlights: list of highlight groups for each paragraph (optional)
    """
    if not paragraphs:
        return ''
    
    result = []
    for i, para in enumerate(paragraphs):
        if i == 0:
            # First paragraph with drop cap
            result.append(render_paragraph(para, is_first=True))
        else:
            # Other paragraphs with optional highlights
            is_last = (i == len(paragraphs) - 1)
            para_highlights = highlights[i] if highlights and i < len(highlights) else None
            if para_highlights:
                result.append(render_highlighted_paragraph(para, para_highlights, is_last=is_last))
            else:
                result.append(render_paragraph(para, is_last=is_last))
    
    return ''.join(result)


def render_news_content(paragraphs: List[str], highlights: Optional[List[List[Tuple[str, str]]]] = None) -> str:
    """Render news content section with paragraphs."""
    if not paragraphs:
        return ''
    
    result = []
    for i, para in enumerate(paragraphs):
        is_last = (i == len(paragraphs) - 1)
        para_highlights = highlights[i] if highlights and i < len(highlights) else None
        if para_highlights:
            result.append(render_highlighted_paragraph(para, para_highlights, is_last=is_last))
        else:
            result.append(render_paragraph(para, is_last=is_last))
    
    return ''.join(result)


def render_news_item(
    index: int,
    title: str,
    tag: str,
    image_url: str,
    image_alt: str,
    paragraphs: List[str],
    highlights: Optional[List[List[Tuple[str, str]]]] = None,
    is_first: bool = True,
) -> str:
    """Render a single news item.
    
    Args:
        index: News index number
        title: News title
        tag: News tag/category
        image_url: Image URL (if empty, no image section will be rendered)
        image_alt: Image alt text
        paragraphs: List of paragraph texts
        highlights: Optional highlights for each paragraph
        is_first: Whether this is the first news item (affects margin-bottom)
    """
    content = render_news_content(paragraphs, highlights)
    
    # Build image section only if image_url is provided and not empty
    if image_url and image_url.strip():
        image_section = f'<section style="width: 100%; margin: 0;"><img src="{escape(image_url)}" style="width: 100%; display: block; margin: 0;" alt="{escape(image_alt)}" /></section>'
    else:
        image_section = ''
    
    template = NEWS_ITEM_FIRST_TEMPLATE if is_first else NEWS_ITEM_TEMPLATE
    
    return template.format(
        index=index,
        title=escape(title),
        tag=escape(tag),
        image_section=image_section,
        paragraphs=content,
    )


def render_apod_section(
    vol: str,
    image_url: str,
    image_alt: str,
    optics: str,
    obj: str,
    title_cn: str,
    title_en: str,
    paragraphs: List[str],
    highlights: Optional[List[List[Tuple[str, str]]]] = None,
) -> str:
    """Render APOD section.
    
    Args:
        image_url: Image URL (if empty, no image section will be rendered)
    """
    content = render_apod_content(paragraphs, highlights)
    
    # Build image section only if image_url is provided and not empty
    if image_url and image_url.strip():
        image_section = f'<section style="width: 100%; margin: 0; line-height: 0;"><img src="{escape(image_url)}" style="width: 100%; display: block; margin: 0;" alt="{escape(image_alt)}" /></section>'
    else:
        image_section = ''
    
    return APOD_TEMPLATE.format(
        vol=escape(vol),
        image_section=image_section,
        optics=escape(optics),
        obj=escape(obj),
        title_cn=escape(title_cn),
        title_en=escape(title_en),
        content=content,
    )


def render_news_section(news_items_html: str) -> str:
    """Render news section wrapper."""
    return NEWS_WRAPPER_TEMPLATE.format(news_items=news_items_html)


def render_header(banner_url: str) -> str:
    """Render header with banner."""
    return HEADER_TEMPLATE.format(banner_url=escape(banner_url))


def render_footer(subtitle: str = "National Aeronautics and Space Administration") -> str:
    """Render footer."""
    return FOOTER_TEMPLATE.format(subtitle=escape(subtitle))


def render_full_html(
    banner_url: str,
    apod_html: str,
    news_html: str,
    show_divider: bool = True,
    footer_subtitle: str = "National Aeronautics and Space Administration",
) -> str:
    """Render complete HTML page."""
    header = render_header(banner_url)
    divider = DIVIDER_TEMPLATE if show_divider else ''
    footer = render_footer(footer_subtitle)

    return PAGE_TEMPLATE.format(
        header=header,
        apod_section=apod_html,
        divider=divider,
        news_section=news_html,
        footer=footer,
    )
