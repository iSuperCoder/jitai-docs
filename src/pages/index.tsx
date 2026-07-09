import React from "react";
import Head from "@docusaurus/Head";
import Link from "@docusaurus/Link";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import OfficialHeader from "@site/src/components/OfficialHeader";
import styles from "./index.module.css";

const PLATFORM_NAME = "企业级智能体开发运行一体化平台";
const TAGLINE = "从 Demo 到生产，重塑企业AI生产力";
const COPYRIGHT_YEAR = new Date().getFullYear();

const getDownloadUrl = (locale: string) =>
    locale === "zh" ? "/zh/download" : "/download";

const getFooterNavItems = (locale: string) =>
    locale === "zh"
        ? [
              { label: "首页", href: "#" },
              { label: "能力", href: "#capabilities" },
              { label: "优势", href: "#delivery" },
              { label: "价值", href: "#value" },
              { label: "联系我们", href: "/zh/contact" },
          ]
        : [
              { label: "Home", href: "#" },
              { label: "Capabilities", href: "#capabilities" },
              { label: "Advantages", href: "#delivery" },
              { label: "Value", href: "#value" },
              { label: "Contact", href: "/contact" },
          ];

const HERO_TAGS = [
    "企业级",
    "BS 多用户协同",
    "私有化部署",
    "对话式开发",
    "全维度自定义",
    "开发运行一体化",
];

const CAPABILITIES = [
    {
        title: "AI 对话式无门槛开发",
        desc: "内置开发智能体，自然语言替代编码。业务人员即可完成业务要素的改造、智能体的搭建和功能模块的开发。",
    },
    {
        title: "全要素自定义",
        desc: "LLM、Skills、Functions、数据模型、UI 界面——五大核心业务要素全部支持自主配置与迭代，平台完全适配企业。",
    },
    {
        title: "双模同源开发",
        desc: "AI 智能体与传统业务系统原生统一，共享同一套函数、数据模型和数据库。不是拼接，是底层一体。",
    },
    {
        title: "开发即运行",
        desc: "改造完成的要素即时生效，无需部署流程。从需求到交付从「周级」压缩到「分钟级」，迭代效率提升 30 倍。",
    },
    {
        title: "企业级协同架构",
        desc: "BS 架构，多部门多角色权限矩阵，支持千人级团队协作。业务要素可跨部门共享复用，沉淀为组织资产。",
    },
    {
        title: "私有化安全部署",
        desc: "全部数据和业务资产部署在企业自有服务器，物理隔离。满足金融、政务等行业的合规要求。",
    },
];

const DELIVERY_STATS = [
    { value: "90%+", label: "人力成本降低" },
    { value: "小时级", label: "系统上线周期" },
    { value: "30x", label: "迭代效率提升" },
];

const VALUE_SECTIONS = [
    {
        eyebrow: "价值一",
        title: "专属业务智能体工作流",
        subtitle: "低成本、高效率打造企业自己的 Agentic 工作流",
        dark: true,
        visual: "workflow",
        points: [
            {
                title: "7×24 小时数字员工",
                desc: "让 AI 不知疲倦地深度参与核心业务流程，执行重复性、规则性任务，确保业务运转的连续性与高效性。",
            },
            {
                title: "重塑业务协作模式",
                desc: "打破部门墙与信息孤岛，实现跨系统、跨岗位的自动化协同与决策，优化甚至颠覆传统业务流程。",
            },
            {
                title: "直接驱动业务增长",
                desc: "提升客户转化率、降低运营成本、缩短服务响应时间——不是辅助工具，是直接创造业务价值的 AI Worker。",
            },
        ],
    },
    {
        eyebrow: "价值二",
        title: "一个平台，替代 N 套系统",
        subtitle: "告别碎片化，实现一体化智能基座",
        dark: false,
        visual: "platform",
        reverse: true,
        points: [
            {
                title: "统一技术底座",
                desc: "一站式承载业务开发、智能体定制、自动化编排和 AI 员工落地，打破数据孤岛，消除重复建设。",
            },
            {
                title: "全链路降本提效",
                desc: "直接削减多系统采购与维护成本，统一交互体验降低学习成本，消除信息壁垒减少管理内耗。",
            },
            {
                title: "可持续演进",
                desc: "不再被各厂商版本升级牵着走。统一底座让企业按自己的节奏渐进式智能化升级，而非推倒重来。",
            },
        ],
    },
    {
        eyebrow: "价值三",
        title: "自主可控的 AI 生产力",
        subtitle: "拒绝技术锁定，构建属于企业自己的 AI 核心能力",
        dark: true,
        visual: "private",
        points: [
            {
                title: "独立技术底座",
                desc: "摆脱外部厂商依赖与黑盒限制。核心代码、数据、模型全部自主掌控，按自己的业务节奏持续演进。",
            },
            {
                title: "全栈能力内化",
                desc: "深度掌握业务规则、逻辑和代码，可自主优化升级。不依赖厂商排期，想改就改。",
            },
            {
                title: "沉淀组织资产",
                desc: "打造私有化的 AI Worker 矩阵，每一个智能体都是可复用、可传承的企业核心资产。",
            },
        ],
    },
];

const handleTopLink = (event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
};

const HomePage: React.FC = () => {
    return (
        <>
            <Head
                title="JitAI — 企业级智能体开发运行一体化平台"
            >
                <meta
                    name="description"
                    content="JitAI 是企业级 BS 架构、多用户协同、支持全私有化部署的智能体开发运行一体化平台。从 Demo 到生产，重塑企业AI生产力。"
                />
                <meta
                    name="keywords"
                    content="JitAI,企业智能体,AI平台,智能体开发,私有化部署,Agentic Company,企业AI"
                />
                <meta
                    property="og:title"
                    content="JitAI — 企业级智能体开发运行一体化平台"
                />
                <meta
                    property="og:description"
                    content="JitAI 是企业级 BS 架构、多用户协同、支持全私有化部署的智能体开发运行一体化平台。从 Demo 到生产，重塑企业AI生产力。"
                />
            </Head>
            <div className={`${styles.homePage} custom-page`}>
                <OfficialHeader />
                <main className={styles.main}>
                    <HeroSection />
                    <ProblemSection />
                    <CapabilitiesSection />
                    <DeliverySection />
                    <ValueSection />
                    <ContactSection />
                </main>
                <HomeFooter />
            </div>
        </>
    );
};

const HeroSection: React.FC = () => (
    <section className={`${styles.section} ${styles.hero}`}>
        <div className={styles.heroGlow} aria-hidden="true">
            <div className={styles.glowLarge} />
            <div className={styles.glowSmall} />
        </div>
        <div className={styles.shell}>
            <div className={styles.heroContent}>
                <p className={styles.heroEyebrow}>
                    JitAI 企业级智能体开发运行一体化平台
                </p>
                <h1>
                    用 AI 重塑生产力
                    <br />
                    <span>打造 Agentic 企业系统</span>
                </h1>
                <p className={styles.heroLead}>
                    告别桌面级玩具，构建真正属于你企业的 AI 数字员工。
                </p>
                <div className={styles.tagList}>
                    {HERO_TAGS.map((tag) => (
                        <span key={tag}>{tag}</span>
                    ))}
                </div>
                <div className={styles.heroActions}>
                    <DownloadButton size="md" />
                </div>
            </div>
        </div>
        <div className={styles.scrollCue} aria-hidden="true">
            <ArrowDownIcon />
        </div>
    </section>
);

const ProblemSection: React.FC = () => (
    <section className={`${styles.section} ${styles.subtleSection}`}>
        <div className={styles.shell}>
            <div className={styles.centerBlock}>
                <Badge>核心问题</Badge>
                <h2>为什么你的 AI 总是落不了地？</h2>
                <p className={styles.sectionLead}>AI 不认识你的业务流程、规则和数据。</p>
                <div className={styles.dividerTitle}>
                    <span />
                    <strong>JITAI</strong>
                    <span />
                </div>
                <p className={styles.problemStatement}>
                    JitAI 平台，把业务要素改造为 AI 可感知和调用的元素，
                    <br />
                    并「装入」AI 智能体，使之真正驱动你的业务。
                </p>
            </div>
            <div className={styles.transformDiagram}>
                <ElementGroup
                    label="你的业务要素"
                    items={["业务规则", "审批流程", "行业知识", "客户数据"]}
                    muted
                />
                <div className={styles.transformBridge}>
                    <span />
                    <div>
                        <strong>JitAI 改造</strong>
                        <small>内置开发智能体</small>
                    </div>
                    <span />
                </div>
                <ElementGroup
                    label="AI 可调用的元素"
                    items={["LLM 模型", "Skills 技能", "Functions 函数", "数据 Models", "UI Cards"]}
                    accent
                />
            </div>
        </div>
    </section>
);

const CapabilitiesSection: React.FC = () => (
    <section
        id="capabilities"
        className={`${styles.section} ${styles.darkSection}`}
    >
        <div className={styles.shell}>
            <SectionHeader
                eyebrow="核心能力"
                title={
                    <>
                        一个平台搞定业务要素的
                        <br />
                        <span>AI 化改造、接入与运行</span>
                    </>
                }
                desc="从对话式开发、到自动部署、到最终运行，JitAI 覆盖业务 AI 化改造到 AI 智能体真实驱动业务的全链路。"
            />
            <div className={styles.capabilityGrid}>
                {CAPABILITIES.map((item) => (
                    <article className={styles.capabilityCard} key={item.title}>
                        <h3>{item.title}</h3>
                        <p>{item.desc}</p>
                    </article>
                ))}
            </div>
        </div>
    </section>
);

const DeliverySection: React.FC = () => (
    <section
        id="delivery"
        className={`${styles.section} ${styles.subtleSection}`}
    >
        <div className={styles.shell}>
            <SectionHeader
                eyebrow="交付能力"
                title="小时级交付，生产级质量"
                desc="基于自研 SDD 规范化体系，支持一次性输出可直接上线的完整业务系统。"
                accentOpacity="strong"
            />
            <div className={styles.statsGrid}>
                {DELIVERY_STATS.map((stat) => (
                    <div key={stat.label}>
                        <strong>{stat.value}</strong>
                        <span>{stat.label}</span>
                    </div>
                ))}
            </div>
            <p className={styles.deliveryLine}>
                能分钟级生成你企业专属的：营销智能体 · 客服智能体 · 数据分析 ·
                审批流系统 · CRM/ERP · 协同办公 OA
            </p>
        </div>
    </section>
);

const ValueSection: React.FC = () => (
    <section id="value">
        {VALUE_SECTIONS.map((section) => (
            <ValuePanel key={section.title} section={section} />
        ))}
    </section>
);

const ValuePanel: React.FC<{
    section: (typeof VALUE_SECTIONS)[number];
}> = ({ section }) => (
    <section
        className={`${styles.section} ${styles.valuePanel} ${
            section.dark ? styles.darkSection : styles.subtleSection
        }`}
    >
        <div className={styles.shell}>
            <div
                className={`${styles.valueGrid} ${
                    section.reverse ? styles.valueGridReverse : ""
                }`}
            >
                <div className={styles.valueCopy}>
                    <span className={styles.valueEyebrow}>{section.eyebrow}</span>
                    <h2>{section.title}</h2>
                    <p className={styles.valueSubtitle}>{section.subtitle}</p>
                    <div className={styles.valuePoints}>
                        {section.points.map((point, index) => (
                            <div className={styles.valuePoint} key={point.title}>
                                <span>{String(index + 1).padStart(2, "0")}</span>
                                <div>
                                    <h3>{point.title}</h3>
                                    <p>{point.desc}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
                <ValueVisual type={section.visual} />
            </div>
        </div>
    </section>
);

const ValueVisual: React.FC<{ type: string }> = ({ type }) => {
    if (type === "platform") {
        return (
            <div className={styles.valueVisual}>
                <div className={styles.visualCard}>
                    <div className={styles.systemTags}>
                        {["CRM", "ERP", "OA", "BI", "AI"].map((item) => (
                            <span key={item}>{item}</span>
                        ))}
                    </div>
                    <strong className={styles.visualArrow}>→</strong>
                    <div className={styles.visualLogo}>JitAI</div>
                    <p>
                        多系统堆砌
                        <br />→ 一体化基座
                    </p>
                </div>
            </div>
        );
    }

    if (type === "private") {
        return (
            <div className={styles.valueVisual}>
                <div className={styles.visualCard}>
                    <strong className={styles.lockMark}>🔒</strong>
                    <h3>完全私有化</h3>
                    <p>
                        数据不出域
                        <br />
                        资产不外流
                        <br />
                        能力不锁定
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className={styles.valueVisual}>
            <div className={styles.visualCard}>
                <strong className={styles.aiMark}>AI</strong>
                <h3>Agentic Workflow</h3>
                <p>
                    从流程自动化
                    <br />
                    到价值创造
                </p>
            </div>
        </div>
    );
};

const ContactSection: React.FC = () => (
    <section id="contact" className={`${styles.section} ${styles.contactSection}`}>
        <div className={styles.shell}>
            <div className={styles.contactBlock}>
                <h2>准备好构建属于你的 AI 数字员工了吗？</h2>
                <p>
                    预约专属演示，了解 JitAI 如何帮助企业落地 AI，转型为智能驱动型组织。
                </p>
                <DownloadButton size="lg" />
                <strong>JitAI，与您共创智能未来！</strong>
            </div>
        </div>
    </section>
);

const HomeFooter: React.FC = () => {
    const { i18n } = useDocusaurusContext();
    const navItems = getFooterNavItems(i18n.currentLocale);

    return (
        <footer className={styles.footer}>
            <div className={styles.shell}>
                <div className={styles.footerTop}>
                    <div className={styles.footerBrand}>
                        <span>JitAI · {PLATFORM_NAME}</span>
                        <p>{TAGLINE}</p>
                    </div>
                    <nav className={styles.footerLinks}>
                        {navItems.map((item) => (
                            <a
                                key={item.href}
                                href={item.href}
                                onClick={
                                    item.href === "#" ? handleTopLink : undefined
                                }
                            >
                                {item.label}
                            </a>
                        ))}
                    </nav>
                </div>
                <div className={styles.footerBottom}>
                    <span>© {COPYRIGHT_YEAR} JitAI. All rights reserved.</span>
                </div>
            </div>
        </footer>
    );
};

const DownloadButton: React.FC<{ size: "md" | "lg" }> = ({ size }) => {
    const { i18n } = useDocusaurusContext();

    return (
        <Link
            to={getDownloadUrl(i18n.currentLocale)}
            className={`${styles.downloadButton} ${
                size === "lg" ? styles.downloadButtonLarge : ""
            }`}
        >
            下载 JitAI 平台
            <ArrowRightIcon />
        </Link>
    );
};

const Badge: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div className={styles.badge}>
        <span />
        <strong>{children}</strong>
    </div>
);

const SectionHeader: React.FC<{
    eyebrow: string;
    title: React.ReactNode;
    desc: string;
    accentOpacity?: "soft" | "strong";
}> = ({ eyebrow, title, desc, accentOpacity = "soft" }) => (
    <div className={styles.sectionHeader}>
        <span
            className={`${styles.sectionEyebrow} ${
                accentOpacity === "strong" ? styles.sectionEyebrowStrong : ""
            }`}
        >
            {eyebrow}
        </span>
        <h2>{title}</h2>
        <p>{desc}</p>
    </div>
);

const ElementGroup: React.FC<{
    label: string;
    items: string[];
    muted?: boolean;
    accent?: boolean;
}> = ({ label, items, muted, accent }) => (
    <div className={styles.elementGroup}>
        <span className={accent ? styles.accentLabel : ""}>{label}</span>
        <div>
            {items.map((item) => (
                <strong
                    className={`${muted ? styles.mutedPill : ""} ${
                        accent ? styles.accentPill : ""
                    }`}
                    key={item}
                >
                    {item}
                </strong>
            ))}
        </div>
    </div>
);

const ArrowRightIcon: React.FC = () => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        fill="currentColor"
        viewBox="0 0 256 256"
        aria-hidden="true"
    >
        <path d="M221.66,133.66l-72,72a8,8,0,0,1-11.32-11.32L196.69,136H40a8,8,0,0,1,0-16H196.69L138.34,61.66a8,8,0,0,1,11.32-11.32l72,72A8,8,0,0,1,221.66,133.66Z" />
    </svg>
);

const ArrowDownIcon: React.FC = () => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        fill="currentColor"
        viewBox="0 0 256 256"
        aria-hidden="true"
    >
        <path d="M205.66,149.66l-72,72a8,8,0,0,1-11.32,0l-72-72a8,8,0,0,1,11.32-11.32L120,196.69V40a8,8,0,0,1,16,0V196.69l58.34-58.35a8,8,0,0,1,11.32,11.32Z" />
    </svg>
);

export default HomePage;
