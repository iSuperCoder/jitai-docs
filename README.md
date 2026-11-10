# JitAI Official Website

This repository maintains the JitAI website using Docusaurus and React. English pages use `/*`; Chinese pages use `/zh/*`.

[中文](README_ZH.md) · [Maintenance notes](WEBSITE_MIGRATION.md) · [News synchronization](scripts/news/README.md) · [Contributing](CONTRIBUTING.md)

## Content and structure

Current pages cover the platform, solutions, technical whitepaper, scenarios, partnerships, company information, feature details, downloads, contact, and legal terms. Referral and macOS installation help pages remain, along with redirects for earlier marketing URLs.

As of November 10, 2026, the legacy English and Chinese blogs, developer and extension guides, API reference, tutorials, open-source and app-market documentation, and versioned documentation have been removed. The docs/blog plugins and legacy search page are disabled.

- `src/pages/`: website routes.
- `src/components/MarketingSite/`: website layouts, content, and translations.
- `src/components/LegalDocuments/`: English and Chinese legal content.
- `static/`: website assets, sitemap, and discovery files.
- `scripts/build-locales.js`: website build for both locales.
- `scripts/news/`: independent server-side news generator and listing templates.
- `tests/news/`: isolated synchronization and publication tests.

## Local validation

Use the existing Node.js 20+ / pnpm environment. Do not install or change workspace dependencies without authorization.

```bash
pnpm start:en
pnpm typecheck
DOCUSAURUS_NO_PERSISTENT_CACHE=1 pnpm build
```

Output is written to `build/` and `build/zh/`. Disabling persistent compilation caches avoids Webpack cache writes to `node_modules`.

## Publication boundaries

Website framework changes are built locally or in CI, uploaded to a separate server staging directory, and applied with the news-directory protection in `scripts/news/apply-main-site.py`. Scheduled news updates fetch Feed and HTML resources on the server and generate independent runtime data outside the repository, with their own CDN refresh. They do not run Docusaurus or depend on a personal computer being online.

The repository publisher and local release skill install the news runtime, initialize the empty page, protect the news directory, and enable the ten-minute timer. The first production deployment completed on 2026-11-10 with source/CDN route checks passing. Configure NEWS_FEED_URL through the local release environment; see scripts/news/README.md for configuration and scripts/news/VALIDATION.md for deployment evidence and remaining checks.
