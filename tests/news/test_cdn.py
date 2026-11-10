"""CDN 协议与状态测试：只替换 HTTP 传输，不替换真实签名、分批、发布或重试业务。

凭证均为固定虚构字符串，响应内存构造；不会向真实阿里云 API 发出请求。
"""

import contextlib
import datetime
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

import test_sync_news as fixture_module

sync = fixture_module.sync


class RecordingTransport:
    """记录实际 Request 并返回指定 JSON；失败只发生于 HTTP 边界，不绕过签名算法。"""

    def __init__(self, fail_at=None):
        """fail_at 为从 1 开始的失败请求序号；None 表示全部返回成功任务 ID。"""
        self.requests = []
        self.fail_at = fail_at

    def open(self, request, timeout):
        """接收 urllib Request，记录后返回可关闭字节流；指定序号模拟网络失败。"""
        self.requests.append(request)
        if len(self.requests) == self.fail_at:
            raise URLError('simulated network failure')
        return io.BytesIO(json.dumps({'RefreshTaskId': 'test-task'}).encode())


class CdnTests(unittest.TestCase):
    """覆盖稳定签名向量、分批请求以及持久化 pending 的真实重试路径。"""

    def setUp(self):
        """仅准备虚构环境凭证；不读取机器上的任何阿里云配置或真实密钥。"""
        self.env = {'NEWS_CDN_MODE': 'aliyun', 'ALIBABA_CLOUD_ACCESS_KEY_ID': 'test-key',
                    'ALIBABA_CLOUD_ACCESS_KEY_SECRET': 'test-secret', 'ALIBABA_CLOUD_SECURITY_TOKEN': 'test-token'}

    def test_signature_matches_fixed_request_vector(self):
        """冻结时间和 nonce，核对固定预期签名及 POST 端点，防止编码规则回归。"""
        transport = RecordingTransport()
        fixed = datetime.datetime(2026, 11, 10, tzinfo=datetime.timezone.utc)
        with patch.object(sync, 'build_opener', return_value=transport), patch.object(sync.uuid, 'uuid4', return_value='fixed-nonce'), patch.object(sync.dt, 'datetime') as clock:
            clock.now.return_value = fixed
            sync.refresh_cdn(['https://official.example/zh/news/'], self.env)
        request = transport.requests[0]
        data = parse_qs(request.data.decode())
        self.assertEqual(request.full_url, 'https://cdn.aliyuncs.com/')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(data['Signature'], ['ROZMNxWbEBQswc1E46JvkTNQvTY='])
        self.assertEqual(data['SecurityToken'], ['test-token'])
        self.assertEqual(data['ObjectType'], ['File'])

    def test_urls_are_split_into_batches_without_loss(self):
        """101 个地址分两批，逐项验证发送内容，无遗漏或重复，最后一条可能是下线地址。"""
        urls = [f'https://official.example/zh/news/articles/{index}/' for index in range(101)]
        transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.refresh_cdn(urls, self.env)
        batches = [parse_qs(request.data.decode())['ObjectPath'][0].splitlines() for request in transport.requests]
        self.assertEqual(list(map(len, batches)), [100, 1])
        self.assertEqual([url for batch in batches for url in batch], urls)

    def test_partial_batch_failure_is_reported(self):
        """第一批成功、第二批失败不能假报全部刷新成功；调用方可保留整份 pending 重试。"""
        transport = RecordingTransport(fail_at=2)
        with patch.object(sync, 'build_opener', return_value=transport):
            with self.assertRaisesRegex(sync.SyncError, 'CDN 刷新请求失败'):
                sync.refresh_cdn([f'https://official.example/{i}' for i in range(101)], self.env)

    def test_disabled_mode_never_opens_transport(self):
        """关闭 CDN 时不需要凭证，也不访问云端；队列是否保留由发布层另行验证。"""
        with patch.object(sync, 'build_opener') as opener:
            sync.refresh_cdn(['https://official.example/zh/news/'], {})
            opener.assert_not_called()

    def test_empty_queue_requires_no_credentials_or_network(self):
        """没有待刷地址时，即使启用 aliyun 也应直接完成，不因未用到的凭证报错。"""
        with patch.object(sync, 'build_opener') as opener:
            sync.refresh_cdn([], {'NEWS_CDN_MODE': 'aliyun'})
            opener.assert_not_called()

    def test_invalid_mode_and_missing_credentials_fail_before_network(self):
        """有刷新任务时拒绝未知模式与不完整 AK，防止配置错误被当成成功。"""
        for env, message in (({'NEWS_CDN_MODE': 'typo'}, '只支持'),
                             ({'NEWS_CDN_MODE': 'aliyun'}, '缺少环境凭证'),
                             ({**self.env, 'ALIBABA_CLOUD_ACCESS_KEY_ID': ''}, '缺少环境凭证'),
                             ({**self.env, 'ALIBABA_CLOUD_ACCESS_KEY_SECRET': ''}, '缺少环境凭证')):
            with self.subTest(env=env), patch.object(sync, 'build_opener') as opener:
                with self.assertRaisesRegex(sync.SyncError, message):
                    sync.refresh_cdn(['https://official.example/zh/news/'], env)
                opener.assert_not_called()

    def test_long_term_credentials_omit_sts_token(self):
        """长期 AK 无 STS token 仍能签名；请求带正确 API 版本，且绝不发送 secret 原文。"""
        env = {key: value for key, value in self.env.items() if key != 'ALIBABA_CLOUD_SECURITY_TOKEN'}
        transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.refresh_cdn(['https://official.example/zh/news/'], env)
        data = parse_qs(transport.requests[0].data.decode())
        self.assertNotIn('SecurityToken', data)
        self.assertEqual(data['Action'], ['RefreshObjectCaches'])
        self.assertEqual(data['Version'], ['2018-05-10'])
        self.assertNotIn('test-secret', transport.requests[0].data.decode())

    def test_batch_boundaries_and_url_encoding(self):
        """1、100、200、201 条验证边界；中文、空格和查询参数编码后必须无损恢复。"""
        for count, sizes in ((1, [1]), (100, [100]), (200, [100, 100]), (201, [100, 100, 1])):
            with self.subTest(count=count):
                urls = [f'https://official.example/zh/news/中文 {i}?a=1&b=%2B' for i in range(count)]
                transport = RecordingTransport()
                with patch.object(sync, 'build_opener', return_value=transport):
                    sync.refresh_cdn(urls, self.env)
                batches = [parse_qs(r.data.decode())['ObjectPath'][0].splitlines() for r in transport.requests]
                self.assertEqual([len(batch) for batch in batches], sizes)
                self.assertEqual([url for batch in batches for url in batch], urls)
                nonces = [parse_qs(r.data.decode())['SignatureNonce'][0] for r in transport.requests]
                self.assertEqual(len(set(nonces)), len(nonces))

    def test_transport_errors_are_sanitized_and_stop_later_batches(self):
        """HTTP 限流/鉴权/服务错误、超时和断网不泄露响应或凭证，且停止后续批次。"""
        for error in (HTTPError('https://cdn.aliyuncs.com/', 403, 'test-secret', {}, None),
                      HTTPError('https://cdn.aliyuncs.com/', 429, 'test-secret', {}, None),
                      HTTPError('https://cdn.aliyuncs.com/', 500, 'test-secret', {}, None),
                      URLError('test-secret'), TimeoutError('test-secret')):
            with self.subTest(error=type(error).__name__), patch.object(sync, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(sync.SyncError, 'CDN 刷新请求失败') as raised:
                    sync.refresh_cdn([f'https://official.example/{i}' for i in range(201)], self.env)
                self.assertNotIn('test-secret', str(raised.exception))
                self.assertEqual(opener.return_value.open.call_count, 1)

    def test_api_error_or_malformed_success_cannot_acknowledge_refresh(self):
        """HTTP 200 不等于受理；错误码、缺失/空/非字符串任务 ID 及非法 JSON 都必须失败。"""
        responses = [b'not-json', b'null', b'[]', b'"RefreshTaskId"', b'{}',
                     b'{"RefreshTaskId":null}', b'{"RefreshTaskId":""}',
                     b'{"RefreshTaskId":"  "}', b'{"RefreshTaskId":123}',
                     b'{"Code":"Forbidden","Message":"test-secret"}',
                     b'{"Code":"Forbidden","RefreshTaskId":"task","Message":"test-secret"}']
        for body in responses:
            with self.subTest(body=body), patch.object(sync, 'build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(body)
                with self.assertRaises(sync.SyncError) as raised:
                    sync.refresh_cdn(['https://official.example/zh/news/'], self.env)
                self.assertNotIn('test-secret', str(raised.exception))

    def fixture(self):
        """创建独立 HTTP 内容源与临时发布区，注册清理；持久化测试使用真实生成和发布逻辑。"""
        fixture = fixture_module.NewsSyncTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def retry(self, fixture, transport, env=None):
        """运行真实 retry-cdn CLI，仅隔离环境与云传输；返回退出码和已脱敏的标准错误。"""
        errors = io.StringIO()
        with patch.dict(os.environ, {**fixture.env, **(self.env if env is None else env)}, clear=True), \
                patch.object(sys, 'argv', ['sync_news.py', 'retry-cdn']), \
                patch.object(sync, 'build_opener', return_value=transport), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            code = sync.main()
        return code, errors.getvalue()

    def test_disabled_publish_and_retry_preserve_pending(self):
        """none 模式允许源站发布但不能丢掉刷新任务，重试也不得访问云端或清空队列。"""
        fixture = self.fixture()
        report = sync.collect(fixture.config)
        transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.publish(fixture.config, report['version'], fixture.env)
        path = fixture.config.work / 'pending-cdn.json'
        before = path.read_bytes()
        self.assertTrue(json.loads(before))
        self.assertEqual(self.retry(fixture, transport, {'NEWS_CDN_MODE': 'none'})[0], 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(transport.requests, [])

    def test_failed_retry_keeps_entire_queue_until_all_batches_succeed(self):
        """第二批失败后整份 201 条队列保持不变；下次重复提交安全，全部受理后才清空。"""
        fixture = self.fixture()
        pending = [f'https://official.example/zh/news/articles/deleted-{i}/' for i in range(201)]
        path = fixture.config.work / 'pending-cdn.json'
        sync.atomic_json(path, pending)
        before = path.read_bytes()
        failing = RecordingTransport(fail_at=2)
        code, errors = self.retry(fixture, failing)
        self.assertEqual(code, 1)
        self.assertIn('CDN 刷新请求失败', errors)
        self.assertEqual(len(failing.requests), 2)
        self.assertEqual(path.read_bytes(), before)
        successful = RecordingTransport()
        self.assertEqual(self.retry(fixture, successful)[0], 0)
        sent = [url for r in successful.requests for url in parse_qs(r.data.decode())['ObjectPath'][0].splitlines()]
        self.assertEqual(sent, pending)
        self.assertEqual(sync.load_json(path), [])

    def test_invalid_api_response_preserves_pending_and_fails_cli(self):
        """API 错误和伪成功不能让 CLI 返回成功或清空任务，日志不得包含服务端回显的密钥。"""
        fixture = self.fixture()
        path = fixture.config.work / 'pending-cdn.json'
        pending = ['https://official.example/zh/news/articles/deleted/']
        for body in (b'{"Code":"Forbidden","Message":"test-secret"}',
                     b'{"RefreshTaskId":null}', b'null', b'not-json'):
            with self.subTest(body=body):
                sync.atomic_json(path, pending)
                transport = RecordingTransport()
                with patch.object(transport, 'open', return_value=io.BytesIO(body)):
                    code, errors = self.retry(fixture, transport)
                self.assertEqual(code, 1)
                self.assertNotIn('test-secret', errors)
                self.assertEqual(sync.load_json(path), pending)

    def test_empty_retry_succeeds_without_credentials(self):
        """无 pending 的定时重试正常完成，不需要 AK，不产生网络请求。"""
        fixture = self.fixture()
        transport = RecordingTransport()
        self.assertEqual(self.retry(fixture, transport, {'NEWS_CDN_MODE': 'aliyun'})[0], 0)
        self.assertEqual(transport.requests, [])
        self.assertEqual(sync.load_json(fixture.config.work / 'pending-cdn.json'), [])

    def test_bootstrap_retries_initial_pending_even_without_feed(self):
        """第一次安装刷新失败后再次安装，显式 bootstrap 应完成遗留队列，不依赖启用 Feed。"""
        fixture = self.fixture()
        fixture.build_publish()
        active = (fixture.config.work / 'active.json').read_bytes()
        pending = sync.load_json(fixture.config.work / 'pending-cdn.json')
        transport = RecordingTransport()
        with patch.dict(os.environ, {**fixture.env, **self.env, 'NEWS_FEED_URL': ''}, clear=True), \
                patch.object(sys, 'argv', ['sync_news.py', 'bootstrap']), \
                patch.object(sync, 'build_opener', return_value=transport), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(), 0)
        sent = [url for r in transport.requests for url in parse_qs(r.data.decode())['ObjectPath'][0].splitlines()]
        self.assertEqual(sent, pending)
        self.assertEqual(sync.load_json(fixture.config.work / 'pending-cdn.json'), [])
        self.assertEqual((fixture.config.work / 'active.json').read_bytes(), active)

    def test_new_publish_merges_old_failures_and_refreshes_removed_resources(self):
        """实际发布新增/修改/下线文章，刷新列表、sitemap、地址变体、同名图片/CSS 和旧失败项。"""
        fixture = self.fixture()
        image = '/api/whwy/app123/storages/preview?file=cover.svg'
        fixture.resources[image] = (b'<svg/>', 'image/svg+xml')
        for slug in ('one', 'two'):
            fixture.resources['/' + slug + '.html'] = (
                ('<html><head><link rel="stylesheet" href="' + slug + '.css"></head>'
                 '<body><article><h1>文章</h1><img src="' + image + '"></article></body></html>').encode(), 'text/html')
            fixture.resources['/' + slug + '.css'] = (b'body{color:red}', 'text/css')
        fixture.build_publish()
        # 覆盖初次 none 模式的队列，独立模拟很早之前下线但刷新失败的任务。
        orphan = 'https://official.example/zh/news/articles/older/index.html'
        sync.atomic_json(fixture.config.work / 'pending-cdn.json', [orphan])
        fixture.feed['items'][1] = {'id': 'three', 'url': fixture.source + '/three.html', 'title': '新文章'}
        fixture.resources['/three.html'] = (b'<html><head><title>new</title></head><body><article><h1>new article</h1></article></body></html>', 'text/html')
        fixture.resources['/one.css'] = (b'body{color:blue}', 'text/css')
        fixture.resources[image] = (b'<svg width="20"/>', 'image/svg+xml')
        fixture.save_feed()
        report = sync.collect(fixture.config)
        transport = RecordingTransport()
        with patch.object(sync, 'build_opener', return_value=transport):
            sync.publish(fixture.config, report['version'], {**fixture.env, **self.env})
        sent = [url for r in transport.requests for url in parse_qs(r.data.decode())['ObjectPath'][0].splitlines()]
        expected = {orphan, 'https://official.example/zh/news', 'https://official.example/zh/news/',
                    'https://official.example/zh/news/index.html', 'https://official.example/zh/news/sitemap.xml',
                    'https://official.example/zh/news/assets/cover.svg',
                    'https://official.example/zh/news/articles/one/one.css',
                    'https://official.example/zh/news/articles/two/two.css'}
        for slug in ('one', 'two', 'three'):
            expected.update('https://official.example/zh/news/articles/' + slug + suffix
                            for suffix in ('', '/', '/index.html'))
        self.assertEqual(set(sent), expected)
        self.assertEqual(len(sent), len(set(sent)))
        self.assertFalse((fixture.root / 'live/articles/two').exists())
        self.assertTrue((fixture.root / 'live/articles/three/index.html').is_file())
        self.assertEqual((fixture.root / 'live/articles/one/one.css').read_bytes(), b'body{color:blue}')
        self.assertEqual((fixture.root / 'live/assets/cover.svg').read_bytes(), b'<svg width="20"/>')
        self.assertEqual(sync.load_json(fixture.config.work / 'pending-cdn.json'), [])

    def test_retry_cdn_sends_saved_urls_then_clears_pending(self):
        """失败发布已经切换源站；真实 retry-cdn CLI 读取持久化 URL，成功后才清空 pending。"""
        fixture = fixture_module.NewsSyncTests()
        fixture.setUp()
        try:
            report = sync.collect(fixture.config)
            failing = RecordingTransport(fail_at=1)
            env = {**fixture.env, **self.env}
            with patch.object(sync, 'build_opener', return_value=failing):
                with self.assertRaisesRegex(sync.SyncError, 'CDN 刷新请求失败'):
                    sync.publish(fixture.config, report['version'], env)
            pending = sync.load_json(fixture.config.work / 'pending-cdn.json')
            self.assertIn('https://official.example/zh/news/articles/one/index.html', pending)
            self.assertEqual(sync.load_json(fixture.config.work / 'active.json')['version'], report['version'])
            successful = RecordingTransport()
            with patch.dict(os.environ, env), patch.object(sys, 'argv', ['sync_news.py', 'retry-cdn']), patch.object(sync, 'build_opener', return_value=successful), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sync.main(), 0)
            sent = parse_qs(successful.requests[0].data.decode())['ObjectPath'][0].splitlines()
            self.assertEqual(sent, pending)
            self.assertEqual(sync.load_json(fixture.config.work / 'pending-cdn.json'), [])
        finally:
            fixture.tearDown()
