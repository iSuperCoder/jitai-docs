#!/usr/bin/env python3
"""官网资讯轻量同步入口；只处理独立资讯目录，不运行 Docusaurus、不修改主站。

check 下载并比较来源，build 生成本地候选版本，publish 显式发布已生成的候选版本。
来源只需配置 NEWS_FEED_URL，文章及资源地址由内容引用解析；官网域名和目录提供默认值，
可用环境变量覆盖。公开 Feed/HTML 获取无需密钥，发布仍须显式启用。
下载逐资源执行并限制体积；HTML/CSS 保留原内容，仅调整地址、搜索元信息与资源引用。
缓存、候选版本和发布状态归 NEWS_WORK_DIR 所有；远程定时器负责调用，脚本不安装定时任务。
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent


class SyncError(RuntimeError):
    """同步契约不满足时中止当前操作；调用方记录错误并保留现有线上版本。"""


class CacheError(SyncError):
    """本地缓存损坏且无法恢复；属于运维故障，不能被来源不可用兜底吞掉。"""


def digest(value: bytes) -> str:
    """返回内容 SHA-256，用于资源名和版本比较；不依据修改时间推断内容未变化。"""
    return hashlib.sha256(value).hexdigest()


def encoded(value) -> bytes:
    """生成稳定 JSON 字节，键排序且无无关空白；列表排序由业务调用方决定。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def atomic_json(path: Path, value) -> None:
    """同目录以 0600 临时文件原子替换内部状态；缓存/候选目录限定 0700，不受 umask 影响。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.name in ('cache', 'candidates'): path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle: handle.write(encoded(value))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def load_json(path: Path, default=None):
    """读取脚本拥有的状态；缺失返回默认值，损坏则中止，避免丢失发布/删除记录。"""
    return json.loads(path.read_text()) if path.exists() else default


def origin(url: str) -> str:
    """获取无凭证的 HTTP(S) origin；拒绝用户名密码、非法协议及缺少主机的 URL。"""
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise SyncError('地址必须是无内嵌凭证的 HTTP(S) URL')
    # 正式网络只允许 HTTPS；HTTP 仅供本地隔离测试服务，不支持任意内网源。
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise SyncError('正式来源必须使用 HTTPS')
    return f'{parsed.scheme}://{parsed.netloc}'


def clean_url(url: str) -> str:
    """校验 URL 并去掉片段；查询参数保留，以支持 /preview?file=... 资源地址。"""
    origin(url)
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))


class Config:
    """本次运行的不可变部署边界；不包含可输出的云密钥，凭证仅在 CDN 请求时读取。"""

    def __init__(self, env):
        """只需配置 Feed；文章来源及资源 origin 由内容引用决定，官网与工作目录提供部署默认值。

        未配置 Feed 时入口直接跳过；非空地址校验延后至抓取阶段，失败可生成首次空状态。站点/路径误配置仍
        明确失败，不能把运行数据写到错误位置。NEWS_SITE_ORIGIN 保留为测试/迁移的可选覆盖。
        """
        self.feed_url = env.get('NEWS_FEED_URL', '').strip()
        self.site = origin(env.get('NEWS_SITE_ORIGIN') or 'https://jit.pro')
        self.public = env.get('NEWS_PUBLIC_PATH', '/zh/news/')
        if not re.fullmatch(r'/(?:[a-zA-Z0-9_-]+/)+', self.public):
            raise SyncError('NEWS_PUBLIC_PATH 必须是带首尾斜线的独立目录路径')
        self.work = Path(env.get('NEWS_WORK_DIR') or '/data/jitai-news-data').expanduser().resolve()
        # 开发时保护完整 Git 仓库；服务器可仅部署脚本目录，不能假定永远保留 scripts/news
        # 两级布局，否则把 /opt/jitai-news 的祖先 / 误当仓库会拒绝所有合法数据目录。
        repository = next((path for path in (HERE, *HERE.parents) if (path / '.git').exists()), HERE)
        if self.work.is_relative_to(repository) or repository.is_relative_to(self.work):
            raise SyncError('资讯数据工作目录必须位于源码仓库之外，且不能包含源码仓库')
        self.resource_limit = int(env.get('NEWS_MAX_RESOURCE_BYTES', '20971520'))
        self.total_limit = int(env.get('NEWS_MAX_TOTAL_BYTES', '268435456'))
        self.max_items = int(env.get('NEWS_MAX_ITEMS', '2000'))
        if min(self.resource_limit, self.total_limit, self.max_items) <= 0:
            raise SyncError('资源与数量限制必须是正整数')
        self.allow_empty = env.get('NEWS_ALLOW_EMPTY_FEED') == '1'


class SafeRedirect(HTTPRedirectHandler):
    """允许内容 App 引用的 CDN/新域名重定向，不要求重复配置域名；仍校验 URL 协议与凭证。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """下一跳沿用正式 HTTPS/本地测试 HTTP 契约，拒绝内嵌凭证与非法协议。"""
        origin(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def prepare_work_directory(config: Config):
    """初始化或修复脚本自有目录权限，不放开缓存内容，也不改变 /data 等宿主父目录。

    工作根 0711 允许 Nginx 穿过但不能列目录；私有目录 0700，根状态 JSON 0600。
    main 与直接 collect 共用此入口，确保已有版本的 bootstrap 也能修复历史 0700 工作根。
    """
    config.work.mkdir(parents=True, exist_ok=True)
    config.work.chmod(0o711)
    for name in ('cache', 'candidates'):
        directory = config.work / name
        directory.mkdir(exist_ok=True)
        directory.chmod(0o700)
    for name in ('active.json', 'pending-cdn.json'):
        path = config.work / name
        if path.is_file(): path.chmod(0o600)


class Fetcher:
    """逐资源下载及条件请求缓存；缓存是探测状态，不代表某版本已发布成功。"""

    def __init__(self, config: Config):
        """创建本次下载会话；缓存索引持久化在独立工作目录，内存仅持有资源描述。"""
        self.config = config
        prepare_work_directory(config)
        self.cache_dir = config.work / 'cache'
        try:
            self.cache = load_json(self.cache_dir / 'index.json', {})
        except ValueError as error:
            raise CacheError('本地缓存索引损坏，请检查磁盘并重新建立缓存') from error
        if not isinstance(self.cache, dict): raise CacheError('本地缓存索引类型不合法')
        self.records = {}
        self.total = 0
        self.opener = build_opener(SafeRedirect())

    def fetch(self, url: str, fresh=False) -> tuple[bytes, str]:
        """返回字节与 MIME；支持 ETag/Last-Modified，fresh 强制重新读取 Feed 验证快照一致。

        发送条件请求前校验缓存；损坏时完整重取，恢复失败抛 CacheError。
        304 只有缓存文件存在且哈希正确才可复用。超时、错误状态或资源超限均中止当前版本；
        不把抓取失败解释为文章删除，也不输出带查询参数的来源 URL 或响应体。
        """
        url = clean_url(url)
        if url in self.records and not fresh:
            info = self.records[url]
            return (self.cache_dir / info['hash']).read_bytes(), info['type']
        previous = self.cache.get(url, {})
        cached_path = self.cache_dir / previous.get('hash', 'missing')
        headers = {'User-Agent': 'JitAI-News-Sync/1.0', 'Accept-Encoding': 'identity'}
        # 校验必须发生在发送 ETag 前，否则服务器会持续返回 304，损坏字节永远无法被替换。
        if not fresh and cached_path.is_file() and digest(cached_path.read_bytes()) != previous.get('hash'):
            try:
                return self.fetch(url, fresh=True)
            except (SyncError, OSError, ValueError) as error:
                raise CacheError('缓存损坏且完整下载恢复失败，请检查来源和本地磁盘') from error
        if not fresh and cached_path.is_file():
            if previous.get('etag'): headers['If-None-Match'] = previous['etag']
            if previous.get('modified'): headers['If-Modified-Since'] = previous['modified']
        try:
            with self.opener.open(Request(url, headers=headers), timeout=30) as response:
                if response.status != 200: raise SyncError('来源响应不是完整 200 内容')
                body = response.read(self.config.resource_limit + 1)
                kind = response.headers.get_content_type()
                info = {'hash': digest(body), 'type': kind, 'etag': response.headers.get('ETag'), 'modified': response.headers.get('Last-Modified'), 'url': clean_url(response.geturl())}
        except HTTPError as error:
            if error.code != 304 or not cached_path.is_file():
                raise SyncError(f'资源抓取失败，HTTP {error.code}') from None
            body = cached_path.read_bytes()
            if digest(body) != previous['hash']: raise CacheError('缓存资源校验失败')
            info = previous
            kind = info['type']
        except (URLError, TimeoutError):
            raise SyncError('资源请求超时或网络异常，本次不生成新版本') from None
        if len(body) > self.config.resource_limit: raise SyncError('单资源大小超限')
        self.total += len(body)
        if self.total > self.config.total_limit: raise SyncError('单次同步累计资源大小超限')
        (self.cache_dir / info['hash']).write_bytes(body)
        self.cache[url] = info
        self.records[url] = info
        return body, kind

    def save(self):
        """保存可复用的下载索引；与成功发布的 active.json 完全分离。"""
        atomic_json(self.cache_dir / 'index.json', self.cache)


def validate_feed(body: bytes, config: Config) -> dict:
    """校验完整 Feed、数量及稳定 ID；只允许全量快照进行删除差异，不接受隐含分页。

    本版以 _item_count 与 _scope 作为来源完整清单声明；分页须先在内容端聚合。
    有效空清单仍需显式 NEWS_ALLOW_EMPTY_FEED=1，以免误配置导致全部下线。
    """
    try: data = json.loads(body)
    except (ValueError, UnicodeError): raise SyncError('Feed 不是有效 JSON') from None
    if not isinstance(data, dict) or data.get('version') != 'https://jsonfeed.org/version/1.1' or not isinstance(data.get('items'), list):
        raise SyncError('需要 JSON Feed 1.1 完整清单')
    items = data['items']
    if data.get('next_url') or data.get('_item_count') != len(items) or data.get('_scope') != '全部已发布内容':
        raise SyncError('无法确认 Feed 为完整已发布清单，禁止基于它同步删除')
    if len(items) > config.max_items or (not items and not config.allow_empty):
        raise SyncError('Feed 数量超限或空清单未获配置允许')
    ids, urls, paths = set(), set(), set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            raise SyncError('每篇文章必须提供非空字符串 id')
        if item['id'] in ids: raise SyncError('Feed 存在重复文章 ID')
        ids.add(item['id'])
        # Feed 是唯一来源配置，条目可指向内容 App 的不同域名，不从 Feed 域名拼文章地址。
        origin(item.get('url', ''))
        # 来源 URL 与生成路径也必须唯一；不同 ID 不能覆盖映射或落入同一个详情文件。
        source_url, destination = clean_url(item['url']), article_path(item)
        if source_url in urls: raise SyncError('Feed 存在重复文章 URL')
        if destination in paths: raise SyncError('Feed 存在冲突的官网详情路径')
        urls.add(source_url); paths.add(destination)
        if not isinstance(item.get('title'), str) or not item['title'].strip():
            raise SyncError('文章缺少有效标题')
        # 新版完整页面协议将列表所需元信息集中到 seo。标题正文仍取条目 title，
        # seo.title 只作为封面短标题；旧字段仅在新字段缺失/为空时兜底，兼容既有 Feed。
        seo = item.get('seo', {})
        if not isinstance(seo, dict): raise SyncError('seo 必须是对象')
        for key in ('title', 'description', 'author', 'language', 'publishedAt', 'updatedAt', 'image'):
            if key in seo and not isinstance(seo[key], str): raise SyncError('seo 文本字段类型不合法')
        for key in ('keywords', 'tags'):
            if key in seo and (not isinstance(seo[key], list) or not all(isinstance(value, str) for value in seo[key])):
                raise SyncError('seo 关键词/标签必须是字符串数组')
        for key, target in {'title': '_seo_title', 'description': 'summary', 'keywords': '_keywords',
                            'tags': 'tags', 'language': 'language', 'publishedAt': 'date_published',
                            'updatedAt': 'date_modified', 'wordCount': '_word_count', 'image': 'image'}.items():
            if seo.get(key): item[target] = seo[key]
        if seo.get('author'): item['authors'] = [{'name': seo['author']}]
    return data


def semantic_feed(feed: dict) -> dict:
    """提取影响资讯页的字段并按 ID 排序，忽略生成时刻和 Feed 排列噪声。"""
    fields = ('id', 'url', 'title', 'summary', 'content_text', 'image', 'image_alt', 'date_published', 'date_modified', 'language', 'tags', '_keywords', '_section', '_section_slug', '_seo_title', '_seo_keywords', '_word_count', '_reading_time_minutes', 'authors')
    return {'items': sorted(({key: item[key] for key in fields if key in item} for item in feed['items']), key=lambda item: item['id'])}


def article_path(item: dict) -> str:
    """以 Feed id（slug）生成官网路径，url 仅用于抓取应用原文，不参与官网路由命名。

    常规安全 ID 保持可读，否则使用完整哈希防止路径逃逸；标题及应用域名变化不改路由。
    """
    identity = item['id']
    slug = identity if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', identity) else 'id-' + digest(identity.encode())
    return f'articles/{slug}/index.html'


class Mirror:
    """将文章及依赖封装成独立静态目录；不对正文二次排版，不引入 iframe 或运行时代理。"""

    def __init__(self, config: Config, fetcher: Fetcher, output: Path, feed: dict):
        """维护本次来源到官网 URL 的映射及共享资源去重；状态仅存在于此次生成过程。"""
        self.config = config
        self.fetcher = fetcher
        self.output = output
        self.assets = {}
        self.visiting = set()
        self.pages = {clean_url(item['url']): config.site + config.public + article_path(item).removesuffix('index.html') for item in feed['items']}
        self.source_homes = {origin(item['url']) + '/' for item in feed['items']}
        if feed.get('home_page_url'): self.source_homes.add(feed['home_page_url'])

    def asset(self, reference: str, base: str) -> str:
        """下载并本地化资源，返回官网绝对路径；存储图片沿用 file 文件名，其余资源按内容哈希命名。

        相对资源按来源文件 URL 解析；data 和片段保留，其他非 HTTP 协议拒绝。
        CSS 递归下载依赖，循环引用中止；本版不打包 JS 模块，遇到模块须由内容站先打包。
        """
        if not reference or reference.startswith(('#', 'data:')): return reference
        url = clean_url(urljoin(base, reference))
        fragment = urlsplit(reference).fragment
        if url in self.assets: return self.assets[url] + ('#' + fragment if fragment else '')
        if url in self.visiting: raise SyncError('资源存在循环 CSS 依赖，无法确定独立发布包')
        self.visiting.add(url)
        body, kind = self.fetcher.fetch(url)
        # 同域重定向可能移动目录，CSS 相对依赖须相对最终响应地址，而不是旧请求地址。
        resource_base = self.fetcher.records[url].get('url', url)
        suffix = Path(urlsplit(url).path).suffix.lower()
        if kind == 'text/html': raise SyncError('资源地址返回 HTML，可能是登录页或错误页面')
        if kind == 'text/css' or suffix == '.css':
            body = self.css(body.decode('utf-8-sig'), resource_base).encode()
            suffix = '.css'
        elif suffix in ('.js', '.mjs') or 'javascript' in kind:
            # 当前来源仅有 JSON-LD。动态脚本携带 API/模块依赖时不假装已完成静态迁移。
            raise SyncError('来源包含可执行脚本；请提供无脚本或已审查的静态发布资源')
        elif kind == 'image/svg+xml' or suffix == '.svg':
            # SVG 本身可含脚本和外部依赖；只接受自包含静态图形，不默许漏镜像的网络依赖。
            try: svg_root = ET.fromstring(body)
            except ET.ParseError: raise SyncError('SVG 资源格式不合法') from None
            for element in svg_root.iter():
                if element.tag.split('}')[-1].lower() in ('script', 'foreignobject'):
                    raise SyncError('SVG 包含可执行或嵌入内容')
                for key, value in element.attrib.items():
                    if key.lower().startswith('on') or (key.split('}')[-1] == 'href' and not value.startswith(('#', 'data:'))):
                        raise SyncError('SVG 含脚本或外部引用，请内容站导出自包含图形')
            suffix = '.svg'
        elif not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix):
            suffix = mimetypes.guess_extension(kind) or '.bin'
        name = digest(body) + suffix
        # 内容 App 的正文图片使用 /api/whwy/<appId>/storages/...?...file=<hash>.<ext>。
        # 保留 file 文件名，不把 preview 当扩展名；拒绝路径穿越及同批不同资源重名，避免互相覆盖。
        if re.match(r'^/api/whwy/[^/]+/storages/', urlsplit(url).path):
            names = parse_qs(urlsplit(url).query).get('file', [])
            if len(names) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9]{1,8}', names[0]):
                raise SyncError('存储图片 file 参数必须是安全的单个文件名')
            if not kind.startswith('image/'): raise SyncError('存储图片响应类型不合法')
            name = names[0]
        destination = self.output / 'assets' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != body:
            raise SyncError('同批资源文件名冲突，禁止覆盖不同内容')
        destination.write_bytes(body)
        mapped = self.config.public + 'assets/' + name
        self.assets[url] = mapped
        self.visiting.remove(url)
        return mapped + ('#' + fragment if fragment else '')

    def css(self, text: str, base: str) -> str:
        """改写普通 CSS url() 和 @import 依赖；保留其余样式，拒绝无法安全解析的 URL 转义。

        采用受限静态内容契约：资源 URL 中禁止 CSS 反斜杠转义；带引号的数据 URL 可保留。
        非标准/复杂 CSS 资源表达式要求内容端预先打包，避免静默漏下载后线上缺图。
        """
        pattern = re.compile(r'/\*.*?\*/|url\(\s*(?:"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|([^)]*))\s*\)|@import\s+(["\'])(.*?)\4', re.I | re.S)
        def replace(match):
            """仅处理已识别的资源 token；注释原样返回，不把注释中的 url 当作依赖。"""
            if match.group(0).startswith('/*'): return match.group(0)
            value = next((match.group(index) for index in (1, 2, 3, 5) if match.group(index) is not None), '').strip()
            if '\\' in value: raise SyncError('CSS 资源 URL 使用了不支持的转义，请内容站预先打包')
            mapped = self.asset(value, base)
            return '@import "' + mapped + '"' if match.group(5) is not None else 'url("' + mapped + '")'
        return pattern.sub(replace, text)

    def html_page(self, item: dict) -> tuple[bytes, str]:
        """发布内容 App 的完整详情，仅调整 SEO、编码及搬运资源必需的 URL。

        不注入官网样式、导航、标签或正文布局；标题、结构、类名、样式值和链接功能由 App 决定。
        本版支持内容站现有的静态 HTML/CSS/图片/JSON-LD、媒体与内联样式；遇到 iframe、
        JS 模块、表单或事件处理器则中止，而不是生成外观相似但交互损坏的页面。
        """
        source = clean_url(item['url'])
        body, kind = self.fetcher.fetch(source)
        # 官网 canonical 仍由 id 决定；仅资源与正文相对链接随最终来源目录解析。
        resource_base = self.fetcher.records[source].get('url', source)
        if kind not in ('text/html', 'application/xhtml+xml'): raise SyncError('文章响应不是 HTML')
        soup = BeautifulSoup(body.decode('utf-8-sig'), 'html.parser')
        if not soup.html or not soup.head or not soup.body or not soup.select_one('article'):
            raise SyncError('来源缺少完整文章结构，不能把登录页或错误页发布到官网')
        canonical = self.pages[source]
        if soup.select('base, iframe, object, embed, form'):
            raise SyncError('来源包含不支持的运行时/嵌入元素，请提供可独立发布的静态 HTML')
        for node in soup.find_all(True):
            if any(key.lower().startswith('on') for key in node.attrs):
                raise SyncError('来源包含内联事件脚本，需要先明确静态发布契约')
            if node.name == 'script':
                if node.get('type', '').lower() != 'application/ld+json' or node.get('src'):
                    raise SyncError('来源包含可执行脚本，需要先明确静态发布契约')
                try: structured = json.loads(node.string or '')
                except ValueError: raise SyncError('文章 JSON-LD 无效') from None
                def rewrite(value):
                    """递归改写 JSON-LD 中 URL 字符串，保留正文、作者和来源发布时间等业务内容。"""
                    if isinstance(value, dict): return {key: rewrite(child) for key, child in value.items()}
                    if isinstance(value, list): return [rewrite(child) for child in value]
                    if isinstance(value, str):
                        for page_source in (source, resource_base):
                            if value == page_source or value.startswith(page_source + '#'): return canonical + value[len(page_source):]
                        if value in self.source_homes: return self.config.site + '/'
                    return value
                structured = rewrite(structured)
                # 当前内容站部分文章把 mainEntityOfPage 写成旧官网 /zh/blog 地址，
                # 与抓取 URL 不同，单纯替换源域名会漏掉。只规范顶层或 @graph 中的主体文章，
                # 不递归覆盖 citation/publisher 等第三方实体；标题、摘要、关键词和日期保留。
                entities = structured if isinstance(structured, list) else [structured]
                for entity in list(entities):
                    if isinstance(entity, dict) and isinstance(entity.get('@graph'), list):
                        entities = [*entities, *entity['@graph']]
                for entity in entities:
                    if not isinstance(entity, dict): continue
                    types = entity.get('@type', [])
                    types = [types] if isinstance(types, str) else types
                    if not isinstance(types, list) or not set(types) & {'Article', 'NewsArticle', 'BlogPosting', 'TechArticle'}:
                        continue
                    main_page = entity.get('mainEntityOfPage')
                    if isinstance(main_page, dict):
                        main_page['@id'] = canonical
                        if 'url' in main_page: main_page['url'] = canonical
                    else:
                        entity['mainEntityOfPage'] = canonical
                    if '@id' in entity:
                        fragment = urlsplit(str(entity['@id'])).fragment
                        entity['@id'] = canonical + ('#' + fragment if fragment else '')
                    if 'url' in entity: entity['url'] = canonical
                    # 只镜像主体文章的图片属性，不碰 publisher/citation 等第三方实体。
                    # image 支持 URL、数组、ImageObject；URL 与 contentUrl 可各自指向实际图片。
                    def mirror_image(value):
                        """将文章 image 的媒体地址转为官网绝对 URL；保留描述字段及片段实体引用。"""
                        if isinstance(value, str):
                            mapped = self.asset(value, resource_base)
                            return self.config.site + mapped if mapped.startswith('/') else mapped
                        if isinstance(value, list): return [mirror_image(child) for child in value]
                        if isinstance(value, dict):
                            return {key: mirror_image(child) if key in ('url', 'contentUrl', 'thumbnailUrl') else child
                                    for key, child in value.items()}
                        return value
                    if 'image' in entity: entity['image'] = mirror_image(entity['image'])
                node.string = json.dumps(structured, ensure_ascii=False).replace('<', chr(92) + 'u003c')
            if node.name == 'style': node.string = self.css(node.get_text(), resource_base)
            if node.get('style'): node['style'] = self.css(node['style'], resource_base)
            for attribute in ('src', 'poster'):
                if node.get(attribute): node[attribute] = self.asset(node[attribute], resource_base)
            if node.get('srcset'):
                # 浏览器 srcset 的 data URL 含逗号，此版明确拒绝而不是错误拆分。
                if 'data:' in node['srcset']: raise SyncError('srcset data URL 尚不支持，请使用独立图片资源')
                parts = []
                for candidate in node['srcset'].split(','):
                    value = candidate.strip().split()
                    if not value: continue
                    parts.append(' '.join([self.asset(value[0], resource_base), *value[1:]]))
                node['srcset'] = ', '.join(parts)
            if node.name == 'link' and node.get('href'):
                rel = set(node.get('rel', []))
                if rel & {'stylesheet', 'icon', 'preload', 'apple-touch-icon'}:
                    # 内容 App 的 <slug>.css 与整页放同目录，保留相对 href 和完整样式。
                    # CSS 若引用图片/字体，仅搬运并适配资源路径，不注入或修改布局规则。
                    if 'stylesheet' in rel and node['href'] == item['id'] + '.css' and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*\.css', node['href']):
                        css_url = clean_url(urljoin(resource_base, node['href']))
                        css_body, css_kind = self.fetcher.fetch(css_url)
                        if css_kind != 'text/css': raise SyncError('文章样式响应不是 CSS')
                        css_base = self.fetcher.records[css_url].get('url', css_url)
                        css_target = self.output / Path(article_path(item)).parent / node['href']
                        css_target.parent.mkdir(parents=True, exist_ok=True)
                        css_target.write_bytes(self.css(css_body.decode('utf-8-sig'), css_base).encode())
                    else:
                        node['href'] = self.asset(node['href'], resource_base)
                    node.attrs.pop('integrity', None)
                elif rel & {'alternate', 'canonical'}: node.decompose(); continue
            if node.name == 'meta':
                name = (node.get('name') or node.get('property') or '').lower()
                # 输出始终重新编码为 UTF-8，旧编码声明不能继续影响浏览器解码。
                if node.has_attr('charset') or node.get('http-equiv', '').lower() == 'content-type':
                    node.decompose(); continue
                if name in ('robots', 'googlebot', 'bingbot'): node.decompose(); continue
                if node.get('http-equiv', '').lower() == 'refresh': raise SyncError('文章不能是跳转页')
                if name in ('og:url', 'twitter:url'): node['content'] = canonical
                if name in ('og:image', 'twitter:image') and node.get('content'):
                    mapped = self.asset(node['content'], resource_base)
                    node['content'] = self.config.site + mapped if mapped.startswith('/') else mapped
            if node.name == 'a' and node.get('href') and not node['href'].startswith('#'):
                href = node['href']
                if urlsplit(href.strip()).scheme.lower() in ('javascript', 'data'): raise SyncError('文章链接含不可发布协议')
                target = urljoin(resource_base, href)
                if target.split('#')[0] in self.pages:
                    node['href'] = self.pages[target.split('#')[0]] + ('#' + target.split('#', 1)[1] if '#' in target else '')
                elif urlsplit(target).scheme in ('http', 'https'):
                    # 非迁移文章仍按 App 原本的目标导航，不能因其属于内容站就删除 href。
                    # 相对地址转为绝对地址只是保持搬迁前的指向，不决定 App 页面内容或交互。
                    node['href'] = target
                elif urlsplit(target).scheme not in ('mailto', 'tel'): raise SyncError('文章链接使用不支持协议')
        # 静态服务器未必附带 charset；声明放在 head 起始处，确保位于浏览器前 1024 字节探测范围。
        soup.head.insert(0, soup.new_tag('meta', charset='utf-8'))
        meta = soup.new_tag('meta', attrs={'name': 'robots', 'content': 'index,follow,max-image-preview:large'})
        soup.head.append(meta)
        soup.head.append(soup.new_tag('link', attrs={'rel': 'canonical', 'href': canonical}))
        return str(soup).encode(), canonical


def render_list(feed: dict, output: Path, config: Config, mirror: Mirror) -> list[dict]:
    """生成包含真实文章链接的静态资讯列表；JS 只增强筛选/视图/轮播，搜索引擎无需执行 JS。

    详情链接始终指向官网路径，源 URL 不下发到浏览器。正文 HTML 不进入列表脚本。
    """
    public_items = []
    for item in feed['items']:
        # 只下发列表消费字段，不将任意来源元数据和来源 URL 复制到浏览器。
        keys = ('id', 'title', 'summary', 'image', 'image_alt', 'date_published', 'date_modified', 'language', 'tags', '_keywords', '_section', '_section_slug', '_seo_title', '_seo_keywords', '_word_count', '_reading_time_minutes', 'authors')
        public_item = {key: item[key] for key in keys if key in item}
        # 当前来源的 content_text 是摘要；缺少可选 summary 时兼容标准 JSON Feed 的纯文本字段。
        public_item['summary'] = item.get('summary') or item.get('content_text') or ''
        public_item['url'] = mirror.pages[clean_url(item['url'])]
        public_item['_canonical_url'] = public_item['url']
        if item.get('image'): public_item['image'] = config.site + mirror.asset(item['image'], item['url'])
        public_items.append(public_item)
    public_items.sort(key=lambda item: item.get('date_published', ''), reverse=True)
    template = (HERE / 'templates' / 'index.html').read_text()
    soup = BeautifulSoup(template, 'html.parser')
    cards = soup.find(id='cards')
    for item in public_items:
        card = soup.new_tag('article', attrs={'class': 'card'})
        content = soup.new_tag('div', attrs={'class': 'card-body'})
        heading = soup.new_tag('h3')
        link = soup.new_tag('a', attrs={'href': item['url'], 'target': '_blank', 'rel': 'noopener noreferrer', 'class': 'article-link stretched'})
        link.string = item['title']; heading.append(link); content.append(heading)
        paragraph = soup.new_tag('p', attrs={'class': 'summary'}); paragraph.string = item.get('summary', ''); content.append(paragraph)
        card.append(content); cards.append(card)
    soup.find(id='feed-snapshot').string = encoded({'items': public_items}).decode().replace('<', chr(92) + 'u003c')
    soup.find(id='result-count').string = f'共 {len(public_items)} 篇文章'
    # 空状态由服务器输出完整 HTML，禁用 JS 时也能看到；搜索无结果是另一个独立状态。
    if not public_items:
        soup.find(id='empty-library').attrs.pop('hidden', None)
        for node in soup.select('.library-tools, .filter-row, .results-line, #end-note'):
            node['hidden'] = ''
    soup.head.append(soup.new_tag('link', attrs={'rel': 'canonical', 'href': config.site + config.public}))
    soup.head.append(soup.new_tag('meta', attrs={'name': 'robots', 'content': 'index,follow,max-image-preview:large'}))
    soup.head.append(soup.new_tag('meta', attrs={'name': 'description', 'content': 'JitAI 资讯中心：案例文章、新闻动态与 AI 业务实践洞察。'}))
    for node in soup.find_all('a', href=True):
        if node['href'].startswith('https://jit.pro'): node['href'] = config.site + node['href'][len('https://jit.pro'):]
    for name in ('interactions.js', 'refinements.css', 'logo.svg', 'logo-dark.svg'):
        body = (HERE / 'templates' / name).read_bytes()
        hashed = digest(body) + Path(name).suffix
        (output / 'ui').mkdir(exist_ok=True)
        (output / 'ui' / hashed).write_bytes(body)
        for node in soup.find_all(True):
            for attribute in ('src', 'href'):
                if node.get(attribute) == name: node[attribute] = config.public + 'ui/' + hashed
        if name == 'logo.svg': soup.html['data-logo-light'] = config.public + 'ui/' + hashed
        if name == 'logo-dark.svg': soup.html['data-logo-dark'] = config.public + 'ui/' + hashed
    (output / 'index.html').write_text(str(soup))
    return public_items


def collect(config: Config, check_only=False, empty=False) -> dict:
    """抓取完整快照及资源，按真实内容和模板摘要判断变化；build 只生成候选，不发布。

    检查会重新验证所有 HTML/CSS/图片，即使 Feed 不变也能发现原 URL 被覆盖的资源。
    两次完整 Feed 校验用于避免生成过程混入不同文章集合；来源若无事务版本，不能保证
    所有资源是同一瞬时快照，但下次检查仍会检测后续资源变化。
    empty 仅供首次来源不可用时生成空候选；不发送网络请求，调用方必须保证尚无已发布版本。
    """
    fetcher = Fetcher(config)
    feed = {'items': []} if empty else validate_feed(fetcher.fetch(config.feed_url, fresh=True)[0], config)
    config.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=config.work) as directory:
        output = Path(directory)
        mirror = Mirror(config, fetcher, output, feed)
        urls = []
        for item in feed['items']:
            body, url = mirror.html_page(item)
            target = output / article_path(item)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            urls.append(url)
            if item.get('image'): mirror.asset(item['image'], item['url'])
        second = feed if empty else validate_feed(fetcher.fetch(config.feed_url, fresh=True)[0], config)
        if semantic_feed(feed) != semantic_feed(second): raise SyncError('同步期间 Feed 改变，保留旧版本并等待下一次任务')
        source_hashes = {url: info['hash'] for url, info in fetcher.records.items() if url != config.feed_url}
        template_hashes = {path.name: digest(path.read_bytes()) for path in (HERE / 'templates').iterdir() if path.is_file()}
        active = load_json(config.work / 'active.json', {})
        # 快照会继承已发布的内容哈希资源，指纹也必须包含这组文件。否则 A→B→A 会复用
        # 首次 A 的目录而丢失 B 的资源，缓存中的 B 页面随即缺图；相同资源集合不会反复触发发布。
        retained = {name: value for name, value in active.get('files', {}).items() if name.startswith(('assets/', 'ui/'))}
        retained.update({str(path.relative_to(output)): digest(path.read_bytes()) for path in (output / 'assets').glob('*') if path.is_file()})
        retained.update({'ui/' + template_hashes[name] + Path(name).suffix: template_hashes[name]
                         for name in ('interactions.js', 'refinements.css', 'logo.svg', 'logo-dark.svg')})
        version = digest(encoded({'feed': semantic_feed(feed), 'resources': source_hashes, 'templates': template_hashes, 'retained': retained, 'engine': digest(Path(__file__).read_bytes()), 'site': config.site, 'public': config.public}))
        fetcher.save()
        changed = active.get('version') != version
        deleted = sorted(set(active.get('urls', [])) - set(urls))
        report = {'version': version, 'changed': changed, 'count': len(urls), 'removed_count': len(deleted), 'urls': sorted(urls), 'deleted_urls': deleted, 'site': config.site, 'public': config.public, 'base_version': active.get('version')}
        if check_only or not changed: return report
        release = config.work / 'releases' / version
        if release.exists():
            # 复用候选只能沿用先前的可信校验记录，不能对可能已损坏的文件重新签发哈希清单。
            existing = load_json(config.work / 'candidates' / (version + '.json'), {})
            actual = {str(path.relative_to(release)): digest(path.read_bytes()) for path in release.rglob('*') if path.is_file()}
            if existing.get('files') != actual:
                raise SyncError('已有候选文件校验失败，请移除损坏候选后重新生成')
        if not release.exists():
            # 保留旧版内容寻址静态资源，避免 CDN 缓存的旧 HTML 或已打开标签页在切换瞬间缺图。
            # 不继承任何旧文章 HTML；下线页面必须真正消失。资源清理需另按缓存保留期执行。
            previous_release = config.work / 'releases' / active.get('version', 'missing')
            for folder in ('assets', 'ui'):
                previous_folder = previous_release / folder
                if previous_folder.is_dir():
                    for old_file in previous_folder.rglob('*'):
                        if not old_file.is_file(): continue
                        destination = output / folder / old_file.relative_to(previous_folder)
                        # file 参数命名的图片可能同名更新，必须保留刚下载的新字节，不能被旧版覆盖。
                        if not destination.exists():
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(old_file, destination)
            render_list(feed, output, config, mirror)
            namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
            ET.register_namespace('', namespace)
            root = ET.Element(f'{{{namespace}}}urlset')
            for url in [config.site + config.public, *sorted(urls)]:
                node = ET.SubElement(root, f'{{{namespace}}}url'); ET.SubElement(node, f'{{{namespace}}}loc').text = url
            (output / 'sitemap.xml').write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
            # TemporaryDirectory 默认 0700，不能直接交给 Nginx。只放开公开静态快照，
            # 缓存、配置和状态仍按部署账号权限保存；工作目录祖先的可遍历权限由部署时配置。
            output.chmod(0o755)
            for path in output.rglob('*'):
                path.chmod(0o755 if path.is_dir() else 0o644)
            release.parent.mkdir(parents=True, exist_ok=True)
            release.parent.chmod(0o755)
            os.replace(output, release)
        report['release'] = str(release)
        report['files'] = {str(path.relative_to(release)): digest(path.read_bytes()) for path in release.rglob('*') if path.is_file()}
        atomic_json(config.work / 'candidates' / (version + '.json'), report)
        return report


def collect_available(config: Config) -> dict:
    """定时 build 的可用性边界：未配置跳过；已配置来源失败保留内容，首次失败生成空页面。

    严格 check/collect 仍报告错误以便排查；此入口只降级为正常页面，不将失败认作下线。
    未配置返回 skipped 摘要，无文件或网络副作用；调用方不得据此发布或重试 CDN。
    配置/HTTP 失败只写运营日志，fallback 摘要不嵌入网页；缓存损坏等磁盘错误仍向上报告。
    """
    if not config.feed_url:
        return {'skipped': True, 'reason': 'feed_not_configured', 'changed': False}
    try:
        return collect(config)
    except CacheError:
        raise
    except (SyncError, ValueError) as error:
        print('资讯来源暂不可用，保留已有页面或生成首次空页面：' +
              (str(error) if isinstance(error, SyncError) else type(error).__name__), file=sys.stderr)
        active = load_json(config.work / 'active.json', {})
        if active:
            return {**active, 'changed': False, 'removed_count': 0, 'fallback': True}
        return {**collect(config, empty=True), 'fallback': True}


def refresh_cdn(urls: list[str], env) -> None:
    """可选阿里云 CDN 刷新；直接以环境凭证签名，不调用旧 CLI profile，不写密钥到文件/日志。

    none 模式跳过；aliyun 模式要求环境 AK，支持 STS token。每批至多 100 个 File URL，
    所有新增、修改及已删除地址都包含在待刷新集；空队列不要求凭证、不请求网络。
    仅接受非空字符串任务 ID；传输/API/响应格式失败均抛 SyncError，由发布层保留 pending。
    """
    mode = env.get('NEWS_CDN_MODE', 'none')
    if mode == 'none': return
    if mode != 'aliyun': raise SyncError('NEWS_CDN_MODE 只支持 none 或 aliyun')
    if not urls: return
    key, secret = env.get('ALIBABA_CLOUD_ACCESS_KEY_ID'), env.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    if not key or not secret: raise SyncError('CDN 刷新缺少环境凭证')
    for start in range(0, len(urls), 100):
        params = {'Format': 'JSON', 'Version': '2018-05-10', 'AccessKeyId': key, 'SignatureMethod': 'HMAC-SHA1', 'SignatureVersion': '1.0', 'SignatureNonce': str(uuid.uuid4()), 'Timestamp': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'Action': 'RefreshObjectCaches', 'ObjectType': 'File', 'ObjectPath': '\n'.join(urls[start:start + 100])}
        if env.get('ALIBABA_CLOUD_SECURITY_TOKEN'): params['SecurityToken'] = env['ALIBABA_CLOUD_SECURITY_TOKEN']
        canonical = '&'.join(quote(key, safe='~') + '=' + quote(value, safe='~') for key, value in sorted(params.items()))
        message = 'POST&%2F&' + quote(canonical, safe='~')
        params['Signature'] = base64.b64encode(hmac.new((secret + '&').encode(), message.encode(), hashlib.sha1).digest()).decode()
        try:
            request = Request('https://cdn.aliyuncs.com/', data=urlencode(params).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with build_opener().open(request, timeout=30) as response: result = json.load(response)
            # HTTP 200 也可能是 API 错误；只有真实任务 ID 才能清空持久化队列，不能只检查键名。
            if (not isinstance(result, dict) or result.get('Code') or
                    not isinstance(result.get('RefreshTaskId'), str) or not result['RefreshTaskId'].strip()):
                raise SyncError('CDN 未返回有效刷新任务 ID')
        except (HTTPError, URLError, TimeoutError, ValueError):
            raise SyncError('CDN 刷新请求失败；凭证与响应体不写入日志，下次任务重试') from None


def publish(config: Config, version: str, env) -> dict:
    """显式发布已校验候选，只替换 NEWS_LIVE_LINK 的符号链接；不触碰主站文件或 nginx。

    必须与全站发布共享 NEWS_RELEASE_LOCK，且全站 rsync 排除资讯目录后才能启用。
    文件切换后先写 active 状态并保存 pending CDN；刷新失败不重新构建，也不丢失删除 URL。
    """
    if not re.fullmatch(r'[a-f0-9]{64}', version): raise SyncError('版本必须是完整 SHA-256')
    if not env.get('NEWS_LIVE_LINK') or not env.get('NEWS_RELEASE_LOCK'):
        raise SyncError('publish 必须显式配置 NEWS_LIVE_LINK 和 NEWS_RELEASE_LOCK')
    report = load_json(config.work / 'candidates' / (version + '.json'))
    release = config.work / 'releases' / version
    if not report or not release.is_dir(): raise SyncError('候选版本不存在')
    if report['site'] != config.site or report['public'] != config.public: raise SyncError('候选与当前域名配置不匹配，请重新 build')
    if report['files'] != {str(path.relative_to(release)): digest(path.read_bytes()) for path in release.rglob('*') if path.is_file()}:
        raise SyncError('候选文件已被修改，禁止发布')
    live = Path(env['NEWS_LIVE_LINK']).absolute()
    if not live.parent.is_dir(): raise SyncError('发布父目录必须预先存在')
    if live.exists() and not live.is_symlink(): raise SyncError('发布目标已是实体目录/文件，拒绝覆盖')
    if live.is_symlink() and not live.resolve().is_relative_to((config.work / 'releases').resolve()):
        raise SyncError('发布目标链接不属于本资讯工作目录')
    with file_lock(Path(env['NEWS_RELEASE_LOCK'])):
        previous = load_json(config.work / 'active.json', {})
        # build/publish 分开执行；中间有别的版本生效时，必须重建基线，禁止陈旧候选覆盖新内容。
        if previous.get('version') not in (report.get('base_version'), report['version']):
            raise SyncError('候选基线已过期，请重新检查并生成候选')
        # 全部公开文章和旧地址并集，包含下线文件的缓存；.html/index.html 变体同时刷新。
        pending = set(load_json(config.work / 'pending-cdn.json', []))
        pending.update(previous.get('urls', [])); pending.update(report['urls'])
        # HTML 同目录 CSS 与 file 命名图片不再都是内容寻址路径；刷新新增/修改/删除资源，
        # 否则正文更新后浏览器/CDN 仍可能加载旧样式或旧图片。UI 哈希文件同样按差异处理。
        old_files, new_files = previous.get('files', {}), report['files']
        for name in set(old_files) | set(new_files):
            if name.endswith('.html') or old_files.get(name) == new_files.get(name): continue
            if name in old_files: pending.add(previous['site'] + previous['public'] + name)
            if name in new_files: pending.add(config.site + config.public + name)
        pending.update([config.site + config.public, config.site + config.public.rstrip('/'), config.site + config.public + 'index.html', config.site + config.public + 'sitemap.xml'])
        for url in list(pending):
            if url.endswith('/'): pending.update([url + 'index.html', url.rstrip('/')])
        atomic_json(config.work / 'pending-cdn.json', sorted(pending))
        temporary = live.with_name(live.name + '.next-' + uuid.uuid4().hex)
        temporary.symlink_to(release)
        os.replace(temporary, live)
        report['previous_version'] = previous.get('version')
        atomic_json(config.work / 'active.json', report)
        refresh_cdn(sorted(pending), env)
        if env.get('NEWS_CDN_MODE', 'none') == 'aliyun': atomic_json(config.work / 'pending-cdn.json', [])
    return {'published': version, 'cdn': env.get('NEWS_CDN_MODE', 'none')}


@contextlib.contextmanager
def file_lock(path: Path):
    """跨进程非阻塞文件锁；同类任务正在执行时中止，文件句柄在退出/异常时自动释放。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SyncError('已有任务持锁，本次跳过') from None
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> int:
    """CLI 入口；未配置 Feed 时常规命令正常跳过，且不初始化目录、锁或网络。

    配置后 check/build 无线上写入，publish 必须显式提供版本，输出只含摘要不含凭证。
    bootstrap 是发布安装专用命令，显式初始化空页或恢复入口，不受定时 Feed 停用语义限制。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'build', 'publish', 'retry-cdn', 'bootstrap'))
    parser.add_argument('--version', help='publish 对应的已生成版本 SHA-256')
    args = parser.parse_args()
    # 直接调用 CLI 也遵守停用语义；必须早于 Config 和 file_lock，避免无配置时创建数据目录。
    if args.command != 'bootstrap' and not os.environ.get('NEWS_FEED_URL', '').strip():
        print(json.dumps({'skipped': True, 'reason': 'feed_not_configured', 'changed': False}))
        return 0
    try:
        config = Config(os.environ)
        prepare_work_directory(config)
        with file_lock(config.work / 'sync.lock'):
            if args.command == 'bootstrap':
                # 仅官网发布安装阶段显式调用，不属于定时抓取。未配置 Feed 也先放置可访问空页，
                # 既有文章绝不能被空页覆盖；链接丢失时用已校验的 active 候选恢复。
                if not os.environ.get('NEWS_LIVE_LINK'): raise SyncError('bootstrap 需要 NEWS_LIVE_LINK')
                active = load_json(config.work / 'active.json', {})
                live = Path(os.environ['NEWS_LIVE_LINK'])
                if active and live.is_symlink() and live.resolve() == config.work / 'releases' / active['version']:
                    # 上次安装可能已经切换空页，但 CDN 失败；重新发布时需完成遗留刷新。
                    # none 模式保留队列，常规定时入口在 Feed 未配置时仍完全跳过。
                    pending = load_json(config.work / 'pending-cdn.json', [])
                    refresh_cdn(pending, os.environ)
                    if os.environ.get('NEWS_CDN_MODE') == 'aliyun': atomic_json(config.work / 'pending-cdn.json', [])
                    print(json.dumps({'initialized': False}))
                else:
                    report = active or collect(config, empty=True)
                    print(json.dumps(publish(config, report['version'], os.environ)))
            elif args.command in ('check', 'build'):
                report = collect(config, check_only=True) if args.command == 'check' else collect_available(config)
                print(json.dumps({**{key: report[key] for key in ('version', 'changed', 'count', 'removed_count')},
                                  'fallback': report.get('fallback', False)}, ensure_ascii=False))
            elif args.command == 'publish':
                if not args.version: raise SyncError('publish 需要 --version')
                print(json.dumps(publish(config, args.version, os.environ)))
            else:
                pending = load_json(config.work / 'pending-cdn.json', [])
                refresh_cdn(pending, os.environ)
                if os.environ.get('NEWS_CDN_MODE') == 'aliyun': atomic_json(config.work / 'pending-cdn.json', [])
                print(json.dumps({'pending': len(load_json(config.work / 'pending-cdn.json', []))}))
        return 0
    except (SyncError, OSError, ValueError) as error:
        # 不打印响应体、配置全集或请求 URL，避免将来源查询参数/云凭证带入日志。
        print('资讯同步失败：' + (str(error) if isinstance(error, SyncError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
