#!/usr/bin/env python3
"""本地预览主站与独立资讯产物；仅绑定回环地址，不参与官网发布。

Docusaurus build 不包含由资讯同步器管理的 /zh/news/。本服务把两个现成静态目录
映射到同一个本地 origin，便于验证导航、案例列表和资讯页之间的真实请求关系。
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class PreviewHandler(SimpleHTTPRequestHandler):
    """按 URL 选择主站或资讯目录；实例仅保存预览目录，不修改生成文件。"""

    def __init__(self, *args, build_dir: Path, news_dir: Path, **kwargs):
        """接收已存在的主站和资讯目录，交给标准静态文件处理器发送内容。"""
        self.build_dir = build_dir
        self.news_dir = news_dir
        super().__init__(*args, directory=str(build_dir), **kwargs)

    def translate_path(self, path: str) -> str:
        """将 /zh/news/ 映射到独立产物，其余映射到 build；兼容 Docusaurus 的 .html 页面 URL。"""
        pathname = urlsplit(path).path
        if pathname == '/zh/news' or pathname.startswith('/zh/news/'):
            self.directory = str(self.news_dir)
            return super().translate_path(pathname[len('/zh/news'):])
        self.directory = str(self.build_dir)
        result = Path(super().translate_path(pathname))
        if not result.exists() and result.with_suffix('.html').is_file():
            return str(result.with_suffix('.html'))
        return str(result)


def main() -> None:
    """读取预览目录和端口，在本机持续提供静态页面；目录不存在时直接报错退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=Path('build'), help='Docusaurus 构建目录')
    parser.add_argument('--news', type=Path, required=True, help='资讯同步器的 live 目录')
    parser.add_argument('--port', type=int, default=3001, help='本地监听端口')
    args = parser.parse_args()
    build_dir, news_dir = args.build.resolve(), args.news.resolve()
    if not (build_dir / 'zh' / 'index.html').is_file() or not (news_dir / 'index.html').is_file():
        parser.error('需要已有的主站构建和资讯列表 index.html')
    handler = partial(PreviewHandler, build_dir=build_dir, news_dir=news_dir)
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'本地预览：http://127.0.0.1:{args.port}/zh/', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
