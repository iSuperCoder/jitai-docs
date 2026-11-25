"""主站真实文件差异与持久化队列测试；仅替换云 API 传输，绝不发送真实刷新。"""
import importlib.util
import json
import os
import pwd
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('main_cdn', Path(__file__).resolve().parents[2] / 'scripts/news/refresh-main-cdn.py')
cdn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdn)


class MainCdnQueueTests(unittest.TestCase):
    """每例使用独立目录和可观察 API 参数，验证不同失败阶段不会互相掩盖。"""

    def setUp(self):
        """准备真实静态文件、独立状态和退役清单；没有任何默认生产路径。"""
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.build = self.root / 'build'; self.build.mkdir()
        self.state_path = self.root / 'state.json'; self.domain = 'https://official.example'
        (self.build / 'index.html').write_text('home')
        self.objects = [('Directory', self.domain + '/old/'), ('File', self.domain + '/old')]
        self.calls = []

    def api(self, action, **params):
        """记录真实参数，提供独立固定配额和任务 ID；不实现被测分批与去重逻辑。"""
        self.calls.append((action, params))
        return {'UrlRemain': '10000', 'DirRemain': '100'} if action == 'DescribeRefreshQuota' else {'RefreshTaskId': 'accepted'}

    def plan(self, state=None):
        """真实扫描当前目录，返回已持久化的候选队列供后续 drain 使用。"""
        state = cdn.plan(state or {}, self.build, self.domain, self.objects, 'zh/news')
        cdn.save(self.state_path, state)
        return state

    def test_unchanged_files_and_retired_routes_are_not_resubmitted(self):
        """首轮受理后，再发布相同主站及退役清单不查询配额、更不重复刷新目录。"""
        state = self.plan(); cdn.drain(self.state_path, state, self.api)
        self.calls.clear(); state = self.plan(state)
        self.assertEqual(cdn.drain(self.state_path, state, self.api), {'accepted': 0, 'pending': 0})
        self.assertEqual(self.calls, [])

    def test_root_alias_never_submits_bare_domain(self):
        """根首页只能生成 / 与 /index.html；裸域名会让阿里云拒绝整个批次。"""
        self.assertEqual(cdn.aliases('index.html', self.domain), {self.domain + '/', self.domain + '/index.html'})
        self.assertEqual(cdn.aliases('zh/index.html', self.domain), {self.domain + '/zh/', self.domain + '/zh', self.domain + '/zh/index.html'})
        state = self.plan({'pending': [('File', self.domain)]})
        self.assertNotIn(('File', self.domain), state['pending'])
        self.assertIn(('File', self.domain + '/'), state['pending'])

    def test_single_css_change_only_refreshes_that_file(self):
        """同名 CSS 字节变化独立触发；首页及已处理的退役目录均不进入请求。"""
        (self.build / 'style.css').write_text('old')
        state = self.plan(); cdn.drain(self.state_path, state, self.api)
        (self.build / 'style.css').write_text('new')
        state = self.plan(state)
        self.assertEqual(state['pending'], [('File', self.domain + '/style.css')])

    def test_deleted_media_and_changed_html_include_public_urls(self):
        """下线媒体仍刷新旧 URL，修改 HTML 包含其别名；未知媒体后缀也按字节扫描。"""
        (self.build / 'movie.custom').write_bytes(b'video'); (self.build / 'cases.html').write_text('old')
        state = self.plan(); cdn.drain(self.state_path, state, self.api)
        (self.build / 'movie.custom').unlink(); (self.build / 'cases.html').write_text('new')
        state = self.plan(state)
        self.assertEqual(set(map(tuple, state['pending'])), {('File', self.domain + p) for p in ['/movie.custom', '/cases', '/cases/', '/cases.html']})

    def test_news_real_directory_and_symlink_are_excluded(self):
        """实体资讯目录和指向站外的链接均不进入主站摘要，职责不因目录形态改变。"""
        (self.build / 'zh/news').mkdir(parents=True); (self.build / 'zh/news/index.html').write_text('news')
        (self.root / 'external').write_text('private'); (self.build / 'linked').symlink_to(self.root / 'external')
        state = self.plan()
        self.assertEqual(state['files'].keys(), {'index.html'})

    def test_directory_quota_zero_still_refreshes_files(self):
        """目录配额耗尽但文件有额度时，只提交文件一批，目录持久化等待后续。"""
        state = self.plan()
        def api(action, **params):
            """仅将目录额度设为零，文件额度与刷新响应保持合法。"""
            self.calls.append((action, params))
            return {'UrlRemain': '100', 'DirRemain': '0'} if action == 'DescribeRefreshQuota' else {'RefreshTaskId': 'ok'}
        result = cdn.drain(self.state_path, state, api)
        self.assertGreater(result['accepted'], 0); self.assertEqual(result['pending'], 1)
        self.assertEqual(json.loads(self.state_path.read_text())['pending'], [['Directory', self.domain + '/old/']])
        self.assertEqual([p['ObjectType'] for a, p in self.calls if a == 'RefreshObjectCaches'], ['File'])

    def test_batch_limits_and_partial_quota_preserve_remainder(self):
        """1001 个 File 本轮最多受理 1000；目录限额为 2，剩余独立保留，下轮不重复成功项。"""
        state = {'pending': [('File', self.domain + f'/f{i}') for i in range(1001)] + [('Directory', self.domain + f'/d{i}/') for i in range(3)]}
        def api(action, **params):
            """配额只允许两个目录，记录批次原始多行参数。"""
            self.calls.append((action, params))
            return {'UrlRemain': '9000', 'DirRemain': '2'} if action == 'DescribeRefreshQuota' else {'RefreshTaskId': 'ok'}
        result = cdn.drain(self.state_path, state, api)
        batches = [p['ObjectPath'].splitlines() for a, p in self.calls if a == 'RefreshObjectCaches']
        self.assertEqual(list(map(len, batches)), [1000, 2])
        self.assertEqual(result, {'accepted': 1002, 'pending': 2})
        self.assertEqual(state['pending'], [('File', self.domain + '/f1000'), ('Directory', self.domain + '/d2/')])
        self.calls.clear()
        with patch.object(cdn.time, 'time', return_value=state['next_attempt'] + 1):
            cdn.drain(self.state_path, state, self.api)
        self.assertEqual([p['ObjectPath'] for a, p in self.calls if a == 'RefreshObjectCaches'], [self.domain + '/f1000', self.domain + '/d2/'])

    def test_second_batch_failure_keeps_only_unacknowledged_tasks(self):
        """File 成功、Directory 失败时，成功批次已落盘；重试不重新消耗文件刷新额度。"""
        state = self.plan()
        def api(action, **params):
            """仅目录提交阶段失败，配额与 File 受理保持有效。"""
            if params.get('ObjectType') == 'Directory': raise RuntimeError('failure')
            return self.api(action, **params)
        with self.assertRaisesRegex(RuntimeError, 'failure'): cdn.drain(self.state_path, state, api)
        self.assertEqual(json.loads(self.state_path.read_text())['pending'], [['Directory', self.domain + '/old/']])

    def test_quota_or_refresh_malformed_response_never_loses_queue(self):
        """无效配额和伪成功分别测试；目标条件之外都合法，队列不被错误确认。"""
        for stage in ('quota', 'refresh'):
            with self.subTest(stage=stage):
                state = self.plan()
                def api(action, **params):
                    """按目标阶段返回无效结构，另一阶段提供合法响应。"""
                    if action == 'DescribeRefreshQuota':
                        return {'UrlRemain': 'invalid', 'DirRemain': '100'} if stage == 'quota' else {'UrlRemain': '100', 'DirRemain': '100'}
                    return {'RefreshTaskId': ''}
                before = list(state['pending'])
                with self.assertRaises((ValueError, RuntimeError)): cdn.drain(self.state_path, state, api)
                self.assertEqual(state['pending'], before)

    def test_next_attempt_throttles_repeated_invocation(self):
        """频繁调用不会连续查询/提交；配额恢复的后续轮次才可重试。"""
        state = {'pending': [('File', self.domain + '/a')], 'next_attempt': 100}
        with patch.object(cdn.time, 'time', return_value=99):
            self.assertEqual(cdn.drain(self.state_path, state, self.api)['pending'], 1)
        self.assertEqual(self.calls, [])

    def test_shell_entry_uses_cli_batches_and_persistent_state(self):
        """运行真实 shell→Python→CLI 装配链，替身仅是 CLI 可执行文件；同次清单第二轮不发请求。"""
        binary = self.root / 'bin'; binary.mkdir()
        log = self.root / 'cli.jsonl'
        executable = binary / 'aliyun'
        # 使用本测试解释器启动 CLI 替身，只记录 argv 并给出固定响应，不复制队列算法。
        executable.write_text('#!' + sys.executable + '\n' +
            'import os,json,sys\n' +
            'with open(os.environ["CLI_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n' +
            'print(json.dumps({"UrlRemain":"10000","DirRemain":"100"} if sys.argv[2]=="DescribeRefreshQuota" else {"RefreshTaskId":"ok"}))\n')
        executable.chmod(0o755)
        env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
               'BUILD_DIR': str(self.build), 'DOMAIN': self.domain, 'MAIN_CDN_STATE_FILE': str(self.state_path),
               'NEWS_PYTHON': sys.executable, 'CLI_LOG': str(log), 'DRY_RUN': '0'}
        command = ['bash', str(Path(__file__).resolve().parents[2] / 'refresh_cdn.sh')]
        subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([call[1] for call in calls], ['DescribeRefreshQuota', 'RefreshObjectCaches', 'RefreshObjectCaches'])
        self.assertGreater(len(calls[1][calls[1].index('--ObjectPath') + 1].splitlines()), 1)
        before = log.read_bytes()
        subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(log.read_bytes(), before)

    def test_cli_config_path_in_service_and_login_environments(self):
        """真实启动 CLI 替身检查配置定位：无 HOME 的 systemd 环境用账户主目录，有 HOME 时沿用它。

        替身只回传 argv，不读取账户配置或访问云；账户目录预期独立来自操作系统用户记录。
        线上 CLI 在缺少 HOME 且未指定配置时会报 region can't be empty，不能只测登录 shell。
        """
        binary = self.root / 'cli-bin'; binary.mkdir()
        executable = binary / 'aliyun'
        executable.write_text('#!' + sys.executable + '\nimport json,sys\nprint(json.dumps({"args":sys.argv[1:]}))\n')
        executable.chmod(0o755)
        for home in (None, str(self.root / 'custom-home')):
            with self.subTest(home=home):
                env = {'PATH': str(binary)}
                if home is not None: env['HOME'] = home
                expected = (home or pwd.getpwuid(os.getuid()).pw_dir) + '/.aliyun/config.json'
                with patch.dict(os.environ, env, clear=True):
                    args = cdn.aliyun('DescribeRefreshQuota')['args']
                    self.assertEqual(os.environ.get('HOME'), home)
                self.assertIn('--config-path', args)
                self.assertEqual(args[args.index('--config-path') + 1], expected)


if __name__ == '__main__':
    unittest.main()
