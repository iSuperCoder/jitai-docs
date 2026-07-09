import React from "react";
import Head from "@docusaurus/Head";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import styles from "./styles.module.css";

type DetailCard = {
    title: string;
    desc: string;
};

type FeaturePanel = {
    mark: string;
    title: string;
    desc: string[];
};

type ComparisonRow = {
    dimension: string;
    legacy: string;
    jitai: string;
};

type DetailSection = {
    title: string;
    desc?: string;
    cards?: DetailCard[];
    panels?: FeaturePanel[];
    checks?: string[];
    comparison?: ComparisonRow[];
};

type CapabilityDetail = {
    title: string;
    eyebrow: string;
    subtitle: string;
    sections: DetailSection[];
};

const CAPABILITY_DETAILS: Record<string, CapabilityDetail> = {
    "agent-business": {
        eyebrow: "产品能力",
        title: "接入真实业务的智能体框架",
        subtitle:
            "能无限接入业务系统与数据要素的智能体框架，实现从感知、决策到执行的全链路贯通，让 AI 智能体真正真实执行业务。",
        sections: [
            {
                title: "从「执行通用任务」到「执行专属真实业务」",
                desc: "当前多数 AI 智能体只能执行写邮件、搜资料、翻译摘要等通用任务。JitAI 的框架突破了这一局限--通过深度接入企业专属的业务系统与数据要素，让智能体真正深入企业的实际业务流程，执行审批、派单、数据更新、客户服务等真实业务操作。",
                cards: [
                    {
                        title: "感知",
                        desc: "实时接入 CRM、ERP、数据库、知识库等多源业务数据，让 AI 对业务状态有全局感知。",
                    },
                    {
                        title: "决策",
                        desc: "基于业务规则、历史数据和 AI 推理，智能体自主分析并制定最优执行方案。",
                    },
                    {
                        title: "执行",
                        desc: "通过 API、函数调用等方式直接操作系统，完成审批、派单、数据更新等真实业务动作。",
                    },
                ],
            },
            {
                title: "高度集成与开放的智能体框架",
                desc: "框架的强大之处在于高度集成化与高度开放性两面一体--既是开箱即用的能力底座，又是无所不连的业务网关。",
                panels: [
                    {
                        mark: "合",
                        title: "高度集成化",
                        desc: [
                            "核心基础能力：内置记忆、文档处理、知识库、数据库、工具函数、技能系统、代码生成与执行、工具批处理等通用能力。",
                            "高级交互能力：支持基于 SSE 的前后端实时通信与双向交互，可扩展的 UI 交互消息卡片。",
                        ],
                    },
                    {
                        mark: "联",
                        title: "高度开放性",
                        desc: [
                            "全要素业务接入：无缝接入业务系统中的 LLM 大模型、Skills、Functions、Models、UI 组件、数据库、知识库 API、CLI 等所有元素。",
                            "灵活双模式配置：支持「自动模式」（智能体自动感知全部元素）和「自定义模式」（按需精细化配置）。",
                        ],
                    },
                ],
            },
            {
                title: "典型应用场景",
                checks: [
                    "营销智能体：接入广告平台、用户画像、触达系统，自动化获客与转化闭环，7x24 在线服务",
                    "业务管理系统：覆盖销售、运营、供应链，实现全链路数字化管控",
                    "CRM / ERP 核心：客户关系与资源计划一体化，驱动业务高效运转",
                    "协同办公 OA：跨部门流程自动化，信息实时同步与高效协作",
                ],
            },
        ],
    },
    "conversational-dev": {
        eyebrow: "核心能力",
        title: "无门槛对话式 AI 开发",
        subtitle: "极致降本提效：从“专业团队数月”到“业务人员分钟级”",
        sections: [
            {
                title: "彻底打破技术壁垒",
                desc: "平台内置专属 AI 开发智能体，彻底打破技术壁垒，将企业智能化开发的门槛降至最低。业务人员无需依赖技术团队，即可自主主导数字化创新与功能构建。",
            },
            {
                title: "四大核心特性",
                cards: [
                    {
                        title: "零门槛自然交互",
                        desc: "无需编程背景，通过日常自然语言对话即可提出需求，像聊天一样完成开发。",
                    },
                    {
                        title: "全场景应用构建",
                        desc: "不仅能定制私有化 AI 业务智能体，还能快速搭建审批、报表、流程等传统企业级业务模块。",
                    },
                    {
                        title: "深度配置与编排",
                        desc: "可视化配置提示词、LLM 模型参数、自定义函数逻辑、业务流程编排及 UI 界面，无需编写复杂代码。",
                    },
                    {
                        title: "实时调试与迭代",
                        desc: "开发过程所见即所得，支持实时调试、在线修改并快速优化业务规则与 AI 能力表现。",
                    },
                ],
            },
            {
                title: "价值重塑",
                desc: "彻底颠覆传统开发模式，将原本需要“专业技术团队投入数月攻坚”的开发周期，压缩为“业务人员通过对话式交互，分钟级完成应用搭建与部署”。大幅降低人力成本，缩短需求到上线的链路，让业务创新不再受制于技术资源瓶颈。",
            },
        ],
    },
    "full-customization": {
        eyebrow: "核心能力",
        title: "全要素灵活自定义",
        subtitle: "真正的适配：平台适配企业，而非企业适配平台",
        sections: [
            {
                title: "全维度 100% 自定义",
                desc: "平台支持企业自主配置、开发、迭代所有核心能力，打破技术黑盒与功能锁死，让企业拥有完全的技术掌控权与业务主动权。",
            },
            {
                title: "六大自定义维度",
                cards: [
                    {
                        title: "自定义 LLM 大模型",
                        desc: "灵活适配行业专属、私有化部署及开源大模型，按需无缝切换，打造贴合业务场景的专属智能基座。",
                    },
                    {
                        title: "自定义 Skills 业务技能",
                        desc: "基于岗位特性与业务流程，搭建专属 AI 技能库，精准赋能客服、销售、生产等多元化核心场景。",
                    },
                    {
                        title: "自定义 Functions 工具函数",
                        desc: "按需编写业务逻辑与自动化流程函数，自由对接 ERP、CRM 等系统，实现从交互到执行的业务闭环。",
                    },
                    {
                        title: "自定义业务 Models",
                        desc: "自由定义和调整业务数据模型，核心数据体系随需而变。",
                    },
                    {
                        title: "自定义 UI Cards 界面组件",
                        desc: "自由定义功能布局与交互样式，快速适配企业独特的操作习惯与展示需求。",
                    },
                    {
                        title: "极致的自定义扩展能力",
                        desc: "支持数据库、知识库、文件存储、登录方式、组织架构等近 30 个企业级系统常见技术领域的自定义扩展。",
                    },
                ],
            },
            {
                title: "业务价值",
                desc: "打破传统 SaaS 的功能限制，无论是金融、制造、零售还是服务行业，任何个性化业务需求均可实现无限制定制。让 AI 和 IT 真正成为企业发展的核心驱动力，而非业务发展的瓶颈。",
            },
        ],
    },
    "enterprise-architecture": {
        eyebrow: "核心能力",
        title: "企业级协同架构",
        subtitle: "专为企业设计：支持大规模团队协同与管理",
        sections: [
            {
                title: "企业级 BS 架构设计",
                desc: "基于 BS 架构、前后端分离、多用户、多应用的企业级架构设计，为企业组织的 AI 应用提供稳固、灵活的底层支撑。免安装、开箱即用，支持浏览器直接访问，降低 IT 运维负担。",
            },
            {
                title: "三大协同能力",
                cards: [
                    {
                        title: "多维权限治理体系",
                        desc: "构建多部门、多账号、多角色的立体化权限矩阵，实现功能与数据的精细化隔离，确保企业级应用的数据安全与合规管控。",
                    },
                    {
                        title: "集团化组织适配",
                        desc: "完美契合中大型企业及集团化多层级组织架构，支持跨地域、跨事业部的资源调度与业务协同，打破组织壁垒，提升管理效率。",
                    },
                    {
                        title: "大规模高效协同",
                        desc: "支持千级规模团队并行开发与协作，高效管理 AI 智能体的全生命周期，实现从开发、部署到迭代的无缝衔接与规模化落地。",
                    },
                ],
            },
            {
                title: "价值总结",
                desc: "以高可用、高扩展的架构底座，承载企业级 AI 应用的规模化落地。告别桌面级单机工具的局限，打造安全可控、敏捷高效的智能协同生态，真正支撑起企业的生产级 AI 应用。",
            },
        ],
    },
    "private-deployment": {
        eyebrow: "核心能力",
        title: "私有化安全部署",
        subtitle: "数据安全至上：100% 私有化，杜绝数据外泄",
        sections: [
            {
                title: "从底层架构杜绝隐患",
                desc: "支持企业本地服务器、私有云及专属机房的私有化部署模式，将核心数据与业务逻辑完全部署在企业可控的物理环境内，从底层架构层面彻底规避数据上云带来的外部泄露隐患，为高安全要求行业提供可靠保障。",
            },
            {
                title: "三大安全保障",
                cards: [
                    {
                        title: "数据完全留存",
                        desc: "企业业务数据、业务流程规则及定制化代码全量留存于内网，数据归属权完全私有化。实现「数据不出域、资产不外流」，从物理层面阻断外部窃取与非法泄露。",
                    },
                    {
                        title: "无第三方风险",
                        desc: "系统架构独立于外部公网环境，从数据传输、存储到使用实现全链路闭环管理，彻底消除因第三方平台漏洞、越权访问或恶意攻击带来的数据泄露与滥用风险。",
                    },
                    {
                        title: "满足合规要求",
                        desc: "契合金融、政务、医疗等行业对数据安全和隐私保护的严格合规要求，通过物理隔离实现最高等级的数据资产保护。",
                    },
                ],
            },
            {
                title: "安全承诺",
                desc: "构建「数据自主可控、安全可审计、合规无死角」的私有化智能基座。企业拥有对全部数据和 AI 资产的完全掌控权，让企业用得放心、管得安心，真正实现技术主权的自主可控。",
            },
        ],
    },
    "devops-unified": {
        eyebrow: "核心能力",
        title: "开发运行一体化",
        subtitle: "告别冗长流程：实时开发 · 实时运行 · 实时迭代",
        sections: [
            {
                title: "重构智能应用的交付逻辑",
                desc: "行业独有的“边开发、边运行、边迭代”一体化模式，重构智能应用的交付与演进逻辑，从根源上突破传统开发的效率瓶颈。",
            },
            {
                title: "三大核心优势",
                cards: [
                    {
                        title: "打破传统壁垒",
                        desc: "摒弃“开发-部署-上线”的割裂式流程，实现开发与运行环境的无缝融合，消除跨阶段的沟通与等待成本，让研发资源聚焦业务价值。",
                    },
                    {
                        title: "实时生效迭代",
                        desc: "功能模块编写完成即自动加载运行，无需人工触发部署。更新实时生效，配置动态同步，实现研发成果的“秒级交付”与快速验证。",
                    },
                    {
                        title: "敏捷业务响应",
                        desc: "面对需求变更可即时修改逻辑与参数，全程无服务中断、无需停机维护。在保障业务连续性的同时，实现对市场变化的极速响应。",
                    },
                ],
            },
            {
                title: "价值重塑",
                desc: "将传统开发上线的“周级”周期压缩至“分钟级”，迭代效率提升 30 倍以上。让企业能够以更灵活的姿态应对市场竞争，快速将创新想法转化为实际的业务成果，构建持续进化的数字化能力。",
            },
        ],
    },
    "active-hub": {
        eyebrow: "核心能力",
        title: "主动式智能中枢",
        subtitle: "内置主动式智能体，实现业务流程的自动化与智能化闭环。",
        sections: [
            {
                title: "从「被动等待指令」到「主动发现问题、自动解决问题」",
                desc: "传统系统总是被动等待用户触发操作，而 JitAI 的主动式企业管家内置了一个主动型智能体。它能像一位经验丰富的业务专家，7×24 小时持续监控企业系统状态，主动感知异常、智能推理对策并自主执行闭环，打破传统系统的被动响应模式。",
                cards: [
                    {
                        title: "主动感知",
                        desc: "智能体如同全天候的「雷达」，持续监控企业系统中的事件、数据异动与业务状态。无需人工触发指令，毫秒级捕捉关键信息，打破传统系统的被动响应模式，为后续决策提供实时、精准的数据基础。",
                    },
                    {
                        title: "智能推理与决策",
                        desc: "基于预设业务规则与深度学习模型，对感知信息进行自主分析、逻辑推理与风险评估。不仅能精准识别问题本质，更能结合历史数据与实时场景，动态生成多套应对策略，并智能优选最佳方案。",
                    },
                    {
                        title: "自主执行与闭环",
                        desc: "依据决策结果自主触发多维度执行动作：调度上下游智能体协同完成复杂任务链；通过邮件、IM 等渠道向责任人发送精准预警；直接调用系统 API 执行预设工作流，无需人工干预。",
                    },
                ],
            },
            {
                title: "主动式 vs 传统被动式",
                comparison: [
                    {
                        dimension: "触发方式",
                        legacy: "等待人工指令",
                        jitai: "自动感知系统事件与状态变化",
                    },
                    {
                        dimension: "响应速度",
                        legacy: "发现问题时已造成损失",
                        jitai: "毫秒级捕捉异常，提前预警",
                    },
                    {
                        dimension: "决策模式",
                        legacy: "依赖人工判断与经验",
                        jitai: "AI 推理 + 业务规则，动态优选",
                    },
                    {
                        dimension: "执行闭环",
                        legacy: "需多角色、多系统手动协同",
                        jitai: "自主调度智能体，自动完成全链路",
                    },
                    {
                        dimension: "覆盖时间",
                        legacy: "5×8 工作时间",
                        jitai: "7×24 全天候值守",
                    },
                ],
            },
            {
                title: "核心价值",
                desc: "将企业从「人找问题」升级为「问题找人」，让智能体成为不知疲倦的数字管家。不仅大幅缩短异常响应与处理时间，更将业务专家的经验系统化为可复用的智能规则，让企业运营从「人为驱动」走向「智能驱动」。",
            },
        ],
    },
    "dual-mode": {
        eyebrow: "核心能力",
        title: "双模同源一体",
        subtitle: "AI 智能体与传统业务系统一体化",
        sections: [
            {
                title: "一套平台，两种能力",
                desc: "JitAI 在同一平台内同时支持 AI 智能体与传统业务系统的开发与运行。不是简单的功能叠加，而是底层技术体系的真正统一--两种形态共享同一套函数、数据模型和数据库。",
            },
            {
                title: "双模能力拆解",
                cards: [
                    {
                        title: "支持 AI 智能体开发运行",
                        desc: "全面拥抱 AI 时代，提供从 AI 智能体设计、开发、部署到运行的全生命周期管理能力，让企业轻松构建和迭代各类智能应用。",
                    },
                    {
                        title: "兼容传统业务模块",
                        desc: "完美兼容 IT 时代的开发模式，支持传统业务功能模块的开发与运行，保障企业现有 IT 资产的延续性与价值最大化。",
                    },
                    {
                        title: "统一技术体系",
                        desc: "AI 智能体与传统模块共享同一套技术体系，包括函数（Functions）、数据模型（Data Models）、数据库等，实现底层技术的统一与高效复用。",
                    },
                ],
            },
            {
                title: "为什么双模一体是核心能力",
                desc: "企业智能化转型的最大痛点不是“能不能做 AI”，而是 AI 系统与原有业务系统的割裂--数据不通、流程断裂、运维复杂。JitAI 的双模一体架构从根本上解决了这一矛盾：在同一套技术底座上，既能用 AI 重构业务流程，又能保持与传统 IT 系统的无缝衔接。不是推倒重来，而是渐进式智能化升级。",
            },
            {
                title: "价值主张",
                desc: "一套平台，同时驾驭 AI 技术与 IT 技术的核心载体，实现新旧技术体系的无缝融合与业务驱动的全链路实现。企业不需要在“拥抱 AI”和“保留现有系统”之间做选择--JitAI 帮你两全其美。",
            },
        ],
    },
};

interface OfficialCapabilityDetailProps {
    slug: string;
}

const OfficialCapabilityDetail: React.FC<OfficialCapabilityDetailProps> = ({
    slug,
}) => {
    const detail = CAPABILITY_DETAILS[slug];
    const { i18n } = useDocusaurusContext();
    const homePath = i18n.currentLocale === "zh" ? "/zh/#capabilities" : "/#capabilities";
    const handleBack = () => {
        window.location.assign(homePath);
    };

    if (!detail) {
        return null;
    }

    return (
        <>
            <Head title={`${detail.title} - JitAI`}>
                <meta name="description" content={detail.subtitle} />
            </Head>
            <main className={styles.page}>
                <div className={styles.shell}>
                    <button
                        className={styles.backLink}
                        onClick={handleBack}
                        type="button"
                    >
                        <ArrowLeftIcon />
                        返回核心能力
                    </button>
                    <header className={styles.hero}>
                        <span>{detail.eyebrow}</span>
                        <h1>{detail.title}</h1>
                        <p>{detail.subtitle}</p>
                    </header>
                    <div className={styles.sections}>
                        {detail.sections.map((section) => (
                            <DetailSectionView
                                key={section.title}
                                section={section}
                            />
                        ))}
                    </div>
                </div>
            </main>
        </>
    );
};

const DetailSectionView: React.FC<{ section: DetailSection }> = ({
    section,
}) => (
    <section className={styles.detailSection}>
        <h2>{section.title}</h2>
        {section.desc ? <p className={styles.sectionDesc}>{section.desc}</p> : null}
        {section.cards ? <CardGrid cards={section.cards} /> : null}
        {section.panels ? <PanelGrid panels={section.panels} /> : null}
        {section.checks ? <CheckGrid checks={section.checks} /> : null}
        {section.comparison ? (
            <ComparisonTable rows={section.comparison} />
        ) : null}
    </section>
);

const CardGrid: React.FC<{ cards: DetailCard[] }> = ({ cards }) => (
    <div className={styles.cardGrid}>
        {cards.map((card, index) => (
            <article className={styles.infoCard} key={card.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{card.title}</h3>
                <p>{card.desc}</p>
            </article>
        ))}
    </div>
);

const PanelGrid: React.FC<{ panels: FeaturePanel[] }> = ({ panels }) => (
    <div className={styles.panelGrid}>
        {panels.map((panel) => (
            <article className={styles.featurePanel} key={panel.title}>
                <div>
                    <span>{panel.mark}</span>
                    <h3>{panel.title}</h3>
                </div>
                {panel.desc.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                ))}
            </article>
        ))}
    </div>
);

const CheckGrid: React.FC<{ checks: string[] }> = ({ checks }) => (
    <div className={styles.checkGrid}>
        {checks.map((check) => (
            <div className={styles.checkItem} key={check}>
                <span>✓</span>
                <p>{check}</p>
            </div>
        ))}
    </div>
);

const ComparisonTable: React.FC<{ rows: ComparisonRow[] }> = ({ rows }) => (
    <div className={styles.tableWrap}>
        <table>
            <thead>
                <tr>
                    <th>对比维度</th>
                    <th>传统被动式系统</th>
                    <th>JitAI 主动式企业管家</th>
                </tr>
            </thead>
            <tbody>
                {rows.map((row) => (
                    <tr key={row.dimension}>
                        <td>{row.dimension}</td>
                        <td>{row.legacy}</td>
                        <td>{row.jitai}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

const ArrowLeftIcon: React.FC = () => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        fill="currentColor"
        viewBox="0 0 256 256"
        aria-hidden="true"
    >
        <path d="M228,128a12,12,0,0,1-12,12H69l51.52,51.51a12,12,0,0,1-17,17l-72-72a12,12,0,0,1,0-17l72-72a12,12,0,0,1,17,17L69,116H216A12,12,0,0,1,228,128Z" />
    </svg>
);

export default OfficialCapabilityDetail;
