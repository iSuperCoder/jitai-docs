import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, RotateCw } from 'lucide-react';
import MarketingLayout from '@site/src/components/MarketingSite';
import { NEWS_PATH, useMarketingCopy } from '@site/src/components/MarketingSite/copy';
import './cases.css';

/** 案例方案只消费资讯同步器已发布的列表快照，不直接访问内容 App。 */
type CaseArticle = {
  id: string; title: string; summary?: string; image?: string;
  image_alt?: string; date_published?: string; tags?: string[]; url: string;
};

/** 接受已发布资讯列表，返回标签文字含“案例”的文章并保留原发布时间顺序；标题和栏目不参与判断。 */
export function selectCases(items: CaseArticle[]): CaseArticle[] {
  return items.filter(item => Array.isArray(item.tags) && item.tags.some(tag => typeof tag === 'string' && tag.includes('案例')));
}

/** 读取已发布资讯快照并展示案例；轮播只改变推荐位，列表顺序和来源数据不变。
 * 计时器、可见性观察及媒体偏好监听均随组件卸载释放，SSR 阶段不访问浏览器 API。
 */
function CaseLibrary() {
  const { text } = useMarketingCopy();
  const [items, setItems] = useState<CaseArticle[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [retry, setRetry] = useState(0);
  const [featureIndex, setFeatureIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [visible, setVisible] = useState(false);
  const [pageVisible, setPageVisible] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const carousel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    // 内容同步器从运行时 NEWS_FEED_URL 获取 feed.json；资讯页内嵌其已发布投影，前端不复制配置地址。
    fetch(NEWS_PATH, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.text(); })
      .then(html => {
        const snapshot = new DOMParser().parseFromString(html, 'text/html').getElementById('feed-snapshot')?.textContent;
        if (!snapshot) throw new Error('Missing news snapshot');
        return JSON.parse(snapshot);
      })
      .then(data => {
        if (!Array.isArray(data.items)) throw new Error('Invalid news list');
        setItems(selectCases(data.items)); setFeatureIndex(0); setState('ready');
      })
      .catch(() => { if (!controller.signal.aborted) setState('error'); });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPaused(motion.matches);
    /** 开启减少动态效果时暂停；关闭该偏好不覆盖用户已经选择的暂停状态。 */
    const onMotion = () => { if (motion.matches) setPaused(true); };
    /** 后台、离开页面和返回页面都重新决定是否计时，恢复时给予完整阅读周期。 */
    const onVisibility = () => setPageVisible(!document.hidden);
    const onPageHide = () => setPageVisible(false);
    onVisibility();
    motion.addEventListener('change', onMotion);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    window.addEventListener('pageshow', onVisibility);
    return () => {
      motion.removeEventListener('change', onMotion);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
      window.removeEventListener('pageshow', onVisibility);
    };
  }, []);

  useEffect(() => {
    if (state !== 'ready' || !carousel.current) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(carousel.current);
    return () => observer.disconnect();
  }, [state, items.length]);

  useEffect(() => {
    // 与资讯中心保持 12 秒周期；悬停、焦点、后台、离屏或单篇均不创建计时器。
    if (state !== 'ready' || items.length < 2 || paused || hovered || focused || !visible || !pageVisible) return;
    const timer = window.setTimeout(() => setFeatureIndex(index => (index + 1) % items.length), 12000);
    return () => window.clearTimeout(timer);
  }, [state, items.length, featureIndex, paused, hovered, focused, visible, pageVisible]);

  /** 手动移动一个位置并循环；仅手动切换播报标题，自动轮播不打断屏幕阅读器。 */
  const moveFeature = (step: number) => {
    const next = (featureIndex + step + items.length) % items.length;
    setFeatureIndex(next);
    setAnnouncement(items[next].title);
  };
  const feature = items[featureIndex];
  /** 返回来源日历日期；无日期显示空串，不对没有时区的来源日期做浏览器时区换算。 */
  const date = (item: CaseArticle) => item.date_published?.slice(0, 10).replaceAll('-', '.') || '';
  return <>
    <section className="case-intro"><div className="wrap">
      <p className="kicker">CASE STUDIES / SOLUTIONS</p>
      <h1>{text('案例方案', 'Cases & Solutions')}</h1>
      <p>{text('从业务现场出发，看见问题、实施路径与解决思路。', 'See the business challenge, implementation path and solution in each story.')}</p>
      {/* 静态提供通往完整文章目录的链接；网络或脚本不可用时仍有可抓取的阅读路径。 */}
      <a className="case-directory-link" href={NEWS_PATH}>{text('浏览全部实践文章', 'Browse all practice articles')} ↗</a>
    </div></section>
    <section className="case-library wrap" aria-label={text('案例文章', 'Case articles')} aria-busy={state === 'loading'}>
      {/* 占位沿用真实封面比例与推荐区结构，避免异步数据到达时从小转圈突然撑开整屏。
          无脚本时隐藏占位，读者可通过上方静态目录链接继续阅读。 */}
      {state === 'loading' && <div className="case-loading" role="status" aria-label={text('正在加载案例', 'Loading cases')}>
        <div className="case-section-heading"><span>{text('精选案例', 'Featured case')}</span></div>
        <div className="case-feature" aria-hidden="true"><div className="case-visual" /><div className="case-feature-content"><span className="case-placeholder-line" /><span className="case-placeholder-line" /><span className="case-placeholder-line" /></div></div>
        <div className="case-carousel-controls" aria-hidden="true"><span className="case-placeholder-line" /></div>
      </div>}
      {(state === 'error' || state === 'ready' && !items.length) && <div className="case-standby" role={state === 'error' ? 'alert' : undefined}>
        <div className="case-standby-content">
          <h2>{state === 'error' ? text('案例暂时无法加载', 'Cases are temporarily unavailable') : text('新的实践，陆续呈现', 'More stories to come')}</h2>
          {state === 'error' && <p>{text('请稍后重试，或先浏览资讯中心。', 'Please try again later or browse News & Insights.')}</p>}
          <div className="case-standby-actions">
            {state === 'error' && <button type="button" onClick={() => setRetry(value => value + 1)}><RotateCw size={16} aria-hidden="true" />{text('重新加载', 'Retry')}</button>}
            <a href={NEWS_PATH}>{text('浏览资讯中心', 'Browse news & insights')}<ArrowUpRight size={16} aria-hidden="true" /></a>
          </div>
        </div>
      </div>}
      {state === 'ready' && feature && <>
        <div className="case-section-heading"><span>{text('精选案例', 'Featured case')}</span><span>{String(items.length).padStart(2, '0')} {text('篇案例', 'stories')}</span></div>
        <div ref={carousel} className="case-carousel" role="region" aria-roledescription={text('轮播', 'carousel')} aria-label={text('精选案例', 'Featured cases')}
          onPointerEnter={event => { if (event.pointerType === 'mouse') setHovered(true); }} onPointerLeave={() => setHovered(false)}
          onFocusCapture={() => setFocused(true)} onBlurCapture={event => setFocused(event.currentTarget.contains(event.relatedTarget))}>
        <article className="case-feature" data-id={feature.id}>
          {/* 每篇重建图片节点，避免上一张加载失败留下 hidden 状态污染下一张封面。 */}
          <div className="case-visual">{feature.image ? <img key={feature.id} src={feature.image} alt={feature.image_alt || ''} loading="eager" fetchPriority="high" onError={event => { event.currentTarget.hidden = true; }} /> : null}<span aria-hidden="true">JitAI / CASE</span></div>
          <div className="case-feature-content"><p className="case-index">{String(featureIndex + 1).padStart(2, '0')} / {String(items.length).padStart(2, '0')}</p><h2><a href={feature.url} target="_blank" rel="noopener noreferrer">{feature.title}<span className="sr-only">{text('（在新标签页打开）', ' (opens in a new tab)')}</span></a></h2><p>{feature.summary}</p><div className="case-meta"><time dateTime={feature.date_published}>{date(feature)}</time><span>{text('阅读案例 ↗', 'Read case ↗')}</span></div></div>
        </article>
        {items.length > 1 && <div className="case-carousel-controls">
          <p>{paused ? text('已暂停', 'Paused') : hovered || focused ? text('阅读中，已暂停', 'Paused while reading') : text('每 12 秒切换', 'Changes every 12 seconds')}</p>
          <div className="case-carousel-actions">
            <button type="button" onClick={() => setPaused(value => !value)}>{paused ? text('播放轮播', 'Play slideshow') : text('暂停轮播', 'Pause slideshow')}</button>
            <button type="button" aria-label={text('上一篇案例', 'Previous case')} onClick={() => moveFeature(-1)}>←</button>
            <span className="case-index">{featureIndex + 1} / {items.length}</span>
            <button type="button" aria-label={text('下一篇案例', 'Next case')} onClick={() => moveFeature(1)}>→</button>
          </div>
        </div>}
        <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
        </div>
        {/* 推荐位会遍历全部案例；下方固定展示全集，保证用户不等待轮播也能直接阅读任何一篇。 */}
        {items.length > 1 && <>
          <div className="case-section-heading case-more-heading"><span>{text('全部案例', 'All cases')}</span><span>{String(items.length).padStart(2, '0')}</span></div>
          <div className="case-list">{items.map((item, index) => <article className="case-row" key={item.id}>
            <span className="case-index">{String(index + 1).padStart(2, '0')}</span>
            {/* 原列表行增加小封面，仍以文字阅读为主；无图或失败沿用品牌占位。 */}
            <div className="case-visual">
              {item.image && <img src={item.image} alt={item.image_alt || ''} loading="lazy" onError={event => { event.currentTarget.hidden = true; }} />}
              <span aria-hidden="true">JitAI / CASE</span>
            </div>
            <div className="case-row-content">
              <h3><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<span className="sr-only">{text('（在新标签页打开）', ' (opens in a new tab)')}</span></a></h3>
              <p>{item.summary}</p>
            </div>
            <time dateTime={item.date_published}>{date(item)}</time><span className="case-row-arrow" aria-hidden="true">↗</span>
          </article>)}</div>
        </>}
      </>}
    </section>
    {/* 发布器只替换这两个槽的内部内容，以同一已发布资讯快照输出完整降级列表与 JSON-LD。
        noscript 在启用脚本时由浏览器按原始文本处理，React 不接管其中列表；关闭脚本可直接阅读。
        构建时没有生产数据，先保留目录入口；部署时和每轮内容同步都会填充，不依赖构建时抓 Feed。 */}
    <noscript id="case-static" suppressHydrationWarning><style>{'.case-library[aria-busy="true"]{display:none}'}</style><section className="case-library wrap"><a href={NEWS_PATH}>{text('浏览全部实践文章', 'Browse all practice articles')}</a></section></noscript>
    <script id="case-list-schema" type="application/ld+json" suppressHydrationWarning dangerouslySetInnerHTML={{ __html: state === 'ready' ? JSON.stringify({
      '@context': 'https://schema.org', '@type': 'CollectionPage', name: text('案例方案', 'Cases & Solutions'),
      url: `https://jit.pro${text('/zh/cases', '/cases')}`, inLanguage: text('zh-CN', 'en'),
      mainEntity: { '@type': 'ItemList', numberOfItems: items.length, itemListElement: items.map((item, index) => ({ '@type': 'ListItem', position: index + 1, name: item.title, url: item.url })) },
    }).replace(/</g, '\\u003c') : '{}' }} />
  </>;
}

/** 官方案例路由；页面外壳仍由 MarketingLayout 负责主题、导航和 SEO。 */
export default function Page() {
  const { text } = useMarketingCopy();
  return <MarketingLayout route="/cases" title={text('AI 原生系统客户案例与解决方案', 'AI-Native System Cases & Solutions')} description={text('阅读 JitAI 客户案例与业务实践，了解 AI 原生系统如何串联业务流程、数据与智能体，以及需求梳理、系统实施和成果验证的方法。', 'Explore JitAI customer cases: connecting business workflows, data and agents, from requirements and implementation to verified outcomes.')} image="https://jit.pro/img/home-video-preview.webp"><CaseLibrary /></MarketingLayout>;
}
