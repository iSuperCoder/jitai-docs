"""案例推荐轮播的 Chrome 验收：真实构建及 React 生命周期，只有资讯 HTTP 快照使用明确 fixture。

不安装浏览器或依赖；以 Playwright 浏览器时钟验证 12 秒边界，不替换组件计时器。
每例独立上下文，结束时继承原浏览器 fixture 的资源清理。
"""
import json
import unittest

import verify_browser_flow as browser_tests


class CaseCarouselTests(browser_tests.BrowserFlowTests):
    """复用已存在的本地构建路由与 Chrome 初始化，不复制前端实现生成期望。"""

    def open_cases(self, count=3, locale='zh', broken_first=False):
        """提供指定篇数的独立快照，进入真实案例路由，等待观察器和 React 完成初始化。"""
        items = [{'id': f'case-{index}', 'title': f'案例 {index}', 'summary': f'独立案例摘要 {index}',
                  'tags': ['客户案例'], 'url': f'https://official.example/zh/news/articles/{index}/',
                  'image': '/img/home-video-preview.webp', 'date_published': '2026-11-24T10:00:00'}
                 for index in range(count)]
        if broken_first and items: items[0]['image'] = 'https://broken.example/missing.png'
        self.page.route('https://official.example/zh/news/', lambda route: route.fulfill(
            content_type='text/html', body='<script id="feed-snapshot" type="application/json">' + json.dumps({'items': items}) + '</script>'))
        self.page.clock.install()
        self.page.goto('https://official.example/' + ('zh/' if locale == 'zh' else '') + 'cases')
        self.page.locator('.case-library[aria-busy="false"]').wait_for()
        if count:
            self.page.locator('.case-carousel').scroll_into_view_if_needed()
            self.page.mouse.move(0, 0)
            self.page.wait_for_timeout(100)

    def test_case_timer_boundary_cycle_and_fixed_list(self):
        """12 秒前不切换，随后遍历三篇并回到首篇；全部案例列表与手动播报不受自动轮播影响。"""
        self.open_cases()
        feature = self.page.locator('.case-feature')
        listing = self.page.locator('.case-list').inner_text()
        self.page.clock.run_for(11800)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.page.clock.run_for(400)
        self.assertEqual(feature.get_attribute('data-id'), 'case-1')
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-2')
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.assertEqual(self.page.locator('.case-row').count(), 3)
        self.assertEqual(self.page.locator('.case-list').inner_text(), listing)
        self.assertEqual(self.page.locator('.case-carousel [aria-live]').inner_text(), '')
        self.assert_clean()

    def test_case_hover_focus_and_explicit_pause(self):
        """分别控制悬停、键盘焦点和显式暂停；移开/失焦恢复后必须重新给满阅读周期。"""
        self.open_cases()
        feature = self.page.locator('.case-feature')
        feature.hover()
        self.page.clock.run_for(25000)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.page.mouse.move(0, 0)
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-1')
        feature.locator('a').focus()
        self.page.clock.run_for(25000)
        self.assertEqual(feature.get_attribute('data-id'), 'case-1')
        feature.locator('a').evaluate('(link) => link.blur()')
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-2')
        self.page.get_by_role('button', name='暂停轮播').click()
        self.page.locator('.case-intro h1').click()
        self.page.mouse.move(0, 0)
        self.page.clock.run_for(25000)
        self.assertEqual(feature.get_attribute('data-id'), 'case-2')
        self.page.get_by_role('button', name='播放轮播').click()
        self.page.locator('.case-intro h1').click()
        self.page.locator('.case-carousel').scroll_into_view_if_needed()
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(100)
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.assert_clean()

    def test_case_manual_keyboard_navigation_and_image_recovery(self):
        """键盘翻页循环并保留按钮焦点；上一图失败不能隐藏下一篇好图；手动切换才播报。"""
        self.page.emulate_media(reduced_motion='reduce')
        self.open_cases(broken_first=True)
        self.page.wait_for_function('document.querySelector(".case-feature img").hidden')
        previous = self.page.get_by_role('button', name='上一篇案例')
        previous.focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.locator('.case-feature').get_attribute('data-id'), 'case-2')
        self.assertTrue(previous.evaluate('(button) => button === document.activeElement'))
        self.assertEqual(self.page.locator('.case-carousel [aria-live]').inner_text(), '案例 2')
        self.page.wait_for_function('document.querySelector(".case-feature img").naturalWidth > 0')
        self.assertTrue(self.page.locator('.case-feature img').is_visible())
        self.assertEqual(self.page.locator('.case-feature a').get_attribute('href'), 'https://official.example/zh/news/articles/2/')
        self.assertEqual(self.page.locator('.case-feature a').get_attribute('target'), '_blank')
        self.assert_clean()

    def test_case_reduced_motion_defaults_to_paused(self):
        """系统减少动态效果在初始加载时暂停，关闭偏好也不擅自恢复用户的暂停状态。"""
        self.page.emulate_media(reduced_motion='reduce')
        self.open_cases()
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('.case-feature').get_attribute('data-id'), 'case-0')
        self.assertTrue(self.page.get_by_role('button', name='播放轮播').is_visible())
        self.page.emulate_media(reduced_motion='no-preference')
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('.case-feature').get_attribute('data-id'), 'case-0')
        self.assert_clean()

    def test_case_offscreen_and_hidden_page_pause(self):
        """真实滚动离屏暂停；单独模拟浏览器可见性事件，验证后台不会切换且恢复重新计时。"""
        self.page.set_viewport_size({'width': 1440, 'height': 600})
        self.open_cases()
        feature = self.page.locator('.case-feature')
        self.page.locator('footer').scroll_into_view_if_needed()
        self.page.wait_for_timeout(100)
        self.assertLessEqual(self.page.locator('.case-carousel').bounding_box()['y'] + self.page.locator('.case-carousel').bounding_box()['height'], 0)
        self.page.clock.run_for(25000)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.page.locator('.case-carousel').scroll_into_view_if_needed()
        self.page.wait_for_timeout(100)
        # 无头浏览器多页未必报告后台状态，只替换浏览器输入，组件监听与计时逻辑保持真实。
        self.page.evaluate('Object.defineProperty(document, "hidden", {configurable:true, value:true}); document.dispatchEvent(new Event("visibilitychange"))')
        self.page.clock.run_for(25000)
        self.assertEqual(feature.get_attribute('data-id'), 'case-0')
        self.page.evaluate('delete document.hidden; document.dispatchEvent(new Event("visibilitychange"))')
        self.page.clock.run_for(12100)
        self.assertEqual(feature.get_attribute('data-id'), 'case-1')
        self.assert_clean()

    def test_case_single_empty_and_responsive_bilingual_controls(self):
        """单篇及空状态无无效控件；双语四断点维持单列小封面列表，每张普通封面真实解码。"""
        self.open_cases(count=1)
        self.assertEqual(self.page.locator('.case-carousel-controls').count(), 0)
        self.page.clock.run_for(25000)
        self.assertEqual(self.page.locator('.case-feature').get_attribute('data-id'), 'case-0')
        self.open_cases(count=0)
        self.assertEqual(self.page.locator('.case-carousel').count(), 0)
        self.assertTrue(self.page.get_by_text('新的实践，陆续呈现').is_visible())
        for locale in ('zh', 'en'):
            for width in (320, 768, 1024, 1440):
                self.page.set_viewport_size({'width': width, 'height': 1000})
                self.open_cases(locale=locale)
                self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                controls = self.page.locator('.case-carousel-controls button')
                self.assertEqual(controls.count(), 3)
                for button in controls.all():
                    self.assertGreaterEqual(button.bounding_box()['height'], 44)
                self.assertTrue(self.page.get_by_role('button', name='下一篇案例' if locale == 'zh' else 'Next case').is_visible())
                # lazy 图片须进入视口后检查解码；只核对 img 存在会漏掉空封面或布局尺寸错误。
                cards = self.page.locator('.case-row')
                self.assertEqual(cards.count(), 3)
                for card in cards.all():
                    image = card.locator('img')
                    image.scroll_into_view_if_needed()
                    image.evaluate('(image) => image.decode()')
                    self.assertTrue(image.is_visible())
                    box = image.bounding_box()
                    self.assertAlmostEqual(box['width'] / box['height'], 16 / 9, places=2)
                    self.assertLessEqual(box['width'], 160)
                    title = card.locator('h3').bounding_box()
                    self.assertGreaterEqual(title['x'], box['x'] + box['width'])
                    self.assertAlmostEqual(title['y'], box['y'], delta=1)
                    self.assertEqual(card.locator('a').count(), 1)
                first, second = cards.nth(0).bounding_box(), cards.nth(1).bounding_box()
                self.assertGreater(second['y'], first['y'])
        self.assert_clean()


if __name__ == '__main__':
    # 继承只为复用 fixture；独立入口仅执行本文件案例测试，完整旧流程另跑原入口。
    suite = unittest.TestSuite(CaseCarouselTests(name) for name in unittest.defaultTestLoader.getTestCaseNames(CaseCarouselTests) if name.startswith('test_case_'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
