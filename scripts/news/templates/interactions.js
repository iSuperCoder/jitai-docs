/**
 * 官网静态资讯列表的渐进增强：数据来自构建时内嵌快照，浏览器不请求内容站。
 * 关闭 JavaScript 时原有静态列表仍可阅读。筛选、布局属于本页状态；轮播独立于列表，
 * 用户阅读、后台和离屏时暂停，pagehide 清理计时器，不占用常驻后台资源。
 */
(() => {
  const items = JSON.parse(document.getElementById('feed-snapshot').textContent).items;
  const root = document.documentElement;
  const search = document.getElementById('search');
  const carousel = document.getElementById('feature-carousel');
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const params = new URLSearchParams(location.search);
  let category = params.get('category') || '全部';
  let topic = params.get('topic') || '';
  let layout = params.get('layout') === 'list' ? 'list' : 'grid';
  let index = 0;
  let paused = reduceMotion.matches;
  let hover = false;
  let focus = false;
  let visible = false;
  let timer;
  const order = [...items];
  // Fisher–Yates 洗牌，一轮内不重复；不根据标题长度或发布时间偏置展示机会。
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  search.value = params.get('q') || '';
  try {
    if (!params.has('layout')) layout = localStorage.getItem('jitai-news-layout') === 'list' ? 'list' : 'grid';
    // 与营销页共享偏好和系统主题回退，避免从未保存偏好的深色官网切入浅色资讯页。
    const savedTheme = localStorage.getItem('jitai-marketing-theme');
    root.dataset.theme = savedTheme === 'dark' || savedTheme === 'light' ? savedTheme : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch { /* 存储受限时仍使用 URL 和默认视图。 */ }

  /** 对来源文字做 HTML/属性编码；空值为空串，不插入未经处理的正文 HTML。 */
  function escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  /** 依次读取有效主题数组/关键词字符串，不混合重复来源或推断栏目。 */
  function words(item) {
    for (const source of [item.tags, item._keywords, String(item._seo_keywords || '').split(/[,，;；]/)]) {
      if (!Array.isArray(source)) continue;
      const result = [...new Set(source.filter(word => typeof word === 'string').map(word => word.trim()).filter(Boolean))];
      if (result.length) return result;
    }
    return [];
  }

  /** 完整生成全部主题筛选按钮，不截断数量；点击标签只筛选，不触发文章链接。 */
  function tags(item) {
    return words(item).map(word => `<button type="button" class="topic-chip" data-topic="${escape(word)}" aria-label="筛选主题：${escape(word)}">${escape(word)}</button>`).join('');
  }

  /** 使用稳定 ID 确定无图封面；有图片时使用构建阶段本地化的官网地址。 */
  function cover(item) {
    let hash = 0;
    for (const ch of item.id) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
    return `<div class="cover ${['one','two','three','four'][hash % 4]} ${item.image ? 'has-image' : ''}"><div class="art" aria-hidden="true"><span></span><span></span><span></span></div><div class="cover-top" aria-hidden="true"><b>JitAI</b><span>${escape(item._section || 'INSIGHTS')}</span></div><p class="cover-heading" aria-hidden="true">${escape(item._seo_title || item.title)}</p>${item.image ? `<img class="cover-image" src="${escape(item.image)}" alt="${escape(item.image_alt || '')}" loading="lazy">` : ''}<div class="cover-keywords">${tags(item)}</div></div>`;
  }

  /** 日期仅展示来源日历日期，避免无时区输入造成相对时间错误；阅读时长缺失则隐藏。 */
  function meta(item) {
    return `<span>${escape((item.date_published || '').slice(0,10).replaceAll('-','.'))}</span>${Number(item._reading_time_minutes) > 0 ? `<span>· ${Number(item._reading_time_minutes)} 分钟阅读</span>` : ''}`;
  }

  /** 文章标题链接扩展到整卡，目标是构建写入的官网 URL；按钮作为独立兄弟节点。 */
  function article(item, feature = false) {
    const heading = feature ? 'h2' : 'h3';
    return `<article class="${feature ? 'feature' : 'card'}" data-id="${escape(item.id)}">${cover(item)}<div class="${feature ? 'feature-body' : 'card-body'}"><span class="kicker">${escape(feature ? '发现好内容' : item._section || 'JitAI 文章')}</span><${heading}><a class="article-link stretched" href="${escape(item.url)}" target="_blank" rel="noopener noreferrer" title="${escape(item.title)}" aria-label="${escape(item.title)}（在新标签页打开）">${escape(item.title)}</a></${heading}><p class="summary">${escape(item.summary || '')}</p>${feature ? '' : `<div class="inline-topics">${tags(item)}</div>`}<div class="meta">${meta(item)}</div>${feature ? '<span class="read-link" aria-hidden="true">阅读全文 ↗</span>' : ''}</div></article>`;
  }

  /** 绑定新渲染封面的图片回退；错误只影响单图，不清空列表。 */
  function imageFallback(container) {
    container.querySelectorAll('.cover-image').forEach(img => img.addEventListener('error', () => { img.closest('.cover').classList.remove('has-image'); img.remove(); }, {once:true}));
  }

  /** 只更新顶部推荐，保留控制器焦点和下方列表；自动轮播不打断屏幕阅读器。 */
  function slide(announce = false) {
    if (!order.length) return;
    document.getElementById('feature-slot').innerHTML = article(order[index], true);
    document.getElementById('slide-counter').textContent = `${index + 1} / ${order.length}`;
    document.getElementById('rotation-controls').hidden = order.length < 2;
    if (announce) document.getElementById('slide-announcement').textContent = order[index].title;
    imageFallback(carousel);
  }

  /** 重置单次 12 秒计时；恢复后给予完整阅读时间，避免离开按钮时立即跳页。 */
  function schedule() {
    clearTimeout(timer);
    document.getElementById('rotation-toggle').textContent = paused ? '播放轮播' : '暂停轮播';
    document.getElementById('rotation-status').textContent = paused ? '已暂停' : hover || focus ? '阅读中，已暂停' : '每 12 秒切换';
    if (!paused && !hover && !focus && visible && !document.hidden && !carousel.hidden && order.length > 1) {
      timer = setTimeout(() => { index = (index + 1) % order.length; slide(); schedule(); }, 12000);
    }
  }

  /** 保存可分享的筛选和布局；所有参数留在官网列表 URL，不传向内容来源。 */
  function save() {
    const url = new URL(location.href);
    url.search = '';
    if (category !== '全部') url.searchParams.set('category', category);
    if (topic) url.searchParams.set('topic', topic);
    if (search.value) url.searchParams.set('q', search.value);
    if (layout === 'list') url.searchParams.set('layout', layout);
    history.replaceState(null, '', url);
  }

  /** 更新主题/栏目和匹配列表；有筛选时收起推荐位，空清单给出明确提示。 */
  function render() {
    // 没有发布内容时展示静态空页面，不提示配置故障，也不展示无意义的搜索/筛选/视图按钮。
    document.getElementById('empty-library').hidden = items.length > 0;
    document.querySelectorAll('.library-tools, .filter-row, .results-line, #end-note').forEach(node => { node.hidden = !items.length; });
    const categories = ['全部', ...new Set(items.map(item => item._section).filter(Boolean))];
    const topics = [...new Set(items.flatMap(words))];
    if (!categories.includes(category)) category = '全部';
    if (!topics.includes(topic)) topic = '';
    document.getElementById('filters').innerHTML = categories.map(label => `<button class="filter" type="button" data-category="${escape(label)}" aria-pressed="${label === category}">${escape(label)}</button>`).join('');
    const select = document.getElementById('topic-select');
    select.innerHTML = '<option value="">全部主题</option>' + topics.map(word => `<option value="${escape(word)}">${escape(word)}</option>`).join('');
    select.value = topic;
    const query = search.value.trim().toLowerCase();
    const filtered = items.filter(item => (category === '全部' || item._section === category) && (!topic || words(item).includes(topic)) && `${item.title} ${item.summary || ''} ${words(item).join(' ')}`.toLowerCase().includes(query));
    const hasFilter = Boolean(query || topic || category !== '全部');
    carousel.hidden = hasFilter || !items.length;
    const cards = document.getElementById('cards');
    cards.classList.toggle('list-view', layout === 'list');
    cards.innerHTML = filtered.map(item => article(item)).join('');
    document.getElementById('clear-filters').hidden = !hasFilter;
    document.getElementById('result-count').textContent = `${filtered.length} 篇 · 新标签页阅读 ↗`;
    document.getElementById('list-heading').textContent = hasFilter ? '筛选结果' : '全部文章';
    document.getElementById('status').innerHTML = filtered.length || !items.length ? '' : '<div class="empty-state" role="status"><h2>暂无匹配文章</h2><p>试试其他主题或关键词，或稍后回来看看。</p></div>';
    document.querySelectorAll('[data-layout]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.layout === layout)));
    imageFallback(cards); schedule();
  }

  /** 应用官网主题与深浅 Logo；偏好保存在同域存储，存储被禁用时不影响切换。 */
  function theme() {
    const dark = root.dataset.theme === 'dark';
    document.querySelector('.brand img').src = dark ? root.dataset.logoDark : root.dataset.logoLight;
    document.getElementById('theme').setAttribute('aria-label', dark ? '切换浅色主题' : '切换深色主题');
    document.querySelector('#theme svg').innerHTML = dark
      ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6L19 19M19 5l-1.4 1.4M6.4 17.6L5 19"/>'
      : '<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>';
  }

  /** 同步移动菜单显示、可访问名称与图标；关闭后是否归还焦点由具体触发方式决定。 */
  function setMenu(open) {
    document.getElementById('site-nav').classList.toggle('is-open', open);
    const button = document.getElementById('menu');
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? '关闭导航' : '展开导航');
    button.querySelector('path').setAttribute('d', open ? 'M6 6l12 12M18 6L6 18' : 'M4 7h16M4 12h16M4 17h16');
  }
  document.getElementById('main').addEventListener('click', event => {
    const tag = event.target.closest('[data-topic]');
    const button = event.target.closest('[data-category]');
    if (tag) { topic = tag.dataset.topic; render(); save(); document.getElementById('topic-select').focus(); }
    if (button) { category = button.dataset.category; render(); save(); document.querySelector('#filters [aria-pressed="true"]').focus(); }
  });
  search.addEventListener('input', event => { if (!event.isComposing) { render(); save(); } });
  search.addEventListener('compositionend', () => { render(); save(); });
  document.getElementById('topic-select').addEventListener('change', event => { topic = event.target.value; render(); save(); });
  document.getElementById('clear-filters').addEventListener('click', () => { category = '全部'; topic = ''; search.value = ''; render(); save(); search.focus(); });
  document.getElementById('view-switch').addEventListener('click', event => {
    const button = event.target.closest('[data-layout]');
    if (!button) return;
    layout = button.dataset.layout; render(); save();
    try { localStorage.setItem('jitai-news-layout', layout); } catch { /* 使用本页状态即可。 */ }
  });
  document.getElementById('rotation-controls').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !order.length) return;
    if (button.id === 'rotation-toggle') paused = !paused;
    else { index = (index + (button.id === 'slide-next' ? 1 : -1) + order.length) % order.length; slide(true); }
    schedule();
  });
  carousel.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') { hover = true; schedule(); } });
  carousel.addEventListener('pointerleave', () => { hover = false; schedule(); });
  carousel.addEventListener('focusin', () => { focus = true; schedule(); });
  carousel.addEventListener('focusout', event => { focus = carousel.contains(event.relatedTarget); schedule(); });
  new IntersectionObserver(entries => { visible = entries[0].isIntersecting; schedule(); }).observe(carousel);
  document.addEventListener('visibilitychange', schedule);
  reduceMotion.addEventListener('change', event => { if (event.matches) paused = true; schedule(); });
  window.addEventListener('pagehide', () => clearTimeout(timer));
  window.addEventListener('pageshow', schedule);
  document.getElementById('theme').addEventListener('click', () => { root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark'; theme(); try { localStorage.setItem('jitai-marketing-theme', root.dataset.theme); } catch { /* 可选偏好。 */ } });
  document.getElementById('menu').addEventListener('click', () => setMenu(document.getElementById('menu').getAttribute('aria-expanded') !== 'true'));
  document.getElementById('site-nav').addEventListener('click', () => setMenu(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.getElementById('menu').getAttribute('aria-expanded') === 'true') {
      setMenu(false);
      document.getElementById('menu').focus();
    }
  });
  // 与营销页使用同一断点，跨到桌面后清理移动菜单状态，防止缩回手机时意外展开。
  matchMedia('(min-width: 1181px)').addEventListener('change', event => { if (event.matches) setMenu(false); });
  theme(); slide(); render();
})();
