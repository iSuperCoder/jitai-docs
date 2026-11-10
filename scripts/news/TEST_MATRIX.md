# 资讯脚本行为覆盖矩阵

本表记录 2026-11-10 的本地评审范围。测试位于 `tests/news/`；正交拆分指每例只改变目标条件、保持其他前提有效，不代表穷举所有输入组合或达到 100% 分支覆盖。真实存在先后依赖的发布、回滚和重试仍保留流程测试。

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
| CDN 持久化 | 禁用、部分批次失败、重试成功、旧失败与新发布合并 | `test_cdn.py`：`failed_retry_keeps_entire_queue_until_all_batches_succeed`、`new_publish_merges_old_failures_and_refreshes_removed_resources`；两个 `only_same_name_*` | 全批受理后才清空；失败队列不丢失；同名资源修改刷新自身，不误刷未变资源 |
| 升级失败阶段 | bootstrap、主站 apply、daemon-reload、timer enable 各自失败 | `test_orthogonal_boundaries.py`：`UpgradeFailureTests` 四例；`test_release_install.py`：`program_switch_failure_restores_original_configuration` | 每例从独立成功基线出发；目标阶段必须实际命中；异常码一致；配置原字节和程序指针恢复；临时候选清理 |
| 凭证生命周期 | 不完整输入、AK/STS、Feed 单独更新、环境遗留 token | `test_orthogonal_boundaries.py`：`CredentialInputTests` 四例；`test_release_install.py`：`ServiceCredentialsTests`、`replacing_sts_with_ak_clears_token_but_feed_only_change_preserves_credentials` | 单规则拒绝在命令执行前发生；有效更新按整组替换；普通 AK 不混入旧 token；Feed 更新不丢凭证 |
| 权限、并发和主站边界 | umask 077、旧权限修复、安装/服务双向锁等待、真实 rsync | `test_release_install.py`：`restrictive_umask_preserves_public_access_and_private_state`、两个 `*_lock_*`；`test_main_site_boundary.py` | 公开文件可读、私有状态不公开；真实子进程等待锁；主站发布保护资讯目录，CDN 刷新职责分离 |

## 测试质量与缺陷敏感性

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
