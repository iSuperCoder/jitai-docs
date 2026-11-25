"""案例静态投影的发布链路回归：真实资讯生成、文件切换与主站 rsync，全部在临时目录。"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
import test_sync_news as fixtures
import test_main_site_boundary as main_fixtures
from cases_projection import prepare_case_pages

SHELL = '<!doctype html><html><head><title>案例</title></head><body><h1>案例</h1><noscript id="case-static">原占位</noscript><script id="case-list-schema" type="application/ld+json">{}</script></body></html>'


class CaseProjectionTests(unittest.TestCase):
    """复用真实源服务器与候选发布 fixture，断言单独来自用户可见契约。"""

    def setUp(self):
        """明确主站根及两种语言页面，一篇含案例标签，另一篇是普通资讯。"""
        self.f = fixtures.NewsSyncTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.site = self.f.root / 'site'
        (self.site / 'zh').mkdir(parents=True)
        for name in ['cases.html', 'zh/cases.html']:
            (self.site / name).write_text(SHELL)
        self.f.env.update(NEWS_MAIN_SITE_DIR=str(self.site), NEWS_LIVE_LINK=str(self.site / 'zh/news'))
        self.f.feed['items'][0]['tags'] = ['任何行业案例']
        self.f.feed['items'][0]['title'] = '案例 </noscript><script>不执行</script> & 真实业务'
        self.f.save_feed()

    def page(self, name='zh/cases.html'):
        """解析实际发布 HTML，而不调用投影函数生成期望。"""
        return BeautifulSoup((self.site / name).read_text(), 'html.parser')

    def test_publish_exposes_only_cases_and_complete_schema_in_both_languages(self):
        """原始 HTML 直接含案例标题、摘要和官网链接；普通资讯不被误归类，特殊标题不逃逸槽。"""
        self.f.build_publish()
        for name in ['cases.html', 'zh/cases.html']:
            page = self.page(name)
            self.assertEqual(len(page.select('#case-static .case-row')), 1)
            self.assertEqual(page.select_one('#case-static h3').text, self.f.feed['items'][0]['title'])
            self.assertEqual(page.select_one('#case-static h3 a')['href'], 'https://official.example/zh/news/articles/one/')
            self.assertEqual(len(page.find_all('script')), 1)
            schema = json.loads(page.find(id='case-list-schema').string)
            self.assertEqual(schema['mainEntity']['numberOfItems'], 1)
            self.assertEqual(schema['url'], 'https://official.example/' + name.removesuffix('.html'))
        pending = fixtures.sync.load_json(self.f.config.work / 'pending-cdn.json')
        self.assertIn('https://official.example/zh/cases', pending)
        self.assertIn('https://official.example/cases.html', pending)

    def test_changed_case_and_unpublish_update_static_links_and_queue(self):
        """新增／改名／删除案例都来自当前快照；删除后不能在原始 HTML 留下失效详情入口。"""
        self.f.build_publish()
        self.f.feed['items'][1]['tags'] = ['新案例']
        self.f.feed['items'][0]['title'] = '已修订案例'
        self.f.save_feed();self.f.build_publish()
        self.assertEqual(len(self.page().select('#case-static h3')), 2)
        self.assertIn('已修订案例', self.page().find(id='case-static').text)
        self.f.feed['items'] = [self.f.feed['items'][1]]
        self.f.feed['_item_count'] = 1
        self.f.save_feed();self.f.build_publish()
        self.assertNotIn('/articles/one/', (self.site / 'zh/cases.html').read_text())
        self.assertEqual(len(self.page().select('#case-static h3')), 1)

    def test_failed_source_preserves_published_cases(self):
        """来源不可用时保留既有案例 HTML 与资讯版本，不将抓取失败当空清单。"""
        self.f.build_publish()
        before = (self.site / 'zh/cases.html').read_bytes()
        self.f.resources['/feed.json'] = (b'unavailable', 'text/plain')
        result = fixtures.sync.collect_available(self.f.config)
        self.assertTrue(result['fallback'])
        self.assertEqual((self.site / 'zh/cases.html').read_bytes(), before)

    def test_case_write_failure_rolls_back_written_locale_and_keeps_news(self):
        """只让第二种语言的文件切换失败，第一种恢复；旧资讯仍可读，不能假报新发布。"""
        old = self.f.build_publish()
        before = {name:(self.site/name).read_bytes() for name in ['cases.html','zh/cases.html']}
        self.f.feed['items'][0]['title']='新版本';self.f.save_feed()
        candidate=fixtures.sync.collect(self.f.config)
        import cases_projection
        real=cases_projection.write_page
        def fail_zh(path, body):
            """仅第二页新内容故障，回滚原内容仍可写，排除回滚存储故障这一独立场景。"""
            if path == self.site/'zh/cases.html' and body != before['zh/cases.html']:
                raise OSError('injected disk failure')
            return real(path,body)
        with patch.object(cases_projection,'write_page',side_effect=fail_zh):
            with self.assertRaisesRegex(OSError,'injected'):
                fixtures.sync.publish(self.f.config,candidate['version'],self.f.env)
        self.assertEqual((self.site/'zh/news').resolve(),Path(old['release']))
        for name,body in before.items():self.assertEqual((self.site/name).read_bytes(),body)

    def test_active_state_failure_restores_news_and_both_case_pages(self):
        """资讯链接已切换后让 active 提交失败，验证两类页面及发布状态都回到旧版本。"""
        old=self.f.build_publish();before=(self.site/'zh/cases.html').read_bytes()
        self.f.feed['items'][0]['title']='新状态';self.f.save_feed()
        candidate=fixtures.sync.collect(self.f.config);real=fixtures.sync.atomic_json
        def fail_active(path,value):
            """只故障 active，允许待刷新队列落盘，确保测试能到达版本提交阶段。"""
            if path.name=='active.json':raise OSError('active commit failed')
            return real(path,value)
        with patch.object(fixtures.sync,'atomic_json',side_effect=fail_active):
            with self.assertRaisesRegex(OSError,'active commit'):
                fixtures.sync.publish(self.f.config,candidate['version'],self.f.env)
        self.assertEqual((self.site/'zh/news').resolve(),Path(old['release']))
        self.assertEqual((self.site/'zh/cases.html').read_bytes(),before)
        self.assertEqual(fixtures.sync.load_json(self.f.config.work/'active.json')['version'],old['version'])

    def test_cdn_failure_keeps_new_pages_and_pending_case_urls(self):
        """CDN 失败发生在内容提交之后，新页面保留且案例 URL 等待重试，不回滚已发布内容。"""
        self.f.build_publish()
        self.f.feed['items'][0]['title']='缓存待刷新';self.f.save_feed()
        candidate=fixtures.sync.collect(self.f.config)
        with patch.object(fixtures.sync,'refresh_cdn',side_effect=fixtures.sync.SyncError('CDN failed')):
            with self.assertRaisesRegex(fixtures.sync.SyncError,'CDN failed'):
                fixtures.sync.publish(self.f.config,candidate['version'],self.f.env)
        self.assertIn('缓存待刷新',self.page().find(id='case-static').text)
        self.assertEqual((self.site/'zh/news').resolve(),Path(candidate['release']))
        self.assertIn('https://official.example/zh/cases',fixtures.sync.load_json(self.f.config.work/'pending-cdn.json'))

    def test_main_site_republish_projects_current_news_under_shared_lock(self):
        """主站新构建不含内容，但真实 rsync 后应重新注入现有已发布案例，不把列表退回占位。"""
        self.f.build_publish()
        stage=self.f.root/'stage';(stage/'zh').mkdir(parents=True)
        for name in ['index.html','zh/index.html']:(stage/name).write_text('site shell')
        for name in ['cases.html','zh/cases.html']:(stage/name).write_text(SHELL.replace('<h1>案例</h1>','<h1>新外壳</h1>'))
        env={**self.f.env,'MAIN_SITE_STAGE_DIR':str(stage),'MAIN_SITE_DIR':str(self.site)}
        self.assertEqual(main_fixtures.main_site.apply_main_site(env,True),0)
        self.assertEqual(self.page().h1.text,'新外壳')
        self.assertEqual(len(self.page().select('#case-static h3')),1)
        self.assertEqual(prepare_case_pages(self.site,self.site/'zh/news','https://official.example'),[])

    def test_legacy_shell_is_supported_but_partial_slots_fail_before_publish(self):
        """无槽旧页面保持兼容；新版缺一槽属于不完整部署，不能悄悄丢掉可抓取内容。"""
        old=self.f.build_publish()
        (self.site/'cases.html').write_text('<html>legacy shell</html>')
        (self.site/'zh/cases.html').write_text('<noscript id="case-static">broken shell</noscript>')
        self.f.feed['items'][0]['title']='新标题';self.f.save_feed()
        candidate=fixtures.sync.collect(self.f.config)
        with self.assertRaisesRegex(ValueError,'不完整'):
            fixtures.sync.publish(self.f.config,candidate['version'],self.f.env)
        self.assertEqual((self.site/'zh/news').resolve(),Path(old['release']))
        self.assertEqual((self.site/'cases.html').read_text(),'<html>legacy shell</html>')


if __name__=='__main__':unittest.main()
