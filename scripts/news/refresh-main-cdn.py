#!/usr/bin/env python3
"""主站 CDN 增量队列：文件摘要去重、CLI 批量刷新、配额预检及逐批持久化。

由 refresh_cdn.sh 提供退役路由清单，定时入口以 --retry 重试已保存任务。
状态位于站点外；不接触资讯目录或云凭证，鉴权交给服务器已配置的 aliyun CLI。
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import quote


def save(path, state):
    """原子保存状态；临时文件和最终文件为 0600，进程退出不留下半份 JSON。"""
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(state, handle, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def aliases(name, domain):
    """为文件返回公开 URL；HTML 同时刷新直接文件与无后缀/目录入口，媒体保留原路径。"""
    url = domain + '/' + quote(name, safe='/')
    result = {url}
    if name.endswith('/index.html') or name == 'index.html':
        directory = url.removesuffix('index.html')
        # 根入口必须带 /；裸域名不是阿里云合法的 ObjectPath，会导致整批拒绝。
        result.add(directory)
        if directory != domain + '/': result.add(directory.rstrip('/'))
    elif name.endswith('.html'):
        route = url[:-5]
        result.update((route, route + '/'))
    return result


def plan(state, build, domain, objects, news_path):
    """合并文件内容差异和首次出现的固定退役路由；失败任务不会因新发布被丢弃。

    更新快照代表已排入队列，不代表已受理；只有 drain 收到任务 ID 才移除 pending。
    不跟随符号链接，避免扫描独立资讯版本；文件摘要包含 CSS/JS/图片/视频等全部静态资源。
    """
    if state.get('domain', domain) != domain or state.get('build', str(build)) != str(build):
        raise ValueError('CDN 状态所属站点不匹配')
    files = {}
    for path in build.rglob('*'):
        name = path.relative_to(build).as_posix()
        if name == news_path or name.startswith(news_path + '/') or path.is_symlink() or not path.is_file(): continue
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''): digest.update(chunk)
        files[name] = digest.hexdigest()
    previous = state.get('files', {})
    # 兼容首版队列中的根别名：规范化为 /，不丢弃其刷新职责，也不再提交无路径域名。
    pending = {(kind, domain + '/' if url == domain else url) for kind, url in state.get('pending', [])}
    for name in files.keys() | previous.keys():
        if files.get(name) != previous.get(name):
            pending.update(('File', url) for url in aliases(name, domain))
    current_urls = set().union(*(aliases(name, domain) for name in files)) if files else set()
    # shell 的有效入口已由文件差异管理；不存在于当前产物的入口及目录属于退役任务。
    fixed = {(kind, url) for kind, url in objects if kind == 'Directory' or url not in current_urls}
    pending.update(fixed - {tuple(item) for item in state.get('fixed', [])})
    return {**state, 'domain': domain, 'build': str(build), 'files': files,
            'fixed': sorted(fixed), 'pending': sorted(pending)}


def aliyun(action, **params):
    """以当前账户配置调用官方 CLI，返回 action/params 对应 JSON；失败抛异常供队列保留。

    显式定位配置以兼容无 HOME 的 systemd 环境，不读取凭证或回显 CLI 错误正文。
    """
    # 官方建议多 URL 以 POST 表单发送；关闭 SDK 内部重试，重试由持久化队列负责。
    # CLI 3.0.306 缺少 HOME 时找不到 profile，报 region can't be empty；Path.home()
    # 可从系统账户解析主目录，有 HOME 时仍沿用它。不改宿主环境，配置内容只由 CLI 读取。
    command = ['aliyun', 'cdn', action, '--method', 'POST', '--retry-count', '0',
               '--config-path', str(Path.home() / '.aliyun/config.json'),
               '--RegionId', os.environ.get('REGION_ID', 'cn-hangzhou')]
    for key, value in params.items(): command.extend(('--' + key, str(value)))
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('阿里云 CDN 请求失败，未受理任务已保留')
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or data.get('Code'): raise RuntimeError('阿里云 CDN 返回错误')
    return data


def drain(path, state, request=aliyun):
    """按真实剩余额度提交并逐批记账，返回已受理及待处理数量；不做同步重试风暴。

    官方上限为每请求 1000 File / 100 Directory、单域名每分钟 10000 URL。
    本进程每轮最多提交 1000 File 和 100 Directory，并至少间隔 60 秒才开始下一轮；
    官方额度查询仅是快照，其他程序仍可能并发消耗，任何错误立即停止且保留未受理任务。
    """
    pending = [tuple(item) for item in state.get('pending', [])]
    accepted = 0
    if not pending or time.time() < state.get('next_attempt', 0):
        return {'accepted': 0, 'pending': len(pending)}
    # 重入限频写在查询前，即使 CLI 失败，下次也不会立即反复提交。
    state['next_attempt'] = time.time() + 60
    save(path, state)
    quota = request('DescribeRefreshQuota')
    for kind, key, maximum in (('File', 'UrlRemain', 1000), ('Directory', 'DirRemain', 100)):
        value = quota.get(key)
        if not isinstance(value, (str, int)) or not str(value).isdigit():
            raise ValueError('CDN 剩余额度响应无效')
        batch = [url for item_kind, url in pending if item_kind == kind][:min(int(value), maximum)]
        if not batch: continue
        result = request('RefreshObjectCaches', ObjectType=kind, ObjectPath='\n'.join(batch))
        if result.get('Code') or not isinstance(result.get('RefreshTaskId'), str) or not result['RefreshTaskId'].strip():
            raise RuntimeError('CDN 未返回有效刷新任务 ID')
        acknowledged = {(kind, url) for url in batch}
        pending = [item for item in pending if item not in acknowledged]
        state['pending'] = pending
        save(path, state)
        accepted += len(batch)
    return {'accepted': accepted, 'pending': len(pending)}


def main():
    """发布时合并清单，定时任务只重试；配额不足正常延期并明确输出 pending，错误非零退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--objects', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--domain', default='https://jit.pro')
    parser.add_argument('--news-path', default='/zh/news/')
    parser.add_argument('--state', type=Path, default=Path('/data/jitai-main-cdn-state/state.json'))
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    if args.retry and not args.state.exists(): return 0
    if not args.retry and (not args.build or not args.objects): parser.error('发布需提供 build 和 objects')
    try:
        if args.build and args.state.resolve().is_relative_to(args.build.resolve()):
            raise ValueError('CDN 状态必须位于站点外')
        args.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with args.state.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(args.state.read_text()) if args.state.exists() else {}
            if not isinstance(state, dict): raise ValueError('CDN 状态格式错误')
            if not args.retry:
                objects = [line.split('\t', 1) for line in args.objects.read_text().splitlines()]
                if any(len(item) != 2 or item[0] not in ('File', 'Directory') or not item[1].startswith(args.domain.rstrip('/') + '/') for item in objects):
                    raise ValueError('刷新清单包含无效地址')
                state = plan(state, args.build.resolve(), args.domain.rstrip('/'), objects, args.news_path.strip('/'))
                save(args.state, state)
            print(json.dumps({'main_cdn': drain(args.state, state)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print('主站 CDN 刷新未完成：请检查云额度/权限或本地状态；待刷新记录保留', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
