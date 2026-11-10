# JitAI 官网

本仓库维护 JitAI 中英文官网，基于 Docusaurus 与 React。中文路径为 `/zh/*`，英文路径为 `/*`。

[English](README.md) · [维护说明](WEBSITE_MIGRATION.md) · [资讯同步方案](scripts/news/README.md) · [贡献说明](CONTRIBUTING_ZH.md)

## 当前内容

首页、解决方案、技术白皮书、场景示例、渠道合作、关于我们、特性详情、下载安装、联系和法律协议。邀请活动、macOS 安装帮助及旧营销地址的兼容跳转继续保留。

2026-11-10 起，旧中英文博客、开发者指南、扩展指南、参考手册、教程、开源介绍、应用市场文档和历史版本已删除；对应 docs/blog 插件及旧搜索页不再启用。

## 目录

- `src/pages/`：官网路由。
- `src/components/MarketingSite/`：官网界面、正文与中英文文案。
- `src/components/LegalDocuments/`：中英文法律协议。
- `static/`：官网资源、站点地图和搜索发现文件。
- `scripts/build-locales.js`：主站中英文构建。
- `scripts/news/`：服务器轻量资讯同步程序与列表模板。
- `tests/news/`：隔离本地同步与发布边界测试。

## 本地检查与构建

使用项目已准备好的 Node.js 20+ / pnpm 环境。不要在现有工作区擅自安装或修改依赖。

```bash
pnpm start:zh
pnpm typecheck
DOCUSAURUS_NO_PERSISTENT_CACHE=1 pnpm build
```

构建产物为 `build/` 和 `build/zh/`。关闭持久化构建缓存可避免向 `node_modules` 写入 Webpack 缓存。

## 两条发布流程

官网框架修改在本地或 CI 构建，再上传到服务器暂存区，经 `scripts/news/apply-main-site.py` 保护资讯目录后应用。资讯由服务器定时拉取 Feed 和 HTML，生成列表、详情、资源与 sitemap，放在仓库外的独立数据目录并单独刷新 CDN；不执行 Docusaurus 构建，不依赖个人电脑在线。

资讯流程已接入仓库发布器与本地发布技能，包含目录保护、首次空页和定时器安装；2026-11-10 已首次上线并通过源站/CDN 路由检查。正式 Feed 通过本地发布环境提供。配置见 scripts/news/README.md，部署证据与剩余验证边界见 scripts/news/VALIDATION.md。
