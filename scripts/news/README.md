# 官网资讯同步与发布

当前实现已接入仓库发布入口及本地官网发布技能。2026-11-10 已首次部署：源站/CDN 路由检查通过，线上 timer 已启用，正式 Feed 已配置为 `https://content.jit.pro/whwy/app1793693462070/Site/zh/feed.json`。首次发布为空页，资讯 CDN 待刷新队列已清空；发布验收时尚未到首次定时触发时间，详见 VALIDATION.md。

## 运行边界

- 官网框架在本地或 CI 构建；服务器不运行 Node/Docusaurus 构建。
- 资讯同步只下载 JSON Feed 1.1、完整 HTML 和依赖，生成独立列表与详情。
- 内容 App 决定详情的完整外壳、样式与正文；官网修改 SEO、编码及搬迁所需的资源地址。
- 中英文官网导航和页脚都进入 `/zh/news/`，文章在新标签页打开。
- 主站发布和资讯发布使用相同锁，主站 rsync 必须保护资讯入口；不能再直接 rsync --delete 到站点根。

## 一次正常官网发布如何生效

在官网仓库根目录，用已有依赖完成本地构建，然后运行仓库发布器。以下命令只在用户授权正式发布时执行 `--apply`：

```bash
DOCUSAURUS_NO_PERSISTENT_CACHE=1 DOCUSAURUS_SSR_CONCURRENCY=1 pnpm build
# 本地预览，不建立 SSH：
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python scripts/publish-site.py
# 已授权发布时：
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python scripts/publish-site.py --apply
```

原技能入口 `~/.codex/skills/jitai-official-release/scripts/publish-jitai-docs.sh` 现在委托同一仓库实现；可用 PUBLISH_PYTHON 选择本地解释器。它不再维护另一套直接上传逻辑。

发布器依次完成：

1. 校验当前双语首页、下载和联系页面，不再要求已经删除的安装指南。
2. 上传完整 build、资讯程序及主站 CDN 脚本到唯一 `/data/jitai-site-staging/<随机ID>/`，该目录在站点外。
3. 服务器安装/复用专用 Python 环境，将资讯代码放入不可变版本目录。
4. 在独占配置锁内准备 0600 候选配置；未提供的新配置保留原值，初次 Feed 未配置也可以安装。此时不覆盖正式配置。
5. 显式 `bootstrap`：首次生成并发布“好内容，正在路上”空页；已有文章则保持原样。完成遗留的初始化 CDN 刷新。
6. 通过 `apply-main-site.py --apply` 持共享锁应用主站，保留资讯链接和全部运行时数据。
7. 初始化和主站应用成功后，在同一配置锁内切换正式配置与程序入口，再激活 service/timer。已有服务从读取配置至运行结束持共享锁，因此安装器会等旧任务结束，新任务会等切换完成。入口替换或 systemd 激活失败时恢复旧配置和程序；不会让首次 timer 触发时找不到程序入口。
8. 验证源站入口，独立刷新主站 CDN（含退役博客），再验证 CDN；失败非零退出，不假报成功。

因此**使用新入口发布官网时会安装并启用定时器**，不需要另外登录服务器配置。服务器需已有 Python 3.10+、venv、rsync、systemd 与原有 aliyun CLI；仅专用 Python 环境缺少 bs4 时安装 `requirements.txt`，不向系统 Python 安装业务依赖，也不修改前端依赖。首次部署已按用户授权安装缺少的 `python3.12-venv` 系统包并成功建立专用运行环境。

发布器支持 REMOTE_HOST、REMOTE_PORT、REMOTE_SITE_DIR、BUILD_DIR、CDN_DOMAIN、REMOTE_CDN_SCRIPT、REFRESH_SCOPE、RSYNC_COMPRESS。SKIP_CDN=1 只跳过本次发布的云请求；SKIP_VERIFY=1 跳过 HTTP 检查；二者都不禁止已安装 timer 的后续运行。旧 SKIP_UPLOAD=1 不适用于完整发布，刷新单独使用 CDN 脚本。

## Feed 配置与凭证

来源只需 **NEWS_FEED_URL**。在本地发布进程环境中设置正式地址，它通过 SSH stdin 传输到服务器；不进入源码、静态包或远程命令行。后续发布省略该变量会沿用服务器配置，显式设为空才停用。文章来源及 CSS/图片域名由 Feed url 和 HTML/CSS 引用解析。

公开 Feed/HTML 获取无需 key。资讯 CDN 使用环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID、ALIBABA_CLOUD_ACCESS_KEY_SECRET、可选 ALIBABA_CLOUD_SECURITY_TOKEN。本地明确提供时同样经 SSH stdin 保存于服务器 0600 配置；没有提供时，运行入口只在服务器本机读取现有 `/root/.aliyun/config.json` 的当前 AK/STS profile，将凭证注入子进程环境。不会把 profile 下载到本地、写入仓库或打印。其他 profile 认证方式不支持时会明确失败。

配置保存在 `/etc/jitai-news.json`，由发布器维护，权限 0600。配置锁为同目录 `jitai-news.json.lock`，独立于同步/页面发布锁，避免 bootstrap 子进程死锁。仅输入新 Feed 时保留凭证；更新凭证必须提供完整 AK 对（两个空值表示回到服务器 profile），未提供 token 时清除旧 token，不能只提供一半 AK 或单独更新 token。从普通 AK profile 加载时也会清除环境遗留的 STS token。安装后的默认值为 NEWS_ENABLE_PUBLISH=1、NEWS_CDN_MODE=aliyun；仓库的 `news.env.example` 是独立开发运行的保守示例，默认只生成候选。两者用途不同。需要禁用 CDN 时可在本地发布环境显式提供 NEWS_CDN_MODE=none，此模式保留 pending，不能据此认为缓存已更新。

安装入口由 JSON 读取配置并注入环境；Python 同步器仍只读环境变量，不依赖配置文件格式，也不读取 CLI profile。未配置 Feed 的定时运行不会读取云凭证。

## 每十分钟调度与空状态

服务器 systemd timer 在每小时 00、10、20、30、40、50 分触发 oneshot 服务；不会重叠启动同一服务，不补跑停机轮次。开机后继续等待下一个时间点。

执行链：timer → service-entry.py → run-news-sync.sh → build → 有变化时 publish / 无变化时 retry-cdn。

**未配置 Feed（含空白）时，定时流程正常退出，不下载、不生成空页、不发布、不刷新 CDN。** `check/build/publish/retry-cdn` 直接调用也遵守该规则。安装专用的显式 `bootstrap` 是例外：它负责首次空页，保证官网导航始终有可访问目标。bootstrap 不属于定时流程。

已配置地址但来源失效时，build 保留已发布内容；首次无内容则生成空候选。空页隐藏筛选/搜索/轮播，禁用 JS 也能阅读。缓存校验失败先完整重下载，恢复失败或索引损坏明确返回运行故障，不会被当成普通来源不可用。

## 目录与 URL

默认服务器路径：

```text
/data/jitai-docs-site/zh/news -> /data/jitai-news-data/releases/<版本>
/data/jitai-news-data/
  releases/<版本>/             列表、详情、资源和 sitemap
  candidates/<版本>.json       候选校验记录
  cache/                       条件请求缓存
  active.json                  已发布状态
  pending-cdn.json             失败待刷新 URL
  sync.lock                    同步互斥锁
/data/locks/jitai-site-release.lock  主站和资讯共用发布锁
/opt/jitai-news -> /opt/jitai-news-releases/<程序哈希>
/opt/jitai-news-runtime/        专用 Python 虚拟环境
/etc/jitai-news.json            0600 配置
/etc/jitai-news.json.lock       安装独占、服务共享的配置/程序切换锁
```

此前只读检查确认：官网由宿主 Nginx 的 `/data/jitai-docs-site` 提供服务，没有可复用的官网 Docker 容器。当前安装器不改 Nginx、不使用其他应用容器的挂载目录。

| 内容 | URL |
| --- | --- |
| 列表 | `https://jit.pro/zh/news/` |
| 详情 | `https://jit.pro/zh/news/articles/<id>/`，实际文件 index.html |
| 本篇 CSS | `https://jit.pro/zh/news/articles/<id>/<id>.css`（来源相对 href 为 `<id>.css` 时） |
| 存储图片 | `https://jit.pro/zh/news/assets/<file参数值>` |
| 其他资源 | `https://jit.pro/zh/news/assets/<内容哈希>.<扩展名>` |
| sitemap | `https://jit.pro/zh/news/sitemap.xml` |

工作根固定为 0711（允许 Web 用户穿过但不列目录），公开版本目录 0755、文件 0644；缓存/候选目录 0700、内部状态 JSON 和配置 0600。首次初始化与升级均修复这些权限，不依赖进程 umask；宿主 /data 等共享父目录仍由主机提供可遍历权限，不递归改写宿主目录。

ID 必须以字母或数字开头，后续仅字母、数字、下划线或连字符，总长度不超过 120；其他 ID 使用 `id-<原始ID的SHA-256>`。url 仅决定抓取来源，不决定官网路由。应用侧检查更新不能仅凭 HTTP 200，应核对 canonical 和本次内容标识；目前未额外提供发布版本查询 API。

## 内容契约、修改与下线

- Feed 为 JSON Feed 1.1 全量快照：items 数组、唯一 id/url、`_item_count` 与条数一致、`_scope=全部已发布内容`、无 next_url。
- seo.title 用于卡片短标题；完整 title、摘要、全部标签等用于列表。HTML 本身提供详情元信息。
- 下载整页 `<slug>.html`、同目录 `<slug>.css` 和正文图片。存储图匹配 `/api/whwy/<appId>/storages/`，安全 file 参数为文件名；同批同名异内容拒绝发布。
- 输出 robots=index,follow,max-image-preview:large，canonical/og:url/主体 Article JSON-LD 指官网；主体 image 的 URL、数组、ImageObject 镜像为官网资源。publisher/citation 等第三方实体保留原义。
- 不重新排版、不注入官网详情外壳；正文链接按搬迁后正确地址保留。当前契约为完整静态页，动态脚本/表单/iframe 等明确拒绝，不静默裁掉。
- 即使 Feed 没变也检查正文/CSS/图片字节；支持 ETag/Last-Modified。忽略 Feed 生成时间和排序噪声，未变化不重新发布。
- 下线条目从下一完整版本的列表、详情、sitemap 删除；最后一篇下线需要 NEWS_ALLOW_EMPTY_FEED=1，防止误输出空清单清空官网。
- 发布比较新旧资源，刷新新增/修改/删除资源及文章的无尾斜线、目录、index.html 地址；同名 CSS/图片变更也刷新。失败整份 pending 保留，后续重试全部受理才清空。
- 主站 CDN 只扫描主站，排除资讯；另外显式刷新退役 `/blog/`、`/zh/blog/`、`/docs/`、`/zh/docs/` 目录及入口别名，即使文件已删除也不遗漏。
- 旧内容哈希资源和版本暂不自动删除，避免缓存中的页面缺图；长期运行需关注磁盘容量。

## 开发与验证

所有本地测试使用 DevPackage 指定 Python。开发脚本不安装/修改 node_modules，不在服务器构建前端。

```bash
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python -m unittest discover -s tests/news -v
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python tests/news/verify_browser_flow.py
```

测试覆盖真实本地 HTTP、生成/发布、目录保护与 rsync、安装重复执行、初始化失败停止、定时入口和 CDN 协议/状态；SSH、systemctl 与真实云接口用替身隔离。详细证据见 VALIDATION.md。真实服务器环境、Nginx 用户权限、CDN 鉴权/额度和边缘传播仍需正式部署时验证；本地测试通过不表示已上线。
