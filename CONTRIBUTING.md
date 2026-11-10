# Contributing to the website

Read the [README](README.md) and [maintenance notes](WEBSITE_MIGRATION.md) before editing.

- Keep English and Chinese pages in sync. Routes live in `src/pages/`; shared website UI and content live in `src/components/MarketingSite/`.
- Preserve active download resources, contact forms, and legal content.
- Legacy docs/blog and versioned content have been retired. Do not add content to those directories.
- News is authored in the content application. This repository holds only the generator and templates in `scripts/news/`; runtime pages, caches, publication state, and secrets stay outside the repository.
- Follow workspace AGENTS.md instructions. Do not install dependencies, modify node_modules, or publish without authorization.
- Validate with `pnpm typecheck`, `DOCUSAURUS_NO_PERSISTENT_CACHE=1 pnpm build`, and `git diff --check`. Check both locales and internal links. News test commands are in its README.
- For UI changes, check desktop/mobile and light/dark themes. Do not submit test customer leads or execute installer commands displayed on the site.
- Explain the problem, change, and validation when submitting work. Deployment requires separate authorization and must protect the independent news data directory.
