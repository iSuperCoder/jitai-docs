import { themes as prismThemes } from "prism-react-renderer";
import type { Config } from "@docusaurus/types";
import type * as Preset from "@docusaurus/preset-classic";

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

import { BRAND_COPY } from "./src/brand";

const config: Config = {
    title: "JitAI",
    tagline: BRAND_COPY.en.description,
    favicon: "https://jit-www.oss-accelerate.aliyuncs.com/logo/logo.svg",

    // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
    future: {
        v4: true, // Improve compatibility with the upcoming Docusaurus v4
        faster: {
            swcHtmlMinimizer: false, // SWC 的 JSON-LD 解析有 bug，退回到 Terser
        },
    },
    trailingSlash: false,
    // Set the production url of your site here
    url: "https://jit.pro",
    // Set the /<baseUrl>/ pathname under which your site is served
    // For GitHub pages deployment, it is often '/<projectName>/'
    baseUrl: process.env.DOCUSAURUS_BASE_URL || "/",
    // Algolia site verification and Google Tag Manager
    headTags: [
        {
            tagName: "meta",
            attributes: {
                name: "algolia-site-verification",
                content: "576057B2D3ECA7D8",
            },
        },
        {
            tagName: "meta",
            attributes: {
                name: "baidu-site-verification",
                content: "codeva-pmUJofMRgx",
            },
        },
        {
            tagName: "script",
            attributes: {},
            innerHTML: `(() => {
  const p = window.location.pathname;
  if (p !== '/' && p !== '') return;
  const preferred = window.localStorage && window.localStorage.getItem('jitai-preferred-language');
  if (preferred === 'en') return;
  window.location.replace('/zh' + window.location.search + window.location.hash);
})();`,
        },
        // 注意：Viewport 配置已移至 themeConfig.metadata
        // 在此处配置会被 Docusaurus 默认的 viewport 覆盖
        // 暂停加载 Google Tag Manager，避免第三方脚本影响页面加载速度。
        /* {
            tagName: "script",
            attributes: {},
            innerHTML: `(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-K39JND5X');`,
        }, */
    ],

    // GitHub pages deployment config.
    // If you aren't using GitHub pages, you don't need these.
    organizationName: "jitai-team", // Usually your GitHub org/user name.
    projectName: "jitai-docs", // Usually your repo name.

    onBrokenLinks: "throw",
    onBrokenAnchors: "throw",

    // Even if you don't use internationalization, you can use this field to set
    // useful metadata like html lang. For example, if your site is Chinese, you
    // may want to replace "en" with "zh-Hans".
    i18n: {
        defaultLocale: "en",
        locales: ["en", "zh"],
        localeConfigs: {
            en: {
                label: "English",
                direction: "ltr",
                htmlLang: "en",
            },
            zh: {
                label: "简体中文",
                direction: "ltr",
                htmlLang: "zh",
            },
        },
    },
    noIndex: false,

    presets: [
        [
            "classic",
            {
                // 旧中英文文档、历史版本与博客已下线；资讯由服务器独立数据目录承载。
                docs: false,
                blog: false,
                theme: {
                    customCss: [
                        "./src/css/variables.css",
                        "./src/css/custom.css",
                    ],
                },
                sitemap: false, // 禁用自动生成 sitemap
            } satisfies Preset.Options,
        ],
    ],

    plugins: [
        function svgrReactQueryPlugin() {
            return {
                name: "svgr-react-query-plugin",
                configureWebpack() {
                    return {
                        mergeStrategy: {
                            "module.rules": "prepend",
                        },
                        ignoreWarnings: [
                            {
                                module: /vscode-languageserver-types/,
                                message: /Critical dependency/,
                            },
                        ],
                        module: {
                            rules: [
                                {
                                    test: /\.svg$/i,
                                    resourceQuery: /react/,
                                    use: [
                                        {
                                            loader: (require as any).resolve(
                                                "@svgr/webpack",
                                            ),
                                            options: {
                                                svgo: true,
                                                titleProp: true,
                                            },
                                        },
                                    ],
                                },
                            ],
                        },
                    };
                },
            };
        },
    ],

    // 添加客户端模块
    clientModules: [
        "./src/clientModules/utmTracker.js",
        "./src/clientModules/fixLocaleLinks.js",
    ],
    markdown: {
        mermaid: true,
        mdx1Compat: {
            comments: true,
            admonitions: true,
            headingIds: true,
        },
        hooks: {
            onBrokenMarkdownLinks: "throw",
        },
    },
    themes: ["@docusaurus/theme-mermaid"],
    themeConfig: {
        // 覆盖默认的 viewport meta 标签，禁止移动端缩放
        metadata: [
            {
                name: "viewport",
                content:
                    "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no",
            },
        ],
        // Replace with your project's social card
        image: "https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_dark.svg",
        colorMode: {
            defaultMode: "light",
            disableSwitch: true, // 暂时禁用主题切换， 因为 深色模式下 logo 要调整，以及官网要强制为浅色模式
            // respectPrefersColorScheme: false,
        },
        navbar: {
            logo: {
                alt: "Jit Logo",
                src: "https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_title.svg",
                srcDark:
                    "https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_title_dark.svg", // logo 大小待调整
            },
            items: [
                {
                    label: "Home",
                    to: "/",
                    position: "left",
                    activeBaseRegex: "^/$",
                },
                {
                    label: "Agent Products",
                    to: "/agent-products",
                    position: "left",
                },
                {
                    label: "Industry Agents",
                    to: "/industry-agents",
                    position: "left",
                },
                // 主题布局仍用于 404 等页面，只保留当前有效入口。
                {
                    label: "Whitepaper",
                    to: "/whitepaper",
                    position: "left",
                },
                {
                    label: "Forum",
                    href: "https://forum.jit.pro",
                    position: "left",
                },
                {
                    label: "Contact Us",
                    to: "/contact",
                    position: "left",
                },
                {
                    type: "localeDropdown",
                    position: "right",
                },
            ],
        },
        footer: {
            style: "dark",
            links: [
                {
                    title: "Products",
                    items: [
                        {
                            label: "Home",
                            to: "/",
                        },
                        {
                            label: "Download",
                            to: "/download",
                        },
                        {
                            label: "Try Online",
                            to: "https://demo.jit.pro/wanyun/AdminApp",
                        },
                    ],
                },
                {
                    title: "Technology",
                    items: [
                        { label: "Whitepaper", to: "/whitepaper" },
                        { label: "Solutions", to: "/solutions" },
                    ],
                },
                {
                    title: "Social",
                    items: [
                        {
                            label: "Forum",
                            href: "https://forum.jit.pro",
                        },
                        {
                            label: "GitHub",
                            href: "https://github.com/jitai-team",
                        },
                        {
                            label: "X (Twitter)",
                            href: "https://x.com/JitAi2017",
                        },
                        {
                            label: "Youtube",
                            href: "https://www.youtube.com/channel/UClvTNJPvBhek3aFuDy87RJQ",
                        },
                        {
                            label: "Instagram",
                            href: "https://www.instagram.com/jitai_2017",
                        },
                    ],
                },
            ],
            logo: {
                alt: "Next-generation AI application development technology system",
                src: "https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_title_dark.svg",
                href: "https://jit.pro",
                width: 340,
                height: 100,
            },
            copyright: `Copyright © ${new Date().getFullYear()} , jitai platform LLC.`,
        },
        prism: {
            theme: prismThemes.github,
            darkTheme: prismThemes.dracula,
        },
        mermaid: {
            theme: {
                light: "neutral",
                dark: "dark",
            },
        },
        // 原 Algolia 搜索面向已删除的文档与博客，停止生成旧搜索页。
    } satisfies Preset.ThemeConfig,
};

export default config;
