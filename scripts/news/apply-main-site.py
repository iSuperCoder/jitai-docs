#!/usr/bin/env python3
"""服务器端应用已上传的主站静态包，保留独立资讯数据入口；不执行任何前端构建。

本地完成 Docusaurus 构建后，应上传到站点之外的专用暂存目录，再调用本脚本。
默认只预览 rsync 差异，--apply 才实际写入；主站 CDN 仍由主站流程单独调用。
仅依赖标准库、服务器 rsync 和 POSIX 文件锁；不依赖资讯解析库或云凭证。
"""

import argparse
import fcntl
import os
from pathlib import Path
import re
import subprocess
import sys


def apply_main_site(env, apply=False):
    """校验环境并在共享锁内同步主站，返回 rsync 退出码；配置冲突时抛出 ValueError。

    MAIN_SITE_STAGE_DIR 是本次完整且上传完毕的静态包，MAIN_SITE_DIR 是已有站点根目录；
    NEWS_PUBLIC_PATH 与 NEWS_RELEASE_LOCK 必须和资讯同步进程一致。暂存目录在本次
    操作期间不得再被上传任务修改。apply=False 仅预览，仍持锁以获得稳定目录状态。
    """
    for key in ('MAIN_SITE_STAGE_DIR', 'MAIN_SITE_DIR', 'NEWS_RELEASE_LOCK'):
        if not env.get(key) or not Path(env[key]).is_absolute():
            raise ValueError(f'{key} 必须配置为绝对路径')
    stage = Path(env['MAIN_SITE_STAGE_DIR']).resolve()
    site = Path(env['MAIN_SITE_DIR']).resolve()
    if site == Path('/') or stage == Path('/') or stage.is_relative_to(site) or site.is_relative_to(stage):
        raise ValueError('暂存目录与站点必须互相独立，且不能为根目录')
    public = env.get('NEWS_PUBLIC_PATH', '/zh/news/')
    if not re.fullmatch(r'/(?:[a-zA-Z0-9_-]+/)+', public):
        raise ValueError('NEWS_PUBLIC_PATH 必须是带首尾斜线的独立目录路径')
    relative = Path(public.strip('/'))
    lock = Path(env['NEWS_RELEASE_LOCK']).resolve()
    if lock.is_relative_to(site) or lock.is_relative_to(stage):
        raise ValueError('共享锁必须位于站点和暂存目录之外，避免被 rsync 删除')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        # 与资讯 publish 使用同一个 flock；不跨 SSH 会话传递锁，也不等待长时间占锁。
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not site.is_dir() or not (stage / 'index.html').is_file() or not (stage / 'zh/index.html').is_file():
            raise ValueError('需要已有站点目录及完整的主站首页、中文首页静态包')
        if any(path.is_symlink() for path in stage.rglob('*')):
            raise ValueError('主站静态包不能含符号链接，避免替换资讯入口的上级目录')
        if (stage / relative).exists() or (stage / relative.with_suffix('.html')).exists():
            raise ValueError('主站静态包不能生成资讯目录或同名 .html 路由')
        if (site / relative.with_suffix('.html')).exists():
            raise ValueError('站点存在抢占资讯路由的 .html 文件，需先单独处理')
        ancestors = list(relative.parents)[:-1]
        if any((site / parent).is_symlink() for parent in ancestors):
            raise ValueError('资讯入口的上级目录不能是符号链接')
        if any(not (stage / parent).is_dir() for parent in ancestors):
            raise ValueError('主站静态包必须保留资讯入口的上级目录')

        # P 只保护接收端资讯入口与后代，H 阻止发送端写入；上级目录由上面的校验确保
        # 保留，不能排除整个 /zh/，否则主站旧页面也删不掉。禁止改变这些语义的额外参数。
        prefix = '/' + relative.as_posix()
        # 静态包可能保留相同的秒级 mtime 且文件长度不变，比较内容避免漏掉这类更新。
        command = ['rsync', '-a', '--checksum', '--delete', '--itemize-changes']
        for rule in ('P ' + prefix, 'P ' + prefix + '/***', 'H ' + prefix, 'H ' + prefix + '/***'):
            command += ['--filter', rule]
        for pattern in ('.DS_Store', '._*', '.AppleDouble', '.Spotlight-V100', '.Trashes'):
            command += ['--exclude', pattern]
        if not apply:
            command.append('--dry-run')
        command += [str(stage) + '/', str(site) + '/']
        # 不接受额外 rsync 参数；锁的句柄覆盖整个同步过程，异常退出由 with 自动释放。
        return subprocess.run(command, check=False).returncode


def main():
    """提供默认预览、显式应用的命令行接口；失败返回非零，不触发构建或 CDN。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='实际应用主站静态包；默认仅预览')
    args = parser.parse_args()
    try:
        return apply_main_site(os.environ, args.apply)
    except (ValueError, OSError) as error:
        print(f'主站静态包应用失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
