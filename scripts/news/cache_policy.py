#!/usr/bin/env python3
"""官网 CDN 缓存策略：按发布路径分层，默认只读预览，--apply 才写阿里云配置。

复用服务器已有 aliyun CLI 身份，不读取或传输凭证、不修改 Nginx。使用官方
path_based_ttl_set 的 swift_follow_cachetime 同时给浏览器明确的有效期。
策略只管理列出的路径和错误状态 TTL；其他域名配置不变。原配置保存于站点外供恢复。
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

# HTML/目录一分钟，普通图片五分钟；只有保证内容寻址的构建资源目录允许一年缓存。
# 同名文章 CSS 和存储文件不属于不可变资源，继续落在短缓存路径并由发布差异主动刷新。
PATH_TTLS = {'/': (60, 1), '/img/': (300, 20), '/zh/img/': (300, 20),
             '/zh/news/assets/': (300, 20), '/assets/': (31536000, 90),
             '/zh/assets/': (31536000, 90), '/zh/news/ui/': (31536000, 90)}
FUNCTIONS = 'path_based_ttl_set,filetype_based_ttl_set,default_ttl_code,set_resp_header'


def request(action, **params):
    """通过现有 CLI 调用指定公开 API；返回 JSON，失败不回显可能含运行环境信息的 stderr。"""
    command = ['aliyun', 'cdn', action, '--method', 'POST', '--retry-count', '0',
               '--config-path', str(Path.home() / '.aliyun/config.json'), '--RegionId', 'cn-hangzhou']
    for key, value in params.items(): command.extend(['--' + key, str(value)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode: raise RuntimeError('缓存策略 API 调用失败：' + action)
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or data.get('Code'): raise RuntimeError('缓存策略 API 返回错误：' + action)
    return data


def arguments(config):
    """将 Describe 的公开参数数组转为映射，只解析功能设置，不访问账户信息。"""
    return {arg['ArgName']: arg['ArgValue'] for arg in config.get('FunctionArgs', {}).get('FunctionArg', [])}


def identity(config):
    """以功能名和具体目录识别可重用配置；不依赖各服务器不同的 ConfigId。"""
    name = config['FunctionName']
    return (name, arguments(config).get('path', ''))


def desired():
    """返回官网拥有的缓存项；客户端遵循同一 TTL，保留 no-store 等源站不缓存语义。"""
    values = []
    for path, (ttl, weight) in PATH_TTLS.items():
        values.append(('path_based_ttl_set', {'path': path, 'ttl': str(ttl), 'weight': str(weight),
                       'swift_origin_cache_high': 'off', 'swift_no_cache_low': 'off',
                       'swift_follow_cachetime': 'on', 'force_revalidate': 'off'}))
    values.append(('default_ttl_code', {'default_ttl_code': '404=10,410=10,5xx=1'}))
    return values


def plan(configs):
    """计算最小 API 更新列表；已有相同路径复用 ID，重复项或全局缓存头冲突明确失败。

    不删除未管理配置。既有按扩展名的 TTL 或 Cache-Control 改写可能覆盖本策略，需显式
    合并而不能宣称已经生效；已知当前线上没有这些冲突项。
    """
    for config in configs:
        args = arguments(config)
        if config['FunctionName'] == 'filetype_based_ttl_set' or (
            config['FunctionName'] == 'set_resp_header' and args.get('key', '').lower() == 'cache-control'):
            raise ValueError('已有缓存规则与官网分层策略重叠，需要先合并明确规则')
    updates = []
    for name, wanted in desired():
        key = (name, wanted.get('path', ''))
        matches = [c for c in configs if identity(c) == key]
        if len(matches) > 1: raise ValueError('缓存规则存在重复目录：' + str(key))
        current = matches[0] if matches else None
        if current and str(current.get('ParentId', 0)) not in ('0', ''):
            raise ValueError('已管理缓存项引用条件规则，不能静默改成全局')
        old = arguments(current) if current else {}
        if current and all(old.get(k) == v for k, v in wanted.items()) and current.get('Status') == 'success': continue
        update = {'functionName': name, 'functionArgs': [{'argName': k, 'argValue': v} for k, v in {**old, **wanted}.items()]}
        if current: update['configId'] = current['ConfigId']
        updates.append(update)
    return updates


def save(path, data):
    """原子保存 0600 的公开配置备份；状态目录必须由部署配置置于网站外。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def queue_policy_refresh(domain, path):
    """策略变化前持主站 CDN 状态锁排队一次整站刷新，清除旧的 30 天对象；不直接消耗云额度。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(path.read_text()) if path.exists() else {}
        origin = 'https://' + domain
        if state.get('domain', origin) != origin: raise ValueError('主站 CDN 队列域名不匹配')
        pending = {tuple(item) for item in state.get('pending', [])}
        pending.add(('Directory', origin + '/'))
        save(path, {**state, 'domain': origin, 'pending': sorted(pending)})


def configure(domain, state, apply=False, api=request, cdn_state=None):
    """读取当前配置并预览／应用最小差异；备份先落盘，提交后查询确认，失败允许幂等重试。"""
    configs = api('DescribeCdnDomainConfigs', DomainName=domain, FunctionNames=FUNCTIONS).get('DomainConfigs', {}).get('DomainConfig', [])
    changes = plan(configs)
    if not apply: return {'domain': domain, 'apply': False, 'changes': changes}
    if not changes: return {'domain': domain, 'changed': False}
    if state.exists():
        backup = json.loads(state.read_text())
        if backup.get('domain') != domain: raise ValueError('缓存备份属于另一个域名')
    else:
        save(state, {'domain': domain, 'before': configs})
    # 先持久排队，进程在云请求后断开也不会漏刷新；刷新失败由既有队列和 timer 重试。
    if cdn_state is not None: queue_policy_refresh(domain, cdn_state)
    response = api('BatchSetCdnDomainConfig', DomainNames=domain, Functions=json.dumps(changes))
    results = response.get('DomainConfigList', {}).get('DomainConfigModel', [])
    if len(results) != len(changes) or any(not item.get('ConfigId') for item in results):
        raise RuntimeError('缓存策略部分提交或未确认；备份保留，重试会先重新查询')
    for attempt in range(3):
        current = api('DescribeCdnDomainConfigs', DomainName=domain, FunctionNames=FUNCTIONS).get('DomainConfigs', {}).get('DomainConfig', [])
        if not plan(current): return {'domain': domain, 'changed': True, 'verified': True, 'backup': str(state)}
        if attempt < 2: time.sleep(2)
    raise RuntimeError('缓存策略已提交但尚未确认生效；保留备份并停止发布验收')


def restore(domain, state, api=request, cdn_state=None):
    """显式恢复本程序管理的原配置，删除新建项；不碰无关配置，恢复后保留备份供审计。"""
    backup = json.loads(state.read_text())
    if backup.get('domain') != domain: raise ValueError('恢复备份域名不匹配')
    # 域名核验通过后、首次云写入前保存刷新任务；非法备份不能污染另一站点的队列。
    if cdn_state is not None: queue_policy_refresh(domain, cdn_state)
    owned = {(name, args.get('path', '')) for name, args in desired()}
    originals = {identity(c): c for c in backup['before'] if identity(c) in owned}
    configs = api('DescribeCdnDomainConfigs', DomainName=domain, FunctionNames=FUNCTIONS).get('DomainConfigs', {}).get('DomainConfig', [])
    for current in configs:
        key = identity(current)
        if key not in owned: continue
        old = originals.pop(key, None)
        if old is None:
            api('DeleteSpecificConfig', DomainName=domain, ConfigId=current['ConfigId'])
        else:
            value = {'functionName': old['FunctionName'], 'configId': current['ConfigId'],
                     'functionArgs': [{'argName': k, 'argValue': v} for k, v in arguments(old).items()]}
            api('BatchSetCdnDomainConfig', DomainNames=domain, Functions=json.dumps([value]))
    for old in originals.values():
        value = {'functionName': old['FunctionName'], 'functionArgs': [{'argName': k, 'argValue': v} for k, v in arguments(old).items()]}
        api('BatchSetCdnDomainConfig', DomainNames=domain, Functions=json.dumps([value]))
    # 只核对管理项的原始参数，不把 API 接收等同于恢复完成。
    current = api('DescribeCdnDomainConfigs', DomainName=domain, FunctionNames=FUNCTIONS).get('DomainConfigs', {}).get('DomainConfig', [])
    actual = {identity(c): arguments(c) for c in current if identity(c) in owned}
    expected = {identity(c): arguments(c) for c in backup['before'] if identity(c) in owned}
    if actual != expected: raise RuntimeError('缓存恢复尚未通过回读校验')
    return {'domain': domain, 'restored': True}


def main():
    """默认只读预览；--apply 应用，--restore 恢复，均只使用服务器现有凭证。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='jit.pro')
    parser.add_argument('--state', type=Path, default=Path('/data/jitai-cache-policy/backup.json'))
    parser.add_argument('--cdn-state', type=Path, default=Path('/data/jitai-main-cdn-state/state.json'))
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--apply', action='store_true')
    actions.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    try:
        if args.restore:
            result = restore(args.domain, args.state, cdn_state=args.cdn_state)
        else:
            result = configure(args.domain, args.state, args.apply, cdn_state=args.cdn_state)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('缓存策略失败：' + str(error))
        return 1


if __name__ == '__main__': raise SystemExit(main())
