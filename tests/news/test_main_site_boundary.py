"""验证主站真实 rsync 不破坏资讯数据、共享锁互斥，以及两套 CDN 刷新范围分离。

所有目录位于本地临时空间，CDN 使用 DRY_RUN；不连接服务器、不调用任何云 API。
"""

import fcntl
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('main_site', ROOT / 'scripts/news/apply-main-site.py')
main_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_site)


class MainSiteBoundaryTests(unittest.TestCase):
    """在独立源码包、站点及数据目录间运行真实文件同步；退出后清除临时文件。"""

    def setUp(self):
        """构造旧主站、待发布主站和外置资讯版本；故意保留应被正常删除的主站旧页。"""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage, self.site, self.data = [self.root / name for name in ('stage', 'site', 'data')]
        for directory in (self.stage, self.site, self.data):
            directory.mkdir()
        for directory, text in ((self.stage, 'new'), (self.site, 'old')):
            (directory / 'zh').mkdir()
            (directory / 'index.html').write_text(text)
            (directory / 'zh/index.html').write_text(text)
        (self.site / 'zh/obsolete.html').write_text('obsolete')
        (self.data / 'index.html').write_text('news listing')
        (self.data / 'article.html').write_text('news detail')
        (self.site / 'zh/news').symlink_to(self.data, target_is_directory=True)
        self.env = {'MAIN_SITE_STAGE_DIR': str(self.stage), 'MAIN_SITE_DIR': str(self.site),
                    'NEWS_RELEASE_LOCK': str(self.root / 'release.lock')}

    def tearDown(self):
        """只清理本测试的临时目录，不接触实际构建产物或服务目录。"""
        self.temp.cleanup()

    def test_preview_then_apply_preserves_news_but_updates_main_site(self):
        """预览无写入；实际应用更新主站并删除旧页，同时保留资讯链接、列表和详情。"""
        self.assertEqual(main_site.apply_main_site(self.env), 0)
        self.assertEqual((self.site / 'index.html').read_text(), 'old')
        self.assertTrue((self.site / 'zh/obsolete.html').exists())
        self.assertEqual(main_site.apply_main_site(self.env, apply=True), 0)
        self.assertEqual((self.site / 'index.html').read_text(), 'new')
        self.assertFalse((self.site / 'zh/obsolete.html').exists())
        self.assertTrue((self.site / 'zh/news').is_symlink())
        self.assertEqual((self.site / 'zh/news/index.html').read_text(), 'news listing')
        self.assertEqual((self.site / 'zh/news/article.html').read_text(), 'news detail')

    def test_real_news_directory_is_also_protected(self):
        """即使迁移前资讯是实体目录，rsync 保护规则也不能删除它的后代文件。"""
        (self.site / 'zh/news').unlink()
        (self.site / 'zh/news').mkdir()
        (self.site / 'zh/news/index.html').write_text('independent data')
        self.assertEqual(main_site.apply_main_site(self.env, apply=True), 0)
        self.assertEqual((self.site / 'zh/news/index.html').read_text(), 'independent data')

    def test_build_route_collision_is_rejected_before_writing(self):
        """框架生成同名资讯路由会抢占 nginx 请求，必须在任何站点写入前失败。"""
        (self.stage / 'zh/news.html').write_text('collision')
        with self.assertRaisesRegex(ValueError, '同名'):
            main_site.apply_main_site(self.env, apply=True)
        self.assertEqual((self.site / 'index.html').read_text(), 'old')

    def test_news_publish_lock_blocks_main_release(self):
        """资讯进程正在发布时主站不能进入同步，验证真实 flock 而非替身调用次数。"""
        with Path(self.env['NEWS_RELEASE_LOCK']).open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                main_site.apply_main_site(self.env, apply=True)
        self.assertEqual((self.site / 'index.html').read_text(), 'old')

    def test_main_cdn_excludes_news_in_all_scopes(self):
        """用实体资讯目录验证 entry/targeted/full 均跳过资讯，主站首页刷新仍存在。"""
        (self.site / 'zh/news').unlink()
        (self.site / 'zh/news/articles').mkdir(parents=True)
        (self.site / 'zh/news/index.html').write_text('listing')
        (self.site / 'zh/news/articles/one.html').write_text('article')
        for scope in ('entry', 'targeted', 'full'):
            with self.subTest(scope=scope):
                result = subprocess.run(['bash', str(ROOT / 'refresh_cdn.sh')],
                                        env={**os.environ, 'BUILD_DIR': str(self.site), 'DRY_RUN': '1',
                                             'DOMAIN': 'https://official.example', 'REFRESH_SCOPE': scope,
                                             'NEWS_PUBLIC_PATH': '/zh/news/'},
                                        capture_output=True, text=True, check=True)
                self.assertIn('File https://official.example/\n', result.stdout)
                self.assertNotIn('https://official.example/zh/news', result.stdout)

    def test_retired_blogs_and_docs_are_purged_even_after_files_are_removed(self):
        """退役内容在磁盘上已不存在，所有刷新模式仍需刷新双语目录和入口地址变体。"""
        for scope in ('entry', 'targeted', 'full'):
            with self.subTest(scope=scope):
                result = subprocess.run(['bash', str(ROOT / 'refresh_cdn.sh')],
                                        env={**os.environ, 'BUILD_DIR': str(self.stage), 'DRY_RUN': '1',
                                             'REFRESH_SCOPE': scope}, capture_output=True, text=True, check=True)
                for prefix in ('/blog', '/zh/blog', '/docs', '/zh/docs'):
                    self.assertIn('Directory https://jit.pro' + prefix + '/', result.stdout)
                    for suffix in ('', '/', '.html', '/index.html'):
                        self.assertIn('File https://jit.pro' + prefix + suffix + '\n', result.stdout)


if __name__ == '__main__':
    unittest.main()
