import React, { useEffect, useRef, useState } from 'react';
import { useMarketingCopy, CONSOLE_URL, DEMO_URL, LOGO_DARK, LOGO_LIGHT, NEWS_PATH } from './copy';

/** 官网导航按下载、体验、云控制台排序；active 标识当前页，theme 与 toggleTheme 由页面管理。
 * 下载沿用站内本地化地址，外部入口新开窗口；用途说明支持悬停、聚焦和 Escape 关闭。
 * 移动菜单覆盖正文视口；打开期间锁定滚动和正文交互，关闭/卸载时恢复原状态。
 */
export default function Header({ active, theme, toggleTheme }: {
  active: string; theme: 'light' | 'dark'; toggleTheme: () => void;
}) {
  const { text, path } = useMarketingCopy();
  const [open, setOpen] = useState(false);
  const [hintDismissed, setHintDismissed] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    // 只锁住当前页面背景，导航自身仍可滚动；保留原值，避免关闭菜单后覆盖页面已有约束。
    const scrolling = [document.documentElement, document.body];
    const scrollPosition = { left: window.scrollX, top: window.scrollY };
    const previousOverflow = scrolling.map(node => node.style.overflow);
    const content = Array.from(menuButton.current?.closest('.marketing-site')?.querySelectorAll<HTMLElement>('main, footer') || []);
    const previousInert = content.map(node => node.inert);
    scrolling.forEach(node => { node.style.overflow = 'hidden'; });
    content.forEach(node => { node.inert = true; });
    return () => {
      scrolling.forEach((node, index) => { node.style.overflow = previousOverflow[index]; });
      content.forEach((node, index) => { node.inert = previousInert[index]; });
      // 部分移动浏览器锁住根滚动容器会重置偏移；关闭时还原阅读位置，不触发平滑滚动。
      window.scrollTo({ ...scrollPosition, behavior: 'instant' });
    };
  }, [open]);
  useEffect(() => {
    /** Escape 关闭菜单；展开时 Tab 在可见导航控件之间循环，不落入被遮挡的正文或跳转链接。 */
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setHintDismissed(true);
      if (event.key === 'Escape' && open) { setOpen(false); menuButton.current?.focus({ preventScroll: true }); }
      if (event.key === 'Tab' && open) {
        const links = Array.from(menuButton.current?.closest('header')?.querySelectorAll<HTMLElement>('a[href], button') || []).filter(node => node.getClientRects().length > 0);
        const first = links[0], last = links[links.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    const media = window.matchMedia('(min-width: 1181px)');
    const resize = () => { if (media.matches) setOpen(false); };
    document.addEventListener('keydown', close);
    media.addEventListener('change', resize);
    return () => { document.removeEventListener('keydown', close); media.removeEventListener('change', resize); };
  }, [open]);
  const items = [
    ['/', text('首页', 'Home')], ['/cases', text('案例方案', 'Cases & Solutions')],
    [NEWS_PATH, text('资讯中心', 'News & Insights')],
    ['/partners', text('渠道合作', 'Partners')], ['/about', text('关于我们', 'About')],
  ];
  // 两处导航共用顺序与文案；说明作为链接内容可被读屏读取，手机端直接展示。
  const actions = [
    { href: path('/download'), label: text('免费下载桌面版', 'Free desktop download'), hint: text('安装到电脑，在本地开发和运行应用。', 'Install on your computer to build and run apps locally.'), primary: true },
    { href: DEMO_URL, label: text('在线体验', 'Try online'), hint: text('无需安装，在公共演示环境中体验功能。', 'Explore features in a shared demo, without installing.'), primary: false },
    { href: CONSOLE_URL, label: text('云控制台', 'Cloud console'), hint: text('购买和管理专属云环境，用于应用部署与运行。', 'Purchase and manage a dedicated cloud environment to deploy and run apps.'), primary: false },
  ].map(({ href, label, hint, primary }) => <a key={href}
    className={`btn btn-${primary ? 'primary' : 'ghost'} btn-sm entry-link`}
    href={href} target={primary ? undefined : '_blank'} rel={primary ? undefined : 'noopener noreferrer'}
    onMouseEnter={() => setHintDismissed(false)} onFocus={() => setHintDismissed(false)}>
    <span>{label}</span><span className="entry-hint">{hint}</span>
    {!primary && <span className="sr-only">{text('（在新窗口打开）', ' (opens in a new window)')}</span>}
  </a>);
  return <header className="site-header" data-hint-dismissed={hintDismissed} data-menu-open={open}>
    <div className="wrap header-inner">
      <a className="brand" href={path('/')} aria-label={text('JitAI 首页', 'JitAI home')}>
        <img className="official-logo" src={theme === 'dark' ? LOGO_DARK : LOGO_LIGHT} alt="JitAI" width="112" height="34" />
      </a>
      <nav className="nav" id="marketing-navigation" aria-label={text('主导航', 'Main navigation')} data-open={open} onClick={() => setOpen(false)}>
        {/* 原生链接使浏览器加载服务器生成的列表，不由 Docusaurus 路由接管。 */}
        {items.map(([route, label]) => <a key={route} href={route === NEWS_PATH ? NEWS_PATH : path(route)} aria-current={active === route ? 'page' : undefined}>{label}</a>)}
        <div className="nav-cta">{actions}</div>
      </nav>
      <div className="header-actions">
        <button className="theme-toggle" type="button" onClick={toggleTheme} aria-label={theme === 'dark' ? text('切换浅色主题', 'Switch to light theme') : text('切换深色主题', 'Switch to dark theme')}>
          {theme === 'dark' ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6L19 19M19 5l-1.4 1.4M6.4 17.6L5 19"/></svg> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>}
        </button>
        {actions}
        <button ref={menuButton} className="nav-toggle" type="button" aria-expanded={open} aria-controls="marketing-navigation" aria-label={open ? text('关闭导航', 'Close navigation') : text('展开导航', 'Open navigation')} onClick={() => setOpen(!open)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d={open ? 'M6 6l12 12M18 6L6 18' : 'M4 7h16M4 12h16M4 17h16'}/></svg>
        </button>
      </div>
    </div>
  </header>;
}
