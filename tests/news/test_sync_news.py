"""资讯同步契约测试：独立临时 HTTP 源与临时发布目录，不连接、不修改线上官网。

测试用例验证源资源更新、删除、失败保留、SEO 改写和显式发布边界；不以实现函数生成
期望哈希。每个用例创建独立工作区，HTTP 替身仅提供文件内容，不替代同步器的业务逻辑。
"""

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

MODULE_PATH = Path(__file__).resolve().parents[2] / 'scripts/news/sync_news.py'
spec = importlib.util.spec_from_file_location('sync_news', MODULE_PATH)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class NewsSyncTests(unittest.TestCase):
    """每个测试拥有来源资源、HTTP 服务器、构建工作区与发布链接，并在结束后释放。"""

    def setUp(self):
        """构造两篇最小静态文章，独立可变 CSS/图片，确保每种变化可单独触发。"""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.resources = {}
        resources = self.resources
        # HTTP 替身只实现标准条件响应和重定向，以真实请求验证缓存/重定向边界。
        self.etags = {}
        self.redirects = {}
        self.requests = []
        etags, redirects, requests = self.etags, self.redirects, self.requests

        class Handler(BaseHTTPRequestHandler):
            """只读本用例资源字典，提供精确状态码和类型；不模拟算法/发布结果。"""

            def do_GET(self):
                """返回独立测试数据，缺失资源明确返回 404，用于验证失败不能被当作下线。"""
                requests.append((self.path, self.headers.get('If-None-Match')))
                if self.path in redirects:
                    self.send_response(302)
                    self.send_header('Location', redirects[self.path])
                    self.end_headers(); return
                if self.path not in resources:
                    self.send_error(404); return
                if self.path in etags and self.headers.get('If-None-Match') == etags[self.path]:
                    self.send_response(304); self.end_headers(); return
                body, content_type = resources[self.path]
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                if self.path in etags:
                    self.send_header('ETag', etags[self.path])
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                """测试不输出每个 HTTP 请求，避免噪声掩盖断言结果。"""

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.source = f'http://127.0.0.1:{self.server.server_port}'
        self.env = {'NEWS_FEED_URL': self.source + '/feed.json', 'NEWS_SITE_ORIGIN': 'https://official.example', 'NEWS_WORK_DIR': str(self.root / 'work'), 'NEWS_LIVE_LINK': str(self.root / 'live'), 'NEWS_RELEASE_LOCK': str(self.root / 'release.lock'), 'NEWS_CDN_MODE': 'none'}
        self.config = sync.Config(self.env)
        self.feed = {'version': 'https://jsonfeed.org/version/1.1', '_scope': '全部已发布内容', '_item_count': 2, '_generated_at': 'clock-1', 'items': [{'id': identity, 'url': self.source + '/' + identity + '.html', 'title': '文章 ' + identity, 'summary': '摘要', 'tags': ['真实主题'], 'date_published': '2026-11-09T12:00:00+08:00'} for identity in ('one', 'two')]}
        for identity in ('one', 'two'):
            self.resources['/' + identity + '.html'] = (f'<!doctype html><html><head><title>{identity}</title><link rel="canonical" href="{self.source}/{identity}.html"><meta name="robots" content="noindex,nofollow"><meta property="og:url" content="{self.source}/{identity}.html"><link rel="stylesheet" href="shared.css"></head><body><article><h1>{identity}</h1><p>原始正文不重排</p><img src="/image.png"><a href="two.html">另一篇</a></article></body></html>'.encode(), 'text/html')
        self.resources['/shared.css'] = (b'article { color: red; background: url("background.png"); }', 'text/css')
        self.resources['/background.png'] = (b'background-pixel', 'image/png')
        self.resources['/image.png'] = (b'image-first', 'image/png')
        self.save_feed()

    def tearDown(self):
        """关闭测试网络服务后清除全部临时文件，确保测试彼此独立。"""
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def save_feed(self):
        """将测试明确指定的 Feed 内容提供给 HTTP 源，不从待测实现推导期望。"""
        self.resources['/feed.json'] = (json.dumps(self.feed).encode(), 'application/json')

    def build_publish(self):
        """将候选发布到本用例临时链接，用于验证后续变更相对已发布版本的行为。"""
        report = sync.collect(self.config)
        sync.publish(self.config, report['version'], self.env)
        return report

    def test_build_is_offline_and_mirrors_html_seo_and_css(self):
        """build 不创建 live 链接；正文保留、SEO 指向官网、CSS 和图片均被本地化。"""
        report = sync.collect(self.config)
        self.assertFalse((self.root / 'live').exists())
        release = Path(report['release'])
        soup = BeautifulSoup((release / 'articles/one/index.html').read_text(), 'html.parser')
        self.assertEqual(soup.article.p.text, '原始正文不重排')
        self.assertEqual(soup.select_one('meta[charset]')['charset'], 'utf-8')
        self.assertEqual(soup.select_one('meta[name="robots"]')['content'], 'index,follow,max-image-preview:large')
        self.assertEqual(soup.select_one('link[rel="canonical"]')['href'], 'https://official.example/zh/news/articles/one/')
        self.assertEqual(soup.select_one('meta[property="og:url"]')['content'], 'https://official.example/zh/news/articles/one/')
        self.assertEqual(soup.article.a['href'], 'https://official.example/zh/news/articles/two/')
        self.assertTrue(soup.img['src'].startswith('/zh/news/assets/'))
        css_path = soup.select_one('link[rel="stylesheet"]')['href'].removeprefix('/zh/news/')
        self.assertIn('/zh/news/assets/', (release / css_path).read_text())
        listing = BeautifulSoup((release / 'index.html').read_text(), 'html.parser')
        self.assertEqual(len(listing.select('#cards a[target="_blank"]')), 2)
        self.assertNotIn('设计预览', listing.get_text())
        self.assertNotIn(self.source, listing.select_one('#feed-snapshot').text)

    def test_generation_timestamp_and_feed_order_do_not_trigger_build(self):
        """生成时刻变化及清单重排不改变文章内容；相对已发布版本应跳过候选生成。"""
        previous = self.build_publish()
        self.feed['_generated_at'] = 'clock-2'
        self.feed['items'].reverse(); self.save_feed()
        current = sync.collect(self.config)
        self.assertFalse(current['changed'])
        self.assertEqual(current['version'], previous['version'])
        self.assertNotIn('release', current)

    def test_only_feed_address_is_required_for_source_configuration(self):
        """仅给 Feed 与隔离测试数据目录即可生成；不配置文章/资源域名，官网默认 jit.pro。"""
        config = sync.Config({'NEWS_FEED_URL': self.source + '/feed.json', 'NEWS_WORK_DIR': str(self.root / 'feed-only')})
        report = sync.collect(config)
        self.assertEqual(report['urls'], ['https://jit.pro/zh/news/articles/one/', 'https://jit.pro/zh/news/articles/two/'])

    def test_feed_articles_and_assets_can_have_different_origins(self):
        """Feed 和文章分别在两个真实 HTTP 服务，图片又指回 Feed 主机，均按引用自动抓取。"""
        other = NewsSyncTests()
        other.setUp()
        try:
            self.feed['items'][0]['url'] = other.source + '/one.html'
            body, kind = other.resources['/one.html']
            other.resources['/one.html'] = (body.replace(b'/image.png', (self.source + '/image.png').encode()), kind)
            self.save_feed()
            report = sync.collect(self.config)
            soup = BeautifulSoup((Path(report['release']) / 'articles/one/index.html').read_text(), 'html.parser')
            self.assertTrue(soup.img['src'].startswith('/zh/news/assets/'))
            self.assertIn(('/one.html', None), other.requests)
            self.assertIn(('/image.png', None), self.requests)
        finally:
            other.tearDown()

    def test_invalid_or_failed_feed_creates_first_empty_candidate(self):
        """首次非法地址、HTTP 404 和坏 JSON 都输出正常空页，不把故障详情暴露给访客。"""
        self.resources['/invalid-feed.json'] = (b'not-json', 'application/json')
        for index, feed_url in enumerate(('not-a-url', self.source + '/missing.json', self.source + '/invalid-feed.json')):
            with self.subTest(feed_url=feed_url):
                config = sync.Config({**self.env, 'NEWS_FEED_URL': feed_url, 'NEWS_WORK_DIR': str(self.root / f'fallback-{index}')})
                report = sync.collect_available(config)
                self.assertTrue(report['fallback'])
                self.assertEqual(report['count'], 0)
                self.assertFalse((self.root / 'live').exists())
                soup = BeautifulSoup((Path(report['release']) / 'index.html').read_text(), 'html.parser')
                self.assertFalse(soup.find(id='empty-library').has_attr('hidden'))
                self.assertIn('好内容，正在路上', soup.get_text())
                self.assertTrue(soup.select_one('.library-tools').has_attr('hidden'))
                self.assertNotIn('HTTP 404', soup.get_text())
                self.assertNotIn('NEWS_FEED_URL', soup.get_text())

    def test_unavailable_source_keeps_published_articles_and_state(self):
        """已发布后 Feed 非法或 404 不得清空列表/文章、改动 active 或误报下线。"""
        first = self.build_publish()
        original_state = (self.config.work / 'active.json').read_bytes()
        for feed_url in ('not-a-url', self.source + '/missing.json'):
            config = sync.Config({**self.env, 'NEWS_FEED_URL': feed_url})
            report = sync.collect_available(config)
            self.assertTrue(report['fallback'])
            self.assertFalse(report['changed'])
            self.assertEqual(report['removed_count'], 0)
            self.assertEqual(report['version'], first['version'])
            self.assertEqual((self.config.work / 'active.json').read_bytes(), original_state)
            self.assertTrue((self.root / 'live/articles/two/index.html').is_file())

    def test_initial_empty_page_recovers_when_feed_is_configured(self):
        """首次空页可按正常显式流程发布；地址配置好后下一次同步自动恢复真实文章。"""
        config = sync.Config({**self.env, 'NEWS_FEED_URL': self.source + '/missing.json'})
        empty = sync.collect_available(config)
        sync.publish(config, empty['version'], self.env)
        self.assertFalse(sync.collect_available(config)['changed'])
        ready = sync.collect_available(self.config)
        self.assertEqual(ready['count'], 2)
        self.assertTrue(ready['changed'])
        sync.publish(self.config, ready['version'], self.env)
        self.assertTrue((self.root / 'live/articles/one/index.html').is_file())
        self.assertFalse(sync.collect(self.config)['changed'])

    def test_missing_feed_skips_collection_without_files_or_network(self):
        """空白地址是未启用同步；直接调用 build 边界也不能下载、创建目录或生成空页。"""
        for value in ('', '  \t\n'):
            with self.subTest(value=value):
                config = sync.Config({**self.env, 'NEWS_FEED_URL': value})
                self.assertEqual(sync.collect_available(config),
                                 {'skipped': True, 'reason': 'feed_not_configured', 'changed': False})
                self.assertFalse(config.work.exists())
                self.assertEqual(self.requests, [])

    def test_scheduler_missing_feed_exits_before_python_or_publish(self):
        """真实 shell 在启用发布时仍须先检查 Feed；不存在的解释器证明未进入 Python/CDN。"""
        for value in (None, '', '  \t\n'):
            with self.subTest(value=value):
                env = {**os.environ, **self.env, 'NEWS_PYTHON': '/missing/python', 'NEWS_ENABLE_PUBLISH': '1'}
                env.pop('NEWS_FEED_URL', None)
                if value is not None:
                    env['NEWS_FEED_URL'] = value
                result = subprocess.run(['bash', str(MODULE_PATH.parent / 'run-news-sync.sh')],
                                        env=env, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout),
                                 {'skipped': True, 'reason': 'feed_not_configured', 'changed': False})
                self.assertFalse(self.config.work.exists())
                self.assertFalse((self.root / 'live').exists())
                self.assertEqual(self.requests, [])

    def test_cli_missing_feed_does_not_touch_existing_release_or_pending(self):
        """所有 CLI 命令先判断未配置；保留现有页面、pending 和锁，避免绕过 shell 后继续运行。"""
        self.build_publish()
        before = {str(p): p.read_bytes() for p in self.config.work.rglob('*') if p.is_file()}
        target = (self.root / 'live').resolve()
        env = {**os.environ, **self.env, 'NEWS_FEED_URL': ' ', 'NEWS_SITE_ORIGIN': 'invalid'}
        self.requests.clear()
        for command in ('check', 'build', 'publish', 'retry-cdn'):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(MODULE_PATH), command], env=env,
                                        capture_output=True, text=True, check=True)
                self.assertTrue(json.loads(result.stdout)['skipped'])
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.config.work.rglob('*') if p.is_file()})
                self.assertEqual((self.root / 'live').resolve(), target)
                self.assertEqual(self.requests, [])

    def test_article_presentation_and_source_links_remain_app_owned(self):
        """详情不注入官网排版：保留 App 的结构/类名/内联样式/锚点及未迁移链接，仅适配地址。"""
        content = '<article class="app-article" data-layout="wide"><section id="intro" style="display:grid;gap:17px"><h1>原文标题</h1><div class="columns"><p>正文</p><aside>侧注</aside></div><a href="#intro">页内目录</a><a class="app-link" href="/help">内容 App 帮助</a></section></article>'
        style = '.app-article { max-width: 1137px; } .columns { display:grid; grid-template-columns:2fr 1fr; }'
        self.resources['/one.html'] = (('<!doctype html><html><head><style>' + style + '</style></head><body>' + content + '</body></html>').encode(), 'text/html')
        report = sync.collect(self.config)
        soup = BeautifulSoup((Path(report['release']) / 'articles/one/index.html').read_text(), 'html.parser')
        expected = BeautifulSoup(content, 'html.parser')
        expected.select_one('.app-link')['href'] = self.source + '/help'
        self.assertEqual(str(soup.article), str(expected.article))
        self.assertEqual(soup.style.string, style)
        self.assertEqual([node.name for node in soup.body.children if node.name], ['article'])

    def test_full_page_css_and_storage_image_follow_new_contract(self):
        """整页外壳保留、slug.css 留在同目录、/api 存储图按 file 命名，主体 SEO 指向官网。"""
        image_url = '/api/whwy/app123/storages/services/StorageSvc/preview?file=abc123.svg'
        self.resources[image_url] = (b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>', 'image/svg+xml')
        css = b'body { margin: 0; } article { display: grid; gap: 17px; }'
        self.resources['/one.css'] = (css, 'text/css')
        html = '<html><head><meta name="robots" content="noindex,nofollow"><link rel="stylesheet" href="one.css"></head><body><header class="app-header">App header</header><main><article><h1>App title</h1><img src="' + image_url + '"></article></main><footer>App footer</footer></body></html>'
        self.resources['/one.html'] = (html.encode(), 'text/html')
        first = self.build_publish()
        release = Path(first['release'])
        soup = BeautifulSoup((release / 'articles/one/index.html').read_text(), 'html.parser')
        self.assertEqual(soup.select_one('link[rel="stylesheet"]')['href'], 'one.css')
        self.assertEqual((release / 'articles/one/one.css').read_bytes(), css)
        self.assertEqual(soup.img['src'], '/zh/news/assets/abc123.svg')
        self.assertEqual((release / 'assets/abc123.svg').read_bytes(), self.resources[image_url][0])
        self.assertEqual([node.name for node in soup.body.children if node.name], ['header', 'main', 'footer'])
        self.assertFalse((release / 'articles/one/body.html').exists())
        self.assertEqual(soup.select_one('meta[name="robots"]')['content'], 'index,follow,max-image-preview:large')
        self.assertFalse(sync.collect(self.config)['changed'])
        # 同文件名更新时不能继承旧版字节；CSS/图片 URL 必须进入待刷新集合。
        sync.atomic_json(self.config.work / 'pending-cdn.json', [])
        self.resources['/one.css'] = (b'article { color: blue; }', 'text/css')
        self.resources[image_url] = (b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>', 'image/svg+xml')
        second = self.build_publish()
        self.assertNotEqual(first['version'], second['version'])
        self.assertEqual((self.root / 'live/assets/abc123.svg').read_bytes(), self.resources[image_url][0])
        pending = sync.load_json(self.config.work / 'pending-cdn.json')
        self.assertIn('https://official.example/zh/news/articles/one/one.css', pending)
        self.assertIn('https://official.example/zh/news/assets/abc123.svg', pending)
        self.assertFalse(sync.collect(self.config)['changed'])

    def test_seo_object_drives_listing_and_change_detection(self):
        """seo 成为列表元信息来源；只改变 seo 也触发更新，完整标题仍使用 Feed title。"""
        self.feed['items'][0]['seo'] = {'title': '封面短标题', 'description': '新摘要',
            'keywords': ['关键词'], 'tags': ['主题一', '主题二'], 'author': '编辑', 'language': 'zh',
            'publishedAt': '2026-11-10T10:00:00', 'updatedAt': '2026-11-10T11:00:00', 'wordCount': 1234, 'image': self.source + '/image.png'}
        self.save_feed()
        first = self.build_publish()
        soup = BeautifulSoup((self.root / 'live/index.html').read_text(), 'html.parser')
        item = next(item for item in json.loads(soup.find(id='feed-snapshot').string)['items'] if item['id'] == 'one')
        self.assertEqual(item['title'], '文章 one')
        self.assertEqual(item['_seo_title'], '封面短标题')
        self.assertEqual(item['summary'], '新摘要')
        self.assertEqual(item['tags'], ['主题一', '主题二'])
        self.assertEqual(item['authors'], [{'name': '编辑'}])
        self.assertEqual(item['date_published'], '2026-11-10T10:00:00')
        self.assertTrue(item['image'].startswith('https://official.example/zh/news/assets/'))
        self.feed['items'][0]['seo']['title'] = '修改后的封面'; self.save_feed()
        second = sync.collect(self.config)
        self.assertNotEqual(first['version'], second['version'])

    def test_storage_file_parameter_cannot_escape_assets_directory(self):
        """file 值不得携带路径，必须在候选写入前拒绝，避免覆盖文章或状态文件。"""
        bad = '/api/whwy/app123/storages/preview?file=..%2Fescape.png'
        self.resources[bad] = (b'image', 'image/png')
        body, kind = self.resources['/one.html']
        self.resources['/one.html'] = (body.replace(b'/image.png', bad.encode()), kind)
        with self.assertRaisesRegex(sync.SyncError, 'file 参数'):
            sync.collect(self.config)

    def test_storage_filename_collision_is_not_silently_overwritten(self):
        """两个存储 origin/path 返回同名不同字节时失败，不能把另一张图片静默覆盖。"""
        first = '/api/whwy/app123/storages/first?file=shared.png'
        second = '/api/whwy/app123/storages/second?file=shared.png'
        self.resources[first] = (b'first-image', 'image/png')
        self.resources[second] = (b'second-image', 'image/png')
        body, kind = self.resources['/one.html']
        self.resources['/one.html'] = (body.replace(b'<img src="/image.png">', f'<img src="{first}"><img src="{second}">'.encode()), kind)
        with self.assertRaisesRegex(sync.SyncError, '文件名冲突'):
            sync.collect(self.config)

    def test_seo_removes_all_noindex_and_normalizes_primary_jsonld(self):
        """来源含机器人专用禁索引和旧官网 JSON-LD 地址；官网统一索引归属且保留外部引用。"""
        body, kind = self.resources['/one.html']
        structured = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'BlogPosting', '@id': 'https://official.example/zh/blog/one.html#article',
             'url': 'https://official.example/zh/blog/one.html',
             'mainEntityOfPage': {'@type': 'WebPage', '@id': 'https://official.example/zh/blog/one.html'},
             'headline': '原有 SEO 标题', 'description': '原有 SEO 描述', 'keywords': ['主题'],
             'citation': {'@type': 'Article', 'url': 'https://research.example/report'},
             'publisher': {'@type': 'Organization', 'url': 'https://official.example'}},
            {'@type': 'BreadcrumbList', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'item': self.source + '/'},
                {'@type': 'ListItem', 'position': 2, 'item': self.source + '/one.html'}]}]}
        extra = '<meta name="ROBOTS" content="noindex"><meta name="googlebot" content="noindex,nofollow"><meta name="bingbot" content="noindex"><meta name="twitter:url" content="https://old.example/one"><meta name="description" content="原有 SEO 描述"><meta name="keywords" content="主题"><script type="application/ld+json">' + json.dumps(structured, ensure_ascii=False) + '</script>'
        self.resources['/one.html'] = (body.replace(b'</head>', extra.encode() + b'</head>'), kind)
        report = sync.collect(self.config)
        soup = BeautifulSoup((Path(report['release']) / 'articles/one/index.html').read_text(), 'html.parser')
        canonical = 'https://official.example/zh/news/articles/one/'
        robots = [node for node in soup.select('meta[name]') if node['name'].lower() in ('robots', 'googlebot', 'bingbot')]
        self.assertEqual([(node['name'], node['content']) for node in robots], [('robots', 'index,follow,max-image-preview:large')])
        self.assertEqual(len(soup.select('link[rel="canonical"]')), 1)
        self.assertEqual(soup.select_one('link[rel="canonical"]')['href'], canonical)
        self.assertEqual(soup.select_one('meta[name="twitter:url"]')['content'], canonical)
        self.assertEqual(soup.select_one('meta[name="description"]')['content'], '原有 SEO 描述')
        data = json.loads(soup.select_one('script[type="application/ld+json"]').string)['@graph']
        article = data[0]
        self.assertEqual(article['mainEntityOfPage']['@id'], canonical)
        self.assertEqual(article['@id'], canonical + '#article')
        self.assertEqual(article['url'], canonical)
        self.assertEqual(article['headline'], '原有 SEO 标题')
        self.assertEqual(article['keywords'], ['主题'])
        self.assertEqual(article['citation']['url'], 'https://research.example/report')
        self.assertEqual(article['publisher']['url'], 'https://official.example')
        self.assertEqual(data[1]['itemListElement'][1]['item'], canonical)

    def test_source_url_change_keeps_official_slug_url(self):
        """应用原文地址改变但 id 不变：抓取新地址，官网路径保持稳定且列表不泄露源地址。"""
        first = self.build_publish()
        self.resources['/renamed.html'] = self.resources.pop('/one.html')
        self.feed['items'][0]['url'] = self.source + '/renamed.html'
        self.save_feed()
        second = sync.collect(self.config)
        self.assertEqual(first['urls'], second['urls'])
        page = BeautifulSoup((Path(second['release']) / 'index.html').read_text(), 'html.parser')
        items = json.loads(page.find(id='feed-snapshot').string)['items']
        self.assertEqual(next(item['url'] for item in items if item['id'] == 'one'),
                         'https://official.example/zh/news/articles/one/')

    def test_data_directory_cannot_be_inside_source_repository(self):
        """配置直接指向源码里的数据目录必须失败，防止生成物混入全站构建/部署边界。"""
        with self.assertRaisesRegex(sync.SyncError, '源码仓库之外'):
            sync.Config({**self.env, 'NEWS_WORK_DIR': str(MODULE_PATH.parents[2] / 'news-data')})

    def test_standalone_server_script_allows_separate_data_directory(self):
        """服务器只部署脚本目录而没有 Git 仓库时，仍能使用与代码平级的独立数据目录。"""
        with patch.object(sync, 'HERE', self.root / 'installed-script'):
            config = sync.Config(self.env)
        self.assertEqual(config.work, (self.root / 'work').resolve())

    def test_same_url_image_change_triggers_new_release(self):
        """只覆盖图片字节，保持 Feed、HTML 和日期完全不变，也必须识别并更新引用。"""
        first = self.build_publish()
        self.resources['/image.png'] = (b'image-replaced', 'image/png')
        second = sync.collect(self.config)
        self.assertTrue(second['changed'])
        self.assertNotEqual(first['version'], second['version'])
        old = BeautifulSoup((Path(first['release']) / 'articles/one/index.html').read_text(), 'html.parser')
        new = BeautifulSoup((Path(second['release']) / 'articles/one/index.html').read_text(), 'html.parser')
        self.assertNotEqual(old.img['src'], new.img['src'])

    def test_css_change_triggers_even_when_feed_unchanged(self):
        """只修改同地址 CSS，防止只比较 Feed 时遗漏样式更新。"""
        first = self.build_publish()
        self.resources['/shared.css'] = (b'article { color: blue; }', 'text/css')
        second = sync.collect(self.config)
        self.assertNotEqual(first['version'], second['version'])

    def test_unpublish_removes_page_sitemap_and_keeps_cdn_tombstone(self):
        """从完整 Feed 下线文章，候选不再含详情/站点地图条目；切换后保存旧 URL 刷新清单。"""
        self.build_publish()
        self.feed['items'] = self.feed['items'][:1]; self.feed['_item_count'] = 1; self.save_feed()
        report = sync.collect(self.config)
        self.assertEqual(report['removed_count'], 1)
        self.assertFalse((Path(report['release']) / 'articles/two/index.html').exists())
        self.assertNotIn('articles/two/', (Path(report['release']) / 'sitemap.xml').read_text())
        sync.publish(self.config, report['version'], self.env)
        self.assertFalse((self.root / 'live/articles/two/index.html').exists())
        self.assertIn('https://official.example/zh/news/articles/two/', sync.load_json(self.config.work / 'pending-cdn.json'))

    def test_missing_resource_does_not_replace_active_release(self):
        """仍在 Feed 中的文章图片返回 404 属于失败，不是删除指令；保持 live 原样。"""
        first = self.build_publish()
        del self.resources['/image.png']
        with self.assertRaisesRegex(sync.SyncError, 'HTTP 404'): sync.collect(self.config)
        self.assertEqual((self.root / 'live').resolve(), Path(first['release']))

    def test_incomplete_feed_cannot_delete(self):
        """条目计数不一致、分页、空清单分别拒绝，防止下载故障被解释为批量下线。"""
        original = copy.deepcopy(self.feed)
        for change in ({'_item_count': 3}, {'next_url': self.source + '/next'}, {'items': [], '_item_count': 0}):
            with self.subTest(change=change):
                self.feed = {**original, **change}; self.save_feed()
                with self.assertRaises(sync.SyncError): sync.collect(self.config)

    def test_active_script_is_rejected(self):
        """来源正文不能将运行时脚本带进官网同源；明确失败而非静默删除造成交互缺损。"""
        body, kind = self.resources['/one.html']
        self.resources['/one.html'] = (body.replace(b'</body>', b'<script>alert(1)</script></body>'), kind)
        with self.assertRaisesRegex(sync.SyncError, '可执行脚本'): sync.collect(self.config)

    def test_publish_refuses_real_directory_and_modified_candidate(self):
        """显式发布也不得覆盖已有实体官网目录，或发布生成后被修改的候选。"""
        report = sync.collect(self.config)
        (self.root / 'live').mkdir()
        with self.assertRaisesRegex(sync.SyncError, '实体目录'): sync.publish(self.config, report['version'], self.env)
        (self.root / 'live').rmdir()
        (Path(report['release']) / 'index.html').write_text('unexpected')
        with self.assertRaisesRegex(sync.SyncError, '候选文件'): sync.publish(self.config, report['version'], self.env)

    def test_cdn_failure_keeps_pending_urls_for_retry(self):
        """CDN 失败发生在源站切换后，必须保留已生效状态和待刷新地址，不把失败当作完全成功。"""
        report = sync.collect(self.config)
        with patch.object(sync, 'refresh_cdn', side_effect=sync.SyncError('CDN unavailable')):
            with self.assertRaisesRegex(sync.SyncError, 'CDN unavailable'): sync.publish(self.config, report['version'], self.env)
        self.assertEqual(sync.load_json(self.config.work / 'active.json')['version'], report['version'])
        self.assertTrue(sync.load_json(self.config.work / 'pending-cdn.json'))

    def test_stale_candidate_cannot_overwrite_newer_publish(self):
        """候选生成后另一版先发布，应拒绝陈旧候选覆盖；重新 build 才可确立新基线。"""
        self.build_publish()
        self.resources['/image.png'] = (b'image-second', 'image/png')
        older = sync.collect(self.config)
        self.resources['/image.png'] = (b'image-third', 'image/png')
        newer = sync.collect(self.config)
        sync.publish(self.config, newer['version'], self.env)
        with self.assertRaisesRegex(sync.SyncError, '基线已过期'):
            sync.publish(self.config, older['version'], self.env)
        self.assertEqual((self.root / 'live').resolve(), Path(newer['release']))

    def test_old_assets_survive_release_switch_without_old_article_pages(self):
        """资源内容变化时旧哈希文件仍可用，避免旧缓存 HTML 缺图；详情删除另有独立验证。"""
        old = self.build_publish()
        old_files = {path.name for path in (Path(old['release']) / 'assets').iterdir()}
        self.resources['/image.png'] = (b'image-next', 'image/png')
        new = sync.collect(self.config)
        new_files = {path.name for path in (Path(new['release']) / 'assets').iterdir()}
        self.assertTrue(old_files < new_files)

    def test_embedded_json_keeps_angle_bracket_text_without_script_injection(self):
        """包含小于号的标题序列化后应还原原文，且不能关闭内嵌 JSON script 节点。"""
        self.feed['items'][0]['title'] = '标题 </script><script>不执行</script>'
        self.save_feed()
        report = sync.collect(self.config)
        page = BeautifulSoup((Path(report['release']) / 'index.html').read_text(), 'html.parser')
        data = json.loads(page.find(id='feed-snapshot').string)
        self.assertEqual(data['items'][0]['title'], self.feed['items'][0]['title'])
        self.assertNotIn('<script>不执行</script>', str(page.find(id='feed-snapshot')))

    def test_generated_release_is_readable_by_web_server_user(self):
        """tempfile 默认 0700；发布快照必须允许不同用户的 Nginx 遍历目录及读取页面。"""
        report = sync.collect(self.config)
        release = Path(report['release'])
        self.assertEqual(release.stat().st_mode & 0o005, 0o005)
        self.assertTrue((release / 'index.html').stat().st_mode & 0o004)

    def test_restoring_old_content_keeps_intermediate_cached_assets(self):
        """A→B→A 内容回退也要保留 B 的资源，避免缓存中的 B 详情突然缺图。"""
        original = self.resources['/image.png']
        first = self.build_publish()
        self.resources['/image.png'] = (b'intermediate-image', 'image/png')
        middle = self.build_publish()
        image = BeautifulSoup((Path(middle['release']) / 'articles/one/index.html').read_text(), 'html.parser').img['src']
        self.resources['/image.png'] = original
        final = self.build_publish()
        self.assertTrue((Path(final['release']) / image.removeprefix('/zh/news/')).is_file())
        self.assertFalse(sync.collect(self.config)['changed'])

    def test_collect_cannot_approve_tampered_existing_candidate(self):
        """候选被篡改后再次 build，不能重算哈希并把篡改内容认证为合法版本。"""
        report = sync.collect(self.config)
        (Path(report['release']) / 'index.html').write_text('tampered candidate')
        with self.assertRaisesRegex(sync.SyncError, '候选'):
            sync.collect(self.config)

    def test_duplicate_source_urls_are_rejected(self):
        """两个不同 ID 不能共享源 URL，否则 URL 映射会覆盖并令一张卡片指错文章。"""
        self.feed['items'][1]['url'] = self.feed['items'][0]['url']; self.save_feed()
        with self.assertRaisesRegex(sync.SyncError, 'URL'):
            sync.collect(self.config)

    def test_duplicate_id_is_rejected_before_page_generation(self):
        """两条来源 URL 不同但 id 相同时也必须拒绝，稳定 slug 不能被不同文章争用。"""
        self.feed['items'][1]['id'] = 'one'; self.save_feed()
        with self.assertRaisesRegex(sync.SyncError, '重复文章 ID'):
            sync.collect(self.config)

    def test_html_only_edit_updates_official_detail(self):
        """保持 Feed、图片和 CSS 不变，仅修改原文 HTML，官网详情仍必须生成新版本。"""
        first = self.build_publish()
        body, kind = self.resources['/one.html']
        self.resources['/one.html'] = (body.replace('原始正文不重排'.encode(), '后台修改后的正文'.encode()), kind)
        second = self.build_publish()
        self.assertNotEqual(first['version'], second['version'])
        self.assertIn('后台修改后的正文', (self.root / 'live/articles/one/index.html').read_text())

    def test_metadata_edit_updates_listing_without_changing_url(self):
        """只修改 Feed 的标题/标签时列表更新，详情路径仍由同一 id 保持稳定。"""
        first = self.build_publish()
        self.feed['items'][0].update(title='新标题', tags=['新主题']); self.save_feed()
        second = self.build_publish()
        self.assertEqual(first['urls'], second['urls'])
        soup = BeautifulSoup((self.root / 'live/index.html').read_text(), 'html.parser')
        items = json.loads(soup.find(id='feed-snapshot').string)['items']
        item = next(item for item in items if item['id'] == 'one')
        self.assertEqual((item['title'], item['tags']), ('新标题', ['新主题']))

    def test_slug_collision_is_rejected(self):
        """非法 ID 的哈希兜底与另一个合法 ID 路径冲突时必须拒绝，不能覆盖详情。"""
        self.feed['items'][0]['id'] = '中文'
        # 固定已知 SHA-256 值；预期路径不调用待测 article_path 推导。
        self.feed['items'][1]['id'] = 'id-72726d8818f693066ceb69afa364218b692e62ea92b385782363780f47529c21'
        self.save_feed()
        with self.assertRaisesRegex(sync.SyncError, '路径'):
            sync.collect(self.config)

    def test_summary_uses_content_text_when_summary_absent(self):
        """JSON Feed 允许仅提供 content_text；列表的静态和增强视图都应得到摘要。"""
        self.feed['items'][0].pop('summary')
        self.feed['items'][0]['content_text'] = '正文站提供的文章摘要'
        self.save_feed()
        report = sync.collect(self.config)
        soup = BeautifulSoup((Path(report['release']) / 'index.html').read_text(), 'html.parser')
        self.assertIn('正文站提供的文章摘要', soup.select_one('#cards').get_text())
        items = json.loads(soup.find(id='feed-snapshot').string)['items']
        self.assertEqual(next(item['summary'] for item in items if item['id'] == 'one'), '正文站提供的文章摘要')

    def test_http_304_uses_verified_cache_and_repairs_corruption(self):
        """有效缓存使用 304；损坏缓存须无条件重取，验证生产 build 边界能恢复而非永久 fallback。"""
        self.etags['/image.png'] = '"image-v1"'
        self.build_publish()
        self.assertFalse(sync.collect(self.config)['changed'])
        self.assertIn(('/image.png', '"image-v1"'), self.requests)
        cache = sync.load_json(self.config.work / 'cache/index.json')
        (self.config.work / 'cache' / cache[self.source + '/image.png']['hash']).write_bytes(b'corrupt')
        self.requests.clear()
        report = sync.collect_available(self.config)
        self.assertFalse(report.get('fallback', False))
        self.assertFalse(report['changed'])
        self.assertIn(('/image.png', None), self.requests)
        self.assertEqual((self.config.work / 'cache' / cache[self.source + '/image.png']['hash']).read_bytes(), b'image-first')

    def test_corrupt_cache_failed_repair_is_an_operational_error(self):
        """损坏缓存重下载 404 必须报告内部恢复失败，保留 active，不能伪装成正常跳过。"""
        self.build_publish()
        active = (self.config.work / 'active.json').read_bytes()
        cache = sync.load_json(self.config.work / 'cache/index.json')
        (self.config.work / 'cache' / cache[self.source + '/image.png']['hash']).write_bytes(b'corrupt')
        del self.resources['/image.png']
        with self.assertRaisesRegex(sync.CacheError, '缓存'):
            sync.collect_available(self.config)
        self.assertEqual((self.config.work / 'active.json').read_bytes(), active)

    def test_corrupt_cache_index_is_not_hidden_by_source_fallback(self):
        """缓存索引不是来源数据；坏 JSON 必须让生产 build 报告故障，不能返回 changed=false。"""
        self.build_publish()
        (self.config.work / 'cache/index.json').write_text('broken index')
        with self.assertRaisesRegex(sync.CacheError, '索引'):
            sync.collect_available(self.config)

    def test_jsonld_article_images_are_mirrored_without_rewriting_external_entities(self):
        """文章 image 的字符串/数组/ImageObject 均镜像；publisher/citation 的图像与实体标识保持原义。"""
        image_path = '/api/whwy/app123/storages/preview?file=structured.svg'
        self.resources[image_path] = (b'<svg/>', 'image/svg+xml')
        expected = 'https://official.example/zh/news/assets/structured.svg'
        for shape in (image_path, [image_path], {'@type': 'ImageObject', 'url': image_path,
                                               'contentUrl': self.source + image_path, 'caption': '原图'}):
            with self.subTest(shape=shape):
                entity = {'@type': 'Article', 'image': shape,
                          'publisher': {'logo': 'https://publisher.example/logo.svg'},
                          'citation': {'image': 'https://citation.example/image.png'}}
                body = '<html><head><script type="application/ld+json">' + json.dumps({'@graph': [entity]}) + '</script></head><body><article>正文</article></body></html>'
                self.resources['/one.html'] = (body.encode(), 'text/html')
                report = sync.collect(self.config)
                soup = BeautifulSoup((Path(report['release']) / 'articles/one/index.html').read_text(), 'html.parser')
                result = json.loads(soup.find('script').string)['@graph'][0]
                target = expected if isinstance(shape, str) else [expected] if isinstance(shape, list) else {
                    '@type': 'ImageObject', 'url': expected, 'contentUrl': expected, 'caption': '原图'}
                self.assertEqual(result['image'], target)
                self.assertEqual(result['publisher'], entity['publisher'])
                self.assertEqual(result['citation'], entity['citation'])
                self.assertEqual((Path(report['release']) / 'assets/structured.svg').read_bytes(), b'<svg/>')

    def test_redirect_with_embedded_credentials_is_rejected(self):
        """自动跟随来源重定向，但不允许 URL 携带隐式凭证。"""
        self.redirects['/image.png'] = 'https://user:secret@example.com/image.png'
        with self.assertRaisesRegex(sync.SyncError, '无内嵌凭证'):
            sync.collect(self.config)

    def test_allowed_redirect_resolves_resources_from_final_url(self):
        """HTML 在允许域名内迁移目录后，样式相对地址应基于最终响应 URL 解析。"""
        self.redirects['/one.html'] = self.source + '/moved/one.html'
        body, kind = self.resources['/one.html']
        self.resources['/moved/one.html'] = (body.replace(b'shared.css', b'theme.css'), kind)
        self.resources['/moved/theme.css'] = (b'article { color: green; }', 'text/css')
        report = sync.collect(self.config)
        self.assertTrue((Path(report['release']) / 'articles/one/index.html').is_file())
        self.assertIn(('/moved/theme.css', None), self.requests)

    def test_unpublished_article_returns_under_same_official_url(self):
        """下线后原 ID 再次发布，恢复官网原路径并重新加入列表与 sitemap。"""
        original = copy.deepcopy(self.feed)
        first = self.build_publish()
        self.feed['items'] = self.feed['items'][:1]; self.feed['_item_count'] = 1; self.save_feed()
        self.build_publish()
        self.feed = original; self.save_feed()
        restored = self.build_publish()
        self.assertEqual(first['urls'], restored['urls'])
        self.assertTrue((self.root / 'live/articles/two/index.html').is_file())
        self.assertIn('https://official.example/zh/news/articles/two/', (self.root / 'live/sitemap.xml').read_text())

    def test_resource_limit_failure_keeps_active_release(self):
        """已发布后图片异常膨胀超过配置上限，本次失败且入口仍指向之前完整版本。"""
        first = self.build_publish()
        self.resources['/image.png'] = (b'x' * 20001, 'image/png')
        limited = sync.Config({**self.env, 'NEWS_MAX_RESOURCE_BYTES': '20000'})
        with self.assertRaisesRegex(sync.SyncError, '单资源大小超限'):
            sync.collect(limited)
        self.assertEqual((self.root / 'live').resolve(), Path(first['release']))

    def test_empty_feed_requires_opt_in_and_removes_all_pages(self):
        """显式允许零条完整清单后可全部下线，并保留旧详情的 CDN 刷新记录。"""
        self.build_publish()
        self.feed['items'] = []; self.feed['_item_count'] = 0; self.save_feed()
        config = sync.Config({**self.env, 'NEWS_ALLOW_EMPTY_FEED': '1'})
        report = sync.collect(config)
        self.assertEqual(report['removed_count'], 2)
        sync.publish(config, report['version'], self.env)
        self.assertFalse((self.root / 'live/articles/one/index.html').exists())
        self.assertFalse((self.root / 'live/articles/two/index.html').exists())
        self.assertIn('https://official.example/zh/news/articles/one/', sync.load_json(config.work / 'pending-cdn.json'))

    def test_scheduler_defaults_to_build_then_publishes_only_when_enabled(self):
        """真实 shell/CLI 执行整条定时入口；默认无 live，开启后发布，第三次无变化仍重试 CDN。"""
        environment = {**os.environ, **self.env, 'NEWS_PYTHON': sys.executable, 'NEWS_ENABLE_PUBLISH': '0'}
        command = ['bash', str(MODULE_PATH.parent / 'run-news-sync.sh')]
        preview = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(preview.stdout)['changed'])
        self.assertFalse((self.root / 'live').exists())
        environment['NEWS_ENABLE_PUBLISH'] = '1'
        live = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
        self.assertIn('published', json.loads(live.stdout.splitlines()[-1]))
        previous_target = (self.root / 'live').resolve()
        again = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(again.stdout.splitlines()[0])['changed'])
        self.assertGreater(json.loads(again.stdout.splitlines()[-1])['pending'], 0)
        self.assertEqual((self.root / 'live').resolve(), previous_target)


if __name__ == '__main__':
    unittest.main()
