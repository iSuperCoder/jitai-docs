#!/usr/bin/env python3
"""官网发布的服务器阶段：安装轻量同步器、初始化空页、保护资讯后应用主站，并启用 timer。

仅在 --apply 时写入；输入是已经完整上传到站点外的 stage（site/、news/、refresh_cdn.sh）。
不运行前端构建，不修改 Nginx；代码采用不可变目录和符号链接，避免更新正在执行的脚本。
本模块只依赖标准库；专用 Python 虚拟环境首次缺依赖时才通过 requirements 安装。
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def write_private(path, value):
    """在目标目录原子写入 0600 JSON 配置，包含密钥时也不产生可公开读取的中间文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(value, handle, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def install(stage, settings, env, apply=False):
    """串行执行安装并与服务共享配置锁；预览无写入，实际安装持独占锁至配置/程序切换完成。

    服务从取得共享锁到子进程结束都持锁，因此不会读取半切换的程序/配置。
    不复用 sync.lock/release.lock，避免 bootstrap 子进程嵌套获取业务锁时死锁。
    """
    if not apply: return install_locked(stage, settings, env, False)
    config_path = Path(env.get('NEWS_CONFIG_FILE', '/etc/jitai-news.json')).absolute()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.with_suffix(config_path.suffix + '.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return install_locked(stage, settings, env, True)


def install_locked(stage, settings, env, apply=False):
    """应用一次完整发布，返回 0；子步骤失败抛异常并停止后续主站更新/定时器启用。

    settings 仅含本次本地明确指定的来源/云环境配置，未传入的设置沿用服务器配置。
    env 指定部署路径（测试全部为临时目录），apply=False 只校验并输出计划，不写入、不执行命令。
    已发布内容由 sync.lock/release.lock 保护；bootstrap 从不以空页替换已有文章。
    """
    stage = Path(stage).resolve()
    site = Path(env.get('REMOTE_SITE_DIR', '/data/jitai-docs-site')).resolve()
    target = Path(env.get('NEWS_INSTALL_DIR', '/opt/jitai-news')).absolute()
    runtime = Path(env.get('NEWS_RUNTIME_DIR', '/opt/jitai-news-runtime')).absolute()
    config_path = Path(env.get('NEWS_CONFIG_FILE', '/etc/jitai-news.json')).absolute()
    units = Path(env.get('NEWS_SYSTEMD_DIR', '/etc/systemd/system')).absolute()
    cdn_script = Path(env.get('REMOTE_CDN_SCRIPT', '/data/scripts/refresh_jitai_cdn.sh')).absolute()
    profile = Path(env.get('NEWS_ALIYUN_PROFILE', '/root/.aliyun/config.json')).absolute()
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in config.items()):
        raise ValueError('已有资讯配置必须是字符串映射')
    allowed = {'NEWS_FEED_URL', 'NEWS_CDN_MODE', 'ALIBABA_CLOUD_ACCESS_KEY_ID',
               'ALIBABA_CLOUD_ACCESS_KEY_SECRET', 'ALIBABA_CLOUD_SECURITY_TOKEN', 'NEWS_ALLOW_EMPTY_FEED'}
    if not isinstance(settings, dict) or not set(settings) <= allowed or not all(isinstance(v, str) for v in settings.values()):
        raise ValueError('发布配置包含不支持的字段或类型')
    # 仅 Feed 等业务配置可以逐项合并；凭证更新必须提供完整 AK 对，token 未提供即清除旧值。
    # 两个空字符串表示显式恢复服务器 profile；token 不允许单独覆盖旧凭证。
    credential_keys = {'ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET', 'ALIBABA_CLOUD_SECURITY_TOKEN'}
    if credential_keys & settings.keys():
        key = settings.get('ALIBABA_CLOUD_ACCESS_KEY_ID')
        secret = settings.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
        if key is None or secret is None or bool(key) != bool(secret) or (settings.get('ALIBABA_CLOUD_SECURITY_TOKEN') and not key):
            raise ValueError('更新云凭证须提供完整 AK 对，不能混用旧凭证')
        for name in credential_keys: config.pop(name, None)
    config.update(settings)
    config.setdefault('NEWS_FEED_URL', '')
    config.setdefault('NEWS_CDN_MODE', 'aliyun')
    config.setdefault('NEWS_ALLOW_EMPTY_FEED', '0')
    config.update(NEWS_SITE_ORIGIN=env.get('CDN_DOMAIN', 'https://jit.pro'), NEWS_PUBLIC_PATH='/zh/news/',
                  NEWS_WORK_DIR=env.get('NEWS_WORK_DIR', config.get('NEWS_WORK_DIR', '/data/jitai-news-data')),
                  NEWS_RELEASE_LOCK=env.get('NEWS_RELEASE_LOCK', '/data/locks/jitai-site-release.lock'),
                  NEWS_LIVE_LINK=str(site / 'zh/news'), NEWS_ENABLE_PUBLISH='1',
                  NEWS_PYTHON=str(runtime / 'bin/python'))
    # 上传区、程序、数据、配置和锁都不得放到站点中，否则下一次主站 --delete 会清除它们。
    for path in (stage, target, runtime, config_path, units, cdn_script, Path(config['NEWS_WORK_DIR']), Path(config['NEWS_RELEASE_LOCK'])):
        path = path.resolve()
        if path == Path('/') or path.is_relative_to(site) or site.is_relative_to(path):
            raise ValueError('部署辅助路径必须与站点目录独立')
    for name in ('site/index.html', 'site/zh/index.html', 'news/sync_news.py',
                 'news/service-entry.py', 'news/requirements.txt', 'refresh_cdn.sh'):
        if not (stage / name).is_file(): raise ValueError('上传包缺少必需文件：' + name)
    if (stage / 'site/zh/news').exists() or (stage / 'site/zh/news.html').exists():
        raise ValueError('主站构建抢占资讯路径')
    if target.exists() and not target.is_symlink(): raise ValueError('程序入口已有实体目录，拒绝覆盖')
    if not apply:
        print('计划：安装资讯运行环境 → 初始化空页 → 保护资讯应用主站 → 启用十分钟 timer')
        return 0
    if sys.version_info < (3, 10): raise ValueError('服务器需要 Python 3.10 或更高版本')
    # 系统能力先验证；不再尝试从已不存在的 Docker 容器复制工具或凭证。
    subprocess.run(['systemctl', '--version'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['rsync', '--version'], check=True, stdout=subprocess.DEVNULL)
    python = runtime / 'bin/python'
    if not python.exists(): subprocess.run([sys.executable, '-m', 'venv', str(runtime)], check=True)
    if subprocess.run([str(python), '-c', 'import bs4'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(stage / 'news/requirements.txt')], check=True)

    source_files = sorted(p for p in (stage / 'news').rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    signature = hashlib.sha256()
    for path in source_files:
        signature.update(str(path.relative_to(stage / 'news')).encode() + b'\0' + path.read_bytes())
    release = target.with_name(target.name + '-releases') / signature.hexdigest()
    release.parent.mkdir(parents=True, exist_ok=True)
    if not release.exists():
        temporary = Path(tempfile.mkdtemp(dir=release.parent))
        try:
            shutil.copytree(stage / 'news', temporary, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            os.replace(temporary, release)
        finally:
            if temporary.exists(): shutil.rmtree(temporary)
    # 代码版本校验防止复用不完整安装目录，避免对未知文件静默重新签发可信摘要。
    if any((release / p.relative_to(stage / 'news')).read_bytes() != p.read_bytes() for p in source_files):
        raise ValueError('已安装脚本版本校验失败')
    site.mkdir(parents=True, exist_ok=True)
    (site / 'zh').mkdir(exist_ok=True)
    # 先验证路由/符号链接边界，再初始化空页；预览步骤仍使用真实共享锁与 rsync dry-run。
    process_env = {**os.environ, **config, 'MAIN_SITE_STAGE_DIR': str(stage / 'site'), 'MAIN_SITE_DIR': str(site)}
    apply_command = [str(python), str(release / 'apply-main-site.py')]
    subprocess.run(apply_command, env=process_env, check=True)
    bootstrap_env = dict(process_env)
    # SKIP_CDN 仅跳过本次安装/发布的云请求，不覆盖服务器保存的长期 CDN 配置。
    # 只给 bootstrap 传私有候选配置；失败时正式配置完全不变，原定时器解锁后继续用原配置。
    temporary_config = release.parent / ('bootstrap-' + str(os.getpid()) + '.json')
    write_private(temporary_config, {**config, **({'NEWS_CDN_MODE': 'none'} if env.get('SKIP_CDN') == '1' else {})})
    try:
        subprocess.run([str(python), str(release / 'service-entry.py'), '--config', str(temporary_config),
                        '--profile', str(profile), '--bootstrap'], env=bootstrap_env, check=True)
    finally:
        temporary_config.unlink(missing_ok=True)
        temporary_config.with_suffix('.json.lock').unlink(missing_ok=True)
    subprocess.run([*apply_command, '--apply'], env=process_env, check=True)
    cdn_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage / 'refresh_cdn.sh', cdn_script)
    cdn_script.chmod(0o755)
    units.mkdir(parents=True, exist_ok=True)
    service = (release / 'systemd/jitai-news-sync.service').read_text()
    service = service.replace('/opt/jitai-news-runtime/bin/python', str(python)).replace(
        '/opt/jitai-news/service-entry.py', str(target / 'service-entry.py')).replace(
        '/etc/jitai-news.json', str(config_path)).replace('/root/.aliyun/config.json', str(profile))
    (units / 'jitai-news-sync.service').write_text(service)
    shutil.copyfile(release / 'systemd/jitai-news-sync.timer', units / 'jitai-news-sync.timer')
    # 初始化和主站应用成功后，在锁内切换配置/入口，再启用 timer，避免首次触发时入口尚不存在。
    # timer 即使立刻触发也须等待解锁；入口替换或 systemd 激活失败均恢复原配置和程序。
    previous_config = json.loads(config_path.read_text()) if config_path.exists() else None
    previous_target = os.readlink(target) if target.is_symlink() else None
    link = target.with_name(target.name + '.next-' + str(os.getpid()))
    try:
        link.symlink_to(release)
        write_private(config_path, config)
        os.replace(link, target)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', '--now', 'jitai-news-sync.timer'], check=True)
    except BaseException:
        if previous_config is None: config_path.unlink(missing_ok=True)
        else: write_private(config_path, previous_config)
        if previous_target is None:
            if target.is_symlink(): target.unlink()
        elif not target.is_symlink() or os.readlink(target) != previous_target:
            link.unlink(missing_ok=True)
            link.symlink_to(previous_target)
            os.replace(link, target)
        raise
    finally:
        link.unlink(missing_ok=True)
    print('主站已应用；资讯目录已保护；十分钟定时器已启用。')
    return 0


def main():
    """读取经 SSH stdin 发送的 JSON 配置；默认预览，--apply 才安装，错误不输出凭证。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        return install(args.stage, json.load(sys.stdin), os.environ, args.apply)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('官网发布安装失败：' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
