#!/usr/bin/env python3
"""systemd 与发布安装共用的服务器入口；从仓库外 JSON 配置向子进程注入环境变量。

配置文件仅由发布器写入，权限 0600；不使用 source/eval，也不打印配置内容。
缺少显式 AK 时可在服务器本机读取已有 aliyun CLI 的当前 AK/STS profile，密钥只进入进程环境。
本文件不安装任务，定时模式仍由 run-news-sync.sh 判断未配置 Feed 后直接结束。
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


def runtime_env(config_path, profile_path, bootstrap=False):
    """合并配置并返回子进程环境；bootstrap 是安装空页操作，需要和正常运行一样支持 CDN。

    未配置 Feed 的定时模式不读取云凭证。仅完整显式 AK 或当前受支持的 CLI profile 可用于签名；
    部分 AK/未知 profile 失败，不输出凭证值或原始 JSON。读取错误由 CLI 脱敏报告。
    """
    env = dict(os.environ)
    if config_path.exists():
        data = json.loads(config_path.read_text())
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError('资讯配置必须是字符串映射')
        # 文件中的 AK 对是一组独立凭证，不得继承宿主环境中的旧 token 或半份 secret。
        if 'ALIBABA_CLOUD_ACCESS_KEY_ID' in data or 'ALIBABA_CLOUD_ACCESS_KEY_SECRET' in data:
            for name in ('ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET', 'ALIBABA_CLOUD_SECURITY_TOKEN'):
                env.pop(name, None)
        env.update(data)
    if not bootstrap and not env.get('NEWS_FEED_URL', '').strip(): return env
    if env.get('NEWS_CDN_MODE') != 'aliyun': return env
    key, secret = env.get('ALIBABA_CLOUD_ACCESS_KEY_ID'), env.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    if key and secret: return env
    if key or secret: raise ValueError('显式 CDN 环境凭证不完整')
    data = json.loads(profile_path.read_text())
    profile = next((p for p in data.get('profiles', []) if p.get('name') == data.get('current')), {})
    if profile.get('mode') not in ('AK', 'StsToken'):
        raise ValueError('当前 aliyun profile 不是 AK/STS；请通过本地发布环境提供 CDN 凭证')
    if not profile.get('access_key_id') or not profile.get('access_key_secret'):
        raise ValueError('当前 aliyun profile 凭证不完整')
    env['ALIBABA_CLOUD_ACCESS_KEY_ID'] = profile['access_key_id']
    env['ALIBABA_CLOUD_ACCESS_KEY_SECRET'] = profile['access_key_secret']
    # profile 替换整组凭证，普通 AK 必须移除配置或环境遗留的 STS token。
    env.pop('ALIBABA_CLOUD_SECURITY_TOKEN', None)
    if profile.get('mode') == 'StsToken':
        if not profile.get('sts_token'): raise ValueError('当前 STS profile 缺少 token')
        env['ALIBABA_CLOUD_SECURITY_TOKEN'] = profile['sts_token']
    return env


def main():
    """默认调用定时 shell；--bootstrap 只由发布器调用；失败输出类型而不泄露配置或密钥。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/jitai-news.json'))
    parser.add_argument('--profile', type=Path, default=Path('/root/.aliyun/config.json'))
    parser.add_argument('--bootstrap', action='store_true')
    args = parser.parse_args()
    try:
        # 在解析程序入口和读取配置之前拿共享锁，并持有到同步结束；发布器独占同一把锁。
        # bootstrap 使用独立候选配置及其锁，不与安装器持有的正式配置锁发生嵌套死锁。
        args.config.parent.mkdir(parents=True, exist_ok=True)
        with args.config.with_suffix(args.config.suffix + '.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            env = runtime_env(args.config, args.profile, args.bootstrap)
            here = Path(__file__).resolve().parent
            command = [env.get('NEWS_PYTHON', sys.executable), str(here / 'sync_news.py'), 'bootstrap'] if args.bootstrap else ['bash', str(here / 'run-news-sync.sh')]
            return subprocess.run(command, env=env, check=False).returncode
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print('资讯运行配置加载失败：' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
