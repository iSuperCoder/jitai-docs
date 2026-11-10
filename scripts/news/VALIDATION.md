# 资讯全链路验收记录

## 导航一致性修复与提交前验证（2026-11-10）

资讯原型导航使用 72px 高度、1216px 容器、100px Logo 和 1150px 菜单断点，与营销页不同。现统一为营销页的 64px 高度、1200px 容器/24px 边距、112×34 Logo、1180px 断点及字体、按钮、sticky 行为。仅调整独立列表导航，不改 App 详情页排版。

新增浏览器对照测试在修复前出现 19 个失败分支：两种主题、9 个宽度的导航高度/位置不同，以及菜单缺少关闭状态。修复后与真实主站构建逐元素比较，Logo、导航项、主题按钮和 CTA 的位置/尺寸差异不超过 0.5px；另验证两个移动 CTA、Escape 返回焦点及跨断点收起。截图人工检查浅色/深色首页、资讯有内容和空页的导航对齐。

当前完整脚本单元/本地集成测试 109 项、浏览器回归 9 项通过；`pnpm typecheck`、关闭持久化缓存的中英文构建、Shell/JS 语法检查通过。仓库未配置本地 pre-commit hook，按 CONTRIBUTING 和 CI 执行现有检查，不将不存在的 hook 记作执行成功。证据：`/tmp/jitai-header-red.log`、`/tmp/jitai-header-unit-final.log`、`/tmp/jitai-header-browser-final.log`、`/tmp/jitai-precommit-typecheck.log`、`/tmp/jitai-precommit-build.log`、`/tmp/jitai-header-comparison.png`。

本地 8766 预览已切换到修复快照；以下首次线上发布记录早于本导航补丁，线上尚未应用本次导航修复。

## 首次正式发布（2026-11-10）

用户明确授权构建发布，并授权安装 `python3.12-venv`。中英文构建与发布预览通过；服务器软件包索引过期造成第一次下载 404，更新索引后安装成功。专用运行环境 `/opt/jitai-news-runtime` 已创建，BeautifulSoup 及其依赖仅安装于该环境。

仓库发布器执行完成并退出 0：独立上传区安装、资讯空页初始化、保护资讯的主站更新、timer 启用、源站检查、真实 CDN 刷新和 CDN 检查均成功。源站/CDN 检查包含中英文当前入口和退役 blog/docs 路由 404；不表示已验证全球所有 CDN 节点。

- Feed 已保存为 `https://content.jit.pro/whwy/app1793693462070/Site/zh/feed.json`，配置权限 0600；发布开启，CDN 模式 aliyun。
- `/zh/news/` 返回 200，包含“好内容，正在路上”，当前 0 篇，pending CDN 队列 0；响应未见 X-Robots-Tag。
- 独立资讯链接指向 `/data/jitai-news-data/releases/c96d006a8e096206c6322dd5885d74429236e459424f80134452a70271487650`，数据根权限 0711，active 状态权限 0600。
- timer 状态 enabled/active，现场显示下次触发时间 2026-11-10 14:20 CST。验收时 LAST 为空，不能将 service 的默认 success 状态算作定时任务已执行成功；实际周期触发及正式来源上线后的文章下载仍待发生。
- 未修改 Nginx、未在服务器构建前端、未提交或推送仓库代码。日志：`/tmp/jitai-release-20261110-build.log`、`/tmp/jitai-release-venv-install-retry.log`、`/tmp/jitai-release-20261110-publish.log`。

以下为历次本地开发验证记录，其中“未部署”等描述仅指对应历史轮次。

日期：2026-11-10。范围：官网仓库、本地发布技能与隔离生成目录。未执行线上发布、线上定时任务安装或真实 CDN 请求。以下按实现轮次记录，后续章节覆盖此前已变更的行为；当前结果见末尾交叉评审修复记录。

## 最终入口

中英文官网导航（场景示例之后）及页脚 → `/zh/news/` → 新标签页 `/zh/news/articles/<id>/`。Feed 的 url 仍指向应用原文，仅供同步器下载。主站不生成资讯占位页面；资讯数据存放在独立目录。

## 实际检查结果

| 检查 | 结果 | 证据范围 |
| --- | --- | --- |
| Python unittest | 42 项通过 | 真实本地 HTTP 源、rsync、shell/CLI；CDN 仅替换 HTTP 传输 |
| Chrome 端到端 | 6 项通过 | 真实主站构建与生成快照，所有网络映射到本地或阻断 |
| TypeScript | 通过 | pnpm typecheck |
| 中英文完整构建 | 通过 | 关闭持久化缓存，未安装或更改依赖 |
| Shell/JS 语法及差异空白 | 通过 | bash -n、node --check、git diff --check |
| 当前真实 Feed | 4 篇生成并逐篇浏览器验证 | 正文、canonical、图片均通过，无外部依赖/缺失资源/脚本错误 |
| 响应式 | 通过 | 320/768/1024/1440；另查中英文导航 1181/1280/1440 |

## 已修复的实际问题

- 官网导航、页脚缺少资讯入口；robots 未发现独立 sitemap。
- 临时目录默认 0700，发布后 Nginx 不同用户可能无法遍历。公开快照改为目录 0755、文件 0644；部署时仍须确认祖先目录权限。
- A→B→A 回退复用最早目录，丢失 B 的缓存资源。版本指纹纳入保留的内容哈希资源集合。
- 已有候选被修改后 build 重新认可篡改内容。复用前校验原候选清单。
- 不同 ID 的来源 URL 重复、ID 哈希兜底路径冲突导致详情覆盖。生成前拒绝冲突。
- 缺少 summary 时没有使用 content_text，列表摘要空白。
- 来源重定向移动目录后按原目录解析资源造成 404。改用最终响应地址。
- HTML 缺少编码声明时详情出现中文乱码。输出 head 起始统一声明 UTF-8。

前六个脚本回归用例在修改前明确失败，修复后通过；重定向用例修复前真实请求返回 404；乱码由浏览器正文断言暴露。其余测试包括无变化跳过、仅 HTML/元数据/CSS/图片变化、下线及重新上线、空清单显式允许、304 与损坏缓存、超限和 404 保留旧版本、陈旧候选拒绝、真实定时入口、主站发布保护和共享锁、CDN 固定签名/分批/重试。测试不以调用次数代替发布结果或链接正确性。

浏览器覆盖双语入口、主题/栏目/关键词筛选、卡片与列表视图、新标签详情、12 秒轮播及悬停/手动/减少动态效果暂停、手机菜单、无 JavaScript 静态链接。测试语言偏好固定为英文，确认英文首页没有被自动重定向为中文后误报。

## 重跑

```bash
pnpm typecheck
DOCUSAURUS_NO_PERSISTENT_CACHE=1 DOCUSAURUS_SSR_CONCURRENCY=1 pnpm build
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python -m unittest discover -s tests/news -v
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python tests/news/verify_browser_flow.py
```

浏览器验收依赖现有 Playwright 和本机 Chrome，不自动安装依赖。生产调度、实际 Nginx 权限和真实 CDN API 未执行；正式域名替换、原发布流程接入保护步骤与共享锁完成后，才能上线。先发布资讯数据，再发布官网入口，避免入口指向尚未生成的列表。

## SEO 专项复查

再次检查真实生成物发现：最初 canonical、robots、og:url 均正确，但 3 篇来源 JSON-LD 的 mainEntityOfPage 写死为旧官网 `/zh/blog/<id>.html`，此前只替换抓取地址未覆盖这些值。新增测试先复现失败后修复：仅规范顶层或 @graph 内主体 Article/NewsArticle/BlogPosting/TechArticle 的 mainEntityOfPage、@id、url，不改写 citation 或 publisher 等外部实体。额外验证大小写 robots、googlebot/bingbot 禁索引覆盖、Twitter URL、标题/描述/关键词保留。42 项脚本测试通过。

当前真实 4 篇重新生成并逐篇验证：唯一 `robots=index,follow`，canonical、og:url 和主体 JSON-LD 均指官网详情；没有残余 `/zh/blog/` 结构化地址；title、description、keywords 与下载原文一致。最新候选位于 `/tmp/jitai-news-review-20261110/releases/c09771abbe7b21c3f72d56c7ddcc90cbbac1ca08a76cc60487eaabb39e685ad9/`，旧候选保留，不代表已发布。

来源 HTTP 响应头不会写入生成的 HTML。生产官网最终响应是否存在 `X-Robots-Tag: noindex` 仍属于上线前服务器/CDN 响应验收，当前没有宣称已验证线上可收录。

详情责任边界调整：移除对未迁移 App 链接删除 href 的行为；新增 DOM/样式/锚点/链接保留测试，修改前失败，修改后 43 项测试全部通过。详情不注入官网排版，资源 URL 适配仅用于搬迁后的正确加载。

## 内容 App 整页协议适配

最新一轮：47 项脚本测试、6 项浏览器端到端测试全部通过。真实 Feed 的 4 篇整页已重新生成并逐篇验收：保留 header/main/footer 外壳，同目录 `<slug>.css` 的相对引用不变，CSS 与下载缓存原始字节完全一致；存储图片文件名等于 file 参数值且浏览器全部解码成功；robots 为 index,follow,max-image-preview:large，canonical/og:url/Article JSON-LD 指官网，isPartOf 指官网根。

新增测试覆盖 seo 对象的列表映射与独立变更识别、整页/CSS/图片契约、同名资源更新与 CDN pending、file 参数路径逃逸拒绝、同名不同图片冲突拒绝。资源继承不再覆盖新下载的同名图片；固定名称的 CSS/图片更新必须刷新对应 URL。此轮候选目录 `/tmp/jitai-news-review-20261110/releases/10f9325b4c956f001b03652de904a4eca0b0c59d1c90982020f86f59bf5261da/`，本地预览 8766 已切换。没有线上变更。

## 单 Feed 配置及来源不可用兜底

53 项脚本测试、7 项浏览器端到端测试通过。只设置 NEWS_FEED_URL 与测试工作目录即可抓取当前真实 4 篇文章，未再传入文章来源域名或额外资源域名。官网默认 https://jit.pro；文章、CSS、图片及重定向按来源引用自动解析。跨域验证使用两个真实本地 HTTP 服务，不替换资源解析逻辑。

该轮原行为（未配置场景已被下节变更替代）：未配置、非法 URL、HTTP 404、坏 JSON 的首次 build 生成正常空候选；已有发布时保留 active 与文章文件、不增加下线数量。空页发布后配置有效 Feed 可恢复真实列表。真实 shell 验证缺少 Feed 时正常返回 fallback 摘要；静态与启用 JS 的空页均隐藏无用筛选控件，保留官网导航及白皮书/场景入口，无脚本错误和手机横向溢出。

本地正常列表仍为 http://127.0.0.1:8766/zh/news/，空状态单独预览于 http://127.0.0.1:8766/zh/news-empty/；空预览仅是本地演示路径，不新增官网路由。首次线上使用仍必须按显式发布流程放置生成的空页或真实内容，不自动发布。


## 未配置即跳过、十分钟调度与 CDN 专项（当前行为）

2026-11-10：67 项脚本单元/集成测试全部通过，其中 CDN 专项 16 项；7 项浏览器测试通过。Shell 语法与差异空白检查通过。测试日志为 `/tmp/jitai-news-ten-minute-tests.log`、`/tmp/jitai-cdn-after.log`、`/tmp/jitai-news-ten-minute-browser.log`。

- 未配置、空字符串、纯空白 Feed：真实 shell 在 Python 启动前正常退出；check/build/publish/retry-cdn CLI 也在配置初始化与加锁前退出。断言没有网络请求、没有新数据目录，已有页面和 pending 字节保持不变。使用不存在的解释器验证 shell 确实未执行后续步骤。
- 已配置但来源失效：继续保留已发布内容；首次空候选和浏览器空状态仍有效，测试输入改为真实本地 HTTP 404。
- CDN：固定签名预期、带/不带 STS token、模式与凭证拒绝、空队列、1/100/101/200/201 条分批、特殊字符编码、不同 nonce、403/429/500/断网/超时、API 错误及非法/空任务 ID、失败停止后续批次、日志脱敏均覆盖。
- 持久化：none 模式保留队列；201 条队列第二批失败后保持整份原记录，成功重试后才清空；新版本合并旧失败项。通过真实发布验证新增/修改/下线文章、列表与 sitemap、无尾斜线和 index.html 变体、同名 CSS/图片更新和已删除 CSS 的完整请求集合，不刷新官网其他路径。
- 缺陷敏感性：先新增测试，原 CDN 实现出现 6 个断言失败、2 个错误（空任务 ID 被误判成功、非对象响应、空队列凭证校验等）；修复后通过。未配置 Feed 的 3 项新测试同样在修复前失败，修复后通过。
- 调度：仓库新增 systemd service/timer 模板，每小时 00/10/20/30/40/50 分触发，单服务避免重叠；没有在服务器安装或执行。当前本地不是 systemd 运行环境，尚未验证服务器实际触发。

CDN 仅在 HTTP 边界使用替身，签名、分批、候选生成、版本切换、状态文件与重试均执行真实实现；未使用真实密钥、未向阿里云提交刷新，不能据此宣称生产权限、额度或边缘缓存生效已验证。本轮未更改线上官网、未执行主站构建、未修改依赖环境。


## 交叉评审四项问题修复（当前结果）

2026-11-10：89 项脚本单元/集成测试通过，其中 CDN 专项 17 项；7 项浏览器测试通过。最后扩展退役文档入口刷新后，6 项主站/CDN 边界测试再次通过。Python 源码解析、Shell 语法、差异空白与本地发布技能校验通过。日志：`/tmp/jitai-review-fixed-final.log`、`/tmp/jitai-review-fixed-browser.log`、`/tmp/jitai-retired-cdn-final.log`。

1. 发布入口：新增仓库 `scripts/publish-site.py`，本地官网发布技能委托此入口。只上传唯一暂存区，由服务器 installer 初始化空页，再通过已有目录保护程序应用主站，最后安装十分钟 timer。不再依赖被删除的安装指南或不存在的 Docker 容器。新增临时目录集成测试实际运行 Python 生成器与 rsync，验证首次空页先于主站上线、重复安装保留文章/配置/凭证/pending、初始化失败不更新主站/不启用 timer、配置权限 0600，以及实际 service ExecStart 在无 Feed 时正常跳过。SSH 和 systemctl 仅替换传输/系统管理边界；本轮未执行线上命令或真实 systemd 启动。
2. 退役内容缓存：所有主站刷新模式均显式加入中英文 blog/docs 目录及无尾斜线、尾斜线、.html、index.html 入口，不依赖已删除文件的扫描结果。真实 DRY_RUN 验证范围；HTTP 验证测试确认缓存中的旧博客仍返回 200 会判为失败。
3. JSON-LD 图片：主体 Article 的 image 字符串/数组/ImageObject.url/contentUrl 镜像到官网。新增回归先在旧实现出现 3 个失败分支，再修复通过；保留 publisher/citation 图片与实体语义，图片真实落盘可读。
4. 缓存恢复：发送条件头前校验本地字节，损坏后无条件完整下载；真实本地 HTTP 验证从损坏状态恢复且不 fallback。恢复 404 或缓存索引损坏以 CacheError 非零报告，保留已发布状态。缓存异常不会再被 collect_available 当成来源临时故障吞掉。

额外补齐安装首次刷新失败后的 bootstrap 重试：即使尚未配置 Feed，显式重新安装也会完成遗留 pending；常规定时入口仍遵守无 Feed 完全跳过。凭证测试只使用虚构 profile，验证 current 选择、AK/STS、显式凭证优先、部分凭证拒绝、无 Feed 不读取 profile；没有读取本机或线上真实密钥。

只读抓取现有真实 Feed，在 `/tmp/jitai-news-review-fix-real-20261110/releases/54d80b8835216c54eda4059a517d646507cc8011b614e5e9597e7ab0aca4da09/` 成功生成 4 篇候选，无 fallback。4 篇 canonical 均为官网详情；当前来源没有主体 image 字段，JSON-LD 图片新行为由独立测试数据验证，不能把真实源无该字段的结果算作覆盖。

评审结论：四项已修复并有本地回归证据。服务器 Python/venv/systemd 能力、真实 Nginx 权限及 CDN 鉴权/额度/边缘传播仍未执行，必须在正式授权发布时验证。当前代码未提交、未推送、未上线。


## 第二轮交叉评审修复（2026-11-10，当前结果）

三项问题均修复：

- 配置与程序切换：安装独占配置锁，服务共享同一把锁并持有至子进程退出。候选配置用于 bootstrap，不提前覆盖正式配置；初始化/主站应用成功后，在锁内切换正式配置和程序，再激活 timer，解锁后服务才读取它们。入口替换或 systemd 激活失败恢复原配置和程序。此保证针对资讯配置/程序，不表示已经写入的主站文件具备全站事务回滚。
- 文件权限：工作根 0711，公开版本 0755/0644；cache/candidates 0700，状态 JSON 和正式配置 0600。初始化和已有版本 bootstrap 均修复历史权限；不改变宿主共享父目录。测试覆盖 umask 077 及人为恢复成旧错误权限后的再次安装。
- 凭证切换：配置凭证按完整 AK 对更新，未提供 token 时清除旧 token；单独改 Feed 不动凭证。拒绝半份 AK 或 token 单独更新。普通 AK profile 与配置 AK 都不混入上层环境遗留 token；STS 仍支持。

新增回归先在旧实现出现 8 个失败分支，修复后通过。全套 98 项脚本测试、7 项浏览器测试通过；最后调整 timer 激活前先放置入口及失败恢复顺序后，26 项发布/安装/配置测试再次全部通过。真实子进程文件锁测试覆盖双向等待，失败注入覆盖 bootstrap、主站应用、timer 激活与最终符号链接替换；未 mock 配置保存、文件锁或 rsync。

证据日志：/tmp/jitai-second-fix-red.log、/tmp/jitai-second-fix-final.log、/tmp/jitai-second-fix-browser.log、/tmp/jitai-second-fix-activation-final.log。语法与差异空白检查通过。测试仅在临时目录执行，systemctl 和云端使用替身；未部署、未启用线上任务、未读取真实云凭证。

## 第三轮评审：正交拆分与断言敏感性（2026-11-10，当前结果）

本轮没有发现新的阻断性实现缺陷；确认原测试有独立触发条件依赖组合用例证明、升级失败共用前序状态的问题。仅增加测试与文档，未修改生产程序。

新增 `test_orthogonal_boundaries.py` 的 11 项独立用例：同名 CSS 单独修改、同名图片单独修改、文章单独下线；bootstrap、主站 apply、daemon-reload、timer enable 各自失败；四种不完整凭证输入。每项有独立临时基线，故障用例明确断言目标阶段命中、异常码、配置原字节、程序指针和临时文件清理。原组合测试保留，用于覆盖有意耦合的顺序行为。

原有 98 项通过，新增 11 项单独通过，最后全套 **109 项脚本单元/本地集成测试通过**（48.113 秒，无跳过或预期失败）。日志：`/tmp/jitai-orthogonal-review-baseline.log`、`/tmp/jitai-orthogonal-new.log`、`/tmp/jitai-orthogonal-final.log`。

在临时源码副本中分别注入“漏掉 CSS 指纹”“漏刷固定名称图片”“不恢复旧配置”三处契约违例，三个测试均在对应目标断言失败，无 fixture 或加载异常；正常源码为通过对照。变异记录：`/tmp/jitai-orthogonal-mutation.log`。源码未注入缺陷，未引入额外测试依赖。

完整维度、代表用例、替身边界和验证限制见 [TEST_MATRIX.md](TEST_MATRIX.md)。本轮 UI 未改，浏览器 7 项采用上一轮通过记录，未重复运行。真实 systemd、Nginx、首次环境安装及 CDN 云端仍未验收；此次没有部署、没有启动线上定时任务。评审状态：`Proceed`，本地覆盖证据足以继续准备发布，不等于生产发布验收通过。
