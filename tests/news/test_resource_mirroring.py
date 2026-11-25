"""资源镜像回归：图片、视频及依赖必须真实下载、改址、落盘并进入 CDN 刷新请求。

每例使用独立 HTTP 来源与发布目录，来源字节作为独立预期；仅 CDN HTTP 传输用替身。
合成媒体用于验证搬运，不冒充浏览器解码；失败用例从完整发布基线验证旧版保持不变。
"""
from pathlib import Path
import json
import re
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from bs4 import BeautifulSoup

import test_sync_news as fixtures
from test_cdn import RecordingTransport

sync = fixtures.sync


class ResourceMirroringTests(unittest.TestCase):
    """按资源引用、资源更新及失败阶段拆分，保持非目标条件始终有效。"""

    def setUp(self):
        """复用现有真实 HTTP 来源；不把同步逻辑替换成测试实现。"""
        self.f = fixtures.NewsSyncTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def add_markup(self, markup):
        """在第一篇有效文章内追加被测引用，保留其余 HTML、Feed 与原有依赖。"""
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'</article>', markup.encode() + b'</article>'), kind)

    def publish_with_cdn(self):
        """执行真实抓取和发布，返回落盘页及实际签名请求中的 URL；只替换云端网络。"""
        report = sync.collect(self.f.config)
        transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.publish(self.f.config, report['version'], {**self.f.env, 'NEWS_CDN_MODE': 'aliyun',
                         'ALIBABA_CLOUD_ACCESS_KEY_ID': 'test-key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'test-secret'})
        page = BeautifulSoup((self.f.root / 'live/articles/one/index.html').read_text(), 'html.parser')
        urls = [url for request in transport.requests for url in parse_qs(request.data.decode())['ObjectPath'][0].splitlines()]
        return page, urls

    def assert_asset(self, reference, expected, urls):
        """校验官网地址、实际字节和真实刷新请求三者对应，不通过被测哈希算法推导预期。"""
        self.assertTrue(reference.startswith('/zh/news/assets/'), reference)
        file = self.f.root / 'live' / reference.split('#')[0].removeprefix('/zh/news/')
        self.assertEqual(file.read_bytes(), expected)
        self.assertIn('https://official.example' + reference.split('#')[0], urls)

    def test_static_resources_do_not_require_format_allowlist(self):
        """MP4、FLV、WebM、未知后缀、无后缀、查询参数与图片均按实际 src 搬运；无格式白名单。"""
        cases = [('movie.mp4', 'video/mp4'), ('movie.flv', 'video/x-flv'), ('movie.webm', 'video/webm'),
                 ('movie.custom', 'application/octet-stream'), ('download?id=7', 'video/mp4'),
                 ('picture?size=2', 'image/webp'), ('poster.avif', 'image/avif')]
        for index, (url, kind) in enumerate(cases):
            self.f.resources['/' + url] = (f'payload-{index}'.encode(), kind)
            self.add_markup(f'<video id="r{index}" src="{url}"></video>')
        page, urls = self.publish_with_cdn()
        for index, (url, kind) in enumerate(cases):
            self.assert_asset(page.find(id=f'r{index}')['src'], f'payload-{index}'.encode(), urls)
        self.assertTrue(page.find(id='r4')['src'].endswith('.mp4'))
        self.assertTrue(page.find(id='r5')['src'].endswith('.webp'))

    def test_storage_media_preserves_existing_file_contract(self):
        """内容 App 的 storage file 协议必须同样允许视频、音频和无扩展名媒体，图片名称不变。"""
        for name, kind in [('clip.mp4', 'video/mp4'), ('clip.flv', 'video/x-flv'), ('sound.mp3', 'audio/mpeg'),
                           ('opaque', 'video/mp4'), ('cover.png', 'image/png')]:
            url = '/api/whwy/app123/storages/preview?file=' + name
            self.f.resources[url] = (name.encode(), kind)
            self.add_markup(f'<source id="{name}" src="{url}">')
        page, urls = self.publish_with_cdn()
        for node in page.select('source'):
            self.assert_asset(node['src'], node['id'].encode(), urls)
        self.assertEqual(page.find(id='cover.png')['src'], '/zh/news/assets/cover.png')
        self.assertTrue(page.find(id='opaque')['src'].endswith('.mp4'))

    def test_source_poster_track_and_srcset_are_mirrored(self):
        """浏览器实际使用的 source、poster、track 与响应式候选全部搬运；每个引用独立核对字节。"""
        for name, kind in [('clip.mp4', 'video/mp4'), ('poster.jpg', 'image/jpeg'), ('caption.vtt', 'text/vtt'),
                           ('small.png', 'image/png'), ('large.png', 'image/png')]:
            self.f.resources['/' + name] = (name.encode(), kind)
        self.add_markup('<video poster="poster.jpg"><source src="clip.mp4"><track src="caption.vtt"></video>'
                        '<picture><source srcset="small.png 1x, large.png 2x"><img src="small.png"></picture>')
        page, urls = self.publish_with_cdn()
        for selector, attr, name in [('video', 'poster', 'poster.jpg'), ('video source', 'src', 'clip.mp4'),
                                      ('track', 'src', 'caption.vtt'), ('picture img', 'src', 'small.png')]:
            self.assert_asset(page.select_one(selector)[attr], name.encode(), urls)
        for value, name in zip(page.select_one('picture source')['srcset'].split(','), ['small.png', 'large.png']):
            self.assert_asset(value.strip().split()[0], name.encode(), urls)

    def test_media_only_change_refreshes_resource_without_feed_edit(self):
        """相同 Feed/HTML 下仅固定名称视频变更，实际字节更新且该 URL 刷新；不误刷旧图片。"""
        url = '/api/whwy/app123/storages/preview?file=clip.flv'
        self.f.resources[url] = (b'video-before', 'video/x-flv')
        self.add_markup(f'<video src="{url}"></video>')
        self.publish_with_cdn()
        feed_before = self.f.resources['/feed.json']
        self.f.resources[url] = (b'video-after', 'video/x-flv')
        page, urls = self.publish_with_cdn()
        self.assert_asset(page.video['src'], b'video-after', urls)
        self.assertNotIn('https://official.example' + page.img['src'], urls)
        self.assertEqual(self.f.resources['/feed.json'], feed_before)
        self.assertFalse(sync.collect(self.f.config)['changed'])

    def test_deferred_image_attributes_mirror_bytes_without_enabling_browser_load(self):
        """延迟图与响应式候选均镜像，但保持 data 属性，不提前赋 src/srcset 或改作者事件。"""
        for name in ('zoom.png', 'small.png', 'large.png'):
            self.f.resources['/' + name] = (name.encode(), 'image/png')
        self.add_markup('<picture><source id="variants" data-srcset="small.png 640w, large.png 1600w">'
                        '<img id="zoom" data-src="zoom.png" width="640" height="360" loading="lazy"'
                        ' sizes="100vw" onclick="this.src=this.dataset.src"></picture>'
                        '<div id="custom" data-src="author-defined-value">自由组件</div>')
        page, urls = self.publish_with_cdn()
        image = page.find(id='zoom')
        self.assert_asset(image['data-src'], b'zoom.png', urls)
        self.assertNotIn('src', image.attrs)
        self.assertEqual(image['onclick'], 'this.src=this.dataset.src')
        self.assertEqual((image['width'], image['height'], image['loading'], image['sizes']), ('640', '360', 'lazy', '100vw'))
        source = page.find(id='variants')
        self.assertNotIn('srcset', source.attrs)
        for value, name, width in zip(source['data-srcset'].split(','), ('small.png', 'large.png'), ('640w', '1600w')):
            reference, descriptor = value.strip().split()
            self.assert_asset(reference, name.encode(), urls)
            self.assertEqual(descriptor, width)
        self.assertEqual(page.find(id='custom')['data-src'], 'author-defined-value')

    def test_deferred_image_with_source_base_still_targets_official_assets(self):
        """作者保留来源 base 时，延迟属性也使用官网绝对资源地址，避免点击后回到来源。"""
        self.f.resources['/pictures/zoom.png'] = (b'zoom-with-base', 'image/png')
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'<head>', b'<head><base href="/pictures/">')
            .replace(b'href="shared.css"', b'href="/shared.css"')
            .replace(b'</article>', b'<img id="zoom" data-src="zoom.png" data-srcset="zoom.png 1x"></article>'), kind)
        page, urls = self.publish_with_cdn()
        image = page.find(id='zoom')
        self.assertTrue(image['data-src'].startswith('https://official.example/zh/news/assets/'))
        self.assert_asset(image['data-src'].removeprefix('https://official.example'), b'zoom-with-base', urls)
        self.assertEqual(image['data-srcset'], image['data-src'] + ' 1x')

    def test_missing_media_keeps_previous_release_and_recovers(self):
        """下载失败时不换 live；来源恢复后新媒体完整发布，不能把失败当成文章下线。"""
        url = '/clip.flv'
        self.f.resources[url] = (b'old-video', 'video/x-flv')
        self.add_markup('<video src="clip.flv"></video>')
        self.publish_with_cdn()
        active = (self.f.config.work / 'active.json').read_bytes()
        live = (self.f.root / 'live').resolve()
        del self.f.resources[url]
        with self.assertRaisesRegex(sync.SyncError, 'HTTP 404'):
            sync.collect(self.f.config)
        self.assertEqual((self.f.root / 'live').resolve(), live)
        self.assertEqual((self.f.config.work / 'active.json').read_bytes(), active)
        self.f.resources[url] = (b'recovered-video', 'video/x-flv')
        page, urls = self.publish_with_cdn()
        self.assert_asset(page.video['src'], b'recovered-video', urls)

    def test_css_image_set_and_nested_font(self):
        """image-set 字符串及 url 候选、嵌套 @import/字体都搬运；type() 和 content 字符串保持原意。"""
        self.f.resources['/shared.css'] = (b'@import /* comment */ "nested.css";'
            b'article{background:image-set("one.webp" 1x type("image/webp"), url(two.webp) 2x);}'
            b'p::after{content:"url(not-a-file)"}', 'text/css')
        self.f.resources['/nested.css'] = (b'@font-face{font-family:x;src:url(font.woff2)}', 'text/css')
        for name, kind in [('one.webp', 'image/webp'), ('two.webp', 'image/webp'), ('font.woff2', 'font/woff2')]:
            self.f.resources['/' + name] = (name.encode(), kind)
        page, urls = self.publish_with_cdn()
        css = (self.f.root / 'live' / page.select_one('link[rel="stylesheet"]')['href'].removeprefix('/zh/news/')).read_text()
        self.assertIn('type("image/webp")', css)
        self.assertIn('content:"url(not-a-file)"', css)
        for name in ['one.webp', 'two.webp', 'font.woff2']:
            file = next(p for p in (self.f.root / 'live/assets').iterdir() if p.read_bytes() == name.encode())
            self.assert_asset('/zh/news/assets/' + file.name, name.encode(), urls)
        self.assertNotIn('"one.webp"', css)

    def test_truncated_download_keeps_cache_and_release_then_recovers(self):
        """HTTP 200 但字节少于 Content-Length 时拒绝发布；旧缓存不污染，恢复后完整资源可发布。"""
        self.f.resources['/clip.mp4'] = (b'complete-before', 'video/mp4')
        self.add_markup('<video src="clip.mp4"></video>')
        self.publish_with_cdn()
        active = (self.f.config.work / 'active.json').read_bytes()
        cache = (self.f.config.work / 'cache/index.json').read_bytes()
        live = (self.f.root / 'live').resolve()
        self.f.resources['/clip.mp4'] = (b'cut', 'video/mp4')
        self.f.response_lengths['/clip.mp4'] = 100
        with self.assertRaisesRegex(sync.SyncError, '下载不完整|网络异常'):
            sync.collect(self.f.config)
        self.assertEqual((self.f.config.work / 'active.json').read_bytes(), active)
        self.assertEqual((self.f.config.work / 'cache/index.json').read_bytes(), cache)
        self.assertEqual((self.f.root / 'live').resolve(), live)
        self.f.resources['/clip.mp4'] = (b'complete-after', 'video/mp4')
        self.f.response_lengths['/clip.mp4'] = len(b'complete-after')
        page, urls = self.publish_with_cdn()
        self.assert_asset(page.video['src'], b'complete-after', urls)

    def test_declared_resource_limit_is_checked_before_accepting_payload(self):
        """其他输入合法且实际响应很小，仅声明长度超限就拒绝，不能让误配大视频进入候选。"""
        first = self.f.build_publish()
        self.f.resources['/clip.mp4'] = (b'video', 'video/mp4')
        self.f.response_lengths['/clip.mp4'] = self.f.config.resource_limit + 1
        self.add_markup('<video src="clip.mp4"></video>')
        with self.assertRaisesRegex(sync.SyncError, '资源声明长度'):
            sync.collect(self.f.config)
        self.assertEqual((self.f.root / 'live').resolve(), Path(first['release']))

    def test_svg_embedded_style_and_external_image(self):
        """SVG 依赖由同一镜像器递归处理，保留内部 # 引用；不将样式或图片遗漏在来源域名。"""
        self.f.resources['/diagram.svg'] = (b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url("shape.css");</style>'
            b'<image href="tile.png"/><rect fill="url(#paint)"/></svg>', 'image/svg+xml')
        self.f.resources['/shape.css'] = (b'rect{fill:red}', 'text/css')
        self.f.resources['/tile.png'] = (b'tile-bytes', 'image/png')
        self.add_markup('<img id="svg" src="diagram.svg">')
        page, urls = self.publish_with_cdn()
        svg = (self.f.root / 'live' / page.find(id='svg')['src'].removeprefix('/zh/news/')).read_text()
        self.assertIn('url(#paint)', svg)
        self.assertNotIn('"tile.png"', svg)
        self.assertNotIn('"shape.css"', svg)
        for expected in [b'tile-bytes', b'rect{fill:red}']:
            file = next(p for p in (self.f.root / 'live/assets').iterdir() if p.read_bytes() == expected)
            self.assert_asset('/zh/news/assets/' + file.name, expected, urls)

    def test_vod_hls_mirrors_playlist_segments_and_key(self):
        """静态 HLS 主清单、子清单、分片和密钥完整下载改址；只改分片时重新生成清单并刷新。"""
        self.f.resources['/master.m3u8'] = (b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nsub/vod.m3u8\n', 'application/vnd.apple.mpegurl')
        self.f.resources['/sub/vod.m3u8'] = (b'#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXT-X-KEY:METHOD=AES-128,URI="../key"\n#EXTINF:1,\nseg.ts\n#EXT-X-ENDLIST\n', 'application/vnd.apple.mpegurl')
        self.f.resources['/key'] = (b'0123456789abcdef', 'application/octet-stream')
        self.f.resources['/sub/seg.ts'] = (b'segment-one', 'video/mp2t')
        self.add_markup('<video src="master.m3u8"></video>')
        page, urls = self.publish_with_cdn()
        first_src = page.video['src']
        master = (self.f.root / 'live' / first_src.removeprefix('/zh/news/')).read_text()
        child_ref = next(line for line in master.splitlines() if line and not line.startswith('#'))
        child = (self.f.root / 'live' / child_ref.removeprefix('/zh/news/')).read_text()
        self.assertNotIn('seg.ts', child)
        self.assertNotIn('../key', child)
        self.f.resources['/sub/seg.ts'] = (b'segment-two', 'video/mp2t')
        page, urls = self.publish_with_cdn()
        self.assertNotEqual(page.video['src'], first_src)
        segment = next(p for p in (self.f.root / 'live/assets').iterdir() if p.read_bytes() == b'segment-two')
        self.assert_asset('/zh/news/assets/' + segment.name, b'segment-two', urls)
        self.assertIn('https://official.example' + page.video['src'], urls)

    def test_live_hls_keeps_original_stream_target(self):
        """直播清单继续指向来源，由播放器持续获取新分片，不冻结内容也不拒绝整篇文章。"""
        self.f.resources['/live.m3u8'] = (b'#EXTM3U\n#EXTINF:1,\nseg.ts\n','application/vnd.apple.mpegurl')
        self.f.resources['/seg.ts'] = (b'segment','video/mp2t')
        self.add_markup('<video src="live.m3u8"></video>')
        self.f.build_publish()
        page = BeautifulSoup((self.f.root / 'live/articles/one/index.html').read_text(), 'html.parser')
        self.assertEqual(page.video['src'], self.f.source + '/live.m3u8')

    def test_nested_dependency_cycle_preserves_previous_release(self):
        """SVG → CSS → SVG 构成循环时明确失败，不能无限递归或只发布一部分。"""
        first = self.f.build_publish()
        self.f.resources['/diagram.svg'] = (b'<svg><style>@import "shape.css";</style></svg>', 'image/svg+xml')
        self.f.resources['/shape.css'] = (b'rect{fill:url(diagram.svg)}','text/css')
        self.add_markup('<img src="diagram.svg">')
        with self.assertRaisesRegex(sync.SyncError, '循环'):
            sync.collect(self.f.config)
        self.assertEqual((self.f.root / 'live').resolve(), Path(first['release']))


if __name__ == '__main__':
    unittest.main()
