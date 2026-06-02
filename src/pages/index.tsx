import React from "react";
import Link from "@docusaurus/Link";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import {
    ArrowRight,
    BadgeCheck,
    Code2,
    GitBranch,
    HardDrive,
    Layers3,
    LockKeyhole,
    MonitorCog,
    Server,
    Sparkles,
} from "lucide-react";
import PageLayout from "@site/src/components/PageLayout";
import styles from "@site/src/pages/index.module.css";

const CONTENT = {
    zh: {
        eyebrow: "Enterprise AI Agent Platform",
        titlePrefix: "构建真正能",
        titleHighlight: "执行业务",
        titleSuffix: "的企业 AI 智能体",
        description:
            "JitAI 让智能体不只回答问题，而是能在安全权限内理解意图、拆解任务、调用系统、处理数据并协同用户完成真实业务。",
        primaryCta: "开始使用",
        secondaryCta: "了解智能体能力",
        outcomes: [
            {
                value: "自主执行",
                label:
                    "从意图识别、任务规划到工具调用，智能体可按业务规则完成指令。",
            },
            {
                value: "接入业务",
                label:
                    "连接服务函数、数据模型、知识库、文件、用户和前端页面，让 AI 进入真实流程。",
            },
            {
                value: "企业可控",
                label:
                    "权限、安全、模型、记忆和部署策略统一配置，保证智能体用不越界。",
            },
        ],
        agentCapabilities: {
            label: "AGENT CAPABILITIES",
            title: "AI 不只回答，它能按权限完成任务",
            subtitle:
                "把复杂能力收在可配置边界里，先开箱使用，再按业务逐步增强。",
            items: [
                {
                    number: "01",
                    title: "会判断，也会行动",
                    description:
                        "自主识别用户意图，判断是否需要查询知识、调用工具、操作系统或请求人工确认，再按业务规则推进任务。",
                },
                {
                    number: "02",
                    title: "能处理长程复杂任务",
                    description:
                        "将复杂目标拆成多个步骤和子任务，持续跟踪上下文、状态、阶段结果与关键记忆，避免任务越跑越散。",
                },
                {
                    number: "03",
                    title: "能驱动企业子系统",
                    description:
                        "可调用 Skills、服务函数、模型、知识库、文件空间、数据库、外部网络、用户和前端 UI，让 AI 真正进入业务执行链路。",
                },
                {
                    number: "04",
                    title: "能力边界可配置",
                    description:
                        "支持自动选择和人工指定智能体可用的工具、对象、数据、模型和交互入口，把灵活性放在可控范围内。",
                },
            ],
        },
        platform: {
            label: "PLATFORM EXPERIENCE",
            title: "AI 开发、传统 IT 和治理，在一个平台里完成",
            subtitle:
                "JitAI 把智能体模块和传统 IT 功能模块放在同一套应用体系中，减少重复建设和跨系统治理成本。",
            items: [
                {
                    icon: Code2,
                    title: "自然语言开发",
                    description:
                        "开发者描述需求，开发智能体自动创建和调整智能体、页面、数据模型、服务函数等应用模块。",
                },
                {
                    icon: MonitorCog,
                    title: "可视化治理",
                    description:
                        "模型、工具、知识库、权限和运行参数可在 GUI 中统一管理，不必每次都消耗 tokens 重新开发。",
                },
                {
                    icon: GitBranch,
                    title: "源码白盒",
                    description:
                        "应用所有模块都是源码级资产，既支持 AI coding，也支持 human coding，复杂逻辑可以继续深度扩展。",
                },
                {
                    icon: Layers3,
                    title: "开箱即用，逐步深入",
                    description:
                        "一键安装、模板启动、热更新交付。先让第一个智能体跑起来，再按业务深度配置和扩展。",
                },
            ],
        },
        assurance: {
            label: "ENTERPRISE READY",
            title: "企业级能力，默认收敛在可控边界内",
            subtitle:
                "部署、安全、权限和模型选择不需要另建一套体系，智能体与业务应用共用企业治理底座。",
            cards: [
                {
                    title: "安全与隐私",
                    description: "自动隐私保护，数据可留在企业内网。",
                    icon: LockKeyhole,
                    items: [
                        "支持私有化部署",
                        "可接入公有 MaaS 或私有化模型",
                        "支持备选模型和专用多模态模型",
                    ],
                },
                {
                    title: "独立权限边界",
                    description: "系统功能层权限独立于智能体运行逻辑。",
                    icon: BadgeCheck,
                    items: [
                        "角色、组织、用户权限统一控制",
                        "工具和函数调用可按权限限制",
                        "防止智能体越权访问数据和操作",
                    ],
                },
                {
                    title: "部署与组织能力",
                    description: "从个人试用到企业生产环境都能平滑推进。",
                    icon: Server,
                    items: [
                        "一键安装、开箱即用、热更新",
                        "跨平台、分布式、多端访问",
                        "多组织、多用户、多登录方式",
                    ],
                },
            ],
        },
        architecture: {
            label: "ARCHITECTURE",
            title: "快速开始，也能长期扩展",
            subtitle:
                "JitAI 把业务应用、开发治理和运行底座放在同一技术体系里，既适合快速落地，也支持源码级持续演进。",
            layers: [
                {
                    number: "01",
                    title: "BizApp",
                    subtitle: "业务应用层 · 智能体与业务模块",
                    items: [
                        ["AI 智能体", "自主执行任务"],
                        ["IT 功能模块", "传统业务能力"],
                        ["页面与 UI", "多端交互入口"],
                        ["数据与知识", "模型/文件/知识库"],
                        ["服务函数", "可调用业务动作"],
                    ],
                },
                {
                    number: "02",
                    title: "JitIDE",
                    subtitle: "开发治理层 · 自然语言与可视化配置",
                    items: [
                        ["AI 开发", "自然语言构建"],
                        ["可视化治理", "统一配置和微调"],
                        ["源码管理", "AI/Human coding"],
                        ["模型配置", "多模型策略"],
                    ],
                },
                {
                    number: "03",
                    title: "JitNode",
                    subtitle: "运行时层 · 私有化与分布式运行",
                    items: [
                        ["私有化部署", "数据自主可控"],
                        ["热更新", "平台和 App 演进"],
                        ["权限控制", "系统级边界"],
                        ["分布式运行", "跨平台扩展"],
                    ],
                },
            ],
        },
        cta: {
            title: "让第一个智能体先跑起来",
            subtitle:
                "从一个具体岗位或流程开始，用 JitAI 构建可执行、可治理、可持续扩展的企业 AI 智能体。",
            button: "联系我们",
        },
    },
    en: {
        eyebrow: "Enterprise AI Agent Platform",
        titlePrefix: "Build enterprise AI agents that ",
        titleHighlight: "execute real work",
        titleSuffix: "",
        description:
            "JitAI helps agents move beyond chat. They can understand intent, break down tasks, call systems, process data, and collaborate with users inside governed enterprise boundaries.",
        primaryCta: "Get Started",
        secondaryCta: "Explore Capabilities",
        outcomes: [
            {
                value: "Autonomous",
                label:
                    "Agents can identify intent, plan tasks, and call tools according to business rules.",
            },
            {
                value: "Connected",
                label:
                    "Connect services, data models, knowledge bases, files, users, and frontend UI to real workflows.",
            },
            {
                value: "Governed",
                label:
                    "Permissions, security, models, memory, and deployment policies are configured in one place.",
            },
        ],
        agentCapabilities: {
            label: "AGENT CAPABILITIES",
            title: "AI does not just answer. It completes governed work.",
            subtitle:
                "JitAI keeps powerful agent capabilities inside configurable boundaries, so teams can start quickly and deepen capabilities over time.",
            items: [
                {
                    number: "01",
                    title: "Decide and act",
                    description:
                        "Agents infer user intent, decide whether to retrieve knowledge, call tools, operate systems, or request human confirmation, then move the task forward.",
                },
                {
                    number: "02",
                    title: "Run long tasks",
                    description:
                        "Complex goals can be decomposed into steps and subtasks while context, state, stage outputs, and working memory stay organized.",
                },
                {
                    number: "03",
                    title: "Drive enterprise subsystems",
                    description:
                        "Agents can call skills, services, functions, models, knowledge bases, file spaces, databases, networks, users, and frontend UI.",
                },
                {
                    number: "04",
                    title: "Configure every boundary",
                    description:
                        "Teams can let agents choose available capabilities automatically or manually define which tools, objects, data, models, and channels they may use.",
                },
            ],
        },
        platform: {
            label: "PLATFORM EXPERIENCE",
            title: "AI development, traditional IT, and governance in one platform",
            subtitle:
                "JitAI puts agent modules and traditional IT modules into the same application system, reducing duplicated engineering and cross-system governance work.",
            items: [
                {
                    icon: Code2,
                    title: "Natural-language development",
                    description:
                        "Developers describe requirements, and development agents create or adjust agents, pages, data models, service functions, and other modules.",
                },
                {
                    icon: MonitorCog,
                    title: "Visual governance",
                    description:
                        "Models, tools, knowledge bases, permissions, and runtime settings can be managed in GUI instead of being rebuilt through tokens every time.",
                },
                {
                    icon: GitBranch,
                    title: "Source-visible modules",
                    description:
                        "Every software module is a source-level asset, supporting both AI coding and human coding for deep business customization.",
                },
                {
                    icon: Layers3,
                    title: "Ready now, extensible later",
                    description:
                        "One-click installation, templates, and hot updates help teams start fast, then expand through configuration and code when needed.",
                },
            ],
        },
        assurance: {
            label: "ENTERPRISE READY",
            title: "Enterprise capability, kept inside controlled boundaries",
            subtitle:
                "Deployment, security, permissions, and model strategy are part of the same governance foundation shared by agents and business applications.",
            cards: [
                {
                    title: "Security and privacy",
                    description: "Automatic privacy protection with data kept under enterprise control.",
                    icon: LockKeyhole,
                    items: [
                        "Private deployment supported",
                        "Use public MaaS or private models",
                        "Fallback and dedicated multimodal models",
                    ],
                },
                {
                    title: "Independent permission boundary",
                    description: "System-level permissions stay separate from agent reasoning logic.",
                    icon: BadgeCheck,
                    items: [
                        "Unified roles, organizations, and user access",
                        "Tool and function calls can be restricted",
                        "Prevents agents from crossing data boundaries",
                    ],
                },
                {
                    title: "Deployment and organization",
                    description: "Move from individual trials to production environments smoothly.",
                    icon: Server,
                    items: [
                        "One-click install, ready to use, hot updates",
                        "Cross-platform, distributed, multi-channel access",
                        "Multi-org, multi-user, multi-login support",
                    ],
                },
            ],
        },
        architecture: {
            label: "ARCHITECTURE",
            title: "Start fast, then extend for the long term",
            subtitle:
                "JitAI brings business applications, development governance, and runtime infrastructure into one technical system for both quick delivery and source-level evolution.",
            layers: [
                {
                    number: "01",
                    title: "BizApp",
                    subtitle: "Application layer · agents and business modules",
                    items: [
                        ["AI Agents", "Autonomous task execution"],
                        ["IT Modules", "Traditional business capabilities"],
                        ["Pages and UI", "Multi-channel interaction"],
                        ["Data and Knowledge", "Models/files/knowledge bases"],
                        ["Service Functions", "Callable business actions"],
                    ],
                },
                {
                    number: "02",
                    title: "JitIDE",
                    subtitle: "Development governance · natural language and visual configuration",
                    items: [
                        ["AI Development", "Build with natural language"],
                        ["Visual Governance", "Configure and tune centrally"],
                        ["Source Management", "AI/Human coding"],
                        ["Model Strategy", "Multi-model configuration"],
                    ],
                },
                {
                    number: "03",
                    title: "JitNode",
                    subtitle: "Runtime layer · private and distributed execution",
                    items: [
                        ["Private Deployment", "Enterprise data control"],
                        ["Hot Updates", "Platform and app evolution"],
                        ["Access Control", "System-level boundaries"],
                        ["Distributed Runtime", "Cross-platform scaling"],
                    ],
                },
            ],
        },
        cta: {
            title: "Get the first agent running",
            subtitle:
                "Start from one role or workflow, then use JitAI to build executable, governable, and extensible enterprise AI agents.",
            button: "Contact Us",
        },
    },
};

const getArchitectureIcon = (title: string) => {
    if (title === "BizApp") return Layers3;
    if (title === "JitIDE") return Code2;
    if (title === "JitNode") return HardDrive;
    return Layers3;
};

const HomePage: React.FC = () => {
    const { i18n } = useDocusaurusContext();
    const isZh = i18n.currentLocale === "zh";
    const content = isZh ? CONTENT.zh : CONTENT.en;

    return (
        <PageLayout pageId="index" containerClassName={styles.container}>
            <section className={styles.homeHero}>
                <div className={styles.sectionContent}>
                    <div className={styles.heroLabel}>{content.eyebrow}</div>
                    <h1 className={styles.homeHeroTitle}>
                        {content.titlePrefix}
                        <span>{content.titleHighlight}</span>
                        {content.titleSuffix}
                    </h1>
                    <p className={styles.homeHeroDescription}>
                        {content.description}
                    </p>
                    <div className={styles.homeHeroButtons}>
                        <Link
                            to={isZh ? "/zh/contact" : "/contact"}
                            className={styles.homePrimaryButton}
                        >
                            {content.primaryCta}
                            <ArrowRight size={20} />
                        </Link>
                        <a href="#agent-capabilities" className={styles.homeSecondaryButton}>
                            {content.secondaryCta}
                            <ArrowRight size={20} />
                        </a>
                    </div>
                    <div className={styles.outcomeGrid}>
                        {content.outcomes.map((outcome) => (
                            <article className={styles.outcomeCard} key={outcome.value}>
                                <h2>{outcome.value}</h2>
                                <p>{outcome.label}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section id="agent-capabilities" className={styles.homeSection}>
                <div className={styles.sectionContent}>
                    <SectionHeader
                        label={content.agentCapabilities.label}
                        title={content.agentCapabilities.title}
                        subtitle={content.agentCapabilities.subtitle}
                    />
                    <div className={styles.capabilityGrid}>
                        {content.agentCapabilities.items.map((item) => (
                            <article className={styles.homeCard} key={item.title}>
                                <div className={styles.featureNumber}>
                                    {item.number}
                                </div>
                                <h3>{item.title}</h3>
                                <p>{item.description}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section id="platform" className={`${styles.homeSection} ${styles.sectionSoft}`}>
                <div className={styles.sectionContent}>
                    <SectionHeader
                        label={content.platform.label}
                        title={content.platform.title}
                        subtitle={content.platform.subtitle}
                    />
                    <div className={styles.capabilityGrid}>
                        {content.platform.items.map((item) => {
                            const Icon = item.icon;
                            return (
                                <article className={styles.homeCard} key={item.title}>
                                    <div className={styles.cardIcon}>
                                        <Icon size={28} />
                                    </div>
                                    <h3>{item.title}</h3>
                                    <p>{item.description}</p>
                                </article>
                            );
                        })}
                    </div>
                </div>
            </section>

            <section id="enterprise-ready" className={styles.homeSection}>
                <div className={styles.sectionContent}>
                    <SectionHeader
                        label={content.assurance.label}
                        title={content.assurance.title}
                        subtitle={content.assurance.subtitle}
                    />
                    <div className={styles.deploymentGrid}>
                        {content.assurance.cards.map((card) => {
                            const Icon = card.icon;
                            return (
                                <article className={styles.deploymentCard} key={card.title}>
                                    <div className={styles.deploymentIcon}>
                                        <Icon size={28} />
                                    </div>
                                    <h3>{card.title}</h3>
                                    <p>{card.description}</p>
                                    <ul>
                                        {card.items.map((item) => (
                                            <li key={item}>
                                                <BadgeCheck size={18} />
                                                <span>{item}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </article>
                            );
                        })}
                    </div>
                </div>
            </section>

            <section
                id="architecture"
                className={`${styles.homeSection} ${styles.sectionSoft}`}
            >
                <div className={styles.sectionContent}>
                    <SectionHeader
                        label={content.architecture.label}
                        title={content.architecture.title}
                        subtitle={content.architecture.subtitle}
                    />
                    <div className={styles.architectureStack}>
                        {content.architecture.layers.map((layer) => (
                            <ArchitectureLayer key={layer.title} layer={layer} />
                        ))}
                    </div>
                </div>
            </section>

            <section id="contact" className={styles.ctaSection}>
                <div className={styles.sectionContent}>
                    <div className={styles.ctaPanel}>
                        <Sparkles size={28} />
                        <h2>{content.cta.title}</h2>
                        <p>{content.cta.subtitle}</p>
                        <Link
                            to={isZh ? "/zh/contact" : "/contact"}
                            className={styles.homePrimaryButton}
                        >
                            {content.cta.button}
                            <ArrowRight size={20} />
                        </Link>
                    </div>
                </div>
            </section>
        </PageLayout>
    );
};

interface SectionHeaderProps {
    label: string;
    title: string;
    subtitle: string;
}

const SectionHeader: React.FC<SectionHeaderProps> = ({ label, title, subtitle }) => (
    <div className={styles.homeSectionHeader}>
        <div className={styles.sectionLabel}>{label}</div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
    </div>
);

const ArchitectureLayer: React.FC<{
    layer: {
        number: string;
        title: string;
        subtitle: string;
        items: string[][];
    };
}> = ({ layer }) => {
    const Icon = getArchitectureIcon(layer.title);

    return (
        <article className={styles.architectureLayer}>
            <div className={styles.layerHeader}>
                <div className={styles.layerNumber}>{layer.number}</div>
                <Icon className={styles.layerIcon} size={24} />
                <div>
                    <h3>{layer.title}</h3>
                    <p>{layer.subtitle}</p>
                </div>
            </div>
            <ArchitectureItems items={layer.items} />
        </article>
    );
};

const ArchitectureItems: React.FC<{ items: string[][] }> = ({ items }) => (
    <div className={styles.architectureItems}>
        {items.map(([name, desc]) => (
            <div className={styles.architectureItem} key={name}>
                <strong>{name}</strong>
                <span>{desc}</span>
            </div>
        ))}
    </div>
);

export default HomePage;
