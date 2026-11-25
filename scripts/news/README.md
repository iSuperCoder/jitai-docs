# 官网资讯同步与发布

当前实现已接入仓库发布入口及本地官网发布技能。2026-11-10 已首次部署：源站/CDN 路由检查通过，线上 timer 已启用，正式 Feed 已配置为 `https://content.jit.pro/whwy/app1793693462070/Site/zh/feed.json`。首次发布为空页，资讯 CDN 待刷新队列已清空；发布验收时尚未到首次定时触发时间，详见 VALIDATION.md。

## 运行边界

- 技术白皮书暂不公开：主站构建排除双语页面及旧跳转路由，主站与资讯列表移除全部阅读入口；发布刷新旧地址缓存，验收要求返回 404。正文源码保留，恢复需同步调整构建排除、入口、CDN 退役清单和验证规则。
- 官网框架在本地或 CI 构建；服务器不运行 Node/Docusaurus 构建。
- 资讯同步只下载 JSON Feed 1.1、完整 HTML 和依赖，生成独立列表与详情。
- 内容 App 决定详情的完整外壳、样式与正文；官网修改 SEO、编码及搬迁所需的资源地址。
- 中英文官网导航和页脚都进入 `/zh/news/`，文章在新标签页打开。
- 案例方案页读取 `/zh/news/` 已发布的内嵌文章快照，并仅展示 `tags` 中含“案例”的文章；资讯同步器从配置的 `NEWS_FEED_URL` 生成快照，前端不重复配置 Feed 地址。
- 资讯列表的推荐首篇、封面、标题、摘要和日期直接输出到静态 HTML，脚本只增强筛选与轮播；初次推荐保持静态首篇，其余文章随机排序。列表同时提供 OG/Twitter 和真实文章集合的 CollectionPage/ItemList。
- 案例页从同一已发布快照生成完整静态案例清单（标题、摘要、小封面、日期与普通详情链接）及 CollectionPage/ItemList；无 JavaScript 时可直接阅读，启用脚本时沿用筛选和轮播。`cases_projection.py` 只替换双语案例页的 `case-static`、`case-list-schema` 两个明确槽，不重排主站页面。安装器显式设置 `NEWS_MAIN_SITE_DIR`，独立同步器未配置主站根时保持原边界。主站重发及资讯更新/下线均重新投影，共享 release.lock；写入/状态提交失败恢复已写案例与资讯链接，CDN 失败保留新内容和重试队列。进程断电不保证多文件事务，下一轮发布重放恢复。
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
5. 显式 `bootstrap`：首次生成并发布“好内容，正在路上”空页；已有版本先校验文件摘要，再用已发布公开快照和新模板重建列表界面，保留文章与资源，按同一快照重建 sitemap，不请求 Feed。模板变化通过正常候选发布与 CDN 刷新生效；无变化只完成遗留 CDN 刷新。
6. 通过 `apply-main-site.py --apply` 持共享锁应用主站，保留资讯链接和全部运行时数据。
7. 初始化和主站应用成功后，在同一配置锁内切换正式配置与程序入口，再激活 service/timer。已有服务从读取配置至运行结束持共享锁，因此安装器会等旧任务结束，新任务会等切换完成。入口替换或 systemd 激活失败时恢复旧配置和程序；不会让首次 timer 触发时找不到程序入口。
8. 验证源站入口及 SEO；通过 `cache_policy.py --apply` 应用并回读官网分层缓存，策略变化先排队整站旧缓存刷新；独立刷新主站 CDN（含退役博客），再验证 CDN 的 SEO 和浏览器缓存头。失败非零退出，不假报成功。

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

已配置地址但来源失效时，build 保留已发布内容；首次无内容则生成空候选。CLI 输出 `fallback=true` 并非零退出，定时任务显示失败，不把保留旧页面误报为本轮同步成功；文章下载失败在日志中附文章 ID。官网发布时的模板升级独立于来源抓取，即使来源失效或未配置，也会更新已发布列表的导航和 UI。空页隐藏筛选/搜索/轮播，禁用 JS 也能阅读。缓存校验失败先完整重下载，恢复失败或索引损坏明确返回运行故障，不会被当成普通来源不可用。

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
- 下载整页及实际引用的图片、视频、音频、字幕、CSS、字体，不按媒体扩展名白名单筛选；MP4、FLV、未知后缀、无后缀及带查询参数的 src 均搬运。存储接口匹配 `/api/whwy/<appId>/storages/`，安全 file 参数有后缀时保留文件名，无后缀按 MIME 推导哈希文件名；同批同名异内容拒绝发布。
- HTML 的 src、srcset、poster、source/track 引用及 img/source 的 data-src/data-srcset 延迟图片约定，CSS 的 url、@import、image-set，SVG 的样式和图像依赖递归下载并改写。静态 HLS 点播还搬运子清单、分片和 URI 密钥；直播、动态 HLS 与 DASH 保留来源地址，由播放器继续访问来源，不冻结为静态快照。搬运不转码，FLV 等能否播放仍取决于浏览器支持。
- 下载分块检查体积及 Content-Length，完成后才缓存；默认单资源 20 MiB、单次累计 256 MiB（可配置），大视频超过限制会明确失败并保留旧版。无 Content-Length 且正常结束的响应无法仅凭 HTTP 判断来源是否漏发字节。
- 来源原始资源应按内容系统意图保持 noindex；同步不修改来源政策、不因禁止索引拒收文章。官网输出 robots=index,follow,max-image-preview:large，移除来源通用及爬虫专用索引 meta，不转发来源 X-Robots-Tag 响应头；canonical/og:url/主体 Article JSON-LD 指官网。主体 image 的 URL、数组、ImageObject 镜像为官网资源，publisher/citation 等第三方实体保留原义。发布验收还检查官网实际响应头和 robots.txt，HTML index 不能覆盖服务器 noindex。
- 网页内容由来源作者决定，同步器不设置标签、脚本、事件、嵌入或链接协议黑名单，不按文章 ID 或脚本名称特殊放行。内联脚本、数据块、事件属性和 SVG 交互保留；正文可使用任意标签结构。可解析的 JSON-LD 沿用 SEO 适配，其他数据块保留原文。
- 不重新排版、不注入官网详情外壳。外部脚本、iframe/object/embed 和表单目标转为来源绝对地址，保留执行属性、相对模块依赖的来源基址及运行目标；来源 base 语义保留，本地镜像资源显式绑定官网。同步器不执行脚本，也不代理来源后端，作者的运行时请求、浏览器 CORS/登录要求仍由来源应用负责。静态资源继续搬运，下载失败保留旧版并报告故障。
- 按条目的 `date_modified` 判断版本，现有 `seo.updatedAt` 映射优先；接受带时区或不带时区的 ISO 日期时间，保留毫秒/微秒差异，不截断到整秒。有合法修改时间且来源 URL 未变时，复用已发布版本记录的 HTML 和全部依赖，只校验本地字节，不发文章/资源 HTTP 请求。内容端必须在正文或依赖更新时同步更新条目时间；只有 Feed 生成时间变化不会触发重下载或发布。版本变化时重新检查完整依赖图（含 CSS 深层图片与仅在 Feed 中出现的封面），允许各个资源合法返回 304；HTML 的 304 不能免去依赖检查。
- 缺失/非法条目时间时沿用内容探测及 ETag/Last-Modified。未变条目缓存缺失或损坏时，无条件下载修复且核对 **active 中已发布版本的摘要**；只接受相同字节，不能用超前下载索引里的未发布字节取代基线。来源已变或下载失败时抛出缓存故障、保留线上版本，不拼接新旧资源后按旧时间发布；内容系统推进条目时间后重新检查整篇即可恢复。普通下载缓存与未发布候选均不能作为免下载基线。先读取变化条目，再处理未变化条目，防止共享资源被旧缓存遮蔽；共享 URL 本轮只下载一次，若其字节变化，使用它的其他详情也可能需要更新改址。
- 下线条目从下一完整版本的列表、详情、sitemap 删除；最后一篇下线需要 NEWS_ALLOW_EMPTY_FEED=1，防止误输出空清单清空官网。
- 发布比较新旧文件字节，刷新新增/修改/删除资源及实际变化文章的无尾斜线、目录、index.html 地址；未变文章不重复刷新，同名 CSS/图片/视频变更也刷新。每批收到有效任务 ID 后立即持久化移除，失败只保留未受理批次；网络响应丢失时无法确认云端是否受理，仍保留该批以免遗漏。资源随静态版本部署到官网源站，由官网 CDN 域名提供；刷新接口受理不代表所有边缘节点已完成，也不执行预热。
- 主站 CDN 由 `refresh_cdn.sh → refresh-main-cdn.py` 处理：扫描全部静态文件摘要（含图片/视频/CSS/JS），只排队新增、修改、删除文件及 HTML 别名，排除独立资讯。退役目录及别名首次排队，受理后不重复提交；新增退役规则仍会进入队列。
- 主站使用服务器官方 aliyun CLI，先调用 DescribeRefreshQuota，按实际 UrlRemain/DirRemain 分别提交 File/Directory。每轮最多 1000 个文件、100 个目录，轮次至少间隔 60 秒；任一配额为零只延期该类型，不阻断另一类型。批量减少请求数，不减少按 URL/目录计算的日配额，也不能保证其他程序同时使用同一账号时绝不发生配额竞争。
- 主站 CLI 显式传入当前账户的 `~/.aliyun/config.json` 路径；systemd 未提供 HOME 时由系统账户解析主目录，避免 CLI 找不到 profile 并报 `region can't be empty`。配置内容仍只由服务器 CLI 读取，不回传本地，也不修改宿主环境。登录环境已有 HOME 时继续沿用它。
- 主站状态在 `/data/jitai-main-cdn-state/state.json`（可由 MAIN_CDN_STATE_FILE 覆盖），快照只表示任务已排队，pending 才是未确认任务；每批受理后独立落盘。重复发布无变化不请求 API。现有资讯十分钟任务在启用发布/CDN且存在该状态时执行 `--retry`；Feed 停用则仍整体跳过，需用主站发布入口或手动 retry。CLI 失败保留任务并非零退出，额度不足明确输出 pending 并等待后续轮次。
- 首次建立主站摘要没有历史基线，需要一次性刷新当前资源；后续才按差异处理。旧程序曾受理的退役目录无持久化记录，首次迁移会重新排队一次，配额不足时安全延期。
- 旧内容哈希资源和版本暂不自动删除，避免缓存中的页面缺图；长期运行需关注磁盘容量。

## 开发与验证

所有本地测试使用 DevPackage 指定 Python。开发脚本不安装/修改 node_modules，不在服务器构建前端。

本地主站构建不包含独立资讯目录；预览首页、案例与资讯之间的跳转时，先在仓库外生成空资讯快照，再用同一个 origin 提供两个目录。预览用的 `NEWS_SITE_ORIGIN` 只影响本地生成链接，不改变正式 Feed 配置或发布目录。构建重跑后可继续使用同一预览服务，资讯目录不会被构建清理。

```bash
npm run build:low-cpu
env -u NEWS_FEED_URL NEWS_SITE_ORIGIN=http://127.0.0.1:3001 \
  NEWS_WORK_DIR=/tmp/jitai-news-preview/work NEWS_LIVE_LINK=/tmp/jitai-news-preview/live \
  NEWS_RELEASE_LOCK=/tmp/jitai-news-preview/release.lock NEWS_CDN_MODE=none \
  /Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python scripts/news/sync_news.py bootstrap
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python scripts/news/preview_site.py \
  --build build --news /tmp/jitai-news-preview/live --port 3001
```

```bash
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python -m unittest discover -s tests/news -v
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python tests/news/verify_browser_flow.py
```

测试覆盖真实本地 HTTP、生成/发布、目录保护与 rsync、安装重复执行、初始化失败停止、定时入口和 CDN 协议/状态；SSH、systemctl 与真实云接口用替身隔离。详细证据见 VALIDATION.md。真实服务器环境、Nginx 用户权限、CDN 鉴权/额度和边缘传播仍需正式部署时验证；本地测试通过不表示已上线。


## 官网缓存政策与 SEO 验收（2026-11-25）

本次线上只读调查发现：根目录 CDN TTL 为 2592000 秒（30 天）、权重 99，普通 HTML 和可变图片没有显式 Cache-Control；浏览器可能采用启发式缓存，不能将 CDN 的 30 天直接称为浏览器 TTL。本地新增策略尚需实际发布才能生效。

`cache_policy.py` 复用服务器已有 aliyun CLI。默认仅 Describe/预览，`--apply` 写云配置后回读，`--restore` 恢复站点外的 `/data/jitai-cache-policy/backup.json`；备份权限 0600，不读取或传输凭证，不修改 Nginx。仅管理列出的目录与错误状态 TTL，保留无关配置；发现重叠扩展名/Cache-Control 改写规则或条件规则时明确报告冲突，不能静默覆盖未知设置。

| 路径/状态 | CDN 有效期 | 理由 |
| --- | --- | --- |
| `/`，包括文章、列表、sitemap、同目录文章 CSS | 60 秒 | 允许内容更新较快生效；配合十分钟同步，不让漏刷新留下数周旧页面 |
| `/img/`、`/zh/img/`、`/zh/news/assets/` | 300 秒 | 其中有同名覆盖资源，不能声明永久不变 |
| `/assets/`、`/zh/assets/`、`/zh/news/ui/` | 31536000 秒 | 构建与 UI 资源按内容生成文件名，更新使用新地址 |
| 404、410 | 10 秒 | 避免资源恢复后长时间沿用旧错误 |
| 5xx | 1 秒 | 短暂源站故障不长期固化 |

路径规则启用 `swift_follow_cachetime`，把最终有效的 CDN 策略返回给浏览器；保留源站 no-store/no-cache 语义。错误状态策略是源站优先规则，不应越过源站显式声明。同步/发布仍按变更刷新，不用短 TTL 代替刷新。云配置不能追回已经存于浏览器的旧缓存；部署后需验实际响应和 CDN 传播。

策略变更前将整站 Directory 刷新合并到主站既有队列，沿用配额与失败重试，不再建立第二套刷新机制。备份、云写入、回读和缓存刷新是不同阶段，任何失败均不能声称线上已完成。

`verify-site.py --seo` 对实际 HTTP 输出核对：官网索引 meta/X-Robots-Tag/canonical、原始案例链接与 schema、双语 hreflang、资讯 sitemap、robots.txt。`--cache` 增加 HTML 和可变封面的 Cache-Control 上限检查。验收不检查作者题材或删改正文，来源质量问题由报告交给内容系统。源站和 CDN 均需验收；API 提交成功不等于边缘传播完成。
