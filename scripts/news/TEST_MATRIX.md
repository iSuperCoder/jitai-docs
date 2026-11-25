# 资讯脚本行为覆盖矩阵

本表记录截至 2026-11-18 的本地评审范围。测试位于 `tests/news/`；正交拆分指每例只改变目标条件、保持其他前提有效，不代表穷举所有输入组合或达到 100% 分支覆盖。真实存在先后依赖的发布、回滚和重试仍保留流程测试。

## 独立维度与断言

下列名称省略 `test_` 前缀；同一行的枚举场景可以由独立用例或重新建立替身的 subTest 覆盖。

| 维度 | 独立输入或状态 | 测试位置与代表用例 | 可观察预期 |
| --- | --- | --- | --- |
| Feed 配置 | 未提供、空白、非法地址、HTTP 失败、恢复有效 | `test_sync_news.py`：`missing_feed_skips_collection_without_files_or_network`、`cli_missing_feed_does_not_touch_existing_release_or_pending`、`invalid_or_failed_feed_creates_first_empty_candidate`、`initial_empty_page_recovers_when_feed_is_configured` | 无配置不请求、不写入、不重试 CDN；来源失败保留已有内容，首次候选为空页；恢复后有正文 |
| 内容变更触发 | HTML、元数据、CSS、图片分别单独变化；生成时间/顺序变化 | `test_sync_news.py`：`html_only_edit_updates_official_detail`、`metadata_edit_updates_listing_without_changing_url`、`generation_timestamp_and_feed_order_do_not_trigger_build`；`test_orthogonal_boundaries.py`：两个 `only_same_name_*` | 必要变化生成新版本；无关变化不生成；实际落盘字节与独立测试输入相等 |
| 下线与重新上线 | 单篇下线、同 ID 恢复、全部下线、非完整 Feed | `test_orthogonal_boundaries.py`：`only_article_removal_purges_its_css_without_refreshing_unchanged_image`；`test_sync_news.py`：`unpublished_article_returns_under_same_official_url`、`empty_feed_requires_opt_in_and_removes_all_pages`、`incomplete_feed_cannot_delete` | 删除详情、sitemap 条目与同目录 CSS；刷新旧 URL；全空需显式开关；残缺清单不能删站 |
| SEO 与呈现边界 | robots、多种主体 JSON-LD、图片字符串/数组/对象、外部引用 | `test_sync_news.py`：`seo_removes_all_noindex_and_normalizes_primary_jsonld`、`jsonld_article_images_are_mirrored_without_rewriting_external_entities`、`article_presentation_and_source_links_remain_app_owned` | 官方 canonical/索引归属正确；主体图片本地可读；publisher/citation 与正文排版不被误改 |
| 资源地址 | 相对 CSS、storage file 参数、重定向、跨域、冲突和越界 | `test_sync_news.py`：`full_page_css_and_storage_image_follow_new_contract`、`allowed_redirect_resolves_resources_from_final_url`、`storage_file_parameter_cannot_escape_assets_directory`、`storage_filename_collision_is_not_silently_overwritten` | 从实际来源地址解析；固定名称正确落盘；危险或冲突输入明确拒绝 |
| 缓存恢复 | 正常 304、坏缓存恢复成功、恢复失败、坏索引 | `test_sync_news.py`：`http_304_uses_verified_cache_and_repairs_corruption`、两个 `corrupt_cache_*` | 真实 HTTP 条件头与下载字节正确；内部缓存故障不能冒充来源不可用；保留 active |
| 发布状态 | 候选被改、候选过时、版本回退、来源缺失/超限 | `test_sync_news.py`：`collect_cannot_approve_tampered_existing_candidate`、`stale_candidate_cannot_overwrite_newer_publish`、`restoring_old_content_keeps_intermediate_cached_assets`、`resource_limit_failure_keeps_active_release` | 不重新认可篡改、不覆盖新版本、保留历史资源和有效页面 |
| CDN 协议 | AK/STS、固定签名向量、0/1/100/101/200/201 条、编码、HTTP/API/任务 ID 错误 | `test_cdn.py`：`signature_matches_fixed_request_vector`、`batch_boundaries_and_url_encoding`、`api_error_or_malformed_success_cannot_acknowledge_refresh` 等 | 独立固定签名正确；无损分批；错误不确认成功、不泄露凭证、不继续后续批次 |
| CDN 持久化 | 禁用、部分批次失败、重试成功、旧失败与新发布合并 | `test_cdn.py`：`failed_retry_keeps_only_batches_not_yet_acknowledged`、`new_publish_merges_old_failures_and_refreshes_removed_resources`；两个 `only_same_name_*` | 逐批受理后记账；未受理队列不丢失；同名资源修改刷新自身，不误刷未变资源 |
| 升级失败阶段 | bootstrap、主站 apply、daemon-reload、timer enable 各自失败 | `test_orthogonal_boundaries.py`：`UpgradeFailureTests` 四例；`test_release_install.py`：`program_switch_failure_restores_original_configuration` | 每例从独立成功基线出发；目标阶段必须实际命中；异常码一致；配置原字节和程序指针恢复；临时候选清理 |
| 凭证生命周期 | 不完整输入、AK/STS、Feed 单独更新、环境遗留 token | `test_orthogonal_boundaries.py`：`CredentialInputTests` 四例；`test_release_install.py`：`ServiceCredentialsTests`、`replacing_sts_with_ak_clears_token_but_feed_only_change_preserves_credentials` | 单规则拒绝在命令执行前发生；有效更新按整组替换；普通 AK 不混入旧 token；Feed 更新不丢凭证 |
| 权限、并发和主站边界 | umask 077、旧权限修复、安装/服务双向锁等待、真实 rsync | `test_release_install.py`：`restrictive_umask_preserves_public_access_and_private_state`、两个 `*_lock_*`；`test_main_site_boundary.py` | 公开文件可读、私有状态不公开；真实子进程等待锁；主站发布保护资讯目录，CDN 刷新职责分离 |

## 测试质量与缺陷敏感性

本次资源与增量同步新增的覆盖：

| 维度 | 测试文件 | 独立预期与边界 |
| --- | --- | --- |
| 通用资源搬运 | `test_resource_mirroring.py` | MP4/FLV/WebM/未知后缀/无后缀/查询参数、storage 视频与音频；核对实际字节、改写地址及刷新请求 |
| 递归依赖 | 同上 | source/poster/track/srcset、CSS image-set/import/字体、SVG 样式/图像、静态 HLS 子清单/分片/密钥；循环明确报错，直播保留来源地址继续播放 |
| 下载完整性 | 同上 | HTTP 200 截断不污染缓存、不替换 live，恢复后发布；声明长度超限独立拒绝 |
| 逐条增量 | `test_incremental_news.py` | 仅 Feed 生成时间变化只请求两次 Feed；单条更新不下载/刷新另一条；seo.updatedAt 和无时区 ISO 时间可用 |
| 增量恢复与共享 | 同上 | 无时间回退探测、坏缓存重下、下线不重下保留篇、更新篇先读取共享资源、未发布候选不作为基线 |

视频测试使用合成字节验证搬运，不证明浏览器支持 FLV 等媒体格式；CDN 传输使用本地替身，未调用真实云接口。时间戳契约要求内容端更新依赖时推进条目时间。

- 新增独立测试不以被测哈希算法生成期望，使用明确资源字节、官方路径、原配置字节和原程序指针作为预期。
- 资源用例执行真实本地 HTTP、生成、落盘和发布；升级用例执行真实配置写入、文件锁和 rsync。替身仅隔离 systemctl/云传输，或在明确目标阶段注入失败。
- 保留原组合用例验证跨步骤交互；新增用例阻止 CSS 与图片同时变化、连续失败共享状态等条件互相掩盖。
- 临时副本中分别删除 CSS 指纹输入、跳过固定图片 CDN 刷新、跳过原配置恢复。三个测试分别在“必须触发更新”“必须包含图片刷新 URL”“必须恢复配置字节”断言失败，均无 fixture/加载异常。仓库实现未注入缺陷。
- 变异复验脚本：`/tmp/jitai-news-orthogonal-mutation.py`，日志：`/tmp/jitai-orthogonal-mutation.log`；这些是本机临时验证证据，不是持续集成依赖。

## 执行与外部边界

```sh
/Users/liushao/Documents/wanyun/jit/DevPackage/.venv/bin/python -m unittest discover -s tests/news -v
```

该命令同时收集脚本单元测试和本地集成测试；浏览器脚本 `verify_browser_flow.py` 不在其收集范围。生产 systemd 实际调度、首次运行环境安装、Nginx 用户权限及响应头、真实 CDN 鉴权/额度/边缘传播仍需正式发布时验证。本地替身通过不证明上述外部环境已验收。升级失败恢复保证的是资讯配置与程序配对，不包含主站已写文件的全站事务回滚。

## 主站增量批量刷新（2026-11-19）

`test_main_cdn_queue.py` 覆盖未变文件与退役目录不重刷、单 CSS 更新、删除媒体/HTML 别名、资讯隔离、目录零额度而文件可提交、1000 File 与目录配额边界、部分成功后失败仅保留剩余任务、无效响应不确认、60 秒重复调用节流。真实 shell→Python→CLI 子进程集成以临时 CLI 替身记录多行 ObjectPath，第二次相同发布无 API 请求。资讯 `test_cdn.py` 验证第二批失败后只重试剩余 101 条，已受理 100 条不再提交。

官方依据：RefreshObjectCaches 每请求最多 1000 File 或 100 Directory，单域名每分钟 10000 URL；DescribeRefreshQuota 返回当前日剩余额度。主站每轮最多 1000 File/100 Directory 且至少间隔 60 秒，资讯维持每批 100 File 的保守配置。

2026-11-20 补充 CLI 配置定位回归：真实子进程替身检查无 HOME 时使用系统账户主目录、有 HOME 时沿用指定目录，两者都显式传入配置文件路径且不修改宿主环境。旧实现于配置路径断言失败；修复后通过。生产 CLI 3.0.306 只读对照中，无 HOME 的旧调用失败，新调用成功获取配额；替身不读取真实凭证，生产凭证未复制到本地。

## 移动导航与视频首帧（2026-11-22）

`verify_browser_flow.py` 用真实浏览器验证主站及独立资讯在 320/390/768/1024 宽度下的整屏导航：屏幕底部命中菜单、背景 inert、背景不滚动、短屏末项可见、Tab 不逃出导航、Escape 及桌面断点关闭后恢复交互。展开前先滚动到非零位置，防止只测页首掩盖滚动锁导致导航上移或关闭后回顶的问题。

首页视频使用原视频提取的 960×540 首帧图，测试在媒体请求被阻断时仍能解码并显示预览；点击后真实媒体失败触发重试，重试恢复可播放预览。真实 CDN 视频播放另以 Chrome 手机视口验证 3840×2160 解码、内联播放、原生控件及无预览滤镜；Chrome 设备模拟不等于 iPhone/微信实机验收。

## 自由网页同步与失败状态（2026-11-24）

`test_page_content_sync.py` 独立覆盖内联脚本/数据块、外部脚本依赖基址与执行属性、事件/自定义协议、嵌入和表单目标、SVG 交互、无 article 的正文、base、混合 data URL 的 srcset、跳转与无法解析的 JSON-LD。按作者提供的内容和原目标地址断言，不采用脚本白名单或单篇文章特例。

真实 shell→CLI 的 HTTP 404 回归从成功发布基线开始，只删除一篇来源文章，要求非零退出且日志包含文章 ID/HTTP 状态，active 字节及 live 指针不变；正常调度、恢复和无配置跳过仍由原有集成测试验证。首次七个新增用例在修复前分别因内容拒绝或错误的成功状态失败，修复后通过。


## 官网 SEO、案例静态发布与缓存（2026-11-25）

- `test_listing_seo.py`：真实列表生成含推荐首屏、封面、摘要、时间、分享元信息及 CollectionPage；空列表不造文章；sitemap 仅采纳合法来源修改日期，无时区取日历日，倒置/非法日期省略。
- `test_cases_projection.py`：真实资讯同步、双语主站槽及 rsync，覆盖案例新增/改名/下线、来源失败、第二页写入失败、active 提交失败、CDN 失败、主站重发、旧壳兼容和半槽拒绝；特殊标题不能逃逸 HTML/JSON。
- `test_sync_news.py`：来源爬虫专用 meta 各自独立出现、HTTP X-Robots-Tag 与普通含 noindex 的描述对照。新测试修复前在七种声明的“未移除”断言失败，修复后通过；来源正文/政策保留，官网允许索引。
- `test_cache_policy.py`：只读预览、分层 TTL、幂等、响应丢失、回读未确认、原配置恢复、错域名无副作用、配置冲突及待刷新队列合并。云 API 使用配置存取替身，不能代替真实生效验证；已对线上配置执行只读预览。
- `test_seo_verification.py`：真实本地 HTTP 提供正式生成产物，逐项只注入一个官网 noindex 头、专用 meta、来源 canonical、漏案例链接、错 schema、错 hreflang、漏 sitemap、robots 禁抓、过长 HTML/图片缓存；正常对照来源仍为 noindex。检查器必须在对应错误处失败。
- `verify_browser_flow.py` 与 `verify_case_carousel.py`：真实 Chrome，脚本/无脚本案例可读、列表封面与轮播交互；异步等待实际 ready，不能把同样拥有推荐样式的骨架误当成功。

本地集成与浏览器测试不证明 CDN 规则已上线、搜索引擎已收录或全体用户的 Core Web Vitals 已达标。发布脚本自动执行源站 SEO、CDN SEO/缓存响应检查；配置应用与线上验收状态必须分开报告。

补充来源方新方案适配：资源回归分别检验 data-src/data-srcset 字节镜像、描述符保留、未提前赋 src、来源 base 下官网绝对地址、自定义组件 data 属性不误改；修复前两个场景在镜像地址断言失败，修复后通过。真实 Chrome 观察初始无该资源请求，点击作者按钮后恰好从官网请求一次且图片解码成功。

## v4 官网侧 TDD 与缓存版本恢复（2026-11-25）

仅推进官网消费端，不修改内容系统模型、发布记录、数据库并发或回填。`test_incremental_news.py` 新增 8 个独立用例：

| 场景 | 可观察预期 |
| --- | --- |
| 缓存 HTML 损坏，旧条目时间下来源正文已变 | 明确 CacheError，active/live 不变；来源推进毫秒时间后正文和媒体同时恢复 |
| 已发布缓存缺失，下载索引已有未发布新版本与 ETag | 无条件恢复下载，不接受超前字节；不能用 304 和索引自洽冒充已发布基线 |
| 已发布缓存缺失，恢复 HTTP 404 | CacheError 向 build 的 collect_available 入口传播，不变成“未变化”或普通来源 fallback |
| 已发布缓存缺失，来源字节仍相同 | 修复缓存，无新版本，不下载其他文章/资源 |
| 同秒两次修改时间相差 1 毫秒 | 第二版正文和媒体落盘、首发日期保留、其他篇不请求；公开快照保留修改时间小数 |
| HTML 与两层 CSS 返回 304，深层图片变更 | 依赖仍逐层条件校验，官网 CSS 最终引用真实新图片 |
| 封面只存在于 Feed、未被 HTML 引用 | 推进修改时间后列表封面采用新字节 |
| 下载 HTML 后完整 Feed 撤回该篇 | 两次清单检查拒绝候选、不换 live；重跑按新完整集合下线 |

修复前前三个用例均在预期 CacheError 未抛出的断言失败；不是导入或 fixture 失败。相同字节修复与毫秒时间场景作为正常对照原本通过。修复只扩展 Fetcher 对已发布缓存的恢复职责；不增加 Feed 字段、内容准入规则或文章特例。

这些用例执行真实本地 HTTP、资源改写、候选生成和发布；仅云刷新用传输替身隔离。下载中撤回在真实 fetch 返回后调度来源变更，不替换 Feed 判断逻辑。它们验证官网处理来源提交结果，不证明来源的单篇并发、共享 Feed 提交、逻辑时间持久化或历史快照回填已完成；上述仍由内容系统交付证据。

本轮实际执行：修改前 195 项回归通过；新增用例在修复前检出上述 3 处目标失败；修复后增量专项 17 项与完整脚本回归 203 项均通过，`git diff --check` 通过。正式公开 Feed 在独立本地工作目录生成 4 篇候选，每篇 robots 允许索引且 canonical 指向官网；该检查没有写入线上，不代表已发布或 CDN 配置已生效。证据保存在本机 `DevPackage/output/seo-audit-20261125/tdd-v4/` 与 `tdd-v4-official-probe/`，不是脚本运行依赖。

### 交叉评审 P2 关闭：验证实际媒体引用

毫秒更新与缓存故障恢复两个用例已改为解析实际发布 HTML 的 `video.src`，读取所指官网文件并直接比较明确的新媒体字节。旧哈希资源继续保留，不以遍历 assets 找到新文件代替用户可见结果。

本次 TDD 敏感性证据：独立进程中保留真实下载、落盘和发布，只把目标新版 HTML 的视频引用恢复成旧地址。修改前两个用例均错误通过；修改后两个用例均在目标文件字节断言失败（`b'one'` 分别不等于新媒体字节），0 个 fixture/运行错误。撤去注入后两项正常通过；增量专项 17 项通过。完整脚本 203 项为上一轮执行结果，本次只修改测试断言与记录，未重复全量。注入脚本及前后结果位于本机 `DevPackage/output/seo-audit-20261125/tdd-v4-review/`；注入不修改产品源码、不作为部署依赖。
