# 官网贡献说明

先阅读 [README](README_ZH.md) 和 [官网改版维护说明](WEBSITE_MIGRATION.md)，确认当前页面和发布边界。

- 官网页面放在 `src/pages/`，共用界面与正文在 `src/components/MarketingSite/`；改动同时维护中英文。
- 保留有效的下载资源、联系表单和法律正文，不因清理旧文档而改动这些服务。
- 旧 docs/blog 与历史版本已下线，不再向这些目录新增文章或指南。
- 新资讯来自内容后台，仓库仅维护 `scripts/news/` 的程序与模板；生成页面、缓存、发布状态及密钥不得放进源码仓库。
- 遵守工作区 AGENTS.md；未经授权不安装依赖、不修改 node_modules、不发布线上。
- 修改后运行 `pnpm typecheck`、`DOCUSAURUS_NO_PERSISTENT_CACHE=1 pnpm build` 和 `git diff --check`；检查中英文页面与站内链接。资讯脚本的验证命令见其 README。
- 界面改动检查桌面/移动端与深浅主题；不得提交测试客户线索或执行页面中的服务器安装命令。
- 提交说明写清问题、修改和验证证据。部署须单独授权，主站发布必须保护独立资讯数据目录。
