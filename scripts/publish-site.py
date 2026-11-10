#!/usr/bin/env python3
"""本地官网发布入口：只上传已构建静态包，服务器安装资讯服务并在共享锁内应用主站。

默认预览不建立 SSH；--apply 才执行。Feed/云配置通过 SSH stdin 发送，不放进构建产物或命令行。
本地发布技能只委托此仓库脚本，避免技能中的旧 rsync 逻辑绕过资讯目录保护。
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent


def publish(env, apply=False):
    """按上传、安装、源站验证、CDN 刷新和验证顺序发布；失败立即停止，保留上传区便于排查。

    env 支持既有主机/端口/目录/跳过 CDN 与验证选项；未指定的来源配置由服务器沿用。
    此函数不构建、不执行前端安装。预览校验构建文件后返回 0，不调用外部命令。
    """
    build = Path(env.get('BUILD_DIR', str(ROOT / 'build'))).resolve()
    host = env.get('REMOTE_HOST', 'root@118.196.33.5')
    port = env.get('REMOTE_PORT', '22')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host) or not port.isdigit():
        raise ValueError('SSH 主机或端口格式不合法')
    if env.get('SKIP_UPLOAD') == '1': raise ValueError('新发布流程需完整上传；单独刷新请使用 refresh_cdn.sh')
    for relative in ('index.html', 'zh/index.html', 'download.html', 'zh/download.html', 'contact.html', 'zh/contact.html'):
        if not (build / relative).is_file(): raise ValueError('构建缺少当前有效页面：' + relative)
    if (build / 'zh/news').exists() or (build / 'zh/news.html').exists(): raise ValueError('构建不得包含运行时资讯目录')
    remote_env = {key: env[key] for key in ('REMOTE_SITE_DIR', 'REMOTE_CDN_SCRIPT', 'CDN_DOMAIN', 'SKIP_CDN') if key in env}
    site = env.get('REMOTE_SITE_DIR', '/data/jitai-docs-site')
    domain = env.get('CDN_DOMAIN', 'https://jit.pro')
    cdn_script = env.get('REMOTE_CDN_SCRIPT', '/data/scripts/refresh_jitai_cdn.sh')
    settings = {key: env[key] for key in ('NEWS_FEED_URL', 'NEWS_CDN_MODE', 'NEWS_ALLOW_EMPTY_FEED',
                 'ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET', 'ALIBABA_CLOUD_SECURITY_TOKEN') if key in env}
    if not apply:
        print('预览：已构建官网 → 独立上传区 → 安装资讯/空页/timer → 保护资讯应用主站 → CDN 刷新及检查。')
        return 0
    ssh = ['ssh', '-p', port, host]

    def remote(arguments, payload=None):
        """以一个正确引用的远程命令调用 SSH，配置可通过 stdin 发送；失败直接上抛。"""
        return subprocess.run([*ssh, shlex.join(arguments)], input=payload, text=True, check=True)

    # 每次上传到唯一目录，绝不再对站点根目录直接 rsync --delete。
    stage = '/data/jitai-site-staging/' + uuid.uuid4().hex
    remote(['mkdir', '-p', stage])
    remote(['chmod', '700', stage])
    flags = ['rsync', '-az' if env.get('RSYNC_COMPRESS', '1') == '1' else '-a', '--delete']
    for pattern in ('.DS_Store', '._*', '.AppleDouble', '.Spotlight-V100', '.Trashes', '__pycache__', '*.pyc'):
        flags += ['--exclude', pattern]
    flags += ['-e', shlex.join(['ssh', '-p', port])]
    for source, destination in ((str(build) + '/', stage + '/site/'),
                                (str(ROOT / 'scripts/news') + '/', stage + '/news/'),
                                (str(ROOT / 'refresh_cdn.sh'), stage + '/refresh_cdn.sh')):
        subprocess.run([*flags, source, host + ':' + destination], check=True)
    remote(['env', *[key + '=' + value for key, value in remote_env.items()], 'python3',
            stage + '/news/install-news.py', '--stage', stage, '--apply'], json.dumps(settings))
    if env.get('SKIP_VERIFY') != '1':
        remote(['python3', stage + '/news/verify-site.py', '--domain', domain, '--origin'])
    if env.get('SKIP_CDN') != '1':
        remote(['env', 'BUILD_DIR=' + site, 'DOMAIN=' + domain,
                'REFRESH_SCOPE=' + env.get('REFRESH_SCOPE', 'targeted'), 'bash', cdn_script])
        if env.get('SKIP_VERIFY') != '1':
            remote(['python3', stage + '/news/verify-site.py', '--domain', domain])
    remote(['rm', '-rf', '--', stage])
    print('官网发布完成；资讯同步由服务器每十分钟触发。')
    return 0


def main():
    """显式 --apply 执行发布；失败只打印类型，避免把带秘密 stdin 的异常或配置输出到日志。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        return publish(os.environ, args.apply)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('官网发布失败：' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
