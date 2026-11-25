"""官网列表 SEO 回归：检查真实静态生成结果，不依赖浏览器替生成器补内容。"""

import json
from pathlib import Path
import tempfile
import unittest

from bs4 import BeautifulSoup
from test_sync_news import sync


class ListingSeoTests(unittest.TestCase):
    """每例在独立目录渲染公开快照，不抓来源、不操作线上发布状态。"""

    def setUp(self):
        """准备含封面和特殊文字的两条记录，验证输出内容与编码边界。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.config = sync.Config({'NEWS_SITE_ORIGIN': 'https://official.example'})
        self.items = [{'id': 'case-one', 'title': '案例 <研发> & 生产', 'summary': '真实摘要',
                       'url': 'https://official.example/zh/news/articles/case-one/',
                       'image': 'https://official.example/zh/news/assets/cover.jpg',
                       'image_alt': '实际生产流程', 'date_published': '2026-11-24T10:00:00+08:00',
                       'tags': ['客户案例']},
                      {'id': 'two', 'title': '第二篇', 'url': 'https://official.example/zh/news/articles/two/'}]

    def render(self, items):
        """调用实际生成入口并解析落盘 HTML；解析器只用于观察输出。"""
        sync.render_public_list(items, self.output, self.config)
        return BeautifulSoup((self.output / 'index.html').read_text(), 'html.parser')

    def test_first_paint_contains_feature_and_all_article_covers(self):
        """无 JS 时推荐位已占位且可读；首图优先加载，列表图延迟加载，标题保持原文。"""
        page = self.render(self.items)
        self.assertFalse(page.find(id='feature-carousel').has_attr('hidden'))
        self.assertEqual(page.select_one('#feature-slot h2').text, '案例 <研发> & 生产')
        hero = page.select_one('#feature-slot img')
        self.assertEqual(hero['loading'], 'eager')
        self.assertEqual(hero['fetchpriority'], 'high')
        self.assertEqual(page.select_one('#cards img')['loading'], 'lazy')
        self.assertEqual(page.select_one('#cards img')['alt'], '实际生产流程')
        self.assertEqual(len(page.select('#cards article')), 2)
        self.assertEqual(page.select_one('#cards time')['datetime'], '2026-11-24T10:00:00+08:00')

    def test_sharing_metadata_and_collection_describe_published_links(self):
        """OG、Twitter 与 CollectionPage 使用官方 URL；列表数据完整且 JSON 可解析。"""
        page = self.render(self.items)
        self.assertEqual(page.select_one('meta[property="og:url"]')['content'], 'https://official.example/zh/news/')
        self.assertEqual(page.select_one('meta[name="twitter:image"]')['content'], self.items[0]['image'])
        data = json.loads(page.select_one('script[type="application/ld+json"]').string)
        self.assertEqual(data['@type'], 'CollectionPage')
        self.assertEqual(data['mainEntity']['numberOfItems'], 2)
        self.assertEqual([i['url'] for i in data['mainEntity']['itemListElement']], [i['url'] for i in self.items])

    def test_empty_library_has_no_invented_article_or_broken_image(self):
        """空清单继续显示真实空状态，不输出虚构文章、无效封面或轮播。"""
        page = self.render([])
        self.assertTrue(page.find(id='feature-carousel').has_attr('hidden'))
        self.assertFalse(page.find(id='empty-library').has_attr('hidden'))
        self.assertEqual(page.select('#cards article'), [])
        data = json.loads(page.select_one('script[type="application/ld+json"]').string)
        self.assertEqual(data['mainEntity']['itemListElement'], [])

    def test_sitemap_uses_real_dates_and_omits_unknown_or_inverted_dates(self):
        """来源带时区保留原义，无时区只写日历日；缺失／非法／早于首发时不伪造 lastmod。"""
        import xml.etree.ElementTree as ET
        cases = [('2026-11-25T10:00:00+08:00', '2026-11-25T10:00:00+08:00'),
                 ('2026-11-25T10:00:00', '2026-11-25'), ('', None), ('invalid', None),
                 ('2026-11-23T10:00:00+08:00', None)]
        for modified, expected in cases:
            with self.subTest(modified=modified):
                self.items[0]['date_modified'] = modified
                self.render(self.items)
                ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                rows = ET.parse(self.output / 'sitemap.xml').findall('s:url', ns)
                dates = {row.findtext('s:loc', namespaces=ns): row.findtext('s:lastmod', namespaces=ns) for row in rows}
                self.assertEqual(dates[self.items[0]['url']], expected)
                self.assertIsNone(dates['https://official.example/zh/news/'])


if __name__ == '__main__':
    unittest.main()
