"""发布 SEO 验收：真实 HTTP 承载生成产物，独立故障逐项证明检查能识别错误。"""
import importlib.util
import json
from pathlib import Path
import unittest

import test_sync_news as fixtures
from cases_projection import prepare_case_pages, case_page_transaction

spec = importlib.util.spec_from_file_location('published_seo_verifier', fixtures.MODULE_PATH.with_name('verify-site.py'))
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class PublishedSEOTests(unittest.TestCase):
    """每例拥有独立源站与生成目录；只改目标错误，其余索引、案例、缓存前提全部有效。"""

    def setUp(self):
        """用正式同步器和案例投影生成有效基线，再由本地 HTTP 返回产物及明确缓存头。"""
        self.fixture = fixtures.NewsSyncTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.domain = self.fixture.source
        self.fixture.env['NEWS_SITE_ORIGIN'] = self.domain
        self.fixture.config = fixtures.sync.Config(self.fixture.env)
        self.fixture.feed['items'][0].update(tags=['客户案例'], image=self.domain + '/image.png')
        self.fixture.save_feed()
        report = self.fixture.build_publish()
        self.release = Path(report['release'])
        for path in self.release.rglob('*'):
            if path.is_file():
                url = '/zh/news/' + path.relative_to(self.release).as_posix()
                if url.endswith('index.html'): url = url[:-10]
                self.fixture.resources[url] = (path.read_bytes(), 'text/html')
                self.fixture.response_headers[url] = {'Cache-Control': 'public, max-age=60'}
        site = self.fixture.root / 'site'
        for route in ('/cases', '/zh/cases'):
            path = site / (route[1:] + '.html')
            path.parent.mkdir(parents=True, exist_ok=True)
            links = ''.join(f'<link rel="alternate" hreflang="{lang}" href="{self.domain}{target}">'
                            for lang, target in [('en', '/cases'), ('zh', '/zh/cases'), ('x-default', '/cases')])
            path.write_text(f'<html><head><link rel="canonical" href="{self.domain}{route}">{links}</head>'
                            '<body><noscript id="case-static"></noscript><script id="case-list-schema">{}</script></body></html>')
        with case_page_transaction(prepare_case_pages(site, self.release, self.domain)):
            pass
        for route in ('/cases', '/zh/cases'):
            self.fixture.resources[route] = ((site / (route[1:] + '.html')).read_bytes(), 'text/html')
            self.fixture.response_headers[route] = {'Cache-Control': 'public, max-age=60'}
        self.fixture.resources['/robots.txt'] = (b'User-agent: *\nAllow: /\n', 'text/plain')

    def replace(self, route, before, after):
        """精确改一个发布响应，不改源数据或其他有效页面；匹配不到即报测试准备错误。"""
        body, kind = self.fixture.resources[route]
        self.assertIn(before.encode(), body)
        self.fixture.resources[route] = (body.replace(before.encode(), after.encode()), kind)

    def test_valid_generated_site_passes_while_source_remains_noindex(self):
        """有效官网全链通过，同时来源 noindex 原文保留，验收器不要求来源开放索引。"""
        verifier.verify_seo(self.domain, cache=True)
        self.assertIn(b'noindex', self.fixture.resources['/one.html'][0])

    def test_official_http_noindex_fails_independently(self):
        """详情 HTML 完全正常，只有官网 HTTP 头禁止索引也必须失败。"""
        self.fixture.response_headers['/zh/news/articles/one/']['X-Robots-Tag'] = 'googlebot: noindex'
        with self.assertRaisesRegex(ValueError, '索引限制'):
            verifier.verify_seo(self.domain)

    def test_crawler_meta_noindex_fails_independently(self):
        """通用 index 保留，专用 googlebot-news noindex 仍必须被识别。"""
        self.replace('/zh/news/articles/one/', '</head>', '<meta name="googlebot-news" content="noindex"></head>')
        with self.assertRaisesRegex(ValueError, '索引限制'):
            verifier.verify_seo(self.domain)

    def test_source_canonical_fails_independently(self):
        """HTTP 与 robots 正常，仅 canonical 指回原始资源也不能通过官网验收。"""
        route = '/zh/news/articles/one/'
        self.replace(route, f'href="{self.domain}{route}"', f'href="{self.domain}/one.html"')
        with self.assertRaisesRegex(ValueError, 'canonical'):
            verifier.verify_seo(self.domain)

    def test_static_case_link_missing_fails_with_valid_schema(self):
        """案例 schema 正常而原始 HTML 漏链接，避免结构化数据掩盖内容不可发现。"""
        self.replace('/zh/cases', f'href="{self.domain}/zh/news/articles/one/"', 'href="/zh/news/"')
        with self.assertRaisesRegex(ValueError, '完整已发布列表'):
            verifier.verify_seo(self.domain)

    def test_case_schema_mismatch_fails_with_valid_links(self):
        """原始案例链接完整，单独错误的 schema 数量必须报错。"""
        self.replace('/zh/cases', '"numberOfItems": 1', '"numberOfItems": 0')
        with self.assertRaisesRegex(ValueError, '结构化数据'):
            verifier.verify_seo(self.domain)

    def test_hreflang_mismatch_fails_independently(self):
        """仅英文 alternate 指向中文版，其他所有内容保持有效。"""
        self.replace('/zh/cases', f'hreflang="en" href="{self.domain}/cases"', f'hreflang="en" href="{self.domain}/zh/cases"')
        with self.assertRaisesRegex(ValueError, '语言链接'):
            verifier.verify_seo(self.domain)

    def test_sitemap_missing_article_fails_independently(self):
        """文章与列表都正常，仅 sitemap 漏项必须报告。"""
        self.replace('/zh/news/sitemap.xml', self.domain + '/zh/news/articles/one/', self.domain + '/wrong/')
        with self.assertRaisesRegex(ValueError, 'sitemap'):
            verifier.verify_seo(self.domain)

    def test_robots_txt_disallow_fails_independently(self):
        """全部页面 index 正常，仅 robots.txt 禁止抓取也不能报允许收录验收成功。"""
        self.fixture.resources['/robots.txt'] = (b'User-agent: *\nDisallow: /zh/news/\n', 'text/plain')
        with self.assertRaisesRegex(ValueError, '阻止抓取'):
            verifier.verify_seo(self.domain)

    def test_long_html_cache_fails_independently(self):
        """保留有效 SEO 产物，只把案例 HTML 的缓存改回线上旧 30 天。"""
        self.fixture.response_headers['/zh/cases']['Cache-Control'] = 'public, max-age=2592000'
        with self.assertRaisesRegex(ValueError, '有效期'):
            verifier.verify_seo(self.domain, cache=True)

    def test_long_mutable_image_cache_fails_independently(self):
        """所有 HTML 缓存正确，仅同名图片过长仍需被验收识别。"""
        news = verifier.PublishedSEO(self.fixture.resources['/zh/news/'][0].decode())
        image = json.loads(news.scripts['feed-snapshot'])['items'][0]['image']
        self.fixture.response_headers[image.removeprefix(self.domain)]['Cache-Control'] = 'max-age=2592000'
        with self.assertRaisesRegex(ValueError, '有效期'):
            verifier.verify_seo(self.domain, cache=True)


if __name__ == '__main__':
    unittest.main()
