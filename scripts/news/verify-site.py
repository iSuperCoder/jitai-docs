#!/usr/bin/env python3
"""发布后的只读 HTTP 验证：验证当前营销入口、资讯空页/列表及已退役页面的状态。

源站走本机 Host 头，CDN 走正式域名；最多等待三轮传播，失败非零退出，不修改网页或云配置。
"""

import argparse
from html.parser import HTMLParser
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree


class PublishedSEO(HTMLParser):
    """提取发布器拥有的索引、链接和 JSON 数据；不执行作者脚本、不检查内容题材。"""

    def __init__(self, body):
        """解析公开 HTML，保留 meta/link、真实锚点和带 ID 的脚本内容供独立验收。"""
        super().__init__()
        self.metas, self.links, self.anchors, self.images, self.scripts = [], [], [], [], {}
        self.script = None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        """记录 SEO 元信息；noscript 内的普通链接也必须能从原始 HTML 中提取。"""
        attrs = dict(attrs)
        if tag == 'meta': self.metas.append(attrs)
        if tag == 'link': self.links.append(attrs)
        if tag == 'a': self.anchors.append(attrs.get('href', ''))
        if tag == 'img': self.images.append(attrs.get('src', ''))
        if tag == 'script' and attrs.get('id'):
            self.script = attrs['id']
            self.scripts[self.script] = ''

    def handle_data(self, data):
        """JSON 脚本仅保存原始文字，后续用 JSON 解码，不运行任意源码。"""
        if self.script is not None: self.scripts[self.script] += data

    def handle_endtag(self, tag):
        """在脚本关闭处停止收集，避免正文混入 JSON。"""
        if tag == 'script': self.script = None


def verify_seo(domain, origin=False, cache=False):
    """读取实际官网响应验证发布归属、静态案例和 sitemap；可选核对 CDN 缓存寿命。

    使用官网已发布 Feed 快照作为条目集合，不请求内容源、不修改来源政策。此验收在
    发布后执行，不作为来源文章的内容筛选；不要求作者必须有某种正文结构或元数据。
    """
    domain = domain.rstrip('/')
    base = 'http://127.0.0.1' if origin else domain

    def fetch(url):
        """只请求本官网路径并返回响应正文与头；拒绝跳转到来源站或其他 origin。"""
        absolute = urljoin(domain + '/', url)
        if urlsplit(absolute).netloc != urlsplit(domain).netloc:
            raise ValueError('官网发布地址指向其他域名：' + url)
        path = urlsplit(absolute).path
        with urlopen(Request(base + path, headers={'Host': urlsplit(domain).netloc}), timeout=30) as response:
            if urlsplit(response.geturl()).netloc != urlsplit(base).netloc:
                raise ValueError('官网响应跳转到其他域名：' + path)
            return response.read().decode('utf-8'), response.headers

    def indexable(body, headers, url, explicit=True):
        """通用及专用机器人声明、HTTP 响应头均不能禁止索引；canonical 必须唯一且为官网。"""
        page = PublishedSEO(body)
        directives = list(headers.get_all('X-Robots-Tag', []))
        general = []
        for meta in page.metas:
            name = (meta.get('name') or meta.get('property') or '').strip().lower()
            equiv = meta.get('http-equiv', '').strip().lower()
            if name == 'robots': general.append(meta.get('content', '').lower())
            if (name in ('robots', 'slurp', 'yandex', 'sogou') or 'bot' in name or 'spider' in name
                    or equiv in ('robots', 'x-robots-tag')):
                directives.append(meta.get('content', ''))
        if any(re.search(r'\b(noindex|none|nofollow|noimageindex|nosnippet|unavailable_after)\b', d, re.I) for d in directives):
            raise ValueError('官网仍有来源索引限制：' + url)
        if explicit and not any({'index', 'follow'} <= {v.strip() for v in value.split(',')} for value in general):
            raise ValueError('官网缺少明确索引声明：' + url)
        canonicals = [link.get('href') for link in page.links if link.get('rel') == 'canonical']
        if canonicals != [url]: raise ValueError('官网 canonical 不一致：' + url)
        return page

    def ttl(headers, limit, url):
        """可变内容不能长于配置上限；要求可观察的浏览器有效期，不能只凭云 API 接受判成功。"""
        value = headers.get('Cache-Control', '')
        match = re.search(r'(?:^|,)\s*max-age\s*=\s*"?(\d+)', value, re.I)
        if not match or int(match.group(1)) > limit:
            raise ValueError('官网缓存有效期未生效：' + url)

    body, headers = fetch('/zh/news/')
    news = indexable(body, headers, domain + '/zh/news/')
    if cache: ttl(headers, 60, '/zh/news/')
    items = json.loads(news.scripts['feed-snapshot'])['items']
    urls = [item['url'] for item in items]
    for url in urls:
        body, headers = fetch(url)
        indexable(body, headers, url)
        if cache: ttl(headers, 60, url)
    cases = [item['url'] for item in items if any('案例' in tag for tag in item.get('tags', []))]
    for path in ('/cases', '/zh/cases'):
        body, headers = fetch(path)
        page = PublishedSEO(body)
        # 案例外壳没有显式 robots 也允许索引，但任何禁止索引声明都需按同一规则检出。
        indexable(body, headers, domain + path, explicit=False)
        actual = {urljoin(domain, url) for url in page.anchors if '/news/articles/' in url}
        if actual != set(cases): raise ValueError('案例原始 HTML 未包含完整已发布列表：' + path)
        schema = json.loads(page.scripts['case-list-schema'])
        listing = schema['mainEntity']
        if (schema.get('@type') != 'CollectionPage' or listing['numberOfItems'] != len(cases)
                or [entry['url'] for entry in listing['itemListElement']] != cases):
            raise ValueError('案例结构化数据与已发布快照不一致：' + path)
        alternates = {link.get('hreflang'): link.get('href') for link in page.links if link.get('rel') == 'alternate'}
        if alternates != {'en': domain + '/cases', 'zh': domain + '/zh/cases', 'x-default': domain + '/cases'}:
            raise ValueError('案例语言链接不正确：' + path)
        if cache: ttl(headers, 60, path)
    sitemap, _ = fetch('/zh/news/sitemap.xml')
    locations = {node.text for node in ElementTree.fromstring(sitemap).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
    if locations != {domain + '/zh/news/', *urls}:
        raise ValueError('资讯 sitemap 与已发布快照不一致')
    robots, _ = fetch('/robots.txt')
    parser = RobotFileParser()
    parser.parse(robots.splitlines())
    for url in [domain + '/zh/news/', domain + '/zh/cases', domain + '/cases', *urls]:
        for bot in ('*', 'Googlebot', 'Bingbot', 'Baiduspider'):
            if not parser.can_fetch(bot, url): raise ValueError('官网 robots.txt 阻止抓取：' + url)
    if cache:
        # 图片本身无需解码成 HTML；只验响应头，保留已有正文与全部资源自由。
        image = next((item.get('image') for item in items if item.get('image')), '/img/home-video-preview.webp')
        path = urlsplit(image).path
        with urlopen(Request(base + path, headers={'Host': urlsplit(domain).netloc}), timeout=30) as response:
            ttl(response.headers, 300, path)


class HeaderLinks(HTMLParser):
    """只读提取页头的有序链接，供源站/CDN 对照首页与独立资讯的导航契约。

    使用标准库保证服务器系统 Python 可运行；只收集文字、目标和新窗口属性，不执行脚本。
    """

    def __init__(self, body, domain):
        """解析 HTML 字符串；相对链接统一解析到正式域名，结果保存为 links 列表。"""
        super().__init__()
        self.domain, self.links = domain, []
        self.in_header, self.anchor = False, None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        """进入页头后记录锚点属性，保留移动菜单与桌面操作入口的原始顺序。"""
        if tag == 'header': self.in_header = True
        if self.in_header and tag == 'a': self.anchor = [dict(attrs), []]

    def handle_data(self, data):
        """收集锚点及其嵌套 span 的文本，包含无障碍新窗口提示。"""
        if self.anchor is not None: self.anchor[1].append(data)

    def handle_endtag(self, tag):
        """关闭锚点时规范化空白和 rel 顺序；页头外的文章链接不参与比较。"""
        if tag == 'a' and self.anchor is not None:
            attrs, text = self.anchor
            self.links.append((' '.join(''.join(text).split()), urljoin(self.domain, attrs.get('href', '')),
                               attrs.get('target', ''), tuple(sorted(attrs.get('rel', '').split()))))
            self.anchor = None
        if tag == 'header': self.in_header = False


def verify(domain, origin=False):
    """核对路由与首页/资讯页头链接一致性；HTTP、网络或内容不符即抛异常，不修改线上。"""
    base = 'http://127.0.0.1' if origin else domain.rstrip('/')
    checks = {'/': 'href="/download"', '/zh/': 'href="/zh/news/"',
              '/download': 'Apple', '/zh/download': 'Apple', '/contact': 'contact',
              '/zh/contact': 'zhcontactus', '/zh/news/': '资讯中心',
              '/zh/news/sitemap.xml': '<urlset', '/blog': None, '/zh/blog': None,
              '/docs/tutorial': None, '/zh/docs/devguide/installation-activation/download-installation': None}
    # 白皮书临时下线：主路由、旧跳转和静态文件别名都必须真实返回 404，不能只有导航隐藏。
    for locale in ('', '/zh'):
        for route in ('/whitepaper', '/agent-products', '/low-code-platform',
                      '/capabilities/enterprise-architecture', '/capabilities/agent-business',
                      '/capabilities/full-customization', '/capabilities/dual-mode',
                      '/capabilities/active-hub', '/capabilities/conversational-dev',
                      '/capabilities/devops-unified', '/capabilities/private-deployment'):
            for suffix in ('', '/', '.html', '/index.html'):
                checks[locale + route + suffix] = None
    headers = {}
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
        if path in ('/zh/', '/zh/news/'):
            headers[path] = HeaderLinks(text, domain).links
    if not headers['/zh/'] or headers['/zh/'] != headers['/zh/news/']:
        raise ValueError('资讯中心顶部菜单与首页不一致')


def main():
    """源站失败立即退出；CDN 最多验证三次，每次间隔五秒，输出不含请求凭证。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='https://jit.pro')
    parser.add_argument('--origin', action='store_true')
    parser.add_argument('--seo', action='store_true', help='核对官网索引归属、静态案例与 sitemap')
    parser.add_argument('--cache', action='store_true', help='核对 CDN 下发的短期浏览器缓存')
    args = parser.parse_args()
    for attempt in range(1 if args.origin else 3):
        try:
            verify(args.domain, args.origin)
            if args.seo or args.cache: verify_seo(args.domain, args.origin, args.cache)
            print('源站验证通过' if args.origin else 'CDN 验证通过')
            return 0
        except (OSError, URLError, ValueError, KeyError, TypeError, ElementTree.ParseError) as error:
            if args.origin or attempt == 2:
                print('发布验证失败：' + str(error))
                return 1
            time.sleep(5)


if __name__ == '__main__':
    raise SystemExit(main())
