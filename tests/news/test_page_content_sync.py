"""自由网页同步回归：来源决定页面内容，同步器只搬运资源并适配地址。

复用真实本地 HTTP 与发布目录；各用例独立加入一种页面能力，避免一个拒绝条件掩盖另一个。
调度失败用例运行真实 shell/CLI，确认旧版保留与进程失败能同时成立。
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from bs4 import BeautifulSoup
import test_sync_news as fixtures

sync = fixtures.sync


class PageContentSyncTests(unittest.TestCase):
    """每例创建独立来源和临时发布目录；资源在 fixture 清理时释放，不访问生产。"""

    def setUp(self):
        """沿用已验证的 HTTP fixture，只调整本例的页面输入，不替换同步实现。"""
        self.f = fixtures.NewsSyncTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def page(self, markup):
        """把指定内容加入有效文章，执行真实收集、发布并返回落盘 HTML。"""
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'</article>', markup.encode() + b'</article>'), kind)
        self.f.build_publish()
        return BeautifulSoup((self.f.root / 'live/articles/one/index.html').read_text(), 'html.parser')

    def test_inline_script_and_data_block_are_preserved(self):
        """普通脚本及非 JSON-LD 数据块逐字保留，不能要求文章使用同步器指定的交互实现。"""
        code = 'document.querySelector("article").dataset.ready = "yes";'
        page = self.page('<script>' + code + '</script><script type="application/json">{"custom":true}</script>')
        self.assertEqual(page.find('script').string, code)
        self.assertEqual(page.select_one('script[type="application/json"]').string, '{"custom":true}')

    def test_external_scripts_keep_source_dependency_base(self):
        """外部脚本保持来源绝对地址及执行属性，使相对 import 和 currentScript 仍基于原目录解析。"""
        page = self.page('<script src="runtime/main.js" defer integrity="sha256-test"></script>'
                         '<script type="module" src="runtime/app.mjs"></script>')
        scripts = page.find_all('script')
        self.assertEqual(scripts[0]['src'], self.f.source + '/runtime/main.js')
        self.assertEqual(scripts[0]['integrity'], 'sha256-test')
        self.assertTrue(scripts[0].has_attr('defer'))
        self.assertEqual(scripts[1]['src'], self.f.source + '/runtime/app.mjs')
        self.assertEqual(scripts[1]['type'], 'module')

    def test_inline_events_and_custom_link_schemes_are_preserved(self):
        """事件、javascript 链接及应用自定义协议由页面作者决定，不删改或拦截。"""
        page = self.page('<button onclick="this.textContent=\'done\'">run</button>'
                         '<a id="js" href="javascript:void(0)">js</a><a id="custom" href="demo:open">open</a>')
        self.assertEqual(page.button['onclick'], "this.textContent='done'")
        self.assertEqual(page.find(id='js')['href'], 'javascript:void(0)')
        self.assertEqual(page.find(id='custom')['href'], 'demo:open')

    def test_embeds_and_forms_keep_original_runtime_targets(self):
        """嵌入页和表单是运行目标而非静态图片；相对地址转来源绝对地址，原属性保留。"""
        page = self.page('<iframe src="viewer.html" sandbox="allow-scripts"></iframe>'
                         '<object data="document.html"></object><embed src="plugin.html">'
                         '<form action="submit" method="post"><button formaction="alternate">send</button></form>')
        for selector, attr, path in [('iframe','src','viewer.html'), ('object','data','document.html'),
                                     ('embed','src','plugin.html'), ('form','action','submit'),
                                     ('form button','formaction','alternate')]:
            self.assertEqual(page.select_one(selector)[attr], self.f.source + '/' + path)
        self.assertEqual(page.form['method'], 'post')
        self.assertEqual(page.iframe['sandbox'], ['allow-scripts'])

    def test_svg_interaction_content_is_preserved(self):
        """SVG 脚本、事件和 foreignObject 是作者内容，不能因扩展名引入另一套黑名单。"""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="run()"><script>function run(){}</script><foreignObject><div>text</div></foreignObject></svg>'
        self.f.resources['/interactive.svg'] = (svg, 'image/svg+xml')
        page = self.page('<img id="interactive" src="interactive.svg">')
        path = self.f.root / 'live' / page.find(id='interactive')['src'].removeprefix('/zh/news/')
        self.assertEqual(path.read_bytes(), svg)

    def test_article_wrapper_is_not_required(self):
        """页面可用 main/div 组织正文；article 标签不是同步清单的额外准入条件。"""
        body, kind = self.f.resources['/one.html']
        self.f.resources['/one.html'] = (body.replace(b'<article>', b'<main>').replace(b'</article>', b'</main>'), kind)
        report = self.f.build_publish()
        self.assertEqual(report['count'], 2)
        self.assertIn('<main>', (self.f.root / 'live/articles/one/index.html').read_text())

    def test_srcset_data_url_and_download_candidate_coexist(self):
        """data URL 内部逗号不拆断；另一独立图片候选仍真实搬运，描述符保持原值。"""
        data = 'data:image/png;base64,YWJjZA=='
        page = self.page('<img id="responsive" srcset="' + data + ' 1x, /image.png 2x">')
        candidates = page.find(id='responsive')['srcset']
        self.assertTrue(candidates.startswith(data + ' 1x, /zh/news/assets/'))
        self.assertTrue(candidates.endswith(' 2x'))

    def test_base_href_keeps_source_semantics_and_mirrors_assets(self):
        """作者 base 保留来源语义，而本地图片地址绑定官网，不能被 base 解析回来源域名。"""
        self.f.resources['/nested/image.png'] = (b'nested-picture', 'image/png')
        self.f.resources['/nested/shared.css'] = (b'article{color:red}', 'text/css')
        page = self.page('<base href="/nested/"><img id="based" src="image.png">')
        self.assertEqual(page.base['href'], self.f.source + '/nested/')
        self.assertTrue(page.find(id='based')['src'].startswith('https://official.example/zh/news/assets/'))

    def test_refresh_metadata_and_invalid_jsonld_are_not_content_filters(self):
        """页面跳转与未解析的数据块也属于作者内容；只适配跳转目标，不据此拒绝同步。"""
        page = self.page('<meta http-equiv="refresh" content="5;url=next.html">'
                         '<script type="application/ld+json">not-json</script>')
        self.assertEqual(page.select_one('meta[http-equiv="refresh"]')['content'], '5;url=' + self.f.source + '/next.html')
        self.assertEqual(page.find('script').string, 'not-json')

    def test_scheduler_reports_failed_fetch_and_preserves_live(self):
        """唯一故障为文章 HTTP 404：真实调度必须非零退出、指出文章 ID，且旧版字节不变。"""
        self.f.build_publish()
        old_state = (self.f.config.work / 'active.json').read_bytes()
        old_live = (self.f.root / 'live').resolve()
        del self.f.resources['/one.html']
        result = subprocess.run(['bash', str(fixtures.MODULE_PATH.parent / 'run-news-sync.sh')],
            env={**os.environ, **self.f.env, 'NEWS_PYTHON': sys.executable, 'NEWS_ENABLE_PUBLISH': '1'},
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('one', result.stderr)
        self.assertIn('HTTP 404', result.stderr)
        self.assertEqual((self.f.root / 'live').resolve(), old_live)
        self.assertEqual((self.f.config.work / 'active.json').read_bytes(), old_state)
        self.assertNotIn('"published"', result.stdout)


if __name__ == '__main__':
    unittest.main()
