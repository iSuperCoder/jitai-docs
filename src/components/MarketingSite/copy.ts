import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import { BRAND_COPY } from '../../brand';
import english from './content/en.json';

export function useMarketingCopy() {
  const { i18n } = useDocusaurusContext();
  const isZh = i18n.currentLocale === 'zh';
  const text = (zh: string, en: string) => isZh ? zh : en;
  const path = (route: string) => isZh ? `/zh${route === '/' ? '/' : route}` : route;
  const t = (source: keyof typeof english) => isZh ? source : `${english[source]} `;
  return { isZh, text, path, t, brand: BRAND_COPY[isZh ? 'zh' : 'en'] };
}

export const CONTACT_EMAIL = 'support@jit.pro';
export const WECHAT_IMAGE = '/img/marketing/wechat.jpg';
export const FORUM_URL = 'https://forum.jit.pro';
// 当前资讯源为中文；中英文官网均进入同一个独立静态列表，不通过 locale 再拼接 /zh。
// 此入口须与服务器 NEWS_PUBLIC_PATH 保持一致，不创建 Docusaurus 同名页面。
export const NEWS_PATH = '/zh/news/';
export const LOGO_LIGHT = 'https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_title.svg';
export const LOGO_DARK = 'https://jit-www.oss-accelerate.aliyuncs.com/logo/logo_title_dark.svg';
