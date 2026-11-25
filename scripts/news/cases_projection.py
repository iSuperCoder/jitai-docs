"""把已发布资讯快照投影到官方案例页的静态降级区和结构化数据。

主站拥有整页与 React 交互，同步器仅更新两个明确标记的内容槽。主站重发和资讯切换
共用本模块且必须持官网 release.lock；只依赖标准库，不抓内容源、不构建前端。
"""

from contextlib import contextmanager
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile


def prepare_case_pages(site: Path, news: Path, origin: str) -> list[tuple[Path, bytes, bytes]]:
    """读取双语页面和指定资讯版本，返回待替换的路径、原字节、新字节，不写文件。

    旧版页面没有槽时保持原样；只有一个槽、重复槽或非法快照说明部署不完整，抛 ValueError。
    site 可以是主站上传区，news 可以是资讯候选版本；所有依赖在发布切换前验证。
    """
    slots = {'static': re.compile(r'(<noscript\b[^>]*\bid="case-static"[^>]*>)(.*?)(</noscript>)', re.S),
             'schema': re.compile(r'(<script\b[^>]*\bid="case-list-schema"[^>]*>)(.*?)(</script>)', re.S)}
    pages = []
    for locale, name in (('en', 'cases.html'), ('zh', 'zh/cases.html')):
        path = site / name
        if not path.is_file(): continue
        if path.is_symlink() or not path.resolve().is_relative_to(site.resolve()):
            raise ValueError('案例投影目标必须是主站内的普通页面')
        original = path.read_bytes()
        html = original.decode('utf-8')
        counts = [len(pattern.findall(html)) for pattern in slots.values()]
        if counts == [0, 0]: continue
        if counts != [1, 1]: raise ValueError('案例页面静态投影槽不完整或重复')
        pages.append((locale, path, original, html))
    if not pages: return []
    match = re.search(r'<script\b[^>]*\bid="feed-snapshot"[^>]*>(.*?)</script>', (news / 'index.html').read_text(), re.S)
    if not match: raise ValueError('案例投影需要完整已发布资讯快照')
    data = json.loads(match.group(1))
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('案例投影快照不是文章列表')
    # 与官网交互层沿用同一栏目契约：任意标签文字含“案例”即纳入，不按题材或 ID 排除。
    items = [item for item in data['items'] if isinstance(item.get('tags'), list)
             and any(isinstance(tag, str) and '案例' in tag for tag in item['tags'])]
    result = []
    for locale, path, original, html in pages:
        title = '案例方案' if locale == 'zh' else 'Cases & Solutions'
        url = origin.rstrip('/') + ('/zh/cases' if locale == 'zh' else '/cases')
        rows = []
        for index, item in enumerate(items):
            image = (f'<img src="{escape(item["image"], quote=True)}" alt="{escape(item.get("image_alt") or "", quote=True)}" loading="lazy">'
                     if item.get('image') else '')
            stamp = item.get('date_published') or ''
            date = f'<time datetime="{escape(stamp, quote=True)}">{escape(stamp[:10])}</time>' if stamp else ''
            rows.append(f'<article class="case-row"><span class="case-index">{index + 1:02}</span>'
                        f'<div class="case-visual">{image}<span aria-hidden="true">JitAI / CASE</span></div>'
                        f'<div class="case-row-content"><h3><a href="{escape(item["url"], quote=True)}">{escape(item["title"])}</a></h3>'
                        f'<p>{escape(item.get("summary") or "")}</p></div>{date}<span class="case-row-arrow" aria-hidden="true">↗</span></article>')
        label = '全部案例' if locale == 'zh' else 'All cases'
        empty = '新的实践，陆续呈现' if locale == 'zh' else 'More stories to come'
        content = (f'<style>.case-library[aria-busy="true"]{{display:none}}</style><section class="case-library wrap">'
                   f'<h2 class="case-section-heading">{label}</h2><div class="case-list">'
                   + (''.join(rows) if rows else f'<p>{empty}</p>') + '</div></section>')
        schema = {'@context': 'https://schema.org', '@type': 'CollectionPage', '@id': url,
                  'url': url, 'name': title, 'inLanguage': 'zh-CN' if locale == 'zh' else 'en',
                  'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(items), 'itemListElement':
                      [{'@type': 'ListItem', 'position': i + 1, 'name': item['title'], 'url': item['url']}
                       for i, item in enumerate(items)]}}
        for key, value in (('static', content), ('schema', json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c'))):
            # 回调替换不把文章里的反斜线解释为正则替换指令，特殊标题只能作为文字出现。
            html = slots[key].sub(lambda m: m.group(1) + value + m.group(3), html)
        body = html.encode('utf-8')
        if body != original: result.append((path, original, body))
    return result


def write_page(path: Path, body: bytes) -> None:
    """在同一目录原子替换一个公开 HTML，保留权限；失败清理临时文件并上抛。"""
    descriptor, name = tempfile.mkstemp(prefix='.case-next-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextmanager
def case_page_transaction(changes: list[tuple[Path, bytes, bytes]]):
    """持外部发布锁应用已准备的投影；调用方提交失败时恢复已改页面，成功退出才保留。

    CDN 请求必须位于上下文外：缓存刷新失败应保留已发布页面和重试队列，不能回滚内容。
    不获取第二把锁，不吞掉写盘／回滚错误；进程断电恢复仍依赖发布器下一轮重放。
    """
    written = []
    try:
        for path, before, after in changes:
            write_page(path, after)
            written.append((path, before))
        yield
    except BaseException:
        for path, before in reversed(written): write_page(path, before)
        raise
