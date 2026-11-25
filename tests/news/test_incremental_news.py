"""按条目更新时间增量同步：真实 HTTP 请求证明未变文章不重下，真实发布证明 CDN 仅刷新变化内容。"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from bs4 import BeautifulSoup
import test_sync_news as fixtures
from test_cdn import RecordingTransport

sync = fixtures.sync


class IncrementalNewsTests(unittest.TestCase):
    """每例先建立完整基线；独立资源确保一个条目变化不会被共享图片掩盖。"""

    def setUp(self):
        """两篇文章都有 date_modified，各自引用独立 FLV；保留固定 Feed 协议。"""
        self.f = fixtures.NewsSyncTests(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        for item in self.f.feed['items']:
            slug = item['id']; item['date_modified'] = '2026-11-18T10:00:00+08:00'
            self.f.resources['/' + slug + '.html'] = (f'<html><head><title>{slug}</title></head><body><article><video src="{slug}.flv"></video></article></body></html>'.encode(), 'text/html')
            self.f.resources['/' + slug + '.flv'] = (slug.encode(), 'video/x-flv')
        self.f.save_feed(); self.first = self.f.build_publish(); self.f.requests.clear()
        sync.atomic_json(self.f.config.work / 'pending-cdn.json', [])

    def publish(self):
        """真实增量构建与发布，只有阿里云传输隔离，返回实际提交的刷新 URL。"""
        report = sync.collect(self.f.config); transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.publish(self.f.config, report['version'], {**self.f.env, 'NEWS_CDN_MODE':'aliyun',
                         'ALIBABA_CLOUD_ACCESS_KEY_ID':'test-key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET':'test-secret'})
        return [u for r in transport.requests for u in parse_qs(r.data.decode())['ObjectPath'][0].splitlines()]

    def test_feed_generation_change_only_requests_feed(self):
        """仅 Feed 生成时间变化，两个条目修改时间均相同：只检查 Feed，无文章或媒体下载、无新发布。"""
        self.f.feed['_generated_at'] = 'new-clock'; self.f.save_feed()
        report = sync.collect(self.f.config)
        self.assertFalse(report['changed'])
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/feed.json'])
        self.assertEqual((self.f.root / 'live').resolve(), Path(self.first['release']))

    def test_one_changed_article_never_downloads_or_refreshes_other(self):
        """只更新第一篇时间和视频字节，第二篇无 HTTP 请求、CDN 刷新或正文变化。"""
        old_two = (self.f.root / 'live/articles/two/index.html').read_bytes()
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T11:00:00+08:00'
        self.f.resources['/one.flv'] = (b'new-one', 'video/x-flv'); self.f.save_feed()
        urls = self.publish()
        paths = [p for p, _ in self.f.requests]
        self.assertIn('/one.html', paths); self.assertIn('/one.flv', paths)
        self.assertNotIn('/two.html', paths); self.assertNotIn('/two.flv', paths)
        self.assertFalse(any('/articles/two' in u for u in urls))
        self.assertEqual((self.f.root / 'live/articles/two/index.html').read_bytes(), old_two)
        self.f.requests.clear(); self.assertFalse(sync.collect(self.f.config)['changed'])
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/feed.json'])

    def test_seo_updated_at_is_authoritative(self):
        """seo.updatedAt 经现有规范化成为 date_modified，变化时重新读取条目资源。"""
        self.f.feed['items'][0]['seo'] = {'updatedAt':'2026-11-18T12:00:00+08:00'}
        self.f.save_feed(); self.publish()
        self.assertIn('/one.html', [p for p, _ in self.f.requests])
        self.assertNotIn('/two.html', [p for p, _ in self.f.requests])

    def test_content_app_timezone_free_update_timestamp(self):
        """实际 Feed 的 seo.updatedAt 不带时区，仍可作为相等版本标记，不因时区缺失每轮重下。"""
        for item in self.f.feed['items']:
            item['seo'] = {'updatedAt': '2026-11-18T15:25:58'}
        self.f.save_feed(); self.publish(); self.f.requests.clear()
        self.assertFalse(sync.collect(self.f.config)['changed'])
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/feed.json'])

    def test_missing_timestamp_falls_back_to_resource_check(self):
        """没有可信修改时间不能永久冻结资源，兼容旧 Feed 的内容指纹探测。"""
        del self.f.feed['items'][0]['date_modified']; self.f.save_feed(); self.publish(); self.f.requests.clear()
        self.f.resources['/one.flv'] = (b'changed-without-stamp','video/x-flv')
        report = sync.collect(self.f.config)
        self.assertTrue(report['changed']); self.assertIn('/one.flv', [p for p, _ in self.f.requests])
        self.assertNotIn('/two.flv', [p for p, _ in self.f.requests])

    def test_corrupt_cached_media_is_refetched_even_with_same_timestamp(self):
        """时间未变但缓存损坏时仅修复损坏资源，不信任缓存、不误用损坏字节。"""
        cache = sync.load_json(self.f.config.work / 'cache/index.json')
        (self.f.config.work / 'cache' / cache[self.f.source + '/one.flv']['hash']).write_bytes(b'corrupt')
        report = sync.collect(self.f.config)
        self.assertFalse(report['changed'])
        paths = [p for p, _ in self.f.requests]
        self.assertIn('/one.flv', paths); self.assertNotIn('/one.html', paths); self.assertNotIn('/two.flv', paths)

    def test_corrupt_html_repair_cannot_mix_new_html_with_old_dependencies(self):
        """旧时间下仅源 HTML 偷跑且缓存损坏：不能把新 HTML 与旧媒体拼成已验证版本。

        HTTP 返回完整合法 HTML，只有字节与已发布基线不同；拒绝不得依赖 MIME、404 或 Feed 错误。
        来源正式推进版本后，应重新检查整张资源图并恢复发布；实际页面引用的媒体须为新字节。
        """
        active_path = self.f.config.work / 'active.json'
        active = active_path.read_bytes()
        cache = sync.load_json(self.f.config.work / 'cache/index.json')
        (self.f.config.work / 'cache' / cache[self.f.source + '/one.html']['hash']).write_bytes(b'corrupt')
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'<article>', b'<article><p>new-body</p>'), kind)
        self.f.resources['/one.flv'] = (b'new-media', 'video/x-flv')
        with self.assertRaisesRegex(sync.CacheError, '已发布.*不一致'):
            sync.collect_available(self.f.config)
        self.assertEqual(active_path.read_bytes(), active)
        self.assertEqual((self.f.root / 'live').resolve(), Path(self.first['release']))
        self.assertNotIn(b'new-body', (self.f.root / 'live/articles/one/index.html').read_bytes())
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T10:00:00.001+08:00'
        self.f.save_feed(); self.publish()
        self.assertIn(b'new-body', (self.f.root / 'live/articles/one/index.html').read_bytes())
        # 旧哈希资源会为缓存中的旧页面保留；必须沿新页面实际引用验字节，不能只查新文件存在。
        page = BeautifulSoup((self.f.root / 'live/articles/one/index.html').read_text(), 'html.parser')
        media_url = page.video['src']
        self.assertTrue(media_url.startswith('/zh/news/assets/'))
        media = self.f.root / 'live' / media_url.removeprefix('/zh/news/')
        self.assertEqual(media.read_bytes(), b'new-media')

    def test_missing_published_cache_cannot_use_unpublished_download_index(self):
        """仅删旧缓存文件，保留未发布候选的新下载：旧 Feed 不能借新索引授权复用新字节。

        候选曾下载成功但没有 publish；模拟来源清单随后恢复旧版本，来源文件仍是新字节。
        与损坏 HTML 用例独立覆盖文件缺失和探测索引超前，防止索引哈希自洽掩盖版本错配。
        """
        old = sync.load_json(self.f.config.work / 'active.json')
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T11:00:00+08:00'
        self.f.resources['/one.flv'] = (b'unpublished-media', 'video/x-flv')
        self.f.etags['/one.flv'] = '"unpublished-version"'
        self.f.save_feed(); sync.collect(self.f.config)
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T10:00:00+08:00'
        self.f.save_feed()
        published = old['article_sources']['one']['sources'][self.f.source + '/one.flv']
        (self.f.config.work / 'cache' / published['hash']).unlink()
        self.f.requests.clear()
        with self.assertRaisesRegex(sync.CacheError, '已发布.*不一致'):
            sync.collect(self.f.config)
        self.assertIn(('/one.flv', None), self.f.requests)
        self.assertEqual(sync.load_json(self.f.config.work / 'active.json'), old)
        self.assertEqual((self.f.root / 'live').resolve(), Path(self.first['release']))

    def test_missing_published_cache_http_failure_is_not_silent_fallback(self):
        """仅丢失有效基线的媒体缓存且恢复 HTTP 失败：报告缓存故障，不能静默称为未变化。"""
        old = sync.load_json(self.f.config.work / 'active.json')
        info = old['article_sources']['one']['sources'][self.f.source + '/one.flv']
        (self.f.config.work / 'cache' / info['hash']).unlink()
        del self.f.resources['/one.flv']
        with self.assertRaisesRegex(sync.CacheError, '缓存.*恢复失败'):
            sync.collect_available(self.f.config)
        self.assertEqual(sync.load_json(self.f.config.work / 'active.json'), old)

    def test_missing_published_cache_repairs_matching_bytes(self):
        """旧版本缓存缺失而来源仍是相同字节：完整下载修复后不造新版本、不重下其他资源。"""
        old = sync.load_json(self.f.config.work / 'active.json')
        info = old['article_sources']['one']['sources'][self.f.source + '/one.flv']
        path = self.f.config.work / 'cache' / info['hash']
        path.unlink()
        self.assertFalse(sync.collect(self.f.config)['changed'])
        self.assertEqual(path.read_bytes(), b'one')
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/one.flv', '/feed.json'])

    def test_same_second_fractional_version_refreshes_html_and_media(self):
        """同秒修改时间不同：正文及其实际引用的媒体更新，首发日期不变，其他篇不下载。"""
        item = self.f.feed['items'][0]
        first_published = item['date_published']
        item['seo'] = {'updatedAt': '2026-11-18T10:00:00.001+08:00'}
        self.f.save_feed(); self.publish(); self.f.requests.clear()
        item['seo']['updatedAt'] = '2026-11-18T10:00:00.002+08:00'
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'<article>', b'<article><p>millisecond-two</p>'), kind)
        self.f.resources['/one.flv'] = (b'millisecond-media-two', 'video/x-flv')
        self.f.save_feed(); self.publish()
        self.assertIn(b'millisecond-two', (self.f.root / 'live/articles/one/index.html').read_bytes())
        # 下载新媒体但继续引用旧哈希地址仍属失败；以实际 src 解析的目标字节作为独立预期。
        page = BeautifulSoup((self.f.root / 'live/articles/one/index.html').read_text(), 'html.parser')
        media_url = page.video['src']
        self.assertTrue(media_url.startswith('/zh/news/assets/'))
        media = self.f.root / 'live' / media_url.removeprefix('/zh/news/')
        self.assertEqual(media.read_bytes(), b'millisecond-media-two')
        state = sync.load_json(self.f.config.work / 'active.json')
        self.assertEqual(state['article_sources']['one']['stamp'], '2026-11-18T10:00:00.002000+08:00')
        snapshot = BeautifulSoup((self.f.root / 'live/index.html').read_text(), 'html.parser').find(id='feed-snapshot')
        published_item = next(i for i in json.loads(snapshot.text)['items'] if i['id'] == 'one')
        self.assertEqual(published_item['date_published'], first_published)
        self.assertEqual(published_item['date_modified'], '2026-11-18T10:00:00.002+08:00')
        self.assertNotIn('/two.html', [p for p, _ in self.f.requests])
        self.assertNotIn('/two.flv', [p for p, _ in self.f.requests])

    def test_version_update_revalidates_nested_css_after_html_304(self):
        """HTML 与 CSS 均可合法返回 304，但修改时间变化后仍须检查深层图片的新字节。"""
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'<head>', b'<head><link rel="stylesheet" href="one.css">'), kind)
        self.f.resources['/one.css'] = (b'@import "nested.css";', 'text/css')
        self.f.resources['/nested.css'] = (b'article{background:url(deep.png)}', 'text/css')
        self.f.resources['/deep.png'] = (b'deep-old', 'image/png')
        self.f.etags.update({'/one.html': '"html-stable"', '/one.css': '"css-stable"',
                             '/nested.css': '"nested-stable"', '/deep.png': '"deep-v1"'})
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T10:00:00.001+08:00'
        self.f.save_feed(); self.publish(); self.f.requests.clear()
        self.f.resources['/deep.png'] = (b'deep-new', 'image/png')
        self.f.etags['/deep.png'] = '"deep-v2"'
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T10:00:00.002+08:00'
        self.f.save_feed(); self.publish()
        self.assertIn(('/one.html', '"html-stable"'), self.f.requests)
        self.assertIn(('/one.css', '"css-stable"'), self.f.requests)
        self.assertIn(('/nested.css', '"nested-stable"'), self.f.requests)
        self.assertIn(('/deep.png', '"deep-v1"'), self.f.requests)
        self.assertTrue(any(p.read_bytes() == b'deep-new' for p in (self.f.root / 'live/assets').iterdir()))
        css = (self.f.root / 'live/articles/one/one.css').read_text()
        nested = self.f.root / 'live' / css.split('"')[1].removeprefix('/zh/news/')
        deep = self.f.root / 'live' / nested.read_text().split('"')[1].removeprefix('/zh/news/')
        self.assertEqual(deep.read_bytes(), b'deep-new')
        self.assertNotIn('/two.html', [p for p, _ in self.f.requests])

    def test_version_update_fetches_cover_outside_html_dependency_graph(self):
        """仅 Feed 封面字节变化、HTML 不引用封面：版本推进仍须下载并更新列表封面。"""
        item = self.f.feed['items'][0]
        item['seo'] = {'updatedAt': '2026-11-18T10:00:00.001+08:00',
                       'image': self.f.source + '/cover.png'}
        self.f.resources['/cover.png'] = (b'cover-v1', 'image/png')
        self.f.save_feed(); self.publish(); self.f.requests.clear()
        self.f.resources['/cover.png'] = (b'cover-v2', 'image/png')
        item['seo']['updatedAt'] = '2026-11-18T10:00:00.002+08:00'
        self.f.save_feed(); self.publish()
        listing = BeautifulSoup((self.f.root / 'live/index.html').read_text(), 'html.parser')
        one = next(i for i in json.loads(listing.find(id='feed-snapshot').text)['items'] if i['id'] == 'one')
        cover = self.f.root / 'live' / one['image'].removeprefix('https://official.example/zh/news/')
        self.assertEqual(cover.read_bytes(), b'cover-v2')
        self.assertIn('/cover.png', [p for p, _ in self.f.requests])
        self.assertNotIn('/two.html', [p for p, _ in self.f.requests])

    def test_feed_withdrawal_during_download_cannot_publish_stale_membership(self):
        """在 HTML 已下载后撤回该条目：第二次真实 HTTP Feed 检查必须拒绝候选，重跑按新集合下线。

        只在下载完成边界调度来源变动，抓取、Feed 判断和发布均使用真实实现。
        """
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T11:00:00+08:00'
        self.f.save_feed()
        original = sync.Fetcher.fetch

        def withdraw_after_html(fetcher, url, fresh=False):
            """在一次真实文章响应结束后替换来源 Feed，制造可重复的跨快照窗口。"""
            result = original(fetcher, url, fresh=fresh)
            if url == self.f.source + '/one.html':
                self.f.feed['items'] = self.f.feed['items'][1:]
                self.f.feed['_item_count'] = 1
                self.f.save_feed()
            return result

        with patch.object(sync.Fetcher, 'fetch', withdraw_after_html):
            with self.assertRaisesRegex(sync.SyncError, '同步期间 Feed 改变'):
                sync.collect(self.f.config)
        self.assertEqual((self.f.root / 'live').resolve(), Path(self.first['release']))
        self.assertEqual(sync.load_json(self.f.config.work / 'active.json')['version'], self.first['version'])
        self.f.requests.clear(); self.publish()
        self.assertFalse((self.f.root / 'live/articles/one').exists())
        self.assertTrue((self.f.root / 'live/articles/two/index.html').exists())
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/feed.json'])

    def test_deletion_does_not_redownload_remaining_article(self):
        """完整 Feed 删除一篇，清理详情并刷新下线 URL，保留篇不下载或刷新。"""
        self.f.feed['items'] = self.f.feed['items'][:1]; self.f.feed['_item_count'] = 1; self.f.save_feed()
        urls = self.publish()
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json','/feed.json'])
        self.assertFalse((self.f.root / 'live/articles/two').exists())
        self.assertIn('https://official.example/zh/news/articles/two/', urls)
        self.assertFalse(any('/articles/one' in u for u in urls))

    def test_changed_article_checks_shared_resource_before_unchanged_cache(self):
        """后面的更新篇与前面的未变篇共用视频，不能被先读取的旧缓存遮蔽；共享 URL 只下载一次。"""
        self.f.resources['/shared.flv'] = (b'shared-old', 'video/x-flv')
        for slug in ('one', 'two'):
            body, kind = self.f.resources['/' + slug + '.html']
            self.f.resources['/' + slug + '.html'] = (body.replace((slug + '.flv').encode(), b'shared.flv'), kind)
        for item in self.f.feed['items']: item['date_modified'] = '2026-11-18T14:00:00+08:00'
        self.f.save_feed(); self.publish(); self.f.requests.clear()
        self.f.feed['items'][1]['date_modified'] = '2026-11-18T15:00:00+08:00'
        self.f.resources['/shared.flv'] = (b'shared-new', 'video/x-flv'); self.f.save_feed()
        self.publish()
        self.assertEqual([p for p, _ in self.f.requests].count('/shared.flv'), 1)
        self.assertNotIn('/one.html', [p for p, _ in self.f.requests])
        self.assertTrue(any(p.read_bytes() == b'shared-new' for p in (self.f.root / 'live/assets').iterdir()))
        self.f.requests.clear(); self.assertFalse(sync.collect(self.f.config)['changed'])
        self.assertEqual([p for p, _ in self.f.requests], ['/feed.json', '/feed.json'])

    def test_unpublished_candidate_never_becomes_reuse_baseline(self):
        """新时间生成候选后未发布，再检查仍以 active 为基线，不能把失败/未发布抓取当成功。"""
        self.f.feed['items'][0]['date_modified'] = '2026-11-18T13:00:00+08:00'; self.f.save_feed()
        sync.collect(self.f.config); self.f.requests.clear()
        sync.collect(self.f.config)
        self.assertIn('/one.flv', [p for p, _ in self.f.requests])
        self.assertNotIn('/two.flv', [p for p, _ in self.f.requests])


if __name__ == '__main__':
    unittest.main()
