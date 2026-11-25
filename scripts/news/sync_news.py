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
from html import escape
import hmac
from http.client import IncompleteRead
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

from cases_projection import prepare_case_pages, case_page_transaction

HERE = Path(__file__).resolve().parent


class SyncError(RuntimeError):
    """同步契约不满足时中止当前操作；调用方记录错误并保留现有线上版本。"""


class CacheError(SyncError):
    """本地缓存损坏且无法恢复；属于运维故障，不能被来源不可用兜底吞掉。"""


def digest(value: bytes) -> str:
    """返回内容 SHA-256，用于资源命名、缓存完整性及候选版本比较。"""
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
        # 只从已发布 active 的条目记录授权复用；普通下载缓存不能证明文章版本已发布。
        self.reuse_records = {}
        self.article_records = {}
        self.total = 0
        self.opener = build_opener(SafeRedirect())

    def fetch(self, url: str, fresh=False) -> tuple[bytes, str]:
        """返回字节与 MIME；支持 ETag/Last-Modified，fresh 强制重新读取 Feed 验证快照一致。

        发送条件请求前校验缓存；损坏时完整重取，恢复失败抛 CacheError。
        未变条目的已发布缓存缺失或损坏时，只接受与发布基线相同的修复字节；不能用普通
        下载索引中的未发布版本替代它。来源已变则保留线上版本，等待来源推进条目时间后整篇重取。
        304 只有缓存文件存在且哈希正确才可复用。超时、错误状态或资源超限均中止当前版本；
        不把抓取失败解释为文章删除，也不输出带查询参数的来源 URL 或响应体。
        """
        url = clean_url(url)
        if url in self.records and not fresh:
            info = self.records[url]
            self.article_records[url] = info
            return (self.cache_dir / info['hash']).read_bytes(), info['type']
        if not fresh and url in self.reuse_records:
            info = self.reuse_records[url]
            cached = self.cache_dir / info['hash']
            # 修改时间相同只免去网络探测，不免去字节完整性验证；缓存授权来自 active，
            # 而非可能已被未发布候选推进的下载索引。正常共享资源已由上方 records 分支去重。
            if cached.is_file():
                body = cached.read_bytes()
                if digest(body) == info['hash']:
                    if len(body) > self.config.resource_limit: raise SyncError('单资源大小超限')
                    self.total += len(body)
                    if self.total > self.config.total_limit: raise SyncError('单次同步累计资源大小超限')
                    self.records[url] = self.article_records[url] = info
                    return body, info['type']
            try:
                # 绕过条件缓存完整修复。若直接落入普通下载逻辑，超前索引可能返回 304，
                # 新 HTML 也可能与仍复用的旧 CSS/图片混合，随后被错误冻结在旧条目时间下。
                body, _ = self.fetch(url, fresh=True)
            except (SyncError, OSError, ValueError) as error:
                raise CacheError('已发布缓存缺失或损坏且完整下载恢复失败，请检查来源和本地磁盘') from error
            if digest(body) != info['hash']:
                raise CacheError('恢复字节与已发布版本不一致，保留现有页面；请内容系统推进条目修改时间后重试')
            # 修复仅恢复原版本；沿用原 MIME 和重定向基址，不能因当前响应元信息变化而
            # 把相同 HTML 中的相对引用解析到另一个目录。本次下载已计入资源体积，无需再累计。
            self.records[url] = self.article_records[url] = info
            return body, info['type']
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
                # 分块计数并核对声明长度，避免截断响应被当作完整资源缓存和发布。
                # 仍保留原有内存返回契约及体积上限；仅在全部字节校验成功后写入缓存。
                declared = response.headers.get('Content-Length')
                if declared is not None and (not declared.isdigit() or int(declared) > self.config.resource_limit):
                    raise SyncError('资源声明长度无效或单资源大小超限')
                chunks, size = [], 0
                while True:
                    chunk = response.read(min(65536, self.config.resource_limit + 1 - size))
                    if not chunk: break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > self.config.resource_limit: raise SyncError('单资源大小超限')
                    if self.total + size > self.config.total_limit: raise SyncError('单次同步累计资源大小超限')
                if declared is not None and size != int(declared):
                    raise SyncError('资源下载不完整，声明长度与实际内容不符')
                body = b''.join(chunks)
                kind = response.headers.get_content_type()
                info = {'hash': digest(body), 'type': kind, 'etag': response.headers.get('ETag'), 'modified': response.headers.get('Last-Modified'), 'url': clean_url(response.geturl())}
        except HTTPError as error:
            if error.code != 304 or not cached_path.is_file():
                raise SyncError(f'资源抓取失败，HTTP {error.code}') from None
            body = cached_path.read_bytes()
            if digest(body) != previous['hash']: raise CacheError('缓存资源校验失败')
            info = previous
            kind = info['type']
        except (URLError, TimeoutError, IncompleteRead, ConnectionError):
            raise SyncError('资源请求超时或网络异常，本次不生成新版本') from None
        if len(body) > self.config.resource_limit: raise SyncError('单资源大小超限')
        self.total += len(body)
        if self.total > self.config.total_limit: raise SyncError('单次同步累计资源大小超限')
        (self.cache_dir / info['hash']).write_bytes(body)
        self.cache[url] = info
        self.records[url] = info
        self.article_records[url] = info
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
    """搬运作者网页与静态依赖；保留交互及来源运行目标，不审查内容或代理后端。"""

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
        """下载并本地化资源，返回官网绝对路径；存储资源沿用安全 file 文件名，其余按内容哈希命名。

        相对资源按来源文件 URL 解析；片段与非 HTTP 协议由浏览器解释并原样保留。
        不按图片/视频扩展名白名单筛选；CSS、SVG、静态 HLS 递归下载依赖，循环中止。
        不审查资源的可执行内容。需要持续请求来源的动态媒体保留来源地址，
        不能把直播清单冻结为一个貌似完整、实际上不会更新的本地文件。
        """
        if not reference or reference.startswith('#') or urlsplit(reference).scheme.lower() not in ('', 'http', 'https'):
            return reference
        url = clean_url(urljoin(base, reference))
        fragment = urlsplit(reference).fragment
        if url in self.assets: return self.assets[url] + ('#' + fragment if fragment else '')
        if url in self.visiting: raise SyncError('资源存在循环依赖，无法确定独立发布包')
        if len(self.visiting) >= 64: raise SyncError('资源依赖层级超限，无法完整镜像')
        self.visiting.add(url)
        body, kind = self.fetcher.fetch(url)
        # 同域重定向可能移动目录，CSS 相对依赖须相对最终响应地址，而不是旧请求地址。
        resource_base = self.fetcher.records[url].get('url', url)
        suffix = Path(urlsplit(url).path).suffix.lower()
        if kind == 'text/css' or suffix == '.css':
            body = self.css(body.decode('utf-8-sig'), resource_base).encode()
            suffix = '.css'
        elif suffix in ('.js', '.mjs') or 'javascript' in kind:
            # 脚本依赖的相对 import/currentScript 必须基于原地址；不解析、执行或改写任意 JS。
            self.assets[url] = resource_base
            self.visiting.remove(url)
            return resource_base + ('#' + fragment if fragment else '')
        elif suffix in ('.m3u8', '.m3u') or kind in ('application/vnd.apple.mpegurl', 'application/x-mpegurl', 'audio/mpegurl', 'audio/x-mpegurl') or body.startswith(b'#EXTM3U'):
            playlist = body.decode('utf-8-sig')
            if ('#EXT-X-ENDLIST' not in playlist and '#EXT-X-STREAM-INF:' not in playlist and '#EXT-X-I-FRAME-STREAM-INF:' not in playlist) or any(
                token in playlist for token in ('{$', '#EXT-X-DEFINE:', '#EXT-X-CONTENT-STEERING:', '#EXT-X-PART:', '#EXT-X-PRELOAD-HINT:', '#EXT-X-RENDITION-REPORT:')):
                self.assets[url] = resource_base
                self.visiting.remove(url)
                return resource_base
            body = self.hls(playlist, resource_base).encode()
            suffix = '.m3u8'
        elif suffix == '.mpd' or kind == 'application/dash+xml' or re.match(rb'\s*(?:<\?xml[^>]*>\s*)?<MPD\b', body[:512]):
            # DASH 时间线和动态分片由浏览器播放器从来源加载，保留原依赖基址。
            self.assets[url] = resource_base
            self.visiting.remove(url)
            return resource_base
        elif kind == 'image/svg+xml' or suffix == '.svg':
            # SVG 的样式、图像及外部片段与 CSS 共用资源图；仅替换依赖，不改变图形内容。
            try: svg_root = ET.fromstring(body)
            except ET.ParseError: raise SyncError('SVG 资源格式不合法') from None
            changed = False
            for element in svg_root.iter():
                tag = element.tag.split('}')[-1].lower()
                if tag == 'style' and element.text:
                    rewritten = self.css(element.text, resource_base)
                    changed |= rewritten != element.text
                    element.text = rewritten
                for key, value in list(element.attrib.items()):
                    attribute = key.split('}')[-1].lower()
                    rewritten = value
                    if attribute == 'href':
                        # a 是跳转链接，不是加载依赖；其余 href（image/use 等）需递归搬运。
                        if tag == 'a':
                            if not value.startswith('#'): rewritten = urljoin(resource_base, value)
                        else: rewritten = self.asset(value, resource_base)
                    elif attribute == 'style' or 'url(' in value.lower():
                        rewritten = self.css(value, resource_base)
                    changed |= rewritten != value
                    element.set(key, rewritten)
            if changed: body = ET.tostring(svg_root, encoding='utf-8')
            suffix = '.svg'
        elif not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix):
            suffix = mimetypes.guess_extension(kind) or '.bin'
        name = digest(body) + suffix
        # storage 路径也是通用资源入口，不能以 image MIME 拒绝视频；保留已有安全文件名协议。
        # 无后缀标识使用 MIME 推导后的哈希名，避免 Nginx 将无后缀视频当作 HTML。
        if re.match(r'^/api/whwy/[^/]+/storages/', urlsplit(url).path):
            names = parse_qs(urlsplit(url).query).get('file', [])
            if len(names) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]{1,8})?', names[0]):
                raise SyncError('存储资源 file 参数必须是安全的单个文件名')
            if '.' in names[0]: name = names[0]
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
        """按 CSS token 改写 url、@import 和 image-set 图片，保持其他样式及字符串逐字不变。

        base 为最终来源地址；注释和普通字符串不当作依赖。用括号栈识别 image-set 中的
        字符串候选，type() 等子函数中的字符串不是 URL。暂不解析 CSS 转义标识符和 URL，
        遇到时明确拒绝而非漏传；下载、依赖循环或不完整语法通过 SyncError 中止候选。
        """
        tokens = re.compile(r'/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
                            r'@import\b|[-\w]+\(|[()]|\s+|.', re.I | re.S)
        parts = list(tokens.finditer(text))
        output, stack, importing = [], [], False
        index = 0
        while index < len(parts):
            token = parts[index].group()
            lower = token.lower()
            if token == '\\':
                raise SyncError('CSS 转义标识符尚不能可靠识别资源，请内容站预先展开')
            if token.startswith('/*') or token.isspace():
                output.append(token)
            elif token.startswith(('"', "'")):
                if importing or (stack and stack[-1] in ('image-set', '-webkit-image-set')):
                    reference = token[1:-1]
                    if '\\' in reference: raise SyncError('CSS 资源 URL 使用了不支持的转义，请内容站预先打包')
                    mapped = self.asset(reference, base)
                    # data URL 与内部片段不搬运，保持原始引号和编码；生成的路径不含引号。
                    output.append(token if mapped == reference else '"' + mapped + '"')
                    importing = False
                else:
                    output.append(token)
            elif lower == '@import':
                importing = True
                output.append(token)
            elif lower == 'url(':
                end = index + 1
                while end < len(parts) and parts[end].group() != ')': end += 1
                if end == len(parts): raise SyncError('CSS url() 未闭合')
                raw = ''.join(p.group() for p in parts[index + 1:end]).strip()
                reference = raw
                if raw.startswith(('"', "'")):
                    if len(raw) < 2 or raw[-1] != raw[0]: raise SyncError('CSS URL 引号未闭合')
                    reference = raw[1:-1]
                elif re.search(r'[\s\(\)\'\"]', raw):
                    raise SyncError('CSS URL 语法无法完整解析')
                if '\\' in reference: raise SyncError('CSS 资源 URL 使用了不支持的转义，请内容站预先打包')
                mapped = self.asset(reference, base)
                output.append(text[parts[index].start():parts[end].end()] if mapped == reference else 'url("' + mapped + '")')
                importing = False
                index = end
            elif token.endswith('('):
                if importing: raise SyncError('CSS @import 资源语法无法完整解析')
                stack.append(lower[:-1])
                output.append(token)
            elif token == ')':
                if not stack: raise SyncError('CSS 函数括号不匹配')
                stack.pop()
                output.append(token)
            else:
                if importing: raise SyncError('CSS @import 缺少资源地址')
                output.append(token)
            index += 1
        if stack or importing: raise SyncError('CSS 资源表达式未闭合')
        return ''.join(output)

    def hls(self, text: str, base: str) -> str:
        """镜像有限、完整的 HLS 点播清单，返回所有 URI 指向官网的 UTF-8 文本。

        普通分片行及 URI 属性（密钥、初始化片段、备用音轨）共用 asset 下载，
        保留 byte-range 等播放参数。asset 已将直播和动态协议保留为来源 URL；
        此方法只搬运静态清单，不对页面是否允许使用动态媒体做准入判断。
        """
        lines = text.splitlines()
        if not lines or lines[0].strip() != '#EXTM3U': raise SyncError('HLS 清单格式不合法')
        output = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                output.append(self.asset(stripped, base))
            elif stripped.startswith('#EXT'):
                def replace_uri(match):
                    """只改写属性名为 URI 的引用，保留密钥算法、码率、分片范围等播放语义。"""
                    return match.group(1) + '"' + self.asset(match.group(2), base) + '"'
                rewritten = re.sub(r'([:,]URI=)"([^"\r\n]+)"', replace_uri, line)
                # URI 按 HLS 协议为 quoted-string；不认识的写法不能原样漏出。
                if len(re.findall(r'[:,]URI=', line)) != len(re.findall(r'[:,]URI="[^"\r\n]+"', line)):
                    raise SyncError('HLS URI 属性语法不合法')
                output.append(rewritten)
            else:
                output.append(line)
        return '\n'.join(output) + ('\n' if text.endswith('\n') else '')

    def html_page(self, item: dict) -> tuple[bytes, str]:
        """发布内容 App 的完整详情，仅调整 SEO、编码及搬运资源必需的 URL。

        不注入官网样式、导航、标签或正文布局；标题、结构、类名、样式值和链接功能由 App 决定。
        内容由配置的来源站负责，脚本、事件、数据块、表单和嵌入内容原样保留，不做标签或协议黑名单。
        脚本及嵌入/提交目标保持来源绝对地址，避免把动态依赖误迁移到官网静态目录。
        下载失败抛 SyncError；只对可解析 JSON-LD 做 SEO 改写，不执行来源脚本。
        """
        source = clean_url(item['url'])
        body, kind = self.fetcher.fetch(source)
        # 官网 canonical 仍由 id 决定；仅资源与正文相对链接随最终来源目录解析。
        resource_base = self.fetcher.records[source].get('url', source)
        if kind not in ('text/html', 'application/xhtml+xml'): raise SyncError('文章响应不是 HTML')
        soup = BeautifulSoup(body.decode('utf-8-sig'), 'html.parser')
        # HTML 可使用 main/div 等任意结构；片段也补齐序列化需要的容器，不限定正文标签。
        if not soup.html:
            root = soup.new_tag('html')
            for child in list(soup.contents): root.append(child.extract())
            soup.append(root)
        if not soup.head: soup.html.insert(0, soup.new_tag('head'))
        if not soup.body:
            body_node = soup.new_tag('body')
            for child in list(soup.html.contents):
                if child is not soup.head: body_node.append(child.extract())
            soup.html.append(body_node)
        base_node = soup.find('base', href=True)
        if base_node:
            resource_base = urljoin(resource_base, base_node['href'])
            base_node['href'] = resource_base
        canonical = self.pages[source]
        for node in soup.find_all(True):
            if node.name == 'script':
                if node.get('src'):
                    node['src'] = urljoin(resource_base, node['src'])
                    continue
                if node.get('type', '').lower() != 'application/ld+json': continue
                try: structured = json.loads(node.string or '')
                except ValueError: continue
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
            # 动态嵌入页和表单不能作为图片下载；只适配明确的 URL 属性，保留作者的其他属性与代码。
            for attribute in ('action', 'formaction'):
                if node.has_attr(attribute): node[attribute] = urljoin(resource_base, node[attribute] or resource_base)
            if node.name == 'form' and not node.has_attr('action'): node['action'] = resource_base
            if node.name in ('iframe', 'object', 'embed'):
                for attribute in ('src', 'data'):
                    if node.get(attribute): node[attribute] = urljoin(resource_base, node[attribute])
            # 延迟图片使用 data-src/data-srcset 保存尚未启用的依赖；先在发布时镜像，
            # 浏览器仍由作者脚本决定何时赋给 src，不能为搬运而提前启用首屏大图请求。
            # 其他元素的任意 data 属性保留原义，不推断自定义组件或脚本字符串的语义。
            resource_attributes = ('src', 'poster', 'data-src') if node.name in ('img', 'source') else ('src', 'poster')
            for attribute in resource_attributes:
                if node.name in ('iframe', 'object', 'embed'): continue
                if node.get(attribute): node[attribute] = self.asset(node[attribute], resource_base)
            for attribute in (('srcset', 'data-srcset') if node.name in ('img', 'source') else ('srcset',)):
                if not node.get(attribute): continue
                # 按浏览器候选解析顺序先取非空白 URL，再取描述符；URL 内逗号属于 data 内容，
                # 仅末尾逗号或描述符后的逗号分隔候选，不按逗号粗切或限制 data URL。
                parts = []
                remaining = node[attribute]
                while remaining.strip(' \t\n\r\f,'):
                    remaining = remaining.lstrip(' \t\n\r\f,')
                    match = re.match(r'\S+', remaining)
                    reference = match.group()
                    remaining = remaining[match.end():]
                    descriptors = ''
                    if reference.endswith(','):
                        reference = reference.rstrip(',')
                    else:
                        depth, end = 0, 0
                        for end, char in enumerate(remaining):
                            if char == '(': depth += 1
                            elif char == ')': depth -= 1
                            elif char == ',' and depth == 0: break
                        else: end = len(remaining)
                        descriptors, remaining = remaining[:end].strip(), remaining[end + 1:]
                    parts.append(self.asset(reference, resource_base) + (' ' + descriptors if descriptors else ''))
                node[attribute] = ', '.join(parts)
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
                name = (node.get('name') or node.get('property') or '').strip().lower()
                http_equiv = node.get('http-equiv', '').strip().lower()
                # 输出始终重新编码为 UTF-8，旧编码声明不能继续影响浏览器解码。
                if node.has_attr('charset') or http_equiv == 'content-type':
                    node.decompose(); continue
                # 来源资源有意不收录，但官网副本必须独立允许索引。爬虫专用声明会覆盖通用
                # index，因此连同专用机器人及旧模板中的 X-Robots-Tag meta 一并重新声明。
                # 这里只适配索引元信息，不按正文词语过滤，也不改作者脚本、事件或嵌入内容。
                if (name in ('robots', 'slurp', 'yandex', 'sogou')
                        or re.fullmatch(r'[\w-]*(?:bot|spider)(?:-[\w-]+)?', name)
                        or http_equiv in ('x-robots-tag', 'robots')):
                    node.decompose(); continue
                if node.get('http-equiv', '').lower() == 'refresh' and node.get('content'):
                    node['content'] = re.sub(r'(?i)(url\s*=\s*)([\'\"]?)(.*?)\2\s*$',
                        lambda match: match.group(1) + match.group(2) + urljoin(resource_base, match.group(3)) + match.group(2), node['content'])
                if name in ('og:url', 'twitter:url'): node['content'] = canonical
                if name in ('og:image', 'twitter:image') and node.get('content'):
                    mapped = self.asset(node['content'], resource_base)
                    node['content'] = self.config.site + mapped if mapped.startswith('/') else mapped
            if node.name == 'a' and node.get('href') and not node['href'].startswith('#'):
                href = node['href']
                target = urljoin(resource_base, href)
                if target.split('#')[0] in self.pages:
                    node['href'] = self.pages[target.split('#')[0]] + ('#' + target.split('#', 1)[1] if '#' in target else '')
                elif urlsplit(target).scheme in ('http', 'https'):
                    # 非迁移文章仍按 App 原本的目标导航，不能因其属于内容站就删除 href。
                    # 相对地址转为绝对地址只是保持搬迁前的指向，不决定 App 页面内容或交互。
                    node['href'] = target
            if base_node:
                # 原 base 必须保留给作者脚本；本地镜像路径显式绑定官网，避免被 base 指回来源。
                for attribute in (*resource_attributes, 'href'):
                    value = node.get(attribute, '')
                    if isinstance(value, str) and value.startswith(self.config.public): node[attribute] = self.config.site + value
                if node.name == 'link' and node.get('href') == item['id'] + '.css':
                    node['href'] = canonical + node['href']
                for attribute in (('srcset', 'data-srcset') if node.name in ('img', 'source') else ('srcset',)):
                    if node.get(attribute): node[attribute] = node[attribute].replace(self.config.public, self.config.site + self.config.public)
                if node.get('style'): node['style'] = node['style'].replace(self.config.public, self.config.site + self.config.public)
                if node.name == 'style' and node.string: node.string = node.string.replace(self.config.public, self.config.site + self.config.public)
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
    render_public_list(public_items, output, config)
    return public_items


def render_public_list(public_items: list[dict], output: Path, config: Config) -> None:
    """以已本地化的公开文章字段渲染列表模板与 UI 资源，不读取 Feed、不修改文章正文。

    正常同步和官网安装共用此渲染入口；安装时传入已发布 feed-snapshot，保持原条目和顺序。
    output 必须已存在；模板或文件写入失败向调用方抛出，不切换线上版本。
    """
    template = (HERE / 'templates' / 'index.html').read_text()
    soup = BeautifulSoup(template, 'html.parser')
    def article(item: dict, feature=False) -> str:
        """渲染来源条目的列表卡片；文字转义且不截断，推荐首图提前加载，其余延迟加载。

        仅消费公开列表字段；不读取正文，不根据标签限制文章。结构与浏览器增强模板一致，
        使首屏在脚本运行前就有完整封面和稳定布局；空图继续展示品牌占位。
        """
        title = escape(item['title'])
        image = item.get('image')
        words = next((values for values in (item.get('tags'), item.get('_keywords'),
                     re.split(r'[,，;；]', str(item.get('_seo_keywords') or ''))) if isinstance(values, list) and values), [])
        tags = ''.join(f'<button type="button" class="topic-chip" data-topic="{escape(word, quote=True)}" aria-label="筛选主题：{escape(word, quote=True)}">{escape(word)}</button>'
                       for word in dict.fromkeys(word.strip() for word in words if isinstance(word, str) and word.strip()))
        stamp = item.get('date_published') or ''
        date = f'<time datetime="{escape(stamp, quote=True)}">{escape(stamp[:10].replace("-", "."))}</time>' if stamp else ''
        reading = item.get('_reading_time_minutes', 0)
        if isinstance(reading, (int, float)) and reading > 0: date += f'<span>· {reading:g} 分钟阅读</span>'
        picture = (f'<img class="cover-image" src="{escape(image, quote=True)}" alt="{escape(item.get("image_alt") or "", quote=True)}" loading="{"eager" if feature else "lazy"}"'
                   + (' fetchpriority="high"' if feature else '') + '>') if image else ''
        heading = 'h2' if feature else 'h3'
        return (f'<article class="{"feature" if feature else "card"}" data-id="{escape(item["id"], quote=True)}">'
                f'<div class="cover one {"has-image" if image else ""}"><div class="art" aria-hidden="true"><span></span><span></span><span></span></div>'
                f'<div class="cover-top" aria-hidden="true"><b>JitAI</b><span>{escape(item.get("_section") or "INSIGHTS")}</span></div>'
                f'<p class="cover-heading" aria-hidden="true">{escape(item.get("_seo_title") or item["title"])}</p>{picture}<div class="cover-keywords">{tags}</div></div>'
                f'<div class="{"feature-body" if feature else "card-body"}"><span class="kicker">{escape("发现好内容" if feature else item.get("_section") or "JitAI 文章")}</span>'
                f'<{heading}><a href="{escape(item["url"], quote=True)}" target="_blank" rel="noopener noreferrer" class="article-link stretched" aria-label="{title}（在新标签页打开）">{title}</a></{heading}>'
                f'<p class="summary">{escape(item.get("summary") or "")}</p>'
                + ('' if feature else f'<div class="inline-topics">{tags}</div>')
                + f'<div class="meta">{date}</div>' + ('<span class="read-link" aria-hidden="true">阅读全文 ↗</span>' if feature else '') + '</div></article>')

    for item in public_items:
        soup.find(id='cards').append(BeautifulSoup(article(item), 'html.parser'))
    if public_items:
        # 首屏固定展示最新文章，与客户端初次渲染一致；之后仍轮播全部文章。
        soup.find(id='feature-carousel').attrs.pop('hidden', None)
        soup.find(id='feature-slot').append(BeautifulSoup(article(public_items[0], True), 'html.parser'))
        soup.find(id='slide-counter').string = f'1 / {len(public_items)}'
        if len(public_items) < 2: soup.find(id='rotation-controls')['hidden'] = ''
    soup.find(id='feed-snapshot').string = encoded({'items': public_items}).decode().replace('<', chr(92) + 'u003c')
    soup.find(id='result-count').string = f'共 {len(public_items)} 篇文章'
    # 空状态由服务器输出完整 HTML，禁用 JS 时也能看到；搜索无结果是另一个独立状态。
    if not public_items:
        soup.find(id='empty-library').attrs.pop('hidden', None)
        for node in soup.select('.library-tools, .filter-row, .results-line, #end-note'):
            node['hidden'] = ''
    soup.head.append(soup.new_tag('link', attrs={'rel': 'canonical', 'href': config.site + config.public}))
    soup.head.append(soup.new_tag('meta', attrs={'name': 'robots', 'content': 'index,follow,max-image-preview:large'}))
    description = 'JitAI 资讯中心：AI 原生系统客户案例、智能体集成方法与业务实践，了解从业务需求到系统落地的过程。'
    canonical = config.site + config.public
    soup.head.append(soup.new_tag('meta', attrs={'name': 'description', 'content': description}))
    # 列表分享信息由官网拥有；优先使用已发布的栅格封面，不将 SVG 强行声明为大图卡。
    share_image = next((item['image'] for item in public_items if item.get('image') and
                       urlsplit(item['image']).path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))), None)
    for key, value in {'og:type': 'website', 'og:title': soup.title.text, 'og:description': description,
                       'og:url': canonical, 'og:site_name': 'JitAI', 'og:locale': 'zh_CN'}.items():
        soup.head.append(soup.new_tag('meta', attrs={'property': key, 'content': value}))
    for key, value in {'twitter:card': 'summary_large_image' if share_image else 'summary',
                       'twitter:title': soup.title.text, 'twitter:description': description}.items():
        soup.head.append(soup.new_tag('meta', attrs={'name': key, 'content': value}))
    if share_image:
        soup.head.append(soup.new_tag('meta', attrs={'property': 'og:image', 'content': share_image}))
        soup.head.append(soup.new_tag('meta', attrs={'name': 'twitter:image', 'content': share_image}))
    # CollectionPage 只描述页面真实展示的文章集合，不把列表误标成 Article 或虚构评分。
    structured = {'@context': 'https://schema.org', '@type': 'CollectionPage', '@id': canonical,
                  'url': canonical, 'name': soup.title.text, 'description': description, 'inLanguage': 'zh-CN',
                  'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(public_items), 'itemListElement':
                      [{'@type': 'ListItem', 'position': index + 1, 'name': item['title'], 'url': item['url']}
                       for index, item in enumerate(public_items)]}}
    node = soup.new_tag('script', attrs={'type': 'application/ld+json'})
    node.string = encoded(structured).decode().replace('<', chr(92) + 'u003c')
    soup.head.append(node)
    # sitemap 与公开列表共用同一快照；只使用来源有效修改时间，不把本次导出时刻伪装成更新。
    # 无时区日期时间仅输出其明确的日历日期；时间倒置或非法时省略可选 lastmod，不拒绝内容。
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    root = ET.Element(f'{{{namespace}}}urlset')
    for item in [{'url': canonical}, *sorted(public_items, key=lambda value: value['url'])]:
        node = ET.SubElement(root, f'{{{namespace}}}url')
        ET.SubElement(node, f'{{{namespace}}}loc').text = item['url']
        try:
            modified = dt.datetime.fromisoformat(item.get('date_modified', '').replace('Z', '+00:00'))
            published = dt.datetime.fromisoformat(item.get('date_published', '').replace('Z', '+00:00')) if item.get('date_published') else None
            if published and (modified < published if bool(modified.tzinfo) == bool(published.tzinfo) else modified.date() < published.date()):
                continue
            ET.SubElement(node, f'{{{namespace}}}lastmod').text = modified.isoformat() if modified.tzinfo else modified.date().isoformat()
        except (ValueError, TypeError, AttributeError):
            pass
    (output / 'sitemap.xml').write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
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


def refresh_published_list(config: Config, active: dict) -> dict:
    """安装时用当前模板重建已发布列表，返回候选报告；无变化返回原版本且不写 active。

    调用方须持 sync.lock，并通过 publish 完成版本切换、共享发布锁与 CDN 刷新。
    不访问内容来源，保留文章、资源和公开快照，按快照重建 sitemap；摘要不符或部署边界变化则拒绝升级。
    """
    previous = config.work / 'releases' / active['version']
    if active['site'] != config.site or active['public'] != config.public:
        raise SyncError('已发布资讯与当前域名配置不匹配，请重新 build')
    actual = {str(p.relative_to(previous)): digest(p.read_bytes()) for p in previous.rglob('*') if p.is_file()}
    if actual != active.get('files'):
        raise SyncError('已发布资讯文件校验失败，禁止升级模板')
    snapshot = BeautifulSoup((previous / 'index.html').read_text(), 'html.parser').find(id='feed-snapshot')
    if snapshot is None: raise SyncError('已发布资讯缺少公开快照，禁止升级模板')
    data = json.loads(snapshot.text)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise SyncError('已发布资讯快照格式不正确')
    with tempfile.TemporaryDirectory(prefix='template-', dir=config.work) as directory:
        output = Path(directory)
        # 复制完整可信版本，绝不就地修改；旧 UI 哈希资源也保留，避免缓存中的旧页缺少依赖。
        shutil.copytree(previous, output, dirs_exist_ok=True)
        render_public_list(data['items'], output, config)
        files = {str(p.relative_to(output)): digest(p.read_bytes()) for p in output.rglob('*') if p.is_file()}
        if files == actual: return {**active, 'changed': False}
        version = digest(encoded({'files': files, 'site': config.site, 'public': config.public}))
        release = config.work / 'releases' / version
        report = {**active, 'version': version, 'base_version': active['version'], 'changed': True,
                  'deleted_urls': [], 'removed_count': 0, 'release': str(release), 'files': files}
        if release.exists():
            # 候选重试必须核对真实字节，不能把磁盘中的损坏文件重新标记为可信版本。
            existing = {str(p.relative_to(release)): digest(p.read_bytes()) for p in release.rglob('*') if p.is_file()}
            if existing != files: raise SyncError('已有模板候选文件校验失败')
        else:
            output.chmod(0o755)
            for path in output.rglob('*'): path.chmod(0o755 if path.is_dir() else 0o644)
            os.replace(output, release)
        atomic_json(config.work / 'candidates' / (version + '.json'), report)
        return report


def collect(config: Config, check_only=False, empty=False) -> dict:
    """抓取完整快照及资源，按真实内容和模板摘要判断变化；build 只生成候选，不发布。

    有合法 date_modified（包括 seo.updatedAt 映射）的条目，以已发布版本记录的修改时间作为契约，
    未变条目只读取并校验本地缓存，不请求文章或依赖。缺时间则按原路径检查；未变条目缓存
    缺失或损坏只允许恢复已发布字节，来源已变则抛 CacheError，避免把新旧依赖拼成旧时间版本。
    内容端必须在正文或任一依赖变化时推进条目时间；候选抓取成功不等于可以跳过下次检查。
    两次完整 Feed 校验用于避免生成过程混入不同文章集合；来源若无事务版本，不能保证
    所有资源是同一瞬时快照；后续依赖变化需内容端推进条目时间，才会在下次检查时读取。
    empty 仅供首次来源不可用时生成空候选；不发送网络请求，调用方必须保证尚无已发布版本。
    """
    fetcher = Fetcher(config)
    feed = {'items': []} if empty else validate_feed(fetcher.fetch(config.feed_url, fresh=True)[0], config)
    active = load_json(config.work / 'active.json', {})
    article_sources = {}
    config.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=config.work) as directory:
        output = Path(directory)
        mirror = Mirror(config, fetcher, output, feed)
        urls, jobs = [], []
        for item in feed['items']:
            # 每篇独立遍历资源图，但下载会话共享去重；记录必须包含深层 CSS/SVG/HLS 依赖，
            # 不能只记 HTML 中直接出现的 URL，否则下次会漏掉资源版本或重复下载。
            stamp = item.get('date_modified')
            try:
                parsed = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00')) if isinstance(stamp, str) else None
                # 内容 App 的现有 Feed 使用无时区 ISO 时间；这里只比较版本是否相等，
                # 不做跨时区先后判断，因此保留来源时间语义，不擅自当成本机时间转换。
                stamp = parsed.isoformat() if parsed is not None and 'T' in stamp else None
            except ValueError:
                stamp = None
            previous = active.get('article_sources', {}).get(item['id'], {})
            reusable = previous.get('sources', {}) if stamp and previous.get('stamp') == stamp and previous.get('url') == item['url'] else {}
            jobs.append((item, stamp, reusable))
        # 先检查变化篇的依赖，再读取未变化篇缓存，防止共享 URL 的旧缓存先进入会话去重表，
        # 导致更新篇也错误沿用旧视频/样式。共享 URL 全局代表同一资源，本次最多下载一次。
        for item, stamp, reusable in sorted(jobs, key=lambda job: bool(job[2])):
            fetcher.reuse_records = reusable
            fetcher.article_records = {}
            mirror = Mirror(config, fetcher, output, feed)
            try:
                body, url = mirror.html_page(item)
            except CacheError:
                raise
            except SyncError as error:
                # 使用不含来源查询参数的 Feed ID 定位文章；保留原错误类型及下载失败原因。
                raise SyncError('文章 ' + item['id'] + ' 同步失败：' + str(error)) from error
            target = output / article_path(item)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            urls.append(url)
            if item.get('image'): mirror.asset(item['image'], item['url'])
            article_sources[item['id']] = {'url': item['url'], 'stamp': stamp, 'sources': dict(fetcher.article_records)}
        second = feed if empty else validate_feed(fetcher.fetch(config.feed_url, fresh=True)[0], config)
        if semantic_feed(feed) != semantic_feed(second): raise SyncError('同步期间 Feed 改变，保留旧版本并等待下一次任务')
        source_hashes = {url: info['hash'] for url, info in fetcher.records.items() if url != config.feed_url}
        template_hashes = {path.name: digest(path.read_bytes()) for path in (HERE / 'templates').iterdir() if path.is_file()}
        # 快照会继承已发布的内容哈希资源，指纹也必须包含这组文件。否则 A→B→A 会复用
        # 首次 A 的目录而丢失 B 的资源，缓存中的 B 页面随即缺图；相同资源集合不会反复触发发布。
        retained = {name: value for name, value in active.get('files', {}).items() if name.startswith(('assets/', 'ui/'))}
        retained.update({str(path.relative_to(output)): digest(path.read_bytes()) for path in (output / 'assets').glob('*') if path.is_file()})
        retained.update({'ui/' + template_hashes[name] + Path(name).suffix: template_hashes[name]
                         for name in ('interactions.js', 'refinements.css', 'logo.svg', 'logo-dark.svg')})
        engine = digest(Path(__file__).read_bytes() + Path(__file__).with_name('cases_projection.py').read_bytes())
        version = digest(encoded({'feed': semantic_feed(feed), 'resources': source_hashes, 'templates': template_hashes, 'retained': retained, 'engine': engine, 'site': config.site, 'public': config.public}))
        fetcher.save()
        changed = active.get('version') != version
        deleted = sorted(set(active.get('urls', [])) - set(urls))
        report = {'version': version, 'changed': changed, 'count': len(urls), 'removed_count': len(deleted), 'urls': sorted(urls), 'deleted_urls': deleted, 'site': config.site, 'public': config.public, 'base_version': active.get('version'), 'article_sources': article_sources}
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
    配置/HTTP 失败写运营日志，fallback 摘要不嵌入网页；CLI 据此非零退出，让定时器报告失败。
    缓存损坏等磁盘错误仍向上报告，不能当作正常未更新。
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


def refresh_cdn(urls: list[str], env, pending_path: Path | None = None) -> None:
    """可选阿里云 CDN 刷新；直接以环境凭证签名，不调用旧 CLI profile，不写密钥到文件/日志。

    none 模式跳过；aliyun 模式要求环境 AK，支持 STS token。每批至多 100 个 File URL，
    所有新增、修改及已删除地址都包含在待刷新集；空队列不要求凭证、不请求网络。
    仅接受非空字符串任务 ID；传输/API/响应格式失败均抛 SyncError。
    pending_path 指定持久化队列时，每批受理后立即写入剩余 URL；失败只重试未确认批次，
    不重复消耗已成功批次的额度。调用方须持同步/发布锁，防止覆盖其他发布的新队列。
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
        if pending_path is not None:
            atomic_json(pending_path, urls[start + 100:])


def publish(config: Config, version: str, env) -> dict:
    """显式发布已校验候选，切换资讯链接并更新主站案例页的两个专属静态槽；不改 nginx。

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
        # 安装器明确提供主站根；独立同步器未接主站时保留旧契约，不推断可写祖先目录。
        # 页面投影基于待发布候选，先准备并校验全部字节；任何失败都不能切换资讯版本。
        case_changes = []
        if env.get('NEWS_MAIN_SITE_DIR'):
            site_root = Path(env['NEWS_MAIN_SITE_DIR']).absolute()
            if site_root / config.public.strip('/') != live:
                raise SyncError('案例投影主站根与资讯入口不一致')
            case_changes = prepare_case_pages(site_root, release, config.site)
        # 全部公开文章和旧地址并集，包含下线文件的缓存；.html/index.html 变体同时刷新。
        pending = set(load_json(config.work / 'pending-cdn.json', []))
        # HTML 同样按内容差异刷新；Feed 只有一篇更新时，不重复刷新其他未变文章。
        old_files, new_files = previous.get('files', {}), report['files']
        for url in set(previous.get('urls', [])) | set(report['urls']):
            relative = url.removeprefix(config.site + config.public) + 'index.html'
            if old_files.get(relative) != new_files.get(relative): pending.add(url)
        # HTML 同目录 CSS 与 file 命名图片不再都是内容寻址路径；刷新新增/修改/删除资源，
        # 否则正文更新后浏览器/CDN 仍可能加载旧样式或旧图片。UI 哈希文件同样按差异处理。
        for name in set(old_files) | set(new_files):
            if name.endswith('.html') or old_files.get(name) == new_files.get(name): continue
            if name in old_files: pending.add(previous['site'] + previous['public'] + name)
            if name in new_files: pending.add(config.site + config.public + name)
        pending.update([config.site + config.public, config.site + config.public.rstrip('/'), config.site + config.public + 'index.html', config.site + config.public + 'sitemap.xml'])
        for path, _, _ in case_changes:
            route = '/' + path.relative_to(site_root).as_posix().removesuffix('.html')
            pending.update(config.site + route + suffix for suffix in ('', '.html', '/', '/index.html'))
        for url in list(pending):
            if url.endswith('/'): pending.update([url + 'index.html', url.rstrip('/')])
        atomic_json(config.work / 'pending-cdn.json', sorted(pending))
        temporary = live.with_name(live.name + '.next-' + uuid.uuid4().hex)
        previous_target = os.readlink(live) if live.is_symlink() else None
        with case_page_transaction(case_changes):
            try:
                temporary.symlink_to(release)
                os.replace(temporary, live)
                report['previous_version'] = previous.get('version')
                atomic_json(config.work / 'active.json', report)
            except BaseException:
                # 状态提交失败恢复资讯入口；外层事务同时恢复案例页，不留下新列表配旧状态。
                temporary.unlink(missing_ok=True)
                if previous_target is None:
                    live.unlink(missing_ok=True)
                else:
                    temporary.symlink_to(previous_target)
                    os.replace(temporary, live)
                raise
            finally:
                temporary.unlink(missing_ok=True)
        refresh_cdn(sorted(pending), env, config.work / 'pending-cdn.json')
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
    build 因来源错误回退旧版时返回 1；页面保留与本次任务成功是两个独立状态。
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
                # 仅官网发布安装阶段调用：已有内容从可信公开快照升级模板，不依赖 Feed 可用性。
                # 没有已发布版本才初始化空页；链接丢失时仍通过正常发布流程恢复。
                if not os.environ.get('NEWS_LIVE_LINK'): raise SyncError('bootstrap 需要 NEWS_LIVE_LINK')
                active = load_json(config.work / 'active.json', {})
                live = Path(os.environ['NEWS_LIVE_LINK'])
                report = refresh_published_list(config, active) if active else collect(config, empty=True)
                if not report['changed'] and live.is_symlink() and live.resolve() == config.work / 'releases' / report['version']:
                    # 上次安装可能已经切换空页，但 CDN 失败；重新发布时需完成遗留刷新。
                    # none 模式保留队列，常规定时入口在 Feed 未配置时仍完全跳过。
                    pending = load_json(config.work / 'pending-cdn.json', [])
                    refresh_cdn(pending, os.environ, config.work / 'pending-cdn.json')
                    if os.environ.get('NEWS_CDN_MODE') == 'aliyun': atomic_json(config.work / 'pending-cdn.json', [])
                    print(json.dumps({'initialized': False}))
                else:
                    print(json.dumps(publish(config, report['version'], os.environ)))
            elif args.command in ('check', 'build'):
                report = collect(config, check_only=True) if args.command == 'check' else collect_available(config)
                print(json.dumps({**{key: report[key] for key in ('version', 'changed', 'count', 'removed_count')},
                                  'fallback': report.get('fallback', False)}, ensure_ascii=False))
                # 回退只保证旧页面可用，不代表本次抓取成功；调度器须看见非零状态并在下一轮重试。
                if report.get('fallback'): return 1
            elif args.command == 'publish':
                if not args.version: raise SyncError('publish 需要 --version')
                print(json.dumps(publish(config, args.version, os.environ)))
            else:
                pending = load_json(config.work / 'pending-cdn.json', [])
                refresh_cdn(pending, os.environ, config.work / 'pending-cdn.json')
                if os.environ.get('NEWS_CDN_MODE') == 'aliyun': atomic_json(config.work / 'pending-cdn.json', [])
                print(json.dumps({'pending': len(load_json(config.work / 'pending-cdn.json', []))}))
        return 0
    except (SyncError, OSError, ValueError) as error:
        # 不打印响应体、配置全集或请求 URL，避免将来源查询参数/云凭证带入日志。
        print('资讯同步失败：' + (str(error) if isinstance(error, SyncError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
