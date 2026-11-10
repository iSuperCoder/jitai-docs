"""按独立风险维度验证资讯同步，补充组合流程不能单独证明的触发条件。

每个用例只改变一项来源或一个失败阶段，其他前提保持有效；源内容、版本目录、队列与配置
由真实实现处理。系统管理与云传输仍是替身，不把本地成功表述为真实服务器验收。
"""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import test_sync_news as source_tests
import test_release_install as release_tests


class ResourceChangeTests(unittest.TestCase):
    """固定 HTML、Feed 与其他资源，每次独立改变 CSS 或图片，检验触发、落盘和刷新范围。"""

    def setUp(self):
        """两篇文章的来源以真实 HTTP 服务提供；第一篇使用同目录 CSS 和固定 file 参数图片。"""
        self.fixture = source_tests.NewsSyncTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        self.image = '/api/whwy/app123/storages/preview?file=cover.svg'
        f.resources[self.image] = (b'<svg width="10"/>', 'image/svg+xml')
        f.resources['/one.css'] = (b'body{color:red}', 'text/css')
        f.resources['/one.html'] = (
            ('<html><head><link rel="stylesheet" href="one.css"></head><body><article><h1>one</h1>'
             '<img src="' + self.image + '"></article></body></html>').encode(), 'text/html')
        self.first = f.build_publish()
        self.feed_before = f.resources['/feed.json'][0]
        source_tests.sync.atomic_json(f.config.work / 'pending-cdn.json', [])

    def test_only_same_name_css_change_triggers_publish_and_cdn(self):
        """只改 one.css 字节；相同 Feed/HTML/图片不能掩盖 CSS 未进入内容指纹的错误。"""
        f = self.fixture
        image_before = f.resources[self.image]
        f.resources['/one.css'] = (b'body{color:blue}', 'text/css')
        report = source_tests.sync.collect(f.config)
        self.assertTrue(report['changed'])
        self.assertEqual(report['count'], 2)
        self.assertEqual(report['removed_count'], 0)
        source_tests.sync.publish(f.config, report['version'], f.env)
        self.assertEqual((f.root / 'live/articles/one/one.css').read_bytes(), b'body{color:blue}')
        pending = source_tests.sync.load_json(f.config.work / 'pending-cdn.json')
        self.assertIn('https://official.example/zh/news/articles/one/one.css', pending)
        self.assertNotIn('https://official.example/zh/news/assets/cover.svg', pending)
        self.assertEqual(f.resources['/feed.json'][0], self.feed_before)
        self.assertEqual(f.resources[self.image], image_before)
        self.assertFalse(source_tests.sync.collect(f.config)['changed'])

    def test_only_same_name_image_change_triggers_publish_and_cdn(self):
        """只替换 file=cover.svg 的字节；CSS 没变时不应被加入资源刷新集。"""
        f = self.fixture
        css_before = f.resources['/one.css']
        f.resources[self.image] = (b'<svg width="20"/>', 'image/svg+xml')
        report = source_tests.sync.collect(f.config)
        self.assertTrue(report['changed'])
        source_tests.sync.publish(f.config, report['version'], f.env)
        self.assertEqual((f.root / 'live/assets/cover.svg').read_bytes(), b'<svg width="20"/>')
        pending = source_tests.sync.load_json(f.config.work / 'pending-cdn.json')
        self.assertIn('https://official.example/zh/news/assets/cover.svg', pending)
        self.assertNotIn('https://official.example/zh/news/articles/one/one.css', pending)
        self.assertEqual(f.resources['/feed.json'][0], self.feed_before)
        self.assertEqual(f.resources['/one.css'], css_before)
        self.assertFalse(source_tests.sync.collect(f.config)['changed'])

    def test_only_article_removal_purges_its_css_without_refreshing_unchanged_image(self):
        """仅下线 one，检查详情与同目录 CSS 删除；保留旧图片的策略不应误报图片内容更新。"""
        f = self.fixture
        f.feed['items'] = [f.feed['items'][1]]
        f.feed['_item_count'] = 1
        f.save_feed()
        report = source_tests.sync.collect(f.config)
        self.assertEqual(report['removed_count'], 1)
        source_tests.sync.publish(f.config, report['version'], f.env)
        pending = source_tests.sync.load_json(f.config.work / 'pending-cdn.json')
        for suffix in ('', '/', '/index.html', '/one.css'):
            self.assertIn('https://official.example/zh/news/articles/one' + suffix, pending)
        self.assertFalse((f.root / 'live/articles/one').exists())
        self.assertTrue((f.root / 'live/articles/two/index.html').is_file())
        self.assertNotIn('https://official.example/zh/news/assets/cover.svg', pending)


class UpgradeFailureTests(unittest.TestCase):
    """失败阶段各自有独立成功发布基线，不复用上一故障可能留下的配置、主站或单位文件。"""

    def setUp(self):
        """准备真实旧配置/程序，再修改候选程序；仅目标失败子进程和 systemctl 使用替身。"""
        self.fixture = release_tests.ReleaseInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.install({'NEWS_FEED_URL': 'https://old.example/feed.json'})
        f = self.fixture
        self.config = Path(f.env['NEWS_CONFIG_FILE'])
        self.original = self.config.read_bytes()
        self.program = Path(f.env['NEWS_INSTALL_DIR']).resolve()
        (f.stage / 'news/README.md').write_text('new candidate program')

    def assert_failure_preserves_pair(self, phase):
        """仅在指定阶段抛子进程错误，检查原配置/程序配对及私有候选文件清理；其他命令正常执行。"""
        f = self.fixture
        hit = []
        def run(args, **kwargs):
            """目标参数匹配时才失败，并记录命中以防提前失败造成假阳性。"""
            if phase in args:
                hit.append(args)
                raise subprocess.CalledProcessError(23, args)
            return f.run_command(args, **kwargs)
        with patch.object(release_tests.installer.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                release_tests.installer.install(f.stage, {'NEWS_FEED_URL': 'https://new.example/feed.json'}, f.env, True)
        self.assertEqual(raised.exception.returncode, 23)
        self.assertEqual(len(hit), 1)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(Path(f.env['NEWS_INSTALL_DIR']).resolve(), self.program)
        self.assertEqual(list((f.root / 'app-releases').glob('bootstrap-*')), [])

    def test_bootstrap_failure(self):
        """初始化失败独立验证，不提前提交正式配置。"""
        self.assert_failure_preserves_pair('--bootstrap')

    def test_main_apply_failure(self):
        """主站应用命令失败独立验证，资讯配置和程序仍保持旧配对。"""
        self.assert_failure_preserves_pair('--apply')

    def test_daemon_reload_failure(self):
        """systemd reload 失败发生于配对切换之后，必须实际执行回滚而不是跳过激活。"""
        self.assert_failure_preserves_pair('daemon-reload')

    def test_timer_enable_failure(self):
        """timer 启用失败独立验证，不依赖同一测试中之前的初始化失败状态。"""
        self.assert_failure_preserves_pair('enable')


class CredentialInputTests(unittest.TestCase):
    """配置凭证输入的单规则拒绝用例；其余字段与部署前提合法，不用联网结果代替输入校验。"""

    def setUp(self):
        """独立临时发布区；预览模式可验证配置合并与拒绝，不能调用安装器副作用命令。"""
        self.fixture = release_tests.ReleaseInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def assert_rejected(self, credentials):
        """断言凭证规则拒绝且没有网络/系统命令或正式配置写入。"""
        f = self.fixture
        with patch.object(release_tests.installer.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, '凭证'):
                release_tests.installer.install(f.stage, credentials, f.env, False)
            run.assert_not_called()
        self.assertFalse(Path(f.env['NEWS_CONFIG_FILE']).exists())

    def test_secret_without_key_rejected(self):
        """单独提供 secret 无法与旧 key 混用。"""
        self.assert_rejected({'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'secret'})

    def test_token_without_pair_rejected(self):
        """单独提供 token 无法与旧 AK 对混用。"""
        self.assert_rejected({'ALIBABA_CLOUD_SECURITY_TOKEN': 'token'})

    def test_nonempty_key_with_empty_secret_rejected(self):
        """字段齐全但 secret 为空，也不是有效 AK 对。"""
        self.assert_rejected({'ALIBABA_CLOUD_ACCESS_KEY_ID': 'key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': ''})

    def test_empty_pair_with_nonempty_token_rejected(self):
        """回到 profile 的空 AK 对不能携带另一组 token。"""
        self.assert_rejected({'ALIBABA_CLOUD_ACCESS_KEY_ID': '', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': '',
                              'ALIBABA_CLOUD_SECURITY_TOKEN': 'token'})


if __name__ == '__main__':
    unittest.main()
