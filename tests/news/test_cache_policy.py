"""CDN 策略测试：替身只模拟阿里云配置存取，预期来自官网的缓存寿命及恢复契约。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_sync_news  # 配置独立部署脚本的正式模块搜索路径。
import cache_policy


class CachePolicyTests(unittest.TestCase):
    """每例独立云配置和磁盘备份，不联网、不调用实际 aliyun CLI。"""

    def setUp(self):
        """重现线上根目录 30 天、权重 99，以及一项与本次无关的图片子目录规则。"""
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)/'backup.json';self.queue=Path(self.temp.name)/'cdn.json'
        self.configs=[{'ConfigId':1,'FunctionName':'path_based_ttl_set','Status':'success','ParentId':0,
                       'FunctionArgs':{'FunctionArg':[{'ArgName':'path','ArgValue':'/'},{'ArgName':'ttl','ArgValue':'2592000'},{'ArgName':'weight','ArgValue':'99'}]}},
                      {'ConfigId':2,'FunctionName':'path_based_ttl_set','Status':'success','ParentId':0,
                       'FunctionArgs':{'FunctionArg':[{'ArgName':'path','ArgValue':'/unrelated/'},{'ArgName':'ttl','ArgValue':'15'}]}}]
        self.before=copy.deepcopy(self.configs);self.calls=[]

    def api(self,action,**params):
        """按接口参数保存／返回原始设置，不计算策略、不决定目录应缓存多久。"""
        self.calls.append((action,params))
        if action=='DescribeCdnDomainConfigs':return {'DomainConfigs':{'DomainConfig':copy.deepcopy(self.configs)}}
        if action=='DeleteSpecificConfig':
            self.configs=[c for c in self.configs if c['ConfigId']!=params['ConfigId']];return {'RequestId':'ok'}
        if action=='BatchSetCdnDomainConfig':
            results=[]
            for f in json.loads(params['Functions']):
                identity=f.get('configId',max([c['ConfigId'] for c in self.configs],default=0)+1)
                self.configs=[c for c in self.configs if c['ConfigId']!=identity]
                self.configs.append({'ConfigId':identity,'FunctionName':f['functionName'],'Status':'success','ParentId':0,
                                     'FunctionArgs':{'FunctionArg':[{'ArgName':a['argName'],'ArgValue':a['argValue']} for a in f['functionArgs']]}})
                results.append({'ConfigId':identity,'DomainName':'jit.pro','FunctionName':f['functionName']})
            return {'DomainConfigList':{'DomainConfigModel':results}}
        raise AssertionError('Unexpected API '+action)

    def test_preview_is_read_only(self):
        """预览只 Describe，且给出复用根规则 ID 的计划，不创建状态或云配置。"""
        result=cache_policy.configure('jit.pro',self.state,api=self.api,cdn_state=self.queue)
        self.assertFalse(result['apply']);self.assertEqual(result['changes'][0]['configId'],1)
        self.assertEqual(self.configs,self.before);self.assertFalse(self.state.exists());self.assertFalse(self.queue.exists())
        self.assertEqual([a for a,_ in self.calls],['DescribeCdnDomainConfigs'])

    def test_apply_sets_distinct_ttls_and_idempotently_keeps_unrelated_settings(self):
        """HTML 60 秒、可变文件 300 秒、内容寻址文件一年，浏览器跟随；重发不重复配置或排队。"""
        result=cache_policy.configure('jit.pro',self.state,True,self.api,self.queue)
        self.assertTrue(result['verified'])
        by_path={cache_policy.arguments(c).get('path'):cache_policy.arguments(c) for c in self.configs}
        for path,ttl in [('/',60),('/zh/news/assets/',300),('/img/',300),('/assets/',31536000),('/zh/news/ui/',31536000)]:
            self.assertEqual(by_path[path]['ttl'],str(ttl))
            self.assertEqual(by_path[path]['swift_follow_cachetime'],'on')
        self.assertEqual(by_path['/']['weight'],'1')
        self.assertIn(self.before[1],self.configs)
        self.assertEqual(json.loads(self.state.read_text())['before'],self.before)
        self.assertIn(['Directory','https://jit.pro/'],json.loads(self.queue.read_text())['pending'])
        self.calls.clear();cache_policy.configure('jit.pro',self.state,True,self.api,self.queue)
        self.assertEqual([a for a,_ in self.calls],['DescribeCdnDomainConfigs'])

    def test_response_loss_retries_by_reading_cloud_and_retains_refresh_queue(self):
        """云端已接受但响应丢失后，不重复创建规则；备份和整站旧缓存刷新任务仍在。"""
        def lose_response(action,**params):
            """仅让写调用的响应丢失，实际配置已经存入云替身。"""
            result=self.api(action,**params)
            if action=='BatchSetCdnDomainConfig':raise RuntimeError('response lost')
            return result
        with self.assertRaisesRegex(RuntimeError,'response lost'):
            cache_policy.configure('jit.pro',self.state,True,lose_response,self.queue)
        count=len(self.configs);self.calls.clear()
        self.assertFalse(cache_policy.configure('jit.pro',self.state,True,self.api,self.queue)['changed'])
        self.assertEqual(len(self.configs),count)
        self.assertTrue(json.loads(self.queue.read_text())['pending'])

    def test_restore_reinstates_original_rules_and_removes_only_created_items(self):
        """恢复根目录原设置、删本次新规则，保留无关目录；回读参数一致后才报成功。"""
        cache_policy.configure('jit.pro',self.state,True,self.api,self.queue)
        self.assertTrue(cache_policy.restore('jit.pro',self.state,self.api)['restored'])
        self.assertEqual(sorted(self.configs,key=lambda c:c['ConfigId']),self.before)

    def test_conflicting_response_header_stops_before_any_write(self):
        """Cache-Control 被另一规则改写时不得假报浏览器遵循 TTL，预检失败且不写备份。"""
        self.configs.append({'ConfigId':3,'FunctionName':'set_resp_header','Status':'success',
                             'FunctionArgs':{'FunctionArg':[{'ArgName':'key','ArgValue':'Cache-Control'},{'ArgName':'value','ArgValue':'max-age=999999'}]}})
        with self.assertRaisesRegex(ValueError,'重叠'):
            cache_policy.configure('jit.pro',self.state,True,self.api,self.queue)
        self.assertFalse(self.state.exists())
        self.assertEqual([a for a,_ in self.calls],['DescribeCdnDomainConfigs'])

    def test_refresh_queue_merge_preserves_pending_and_domain(self):
        """缓存策略刷新与既有失败队列并存，不覆盖文件刷新或下一次尝试时间。"""
        self.queue.write_text(json.dumps({'domain':'https://jit.pro','pending':[['File','https://jit.pro/zh/cases']], 'next_attempt':123}))
        cache_policy.queue_policy_refresh('jit.pro',self.queue)
        data=json.loads(self.queue.read_text())
        self.assertEqual(data['next_attempt'],123)
        self.assertEqual(len(data['pending']),2)
        with self.assertRaisesRegex(ValueError,'域名'):
            cache_policy.queue_policy_refresh('other.example',self.queue)

    def test_unconfirmed_cloud_write_keeps_backup_and_refresh_pending(self):
        """云接口接受写入但回读一直是旧配置，不能把提交请求误报成配置已经生效。"""
        def stale_api(action, **params):
            """只让 Describe 始终返回原配置，保留正常的写入响应与全部其他前提。"""
            if action == 'DescribeCdnDomainConfigs':
                return {'DomainConfigs': {'DomainConfig': copy.deepcopy(self.before)}}
            return self.api(action, **params)
        with patch.object(cache_policy.time, 'sleep'), self.assertRaisesRegex(RuntimeError, '尚未确认'):
            cache_policy.configure('jit.pro', self.state, True, stale_api, self.queue)
        self.assertEqual(json.loads(self.state.read_text())['before'], self.before)
        self.assertIn(['Directory', 'https://jit.pro/'], json.loads(self.queue.read_text())['pending'])

    def test_restore_wrong_domain_has_no_cloud_or_queue_side_effects(self):
        """备份属于别的域名时在 API 和刷新队列写入之前失败。"""
        self.state.write_text(json.dumps({'domain': 'other.example', 'before': self.before}))
        with self.assertRaisesRegex(ValueError, '域名'):
            cache_policy.restore('jit.pro', self.state, self.api, self.queue)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.queue.exists())


if __name__=='__main__':unittest.main()
