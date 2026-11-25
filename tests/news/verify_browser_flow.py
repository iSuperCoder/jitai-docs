"""浏览器验收：真实官网构建入口 → 独立生成列表 → 新标签页详情，全程不访问线上。

先执行 pnpm build，再用工作区指定 Python 运行本文件。依赖已有 Playwright 与本机
Chrome；不安装浏览器或前端依赖。官网域名请求映射到本地 build/ 和临时资讯发布目录，
所有其他请求阻断；测试结束关闭浏览器、HTTP 内容源并删除临时发布数据。
"""

import base64
import json
import shutil
from pathlib import Path
import unittest
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright
import test_sync_news as fixtures


class BrowserFlowTests(unittest.TestCase):
    """在真实 Chrome 中检验入口、交互和静态降级，资源来自实际同步器生成的快照。"""

    @classmethod
    def setUpClass(cls):
        """准备独立内容源及两篇可筛选文章，真实生成发布快照；启动已有 Chrome。"""
        cls.build = Path(__file__).resolve().parents[2] / 'build'
        if not (cls.build / 'zh/index.html').is_file():
            raise RuntimeError('请先构建中英文官网')
        cls.fixture = fixtures.NewsSyncTests()
        cls.fixture.setUp()
        cls.addClassCleanup(cls.fixture.tearDown)
        # 单像素 PNG 是合法图片，浏览器必须实际解码，不能仅断言 URL 字符串正确。
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        for name in ('image.png', 'background.png'):
            cls.fixture.resources['/' + name] = (png, 'image/png')
        cls.fixture.feed['items'][0].update(tags=['制造', 'AI', '客户案例'], _section='案例')
        cls.fixture.feed['items'][1].update(tags=['企业管理'], _section='观点')
        cls.fixture.save_feed()
        cls.fixture.build_publish()
        # 在临时副本中走正式案例投影，与部署后的 HTML 一致；原始构建目录不被测试改写。
        from cases_projection import prepare_case_pages, case_page_transaction
        cls.case_site = cls.fixture.root / 'case-site'
        for name in ('cases.html', 'zh/cases.html'):
            target = cls.case_site / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cls.build / name, target)
        with case_page_transaction(prepare_case_pages(cls.case_site, cls.fixture.root / 'live', 'https://official.example')):
            pass
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(channel='chrome', headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        """每例独立浏览器上下文，隔离存储和计时器；只允许映射后的本地网页及资源。"""
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000})
        self.addCleanup(self.context.close)
        # 明确英文偏好，使 / 真正检查英文首页，避免默认跳转 /zh 后误报两种语言均已验证。
        self.context.add_init_script("if (location.origin === 'https://official.example') localStorage.setItem('jitai-preferred-language', 'en')")
        self.missing = []
        self.errors = []
        self.context.route('**/*', self.serve_local)
        self.context.on('page', lambda page: page.on('pageerror', lambda error: self.errors.append(str(error))))
        self.page = self.context.new_page()

    def serve_local(self, route):
        """将官网请求路由到真实构建或发布产物，其他域名拒绝；模拟 nginx 的 .html/目录查找。"""
        parsed = urlsplit(route.request.url)
        if parsed.netloc != 'official.example':
            route.abort(); return
        path = unquote(parsed.path)
        if path.startswith('/zh/news/'):
            target = self.fixture.root / 'live' / path.removeprefix('/zh/news/')
        elif path.rstrip('/') in ('/cases', '/zh/cases'):
            target = self.case_site / path.strip('/')
        else:
            target = self.build / path.lstrip('/')
        candidates = [target, target.with_name(target.name + '.html'), target / 'index.html']
        match = next((candidate for candidate in candidates if candidate.is_file()), None)
        if match:
            route.fulfill(path=str(match))
        else:
            self.missing.append(path)
            route.fulfill(status=404, body='Not found')

    def assert_clean(self):
        """所有官网内资源必须可读取，增强脚本不能产生未捕获异常。"""
        self.assertEqual(self.missing, [])
        self.assertEqual(self.errors, [])

    def test_home_navigation_list_and_new_tab_detail(self):
        """中英文官网均有资讯入口，点击进入列表，再点击文章在新标签页打开官网镜像。"""
        for home in ('/', '/zh/'):
            self.page.goto('https://official.example' + home)
            self.assertEqual(self.page.locator('html').get_attribute('lang'), 'en' if home == '/' else 'zh')
            link = self.page.locator('.site-header a[href="/zh/news/"]')
            self.assertEqual(link.count(), 1)
            self.assertEqual(self.page.locator('.site-footer a[href="/zh/news/"]').count(), 1)
            link.click()
            self.page.locator('#cards .cover').first.wait_for()
            self.assertEqual(self.page.url, 'https://official.example/zh/news/')
            with self.page.expect_popup() as opened:
                self.page.locator('#cards a.article-link').first.click()
            article = opened.value
            article.wait_for_load_state()
            self.assertEqual(article.url, 'https://official.example/zh/news/articles/one/')
            self.assertIn('原始正文不重排', article.locator('article').inner_text())
            self.assertTrue(article.locator('img').evaluate_all('(imgs) => imgs.every(img => img.complete && img.naturalWidth > 0)'))
            self.assertEqual(article.locator('link[rel="canonical"]').get_attribute('href'), article.url)
            article.close()
        self.assert_clean()

    def test_cases_route_remains_available_without_whitepaper_entry(self):
        """白皮书暂时下线后案例导航仍可用，且只显示标签包含“案例”的文章。"""
        self.page.goto('https://official.example/zh/')
        self.assertEqual(self.page.locator('a[href*="whitepaper"]').count(), 0)
        self.page.locator('.site-header a[href="/zh/cases"]').click()
        # 占位也复用推荐位样式；必须等真实数据完成后再断言正文，不能把骨架当成案例。
        self.page.locator('.case-library[aria-busy="false"] .case-feature').wait_for()
        self.assertEqual(self.page.locator('.case-feature').count(), 1)
        self.assertEqual(self.page.locator('.case-row').count(), 0)
        self.assertIn('文章', self.page.locator('.case-feature').inner_text())
        self.page.locator('.site-header a[href="/zh/news/"]').click()
        self.assertEqual(self.page.url, 'https://official.example/zh/news/')
        self.assert_clean()

    def test_deferred_image_loads_official_copy_only_after_author_interaction(self):
        """真实生成与 Chrome 验证：镜像图首屏不请求，作者按钮激活后从官网加载并解码。"""
        from io import BytesIO
        from PIL import Image
        from bs4 import BeautifulSoup
        source = fixtures.NewsSyncTests()
        source.setUp()
        self.addCleanup(source.tearDown)
        picture = BytesIO()
        Image.new('RGB', (2, 2), (20, 80, 160)).save(picture, format='PNG')
        source.resources['/zoom.png'] = (picture.getvalue(), 'image/png')
        body, kind = source.resources['/one.html']
        source.resources['/one.html'] = (body.replace(b'</article>',
            b'<button id="open-zoom" onclick="const image=document.getElementById(\'zoom\');image.hidden=false;image.src=image.dataset.src">open</button>'
            b'<img id="zoom" hidden data-src="zoom.png" width="2" height="2"></article>'), kind)
        report = source.build_publish()
        output = BeautifulSoup((Path(report['release']) / 'articles/one/index.html').read_text(), 'html.parser')
        reference = output.find(id='zoom')['data-src']
        self.assertTrue(reference.startswith('/zh/news/assets/'))
        # 本用例覆盖实例的静态响应目录，类级其他浏览器用例仍使用原独立 fixture。
        self.fixture = source
        requested = []
        self.page.on('request', lambda request: requested.append(urlsplit(request.url).path))
        self.page.goto('https://official.example/zh/news/articles/one/', wait_until='networkidle')
        self.assertNotIn(reference, requested)
        self.assertIsNone(self.page.locator('#zoom').get_attribute('src'))
        self.page.locator('#open-zoom').click()
        self.page.wait_for_function('document.getElementById("zoom").naturalWidth === 2')
        self.assertEqual(requested.count(reference), 1)
        self.assertEqual(self.page.locator('#zoom').get_attribute('src'), reference)
        self.assert_clean()

    def test_whitepaper_is_absent_from_build_and_public_entries(self):
        """双语构建不含白皮书 HTML、正文或入口；独立资讯同样移除导航、页脚及空页阅读链接。"""
        for path in self.build.rglob('*.html'):
            self.assertNotIn('whitepaper', path.name)
            document = path.read_text()
            self.assertNotIn('/whitepaper', document, str(path))
            self.assertNotIn('wp-article', document, str(path))
        for locale in ('', 'zh/'):
            for relative in ('whitepaper.html', 'agent-products.html', 'low-code-platform.html', 'capabilities/active-hub.html'):
                self.assertFalse((self.build / locale / relative).exists())
        for route in ('/', '/zh/', '/zh/news/', '/zh/feature-auto'):
            self.page.goto('https://official.example' + route)
            self.assertEqual(self.page.locator('a[href*="whitepaper"]').count(), 0, route)
        self.assert_clean()

    def test_hero_video_slot_is_visible_with_native_controls(self):
        """手机和桌面使用同一视频首帧预览；媒体请求被阻断时仍可见，点击前不预载或显示原生控件。"""
        for width, height in ((1440, 900), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            self.page.goto('https://official.example/zh/')
            frame = self.page.locator('.home-video-frame')
            bounds = frame.bounding_box()
            self.assertIsNotNone(bounds)
            self.assertGreater(bounds['width'], 250)
            self.assertLessEqual(bounds['y'] + bounds['height'], height)
            video = frame.locator('video')
            self.assertEqual(video.get_attribute('src'), 'https://assets.jit.pro/videos/JitAI.mp4')
            self.assertIsNone(video.get_attribute('controls'))
            self.assertIsNone(video.get_attribute('poster'))
            self.assertEqual(video.get_attribute('preload'), 'none')
            self.assertEqual(video.get_attribute('playsinline'), '')
            preview = frame.locator('.home-video-preview')
            self.assertTrue(preview.evaluate('e => e.complete && e.naturalWidth === 960 && e.naturalHeight === 540'))
            self.assertEqual(frame.locator('.home-video-start').get_attribute('aria-busy'), 'false')
            self.assertEqual(frame.locator('.home-video-start').count(), 1)
            self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
        self.assertEqual(
            self.page.locator('.site-header .nav > a').evaluate_all('(links) => links.map(link => link.textContent.trim())'),
            ['首页', '案例方案', '资讯中心', '渠道合作', '关于我们'],
        )
        self.assert_clean()

    def test_mobile_video_failure_returns_to_static_preview(self):
        """手机点击才请求视频；外部媒体失败显示重试，重试恢复首帧而不是永久转圈或留下黑屏。"""
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.goto('https://official.example/zh/')
        self.page.locator('[data-reveal-ready="true"]').wait_for()
        frame = self.page.locator('.home-video-frame')
        self.assertTrue(frame.locator('.home-video-preview').is_visible())
        # serve_local 阻断外域请求，真实 video.play() 的失败应被组件处理，无需替换播放实现。
        frame.locator('.home-video-start').click()
        frame.locator('.home-video-error').wait_for()
        self.assertEqual(frame.locator('.home-video-preview').count(), 0)
        frame.get_by_role('button', name='重新加载视频').click()
        self.assertTrue(frame.locator('.home-video-preview').is_visible())
        self.assertEqual(frame.locator('.home-video-start').get_attribute('aria-busy'), 'false')
        self.assertIsNone(frame.locator('video').get_attribute('controls'))
        self.assert_clean()

    def test_mobile_menu_covers_content_and_restores_interaction(self):
        """主站与独立资讯菜单覆盖剩余视口；背景不可滚动/聚焦，关闭或跨桌面断点恢复原状态。

        用屏幕底部命中测试识别旧半屏菜单，不能仅凭 z-index 或展开属性断言遮挡正确。
        短屏允许菜单内部滚动，不能把最后一个云入口裁掉。
        """
        for route in ('/zh/', '/zh/news/'):
            for width, height in ((320, 568), (390, 844), (768, 600), (1024, 768)):
                with self.subTest(route=route, width=width):
                    self.page.set_viewport_size({'width': width, 'height': height})
                    self.page.goto('https://official.example' + route)
                    if route == '/zh/': self.page.locator('[data-reveal-ready="true"]').wait_for()
                    # 在非零阅读位置打开，防止只测页首掩盖移动滚动锁导致的回顶问题。
                    self.page.evaluate('scrollTo({top: 300, behavior: "instant"})')
                    reading_position = self.page.evaluate('scrollY')
                    button = self.page.locator('.nav-toggle' if route == '/zh/' else '#menu')
                    button.click()
                    self.page.wait_for_timeout(250)
                    self.assertTrue(self.page.evaluate('!!document.elementFromPoint(innerWidth / 2, innerHeight - 4)?.closest(".nav")'))
                    self.assertTrue(self.page.locator('main').evaluate('e => e.inert'))
                    y = self.page.evaluate('scrollY')
                    self.page.mouse.move(width / 2, height - 4)
                    self.page.mouse.wheel(0, 600)
                    self.page.wait_for_timeout(100)
                    self.assertEqual(self.page.evaluate('scrollY'), y)
                    cloud = self.page.locator('.nav-cta .entry-link').last
                    cloud.scroll_into_view_if_needed()
                    box = cloud.bounding_box()
                    self.assertLessEqual(box['y'] + box['height'], height)
                    button.focus()
                    self.page.keyboard.press('Tab')
                    self.assertTrue(self.page.evaluate('!!document.activeElement.closest(".site-header")'))
                    self.page.keyboard.press('Escape')
                    self.assertEqual(button.get_attribute('aria-expanded'), 'false')
                    self.assertFalse(self.page.locator('main').evaluate('e => e.inert'))
                    self.assertTrue(button.evaluate('e => e === document.activeElement'))
                    self.assertEqual(self.page.evaluate('scrollY'), reading_position)
                    button.click()
                    self.page.set_viewport_size({'width': 1440, 'height': 900})
                    self.page.wait_for_function('!document.querySelector("main").inert')
                    self.assertEqual(button.get_attribute('aria-expanded'), 'false')
        self.assert_clean()

    def test_experience_entries_distinguish_demo_desktop_and_cloud(self):
        """三个入口按下载、体验、云控制台排序；可见说明区分本地、公共演示和专属云环境。"""
        self.page.goto('https://official.example/zh/')
        hero = self.page.locator('.hero-actions')
        demo = hero.locator('a[href="https://demo.jit.pro"]')
        desktop = hero.locator('a[href="/zh/download"]')
        self.assertIn('在线体验', demo.inner_text())
        self.assertIn('公共演示', self.page.locator('#demo-entry-description').inner_text())
        self.assertIn('本地开发与运行', self.page.locator('#desktop-entry-description').inner_text())
        self.assertIn('专属云环境', self.page.locator('#cloud-entry-description').inner_text())
        self.assertIn('免费', desktop.inner_text())
        self.assertEqual(hero.locator('a').evaluate_all('(links) => links.map(a => a.getAttribute("href"))'),
                         ['/zh/download', 'https://demo.jit.pro', 'https://console.jit.pro/whwy/jitcloud'])
        columns = self.page.locator('.delivery-table thead th')
        self.assertEqual(columns.nth(1).locator('a[href="/zh/download"]').count(), 1)
        self.assertEqual(columns.nth(3).locator('a[href="/zh/contact"]').count(), 1)
        self.assertIn('咨询私有化', columns.nth(3).inner_text())
        console = columns.nth(2).locator('a[href="https://console.jit.pro/whwy/jitcloud"]')
        for link in (demo, console):
            self.assertEqual(link.get_attribute('target'), '_blank')
            self.assertIn('noopener', link.get_attribute('rel'))
        self.assertIsNone(desktop.get_attribute('target'))
        for route in ('/zh/', '/zh/news/'):
            self.page.goto('https://official.example' + route)
            self.assertEqual(self.page.locator('.header-actions > a').evaluate_all(
                '(links) => links.map(a => new URL(a.href).pathname)'),
                ['/zh/download', '/', '/whwy/jitcloud'])
            for url in ('https://demo.jit.pro', 'https://console.jit.pro/whwy/jitcloud'):
                link = self.page.locator(f'.site-header .header-actions a[href="{url}"]')
                self.assertEqual(link.count(), 1)
                self.assertEqual(link.get_attribute('target'), '_blank')
                self.assertIn('noopener', link.get_attribute('rel'))
        self.assert_clean()

    def test_entry_hints_support_focus_hover_and_escape(self):
        """桌面用途说明可由键盘和鼠标独立打开；Escape 关闭后重新进入可恢复，不触发导航。"""
        for route in ('/zh/', '/zh/news/'):
            self.page.mouse.move(0, 900)
            self.page.goto('https://official.example' + route)
            link = self.page.locator('.header-actions .entry-link').last
            hint = link.locator('.entry-hint')
            self.assertFalse(hint.is_visible())
            link.focus()
            self.assertTrue(hint.is_visible())
            self.assertIn('专属云环境', hint.inner_text())
            self.page.keyboard.press('Escape')
            self.assertFalse(hint.is_visible())
            self.page.locator('.site-header .brand').focus()
            link.hover()
            self.assertTrue(hint.is_visible())
            self.page.keyboard.press('Escape')
            self.assertFalse(hint.is_visible())
        self.assert_clean()

    def test_filters_and_list_layout_keep_official_article_links(self):
        """卡片主题按钮只筛选，切到列表后仍保留正确新标签链接，空搜索可恢复。"""
        self.page.goto('https://official.example/zh/news/')
        self.page.locator('#cards .cover').first.wait_for()
        self.page.locator('#cards [data-topic="制造"]').first.click()
        self.assertEqual(len(self.context.pages), 1)
        self.assertEqual(self.page.locator('#cards article').count(), 1)
        self.page.locator('[data-layout="list"]').click()
        self.assertIn('list-view', self.page.locator('#cards').get_attribute('class'))
        self.assertEqual(self.page.locator('#cards a.article-link').get_attribute('target'), '_blank')
        self.page.locator('#clear-filters').click()
        self.page.locator('#search').fill('没有这篇文章')
        self.assertEqual(self.page.locator('#cards article').count(), 0)
        self.assertIn('暂无匹配文章', self.page.locator('#status').inner_text())
        self.page.locator('#clear-filters').click()
        self.assertEqual(self.page.locator('#cards article').count(), 2)
        self.page.locator('[data-category="观点"]').click()
        self.assertEqual(self.page.locator('#cards article').count(), 1)
        self.assertEqual(self.page.locator('#cards article').get_attribute('data-id'), 'two')
        self.assert_clean()

    def test_reduced_motion_and_hover_pause_rotation(self):
        """减少动态效果默认暂停；普通模式悬停暂停，移开后重新给满 12 秒阅读时间。"""
        self.page.clock.install()
        self.page.emulate_media(reduced_motion='reduce')
        self.page.goto('https://official.example/zh/news/')
        self.page.locator('#feature-slot article').wait_for()
        first = self.page.locator('#feature-slot article').get_attribute('data-id')
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('#feature-slot article').get_attribute('data-id'), first)
        self.page.emulate_media(reduced_motion='no-preference')
        self.page.reload()
        self.page.locator('#feature-slot article').wait_for()
        self.page.locator('#feature-slot article').hover()
        first = self.page.locator('#feature-slot article').get_attribute('data-id')
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('#feature-slot article').get_attribute('data-id'), first)
        self.page.mouse.move(0, 0)
        self.page.clock.run_for(12100)
        self.assertNotEqual(self.page.locator('#feature-slot article').get_attribute('data-id'), first)
        self.assert_clean()

    def test_carousel_rotates_and_pauses_without_reordering_list(self):
        """模拟浏览器时间验证 12 秒轮播与明确暂停，下方完整列表顺序始终稳定。"""
        self.page.clock.install()
        self.page.goto('https://official.example/zh/news/')
        self.page.locator('#feature-slot article').wait_for()
        self.page.locator('#feature-carousel').scroll_into_view_if_needed()
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(100)
        first = self.page.locator('#feature-slot article').get_attribute('data-id')
        listing = self.page.locator('#cards').inner_text()
        self.page.clock.run_for(12100)
        second = self.page.locator('#feature-slot article').get_attribute('data-id')
        self.assertNotEqual(first, second)
        self.assertEqual(self.page.locator('#cards').inner_text(), listing)
        self.page.locator('#rotation-toggle').click()
        self.page.locator('#page-title').click()
        self.page.mouse.move(0, 0)
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('#feature-slot article').get_attribute('data-id'), second)
        self.assert_clean()

    def test_responsive_entry_and_list(self):
        """四种宽度检查官网与资讯页无横向溢出，手机菜单能够进入资讯列表。"""
        for width in (320, 768, 1024, 1440):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            self.page.goto('https://official.example/zh/')
            # 等待真实 React effect 的标记，再操作客户端菜单；SSR 链接本身无需等待 hydration。
            self.page.locator('[data-reveal-ready="true"]').wait_for()
            if width < 1181:
                self.page.locator('.nav-toggle').click()
            self.page.locator('.site-header a[href="/zh/news/"]').wait_for(state='visible')
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            self.page.locator('.site-header a[href="/zh/news/"]').click()
            self.page.locator('#cards .cover').first.wait_for()
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assert_clean()

    def test_news_header_matches_marketing_header_geometry(self):
        """两页切换时导航不位移：覆盖桌面、手机及菜单断点两侧，比较真实布局而非 CSS 字符串。

        以现有中文首页为独立参照，测量 Logo、导航文字、主题按钮及 CTA；深浅主题分别验证。
        每次先等待主题应用和 React 初始化，避免把加载中状态当作稳定布局。
        """
        selectors = ['.site-header', '.site-header .header-inner', '.site-header .brand img',
                     '.site-header .header-actions', '.site-header .header-actions button:first-child']
        measure = """node => {
            const rect = node.getBoundingClientRect();
            return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
        }"""
        for theme in ('light', 'dark'):
            self.page.goto('https://official.example/zh/')
            self.page.evaluate('(theme) => localStorage.setItem("jitai-marketing-theme", theme)', theme)
            for width in (320, 768, 1024, 1151, 1180, 1181, 1280, 1440, 1920):
                with self.subTest(theme=theme, width=width):
                    self.page.set_viewport_size({'width': width, 'height': 1000})
                    self.page.mouse.move(0, 900)
                    self.page.goto('https://official.example/zh/')
                    self.page.locator(f'[data-reveal-ready="true"][data-marketing-theme="{theme}"]').wait_for()
                    measured = selectors + (['.nav > a', '.header-actions > a'] if width > 1180 else [])
                    expected = {selector: self.page.locator(selector).evaluate_all(
                        '(nodes) => nodes.map(' + measure + ')') for selector in measured}
                    # 文案、顺序和实际跳转目标也必须一致；仅比尺寸可能漏掉同宽旧菜单。
                    links = '(nodes) => nodes.map(a => ({text:a.textContent.trim(), href:a.href, target:a.target, rel:a.rel}))'
                    expected_links = self.page.locator('.site-header a').evaluate_all(links)
                    self.page.goto('https://official.example/zh/news/')
                    self.page.locator(f'html[data-theme="{theme}"]').wait_for()
                    self.assertEqual(self.page.locator('.site-header a').evaluate_all(links), expected_links)
                    for selector in measured:
                        actual = self.page.locator(selector).evaluate_all('(nodes) => nodes.map(' + measure + ')')
                        self.assertEqual(len(actual), len(expected[selector]), selector)
                        for reference, result in zip(expected[selector], actual):
                            for axis in ('x', 'y', 'width', 'height'):
                                self.assertAlmostEqual(result[axis], reference[axis], delta=0.5,
                                                       msg=f'{theme}/{width}/{selector}/{axis}')
                    self.assertEqual(self.page.locator('#menu').is_visible(), width <= 1180)
                    self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assert_clean()

    def test_news_mobile_menu_matches_marketing_actions_and_dismissal(self):
        """移动导航保留三个入口及常驻用途说明；Escape 归还焦点，跨断点后菜单收起。"""
        self.page.set_viewport_size({'width': 768, 'height': 1000})
        self.page.goto('https://official.example/zh/news/')
        menu = self.page.locator('#menu')
        menu.click()
        self.assertEqual(menu.get_attribute('aria-expanded'), 'true')
        self.assertEqual(menu.get_attribute('aria-label'), '关闭导航')
        self.assertEqual(self.page.locator('.nav-cta a').evaluate_all(
            '(links) => links.map(a => new URL(a.href).pathname)'), ['/zh/download', '/', '/whwy/jitcloud'])
        for hint in self.page.locator('.nav-cta .entry-hint').all():
            self.assertTrue(hint.is_visible())
        self.assertTrue(self.page.locator('.nav-cta a[href="https://demo.jit.pro"]').is_visible())
        self.assertTrue(self.page.locator('.nav-cta a[href="https://console.jit.pro/whwy/jitcloud"]').is_visible())
        self.page.locator('.nav > a').first.focus()
        self.page.keyboard.press('Escape')
        self.assertEqual(menu.get_attribute('aria-expanded'), 'false')
        self.assertTrue(menu.evaluate('node => node === document.activeElement'))
        menu.click()
        self.page.set_viewport_size({'width': 1440, 'height': 1000})
        self.page.wait_for_function('document.getElementById("menu").getAttribute("aria-expanded") === "false"')
        self.page.set_viewport_size({'width': 768, 'height': 1000})
        self.assertFalse(self.page.locator('.nav > a').first.is_visible())
        self.assert_clean()

    def test_no_javascript_still_exposes_static_article_links(self):
        """禁用 JS 仍可从生成列表读标题和摘要并打开详情，搜索引擎不依赖客户端渲染。"""
        context = self.browser.new_context(java_script_enabled=False)
        try:
            context.route('**/*', self.serve_local)
            page = context.new_page()
            page.goto('https://official.example/zh/news/')
            self.assertEqual(page.locator('#cards a[target="_blank"]').count(), 2)
            self.assertIn('摘要', page.locator('#cards').inner_text())
            self.assertEqual(page.locator('#cards a').first.get_attribute('href'), 'https://official.example/zh/news/articles/one/')
        finally:
            context.close()
        self.assert_clean()

    def test_cases_without_javascript_keep_full_list_and_schema(self):
        """双语案例原文都有当前案例、摘要、普通详情链接和完整 schema，不需执行轮播或 Fetch。"""
        context = self.browser.new_context(java_script_enabled=False)
        try:
            context.route('**/*', self.serve_local)
            page = context.new_page()
            for route in ('/cases', '/zh/cases'):
                page.goto('https://official.example' + route)
                self.assertEqual(page.locator('#case-static .case-row').count(), 1)
                self.assertTrue(page.locator('#case-static .case-row').is_visible())
                self.assertEqual(page.locator('#case-static h3 a').get_attribute('href'), 'https://official.example/zh/news/articles/one/')
                self.assertIn('摘要', page.locator('#case-static').inner_text())
                self.assertFalse(page.locator('.case-loading').is_visible())
                data = json.loads(page.locator('#case-list-schema').text_content())
                self.assertEqual(data['mainEntity']['numberOfItems'], 1)
        finally:
            context.close()
        self.assert_clean()

    def test_empty_library_works_with_and_without_javascript(self):
        """已配置 Feed 但首次 HTTP 404 的空候选仍是正常页面，不显示无效控件或运维错误。"""
        config = fixtures.sync.Config({**self.fixture.env, 'NEWS_FEED_URL': self.fixture.source + '/missing-feed.json',
                                       'NEWS_WORK_DIR': str(self.fixture.root / 'empty-browser')})
        report = fixtures.sync.collect_available(config)
        release = Path(report['release'])

        def serve_empty(route):
            """仅将本用例空快照映射至资讯路径，其余网页沿用本地官网构建。"""
            path = unquote(urlsplit(route.request.url).path).removeprefix('/zh/news/')
            target = release / path
            if target.is_dir(): target = target / 'index.html'
            if target.is_file(): route.fulfill(path=str(target))
            else: route.fulfill(status=404, body='Not found')

        for javascript in (True, False):
            context = self.browser.new_context(java_script_enabled=javascript, viewport={'width': 390, 'height': 900})
            try:
                context.route('**/*', self.serve_local)
                context.route('**/zh/news/**', serve_empty)
                page = context.new_page()
                page.on('pageerror', lambda error: self.errors.append(str(error)))
                response = page.goto('https://official.example/zh/news/?q=anything&topic=missing')
                self.assertEqual(response.status, 200)
                self.assertTrue(page.locator('#empty-library').is_visible())
                self.assertIn('好内容，正在路上', page.locator('#empty-library').inner_text())
                self.assertFalse(page.locator('.library-tools').is_visible())
                self.assertFalse(page.locator('#view-switch').is_visible())
                self.assertFalse(page.locator('#feature-carousel').is_visible())
                self.assertEqual(page.locator('#cards article').count(), 0)
                self.assertNotIn('NEWS_FEED_URL', page.locator('body').inner_text())
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            finally:
                context.close()
        self.assert_clean()


if __name__ == '__main__':
    unittest.main(verbosity=2)
