#!/usr/bin/env python3
"""发布后的只读 HTTP 验证：验证当前营销入口、资讯空页/列表及已退役页面的状态。

源站走本机 Host 头，CDN 走正式域名；最多等待三轮传播，失败非零退出，不修改网页或云配置。
"""

import argparse
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def verify(domain, origin=False):
    """对每个路由核对状态和稳定内容标记；HTTP/网络/内容不符抛 ValueError 或网络异常。"""
    base = 'http://127.0.0.1' if origin else domain.rstrip('/')
    checks = {'/': 'href="/download"', '/zh/': 'href="/zh/news/"',
              '/download': 'Apple', '/zh/download': 'Apple', '/contact': 'contact',
              '/zh/contact': 'zhcontactus', '/zh/news/': '资讯中心',
              '/zh/news/sitemap.xml': '<urlset', '/blog': None, '/zh/blog': None,
              '/docs/tutorial': None, '/zh/docs/devguide/installation-activation/download-installation': None}
    for path, marker in checks.items():
        try:
            with urlopen(Request(base + path, headers={'Host': urlsplit(domain).netloc}), timeout=30) as response:
                status, text = response.status, response.read().decode('utf-8')
        except HTTPError as error:
            status, text = error.code, ''
        if marker is None:
            if status != 404: raise ValueError('退役路由未返回 404：' + path)
        elif status != 200 or marker not in text:
            raise ValueError('页面状态或内容不符合预期：' + path)


def main():
    """源站失败立即退出；CDN 最多验证三次，每次间隔五秒，输出不含请求凭证。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='https://jit.pro')
    parser.add_argument('--origin', action='store_true')
    args = parser.parse_args()
    for attempt in range(1 if args.origin else 3):
        try:
            verify(args.domain, args.origin)
            print('源站验证通过' if args.origin else 'CDN 验证通过')
            return 0
        except (OSError, URLError, ValueError) as error:
            if args.origin or attempt == 2:
                print('发布验证失败：' + str(error))
                return 1
            time.sleep(5)


if __name__ == '__main__':
    raise SystemExit(main())
