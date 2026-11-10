"""官网发布集成回归：真实临时文件、Python 子进程和 rsync，隔离 SSH/systemd/云接口。

不连接生产、不安装依赖。发布器测试只替换传输边界；安装器测试仅替换 systemctl，
实际生成首次空页和应用主站，以验证导航上线前的内容可用性与重复部署保护。
"""

import importlib.util
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    """按文件入口加载普通部署模块用于测试；不会执行其 main 或联网。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('news_install', ROOT / 'scripts/news/install-news.py')
publisher = load('site_publish', ROOT / 'scripts/publish-site.py')
service = load('news_service', ROOT / 'scripts/news/service-entry.py')
verifier = load('news_verify', ROOT / 'scripts/news/verify-site.py')


class ReleaseInstallTests(unittest.TestCase):
    """每例独立上传区/运行区/主站；只让 systemctl 成功返回，不模拟生成器或 rsync。"""

    def setUp(self):
        """建立最小双语官网与真实脚本上传包，解释器包装只调用指定工作区 Python。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'stage'
        (self.stage / 'site/zh').mkdir(parents=True)
        for name in ('index.html', 'zh/index.html', 'download.html', 'zh/download.html', 'contact.html', 'zh/contact.html'):
            (self.stage / 'site' / name).write_text('new marketing')
        shutil.copytree(ROOT / 'scripts/news', self.stage / 'news', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(ROOT / 'refresh_cdn.sh', self.stage / 'refresh_cdn.sh')
        self.site = self.root / 'site'
        (self.site / 'zh').mkdir(parents=True)
        (self.site / 'index.html').write_text('old marketing')
        (self.site / 'old.html').write_text('obsolete')
        runtime = self.root / 'runtime'
        (runtime / 'bin').mkdir(parents=True)
        (runtime / 'bin/python').write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        (runtime / 'bin/python').chmod(0o755)
        self.env = {'REMOTE_SITE_DIR': str(self.site), 'NEWS_INSTALL_DIR': str(self.root / 'app'),
                    'NEWS_RUNTIME_DIR': str(runtime), 'NEWS_CONFIG_FILE': str(self.root / 'config.json'),
                    'NEWS_SYSTEMD_DIR': str(self.root / 'units'), 'NEWS_WORK_DIR': str(self.root / 'data'),
                    'NEWS_RELEASE_LOCK': str(self.root / 'release.lock'),
                    'REMOTE_CDN_SCRIPT': str(self.root / 'cdn.sh'), 'SKIP_CDN': '1'}
        self.commands = []
        self.real_run = subprocess.run

    def run_command(self, args, **kwargs):
        """替换系统管理边界；任何依赖安装都是测试错误，其余调用原生子进程。"""
        self.commands.append(args)
        if args[0] == 'systemctl':
            if 'enable' in args:
                # timer 可能启用后立即触发：程序和配置必须已存在，服务读锁则必须仍被安装锁阻塞。
                self.assertTrue(Path(self.env['NEWS_INSTALL_DIR']).is_symlink())
                config = Path(self.env['NEWS_CONFIG_FILE'])
                self.assertTrue(config.is_file())
                with config.with_suffix('.json.lock').open('a') as handle:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return subprocess.CompletedProcess(args, 0)
        if 'pip' in args or 'venv' in args: raise AssertionError('测试不应安装运行环境')
        return self.real_run(args, **kwargs)

    def install(self, settings=None):
        """在临时目录执行真实安装；云模式固定 none，避免测试继承机器凭证或产生请求。"""
        with patch.object(installer.subprocess, 'run', side_effect=self.run_command):
            return installer.install(self.stage, {'NEWS_CDN_MODE': 'none', **(settings or {})}, self.env, True)

    def test_preview_has_no_write_or_command_side_effects(self):
        """默认预览既不改站点也不创建配置/锁，更不能启动 timer 或 Python 安装。"""
        with patch.object(installer.subprocess, 'run') as run:
            self.assertEqual(installer.install(self.stage, {}, self.env), 0)
            run.assert_not_called()
        self.assertFalse(Path(self.env['NEWS_CONFIG_FILE']).exists())
        self.assertEqual((self.site / 'index.html').read_text(), 'old marketing')

    def test_failed_upgrade_preserves_active_configuration_and_program(self):
        """重复发布在 bootstrap、主站应用或 timer 启用失败时，原配置和程序入口仍保持完整配对。"""
        self.install({'NEWS_FEED_URL': 'https://old.example/feed.json'})
        config = Path(self.env['NEWS_CONFIG_FILE'])
        before = config.read_bytes()
        target = Path(self.env['NEWS_INSTALL_DIR']).resolve()
        (self.stage / 'news/README.md').write_text('changed program package')
        for phase in ('--bootstrap', '--apply', 'enable'):
            with self.subTest(phase=phase):
                def fail(args, **kwargs):
                    """失败前确认正式配置未提前覆盖，替身仅隔离所选子进程失败。"""
                    if args[:2] not in (['systemctl', 'daemon-reload'], ['systemctl', 'enable']):
                        self.assertEqual(config.read_bytes(), before)
                    if phase in args: raise subprocess.CalledProcessError(1, args)
                    return self.run_command(args, **kwargs)
                with patch.object(installer.subprocess, 'run', side_effect=fail):
                    with self.assertRaises(subprocess.CalledProcessError):
                        installer.install(self.stage, {'NEWS_FEED_URL': 'https://new.example/feed.json'}, self.env, True)
                self.assertEqual(config.read_bytes(), before)
                self.assertEqual(Path(self.env['NEWS_INSTALL_DIR']).resolve(), target)

    def test_restrictive_umask_preserves_public_access_and_private_state(self):
        """077 下公开版本仍可读，工作根可穿过但不可列目录，缓存/候选/状态/配置不可被其他用户读取。"""
        previous = os.umask(0o077)
        try: self.install()
        finally: os.umask(previous)
        work = Path(self.env['NEWS_WORK_DIR'])
        self.assertEqual(work.stat().st_mode & 0o777, 0o711)
        for path in (work / 'releases', (self.site / 'zh/news').resolve()):
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.site / 'zh/news/index.html').stat().st_mode & 0o777, 0o644)
        for name in ('cache', 'candidates'):
            self.assertEqual((work / name).stat().st_mode & 0o777, 0o700)
        for name in ('active.json', 'pending-cdn.json'):
            self.assertEqual((work / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(self.env['NEWS_CONFIG_FILE']).stat().st_mode & 0o777, 0o600)
        # 已有文章时 bootstrap 不创建 Fetcher，也必须修复旧版本留下的根目录和状态权限。
        work.chmod(0o700)
        (work / 'active.json').chmod(0o644)
        (work / 'cache').chmod(0o755)
        self.install()
        self.assertEqual(work.stat().st_mode & 0o777, 0o711)
        self.assertEqual((work / 'active.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((work / 'cache').stat().st_mode & 0o777, 0o700)

    def test_replacing_sts_with_ak_clears_token_but_feed_only_change_preserves_credentials(self):
        """凭证按一组替换，Feed 单独修改不动凭证；新 AK 未提供 token 表示普通 AK。"""
        self.install({'ALIBABA_CLOUD_ACCESS_KEY_ID': 'sts-key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'sts-secret',
                      'ALIBABA_CLOUD_SECURITY_TOKEN': 'old-token'})
        self.install({'NEWS_FEED_URL': 'https://new.example/feed.json'})
        path = Path(self.env['NEWS_CONFIG_FILE'])
        self.assertEqual(json.loads(path.read_text())['ALIBABA_CLOUD_SECURITY_TOKEN'], 'old-token')
        self.install({'ALIBABA_CLOUD_ACCESS_KEY_ID': 'ak-key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'ak-secret'})
        saved = json.loads(path.read_text())
        self.assertEqual(saved['ALIBABA_CLOUD_ACCESS_KEY_ID'], 'ak-key')
        self.assertFalse(saved.get('ALIBABA_CLOUD_SECURITY_TOKEN'))

    def test_partial_credential_update_is_rejected_before_writing(self):
        """更新一半凭证不能悄悄沿用旧 secret/token；正式配置保持不变。"""
        self.install({'ALIBABA_CLOUD_ACCESS_KEY_ID': 'key', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'secret'})
        path = Path(self.env['NEWS_CONFIG_FILE']); before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, '凭证'):
            self.install({'ALIBABA_CLOUD_ACCESS_KEY_ID': 'new-key'})
        self.assertEqual(path.read_bytes(), before)

    def test_program_switch_failure_restores_original_configuration(self):
        """最后一次入口替换失败时，已暂时写入的新配置必须恢复，旧程序链接保持不变。"""
        self.install({'NEWS_FEED_URL': 'https://old.example/feed.json'})
        config = Path(self.env['NEWS_CONFIG_FILE']); before = config.read_bytes()
        target = Path(self.env['NEWS_INSTALL_DIR']); old = target.resolve()
        (self.stage / 'news/README.md').write_text('new program')
        real_replace = os.replace
        def fail_link(source, destination):
            """仅在程序链接提交边界注入磁盘错误，私有配置原子写入和恢复仍执行真实代码。"""
            if Path(destination) == target: raise OSError('simulated switch failure')
            return real_replace(source, destination)
        with patch.object(installer.os, 'replace', side_effect=fail_link):
            with self.assertRaises(OSError): self.install({'NEWS_FEED_URL': 'https://new.example/feed.json'})
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(target.resolve(), old)
        self.assertEqual(list(target.parent.glob(target.name + '.next-*')), [])

    def test_service_waits_for_install_lock_before_reading_configuration(self):
        """用真实子进程证明 service 在安装独占锁释放前不读取旧的损坏配置，释放后读取新配置。"""
        config = Path(self.env['NEWS_CONFIG_FILE'])
        config.write_text('invalid until installation completes')
        command = [sys.executable, str(ROOT / 'scripts/news/service-entry.py'), '--config', str(config)]
        with config.with_suffix('.json.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired): child.communicate(timeout=0.3)
                installer.write_private(config, {'NEWS_FEED_URL': ''})
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                try: stdout, stderr = child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate(); raise
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(json.loads(stdout)['reason'], 'feed_not_configured')

    def test_active_service_lock_defers_installer_configuration_reads(self):
        """运行服务持共享锁期间安装器等待；锁释放前不创建新配置或开始 systemctl 等安装步骤。"""
        config = Path(self.env['NEWS_CONFIG_FILE'])
        config.write_text('invalid configuration')
        # 锁释放后会在读取无效配置时退出，不会触发真实 systemctl；因此可安全执行真实 CLI。
        command = [sys.executable, str(ROOT / 'scripts/news/install-news.py'), '--stage', str(self.stage), '--apply']
        with config.with_suffix('.json.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            child = subprocess.Popen(command, env={**os.environ, **self.env}, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired): child.communicate(input='{}', timeout=0.3)
                self.assertEqual(config.read_text(), 'invalid configuration')
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                try: stdout, stderr = child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate(); raise
        self.assertEqual(child.returncode, 1)
        self.assertIn('官网发布安装失败', stderr)

    def test_first_install_creates_empty_page_before_main_site_and_enables_timer(self):
        """首次 Feed 留空也由安装阶段生成真实空页，主站更新后可访问，启用每十分钟任务。"""
        self.assertEqual(self.install(), 0)
        self.assertTrue((self.site / 'zh/news').is_symlink())
        self.assertIn('好内容，正在路上', (self.site / 'zh/news/index.html').read_text())
        self.assertEqual((self.site / 'index.html').read_text(), 'new marketing')
        self.assertFalse((self.site / 'old.html').exists())
        bootstrap = next(i for i, c in enumerate(self.commands) if '--bootstrap' in c)
        apply = next(i for i, c in enumerate(self.commands) if '--apply' in c)
        enable = self.commands.index(['systemctl', 'enable', '--now', 'jitai-news-sync.timer'])
        self.assertLess(bootstrap, apply)
        self.assertLess(apply, enable)
        config = Path(self.env['NEWS_CONFIG_FILE'])
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(config.read_text())['NEWS_FEED_URL'], '')
        text = (Path(self.env['NEWS_SYSTEMD_DIR']) / 'jitai-news-sync.timer').read_text()
        self.assertIn('OnCalendar=*-*-* *:00/10:00', text)
        self.assertIn(str(Path(self.env['NEWS_INSTALL_DIR']) / 'service-entry.py'),
                      (Path(self.env['NEWS_SYSTEMD_DIR']) / 'jitai-news-sync.service').read_text())

    def test_repeat_install_preserves_feed_secrets_published_data_and_pending(self):
        """重复发布沿用服务器配置、已有文章与刷新队列，不以 bootstrap 空页覆盖运行时数据。"""
        self.install({'NEWS_FEED_URL': 'https://content.example/feed.json',
                      'ALIBABA_CLOUD_ACCESS_KEY_ID': 'fake-id', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'fake-secret'})
        # 用独立真实同步 fixture 发布文章到相同数据与入口，避免仅修改文件而破坏候选校验。
        import test_sync_news as fixtures
        f = fixtures.NewsSyncTests(); f.setUp(); self.addCleanup(f.tearDown)
        env = {**f.env, 'NEWS_WORK_DIR': self.env['NEWS_WORK_DIR'], 'NEWS_LIVE_LINK': str(self.site / 'zh/news'),
               'NEWS_RELEASE_LOCK': self.env['NEWS_RELEASE_LOCK'], 'NEWS_SITE_ORIGIN': 'https://jit.pro'}
        config = fixtures.sync.Config(env)
        report = fixtures.sync.collect(config)
        fixtures.sync.publish(config, report['version'], env)
        active = (config.work / 'active.json').read_bytes()
        pending = (config.work / 'pending-cdn.json').read_bytes()
        self.commands.clear()
        self.install()
        self.assertEqual((config.work / 'active.json').read_bytes(), active)
        self.assertEqual((config.work / 'pending-cdn.json').read_bytes(), pending)
        self.assertIn('原始正文不重排', (self.site / 'zh/news/articles/one/index.html').read_text())
        saved = json.loads(Path(self.env['NEWS_CONFIG_FILE']).read_text())
        self.assertEqual(saved['NEWS_FEED_URL'], 'https://content.example/feed.json')
        self.assertEqual(saved['ALIBABA_CLOUD_ACCESS_KEY_SECRET'], 'fake-secret')
        # 显式空字符串才能停用，省略绝不能把原配置重置为空。
        self.install({'NEWS_FEED_URL': ''})
        self.assertEqual(json.loads(Path(self.env['NEWS_CONFIG_FILE']).read_text())['NEWS_FEED_URL'], '')

    def test_conflicting_news_route_aborts_before_install(self):
        """框架包抢占资讯路径时，安装器必须在写配置或调用 systemd 之前拒绝。"""
        (self.stage / 'site/zh/news.html').write_text('collision')
        with patch.object(installer.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, '抢占'):
                installer.install(self.stage, {}, self.env, True)
            run.assert_not_called()
        self.assertFalse(Path(self.env['NEWS_CONFIG_FILE']).exists())

    def test_bootstrap_failure_does_not_publish_main_site_or_enable_timer(self):
        """资讯初始化失败不能把新导航上线；保留原主站，且不启用尚未准备好的 timer。"""
        def fail_bootstrap(args, **kwargs):
            """在实际初始化命令边界模拟进程失败，其余步骤仍正常验证。"""
            if '--bootstrap' in args: raise subprocess.CalledProcessError(1, args)
            return self.run_command(args, **kwargs)
        with patch.object(installer.subprocess, 'run', side_effect=fail_bootstrap):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install(self.stage, {'NEWS_CDN_MODE': 'none'}, self.env, True)
        self.assertEqual((self.site / 'index.html').read_text(), 'old marketing')
        self.assertNotIn(['systemctl', 'enable', '--now', 'jitai-news-sync.timer'], self.commands)

    def test_publisher_uploads_only_to_stage_and_sends_secrets_via_stdin(self):
        """真实编排使用 SSH/rsync 替身；校验上传目标、安装顺序与凭证不出现在命令参数中。"""
        calls = []
        def transport(args, **kwargs):
            """记录传输边界，不建立 SSH 或执行任何云调用。"""
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0)
        env = {'BUILD_DIR': str(self.stage / 'site'), 'REMOTE_HOST': 'test.example',
               'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'fake-sensitive-secret', 'NEWS_FEED_URL': 'https://content.example/feed.json'}
        with patch.object(publisher.subprocess, 'run', side_effect=transport):
            self.assertEqual(publisher.publish(env, True), 0)
        uploads = [args for args, _ in calls if args[0] == 'rsync']
        self.assertEqual(len(uploads), 3)
        self.assertTrue(all(':/data/jitai-site-staging/' in args[-1] for args in uploads))
        self.assertFalse(any(':/data/jitai-docs-site' in args[-1] for args in uploads))
        install_index = next(i for i, (args, _) in enumerate(calls) if 'install-news.py' in args[-1])
        verify_index = next(i for i, (args, _) in enumerate(calls) if 'verify-site.py' in args[-1])
        self.assertLess(install_index, verify_index)
        self.assertEqual(json.loads(calls[install_index][1]['input'])['ALIBABA_CLOUD_ACCESS_KEY_SECRET'], 'fake-sensitive-secret')
        self.assertNotIn('fake-sensitive-secret', str([args for args, _ in calls]))
        self.assertNotIn('docker', str(calls))

    def test_publisher_preview_does_not_connect_or_require_retired_docs(self):
        """只有当前营销页面的包也能预览发布；不会再要求已下线的安装文档。"""
        with patch.object(publisher.subprocess, 'run') as run:
            self.assertEqual(publisher.publish({'BUILD_DIR': str(self.stage / 'site')}), 0)
            run.assert_not_called()

    def test_publisher_install_failure_stops_cdn_and_verification(self):
        """SSH 安装失败后保留暂存包，禁止继续 CDN 刷新或把发布报告为成功。"""
        calls = []
        def transport(args, **kwargs):
            """只模拟安装命令失败，其他传输记账但不实际连接。"""
            calls.append(args)
            if 'install-news.py' in args[-1]: raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0)
        with patch.object(publisher.subprocess, 'run', side_effect=transport):
            with self.assertRaises(subprocess.CalledProcessError):
                publisher.publish({'BUILD_DIR': str(self.stage / 'site')}, True)
        self.assertFalse(any('verify-site.py' in a[-1] or 'rm -rf' in a[-1] or 'bash /data/scripts/' in a[-1] for a in calls))

    def test_timer_service_command_runs_without_feed_or_cloud_profile(self):
        """执行实际安装后的 systemd ExecStart 命令，空 Feed 应正常结束且不改已有空页状态。"""
        self.install()
        config = json.loads(Path(self.env['NEWS_CONFIG_FILE']).read_text())
        active = Path(config['NEWS_WORK_DIR']) / 'active.json'
        before = active.read_bytes()
        unit = (Path(self.env['NEWS_SYSTEMD_DIR']) / 'jitai-news-sync.service').read_text()
        command = shlex.split(next(line[len('ExecStart='):] for line in unit.splitlines() if line.startswith('ExecStart=')))
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['reason'], 'feed_not_configured')
        self.assertEqual(active.read_bytes(), before)


class ServiceCredentialsTests(unittest.TestCase):
    """仅用虚构 profile 验证服务器本机注入，不读取真实用户或服务器凭证。"""

    def setUp(self):
        """每例独立配置与 profile，清空继承环境，避免宿主设置影响断言。"""
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config, self.profile = self.root / 'config.json', self.root / 'aliyun.json'
        self.config.write_text(json.dumps({'NEWS_FEED_URL': 'https://source.example/feed.json', 'NEWS_CDN_MODE': 'aliyun'}))
        self.profile.write_text(json.dumps({'current': 'news', 'profiles': [
            {'name': 'unrelated', 'mode': 'AK', 'access_key_id': 'wrong', 'access_key_secret': 'wrong'},
            {'name': 'news', 'mode': 'AK', 'access_key_id': 'right', 'access_key_secret': 'fake-secret'}]}))
        environment = patch.dict(os.environ, {}, clear=True); environment.start(); self.addCleanup(environment.stop)

    def test_current_profile_is_injected_only_into_returned_environment(self):
        """取 current 指定 profile，不使用第一项，不改写磁盘、不把凭证放到宿主全局环境。"""
        original = self.config.read_bytes()
        env = service.runtime_env(self.config, self.profile)
        self.assertEqual(env['ALIBABA_CLOUD_ACCESS_KEY_ID'], 'right')
        self.assertEqual(env['ALIBABA_CLOUD_ACCESS_KEY_SECRET'], 'fake-secret')
        self.assertNotIn('ALIBABA_CLOUD_ACCESS_KEY_SECRET', os.environ)
        self.assertEqual(self.config.read_bytes(), original)

    def test_explicit_credentials_do_not_read_profile(self):
        """显式环境 AK 优先，profile 不存在也能运行。"""
        self.profile.unlink()
        os.environ.update(ALIBABA_CLOUD_ACCESS_KEY_ID='explicit', ALIBABA_CLOUD_ACCESS_KEY_SECRET='secret')
        self.assertEqual(service.runtime_env(self.config, self.profile)['ALIBABA_CLOUD_ACCESS_KEY_ID'], 'explicit')

    def test_missing_feed_skips_profile_lookup(self):
        """未配置来源时不读取密钥，不因缺少 CLI profile 破坏正常跳过行为。"""
        self.config.write_text('{"NEWS_FEED_URL":"","NEWS_CDN_MODE":"aliyun"}')
        self.profile.unlink()
        self.assertEqual(service.runtime_env(self.config, self.profile)['NEWS_FEED_URL'], '')

    def test_partial_credentials_are_rejected(self):
        """显式 AK 只给一半时拒绝，不混用 profile 中另一半导致难以定位的签名错误。"""
        os.environ['ALIBABA_CLOUD_ACCESS_KEY_ID'] = 'partial'
        with self.assertRaisesRegex(ValueError, '不完整'): service.runtime_env(self.config, self.profile)

    def test_sts_token_profile_is_supported(self):
        """当前 STS profile 的 token 一并进入环境，保证临时凭证签名可用。"""
        self.profile.write_text(json.dumps({'current': 'sts', 'profiles': [{'name': 'sts', 'mode': 'StsToken',
                                  'access_key_id': 'key', 'access_key_secret': 'secret', 'sts_token': 'token'}]}))
        self.assertEqual(service.runtime_env(self.config, self.profile)['ALIBABA_CLOUD_SECURITY_TOKEN'], 'token')

    def test_ak_profile_discards_stale_token(self):
        """profile 的凭证是一组；普通 AK 不得混入配置或宿主环境遗留的 STS token。"""
        os.environ['ALIBABA_CLOUD_SECURITY_TOKEN'] = 'environment-token'
        data = json.loads(self.config.read_text()); data['ALIBABA_CLOUD_SECURITY_TOKEN'] = 'expired-token'
        self.config.write_text(json.dumps(data))
        env = service.runtime_env(self.config, self.profile)
        self.assertEqual(env['ALIBABA_CLOUD_ACCESS_KEY_ID'], 'right')
        self.assertNotIn('ALIBABA_CLOUD_SECURITY_TOKEN', env)

    def test_config_ak_does_not_inherit_environment_token(self):
        """配置文件显式 AK 覆盖环境凭证时，同时隔离环境中的旧 token。"""
        os.environ.update(ALIBABA_CLOUD_ACCESS_KEY_ID='old', ALIBABA_CLOUD_ACCESS_KEY_SECRET='old',
                          ALIBABA_CLOUD_SECURITY_TOKEN='expired')
        data = json.loads(self.config.read_text())
        data.update(ALIBABA_CLOUD_ACCESS_KEY_ID='new', ALIBABA_CLOUD_ACCESS_KEY_SECRET='new-secret')
        self.config.write_text(json.dumps(data))
        env = service.runtime_env(self.config, self.profile)
        self.assertEqual(env['ALIBABA_CLOUD_ACCESS_KEY_ID'], 'new')
        self.assertNotIn('ALIBABA_CLOUD_SECURITY_TOKEN', env)


class PublishedRouteTests(unittest.TestCase):
    """用真实本地 HTTP 服务验证部署检查，防止仍要求旧文档可用或漏掉退役博客。"""

    def setUp(self):
        """提供独立的当前营销/资讯响应；没有加入资源的旧页面由服务返回真实 404。"""
        import test_sync_news as fixtures
        self.fixture = fixtures.NewsSyncTests(); self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        resources = {'/': '<a href="/download">Download</a>', '/zh/': '<a href="/zh/news/">资讯中心</a>',
                     '/download': 'Apple installer', '/zh/download': 'Apple 芯片', '/contact': 'contact',
                     '/zh/contact': 'zhcontactus', '/zh/news/': '资讯中心',
                     '/zh/news/sitemap.xml': '<urlset></urlset>'}
        self.fixture.resources.update({path: (body.encode(), 'text/html') for path, body in resources.items()})

    def test_current_routes_and_retired_404_pass(self):
        """所有当前入口成功且旧路由 404 时验证通过，不依赖已删除安装指南的产物。"""
        verifier.verify(self.fixture.source)

    def test_cached_retired_blog_is_detected(self):
        """模拟 CDN 仍返回已下线博客，HTTP 检查必须失败而不是只确认首页正常。"""
        self.fixture.resources['/zh/blog'] = (b'old cached blog', 'text/html')
        with self.assertRaisesRegex(ValueError, '退役路由'):
            verifier.verify(self.fixture.source)

    def test_news_missing_or_wrong_page_fails(self):
        """资讯入口 200 但返回别的内容也必须失败，避免主站回退页掩盖初始化缺失。"""
        self.fixture.resources['/zh/news/'] = (b'wrong home page', 'text/html')
        with self.assertRaisesRegex(ValueError, '内容'):
            verifier.verify(self.fixture.source)


if __name__ == '__main__':
    unittest.main()
