import React, { useEffect } from 'react';
import Head from '@docusaurus/Head';
import { useMarketingCopy } from './copy';

/** 旧营销地址保持可达；to 是当前语言下的相对官网路径，preserveHash 控制旧章节锚点是否沿用。导航在挂载后替换当前历史项。 */
export default function LegacyRedirect({ to, preserveHash = true }: { to: string; preserveHash?: boolean }) {
  const { path, text } = useMarketingCopy();
  const destination = path(to);
  useEffect(() => {
    const target = new URL(destination, window.location.origin);
    target.search = window.location.search;
    // 白皮书章节可继续定位；旧解决方案的销售等锚点在案例页不存在，应回到列表开头。
    if (window.location.hash && preserveHash) target.hash = window.location.hash;
    window.location.replace(target.href);
  }, [destination, preserveHash]);
  return <>
    <Head><meta name="robots" content="noindex, follow" /><link rel="canonical" href={`https://jit.pro${destination}`} /></Head>
    <main style={{ padding: '48px 24px', maxWidth: 900, margin: 'auto' }}>
      <h1>{text('页面已更新', 'This page has moved')}</h1>
      <a href={destination}>{text('前往新版页面', 'Continue to the updated page')}</a>
    </main>
  </>;
}
