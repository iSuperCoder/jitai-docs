import React, { useMemo, useState } from "react";
import PageLayout from "@site/src/components/PageLayout";
import { addUTMToUrl } from "@site/src/utils/utm";
import {
    ArrowRight,
    Check,
    Clipboard,
    Mail,
    MessageCircle,
} from "lucide-react";
import styles from "./contact.module.css";

interface ContactExperienceProps {
    currentLocale?: string;
}

const CONTACT_CHANNELS = {
    zh: {
        formTitle: "在线表单",
        wechatTitle: "微信咨询",
        wechatDesc: "扫码添加，即时响应",
        emailTitle: "邮件联系",
        emailSubject: "",
        formUrl: "https://wy.jit.pro/whwy/aicrm/s/zhcontactus?is_popup=1",
        email: "support@jit.pro",
        qrCodeUrl:
            "https://jit-www.oss-accelerate.aliyuncs.com/contact_us_wx_qr.jpg",
    },
    en: {
        formTitle: "Online Form",
        wechatTitle: "Wechat",
        wechatDesc: "Scan to chat instantly",
        emailTitle: "Email Contact",
        emailSubject: "",
        formUrl: "https://wy.jit.pro/whwy/aicrm/s/contactus?is_popup=1",
        email: "support@jit.pro",
        qrCodeUrl:
            "https://jit-www.oss-accelerate.aliyuncs.com/contact_us_wa_qr.jpg",
    },
};

const PAGE_COPY = {
    zh: {
        eyebrow: "联系我们",
        title: "和 JitAI 团队聊聊你的企业 AI 落地计划",
        description:
            "告诉我们你的业务场景、部署方式和团队现状，我们会尽快给出适合的产品演示、试用和落地建议。",
        responseTitle: "你可以咨询",
        responseItems: [
            "企业私有化部署",
            "AI 数字员工工作流",
            "试用、安装与技术支持",
        ],
        formTitle: "留下需求",
        emailHelper: "用于产品咨询、技术支持和合作沟通",
        copyEmail: "复制邮箱",
        copiedEmail: "已复制",
        openMail: "发送邮件",
    },
    en: {
        eyebrow: "Contact Us",
        title: "Talk to the JitAI team about your enterprise AI rollout",
        description:
            "Share your business scenario, deployment plan, and team setup. We will follow up with a practical demo, trial, or implementation suggestion.",
        responseTitle: "We can help with",
        responseItems: [
            "Enterprise private deployment",
            "AI digital employee workflows",
            "Trial, installation, and technical support",
        ],
        formTitle: "Leave Your Request",
        emailHelper: "For product consulting, technical support, and partnerships",
        copyEmail: "Copy email",
        copiedEmail: "Copied",
        openMail: "Send email",
    },
};

const ContactPage: React.FC = () => {
    return (
        <PageLayout
            pageId="contact"
            containerClassName={styles.contactPage}
            withLayout={false}
        >
            <ContactExperience />
        </PageLayout>
    );
};

const ContactExperience: React.FC<ContactExperienceProps> = ({
    currentLocale,
}) => {
    const locale = currentLocale === "zh" ? "zh" : "en";
    const contactContent = CONTACT_CHANNELS[locale];
    const copy = PAGE_COPY[locale];
    const [copied, setCopied] = useState(false);
    const formUrl = useMemo(
        () => addUTMToUrl(contactContent.formUrl),
        [contactContent.formUrl],
    );

    const handleCopyEmail = async () => {
        try {
            await navigator.clipboard.writeText(contactContent.email);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
        } catch (error) {
            console.error("Failed to copy email:", error);
        }
    };

    return (
        <main className={styles.main}>
            <section className={styles.heroSection}>
                <div className={styles.shell}>
                    <div className={styles.heroGrid}>
                        <div className={styles.heroCopy}>
                            <p className={styles.eyebrow}>{copy.eyebrow}</p>
                            <h1>{copy.title}</h1>
                            <p className={styles.heroDescription}>
                                {copy.description}
                            </p>
                            <a
                                className={styles.primaryLink}
                                href="#contact-form"
                            >
                                {copy.formTitle}
                                <ArrowRight aria-hidden="true" />
                            </a>
                        </div>
                        <aside className={styles.summaryPanel}>
                            <p>{copy.responseTitle}</p>
                            <ul>
                                {copy.responseItems.map((item) => (
                                    <li key={item}>
                                        <Check aria-hidden="true" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </aside>
                    </div>
                </div>
            </section>

            <section className={styles.contactSection}>
                <div className={styles.shell}>
                    <div className={styles.contactGrid}>
                        <article
                            id="contact-form"
                            className={styles.formPanel}
                        >
                            <iframe
                                src={formUrl}
                                className={styles.formIframe}
                                title={contactContent.formTitle}
                                loading="eager"
                            />
                        </article>

                        <aside className={styles.sideColumn}>
                            <article className={styles.contactCard}>
                                <div className={styles.cardHeader}>
                                    <span className={styles.iconBox}>
                                        <MessageCircle aria-hidden="true" />
                                    </span>
                                    <div>
                                        <h2>{contactContent.wechatTitle}</h2>
                                        <p>{contactContent.wechatDesc}</p>
                                    </div>
                                </div>
                                <div className={styles.qrFrame}>
                                    <img
                                        src={contactContent.qrCodeUrl}
                                        alt={contactContent.wechatTitle}
                                    />
                                </div>
                            </article>

                            <article className={styles.contactCard}>
                                <div className={styles.cardHeader}>
                                    <span className={styles.iconBox}>
                                        <Mail aria-hidden="true" />
                                    </span>
                                    <div>
                                        <h2>{contactContent.emailTitle}</h2>
                                        <p>{copy.emailHelper}</p>
                                    </div>
                                </div>
                                <a
                                    href={`mailto:${
                                        contactContent.email
                                    }?subject=${encodeURIComponent(
                                        contactContent.emailSubject,
                                    )}`}
                                    className={styles.emailLink}
                                >
                                    {contactContent.email}
                                </a>
                                <div className={styles.emailActions}>
                                    <a
                                        href={`mailto:${
                                            contactContent.email
                                        }?subject=${encodeURIComponent(
                                            contactContent.emailSubject,
                                        )}`}
                                        className={styles.secondaryButton}
                                    >
                                        {copy.openMail}
                                    </a>
                                    <button
                                        type="button"
                                        className={styles.copyButton}
                                        onClick={handleCopyEmail}
                                    >
                                        <Clipboard aria-hidden="true" />
                                        {copied
                                            ? copy.copiedEmail
                                            : copy.copyEmail}
                                    </button>
                                </div>
                            </article>
                        </aside>
                    </div>
                </div>
            </section>
        </main>
    );
};

export default ContactPage;
