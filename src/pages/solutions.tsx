import React from 'react';
import LegacyRedirect from '@site/src/components/MarketingSite/LegacyRedirect';
/** 旧解决方案地址转入案例方案；旧分类锚点在内容列表中已无对应节点。 */
export default function Page() {
  return <LegacyRedirect to="/cases" preserveHash={false} />;
}
