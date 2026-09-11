
const $ = s => document.querySelector(s);
const state = { clouds:[], selected:new Set(), items:[], meta:null, sort:'relevance',
                lastQuery:null };

/* ---------- 主题 ---------- */
const savedTheme = localStorage.getItem('pr-theme');
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$('#themeBtn').onclick = () => {
  const cur = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = cur;
  localStorage.setItem('pr-theme', cur);
};

/* ---------- 初始化 ---------- */
async function init(){
  const m = await (await fetch('/api/meta')).json();
  state.meta = m;
  $('#ver').textContent = 'v' + m.version;
  state.clouds = m.clouds;
  const savedSel = localStorage.getItem('pr-clouds');
  state.selected = new Set(savedSel ? JSON.parse(savedSel)
                                    : m.clouds.map(c => c.key));
  renderCloudChips();
  loadHistory();
}
function renderCloudChips(){
  const box = $('#cloudChips'); box.innerHTML = '';
  state.clouds.forEach(c => {
    const b = document.createElement('div');
    b.className = 'chip' + (state.selected.has(c.key) ? ' on' : '');
    b.textContent = c.label;
    if (state.selected.has(c.key)) b.style.background = c.color;
    b.onclick = () => {
      state.selected.has(c.key) ? state.selected.delete(c.key) : state.selected.add(c.key);
      localStorage.setItem('pr-clouds', JSON.stringify([...state.selected]));
      renderCloudChips();
    };
    box.appendChild(b);
  });
}
$('#onlyMain').onclick = () => {
  state.selected = new Set(['baidu','quark','aliyun']);
  localStorage.setItem('pr-clouds', JSON.stringify([...state.selected]));
  renderCloudChips();
};
$('#allClouds').onclick = () => {
  state.selected = new Set(state.clouds.map(c => c.key));
  localStorage.setItem('pr-clouds', JSON.stringify([...state.selected]));
  renderCloudChips();
};

/* ---------- 搜索 ---------- */
$('#go').onclick = doSearch;
['main','author'].forEach(id => $('#'+id).addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
}));
$('#sort').onchange = e => { state.sort = e.target.value; doSearch(true); };

async function doSearch(reuse, refresh){
  const main = $('#main').value.trim(), author = $('#author').value.trim();
  if (!main && !author) { $('#main').focus(); return; }
  localStorage.setItem('pr-last', JSON.stringify({main, author}));

  const goBtn = $('#go'), digBtn = $('#dig');
  goBtn.disabled = true; if (digBtn) digBtn.disabled = true;
  $('#status').innerHTML = '';
  const stale = $('#suggest'); if (stale) stale.remove();
  $('#results').innerHTML = '<div class="empty"><div class="spinner"></div>'
    + (refresh ? '正在重新挖掘各源并合并新结果，通常 10–30 秒…'
               : '正在并发查询各搜索源，通常 5–15 秒…') + '</div>';

  const q = new URLSearchParams({
    main, author,
    deep: $('#deep').checked ? '1' : '0',
    refresh: refresh ? '1' : '0',
    sort: state.sort,
    clouds: [...state.selected].join(',')
  });
  const t0 = Date.now();
  try {
    const r = await (await fetch('/api/search?' + q)).json();
    if (!r.ok) throw new Error(r.error || '搜索失败');
    state.items = r.items;
    state.lastQuery = {main, author};
    renderStatus(r, Date.now() - t0);
    renderResults(r);
    loadHistory();
  } catch (e) {
    $('#results').innerHTML = '<div class="err">⚠️ ' + esc(e.message) + '</div>';
    $('#status').innerHTML = '';
  } finally {
    goBtn.disabled = false; if (digBtn) digBtn.disabled = false;
  }
}

/* 「再挖一次」：跳过缓存重新查询，新结果并入已有缓存（越挖越全） */
function digMore(){
  if (!state.lastQuery) return;
  if (state.lastQuery.main) $('#main').value = state.lastQuery.main;
  if (state.lastQuery.author) $('#author').value = state.lastQuery.author;
  doSearch(true, true);
}

function renderStatus(r, wall){
  const st = r.stats, parts = [];
  parts.push(`<span>命中 <b style="color:var(--text)">${st.total}</b> 条`
    + `（去重后展示 ${st.shown}，原始 ${st.raw}）</span>`);
  parts.push(`<span>耗时 ${st.secs}s</span>`);
  parts.push(`<span>${st.cached ? '⚡ 缓存命中' : '关键词 ' + st.queries + ' 组'}</span>`);
  if (st.degraded) parts.push(`<span style="color:var(--warn)">↯ 完整短语无结果，已自动降级分词：${esc((st.tokens||[]).join(' / '))}</span>`);
  if (r.queries && r.queries.length)
    parts.push(`<span style="opacity:.75">查询词：${esc(r.queries.join(' / '))}</span>`);
  if (st.total > 0 && st.total < 8)
    parts.push(`<span style="opacity:.75">结果偏少？点「再挖一次」，新一批会并入累积</span>`);
  for (const [name, v] of Object.entries(st.sources || {})) {
    const col = v.ok ? 'var(--ok)' : 'var(--err)';
    const txt = v.ok ? `${v.items} 条${v.cached ? ' (缓存)' : ''}`
                     : esc((v.error||'失败').slice(0,40));
    parts.push(`<span class="srcstat"><i class="dot" style="background:${col}"></i>`
      + `${esc(name)}：${txt}</span>`);
  }
  const dig = document.createElement('button');
  parts.push('<button class="btn" id="dig">⟳ 再挖一次</button>');
  $('#status').innerHTML = parts.join('');
  const digEl = $('#dig');
  if (digEl) digEl.onclick = digMore;
  renderSuggest(r.suggest);
}

/* 「顺藤摸瓜」：搜作者名常常只出几条 —— 因为资源是按**课程名**索引的。
   后端从已搜到的标题里认出「除了搜索词之外的名字」（如搜「风间影月」认出
   「Java高级工程师」），点一下换个词再搜，命中量往往翻几十倍。 */
function renderSuggest(topics){
  const old = $('#suggest'); if (old) old.remove();
  if (!topics || !topics.length) return;
  const box = document.createElement('div');
  box.className = 'suggest'; box.id = 'suggest';
  const label = document.createElement('span');
  label.className = 'sg-label';
  label.textContent = '💡 顺藤摸瓜：从搜到的标题里认出了这些名字，点一下换它再搜';
  box.appendChild(label);
  topics.forEach(t => {
    const b = document.createElement('button');
    b.className = 'chip'; b.textContent = t;
    b.title = '用「' + t + '」重新搜索';
    b.onclick = () => { $('#main').value = t; $('#author').value = ''; doSearch(false); };
    box.appendChild(b);
  });
  $('#status').insertAdjacentElement('afterend', box);
}

function renderResults(r){
  const box = $('#results');
  if (!r.groups.length){
    box.innerHTML = '<div class="empty">各数据源都没有命中（已包含自动分词降级搜索）。<br>'
      + '可以试试：<br>· 换更短的课程名，去掉书名号 / 引号 / 标点<br>'
      + '· 只填其中一个关键词（比如只填「创造营」或只填「AI产品」）<br>'
      + '· 勾选「深度搜索」<br>'
      + '· 在 <code>config.json</code> 里多加几个数据源，或 Docker 自建 PanSou 当主源</div>';
    return;
  }
  let html = '';
  r.groups.forEach(g => {
    html += `<div class="group"><div class="ghead">`
      + `<i class="bar" style="background:${g.color}"></i>${esc(g.label)}`
      + `<span class="n">${g.items.length} 条</span></div>`;
    g.items.forEach(it => { html += card(it, g.color); });
    html += '</div>';
  });
  box.innerHTML = html;
  box.querySelectorAll('[data-copy]').forEach(b => b.onclick = () => copy(b));
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => {
    window.open(b.dataset.open, '_blank', 'noopener');
  });
}

function fmtSize(n){
  if (!n || n <= 0) return '';
  const u = ['B','KB','MB','GB','TB']; let i = 0; n = Number(n);
  while (n >= 1024 && i < u.length - 1){ n /= 1024; i++; }
  return (n >= 100 ? Math.round(n) : n.toFixed(1)) + u[i];
}

function card(it, color){
  const dt = it.dt_display || '日期未知';
  const age = (it.age_days != null) ? `${it.age_days} 天前` : '';
  const pwd = it.pwd ? `<span class="pwd">提取码 ${esc(it.pwd)}</span>` : '';
  const size = fmtSize(it.size);
  const rel = (it.rel != null) ? `${Math.round(it.rel * 100)}%` : '';
  const img = (it.images && it.images[0])
    ? `<img class="thumb" src="${esc(it.images[0])}" referrerpolicy="no-referrer"
         onerror="this.style.display='none'">` : '';
  const payload = it.pwd ? `${it.url} 提取码:${it.pwd}` : it.url;
  return `<div class="card">${img}<div class="cbody">
      <div class="title" title="${esc(it.title || '')}">${esc(it.title || '(无标题)')}</div>
      <div class="meta">
        <span style="color:${color};font-weight:600">${esc(it.cloud_label)}</span>
        ${pwd}
        ${size ? `<span>${size}</span>` : ''}
        <span>${esc(dt)}${age ? ' · ' + age : ''}</span>
        ${rel ? `<span>匹配 ${rel}</span>` : ''}
        ${it.low ? '<span style="opacity:.6">低相关</span>' : ''}
        ${it.source ? `<span>${esc(it.source.replace('plugin:',''))}</span>` : ''}
      </div>
      <div class="link">${esc(it.url)}</div>
    </div>
    <div class="acts">
      <button class="btn" data-copy="${esc(payload)}">复制链接</button>
      <button class="btn" data-open="${esc(it.url)}">打开</button>
    </div></div>`;
}

function copy(btn){
  const text = btn.dataset.copy;
  const done = () => {
    const old = btn.textContent; btn.textContent = '✓ 已复制'; btn.classList.add('done');
    setTimeout(() => { btn.textContent = old; btn.classList.remove('done'); }, 1400);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}
function fallbackCopy(text, done){
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); done(); } catch(e) { alert('复制失败，请手动选择'); }
  document.body.removeChild(ta);
}

/* ---------- 导出 ---------- */
async function exportAs(fmt){
  if (!state.items.length) { alert('还没有搜索结果'); return; }
  const r = await fetch('/api/export', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({fmt, items: state.items})
  });
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `panradar-${new Date().toISOString().slice(0,10)}.${fmt}`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
$('#expMd').onclick = () => exportAs('md');
$('#expCsv').onclick = () => exportAs('csv');

/* ---------- 历史 / 缓存 ---------- */
async function loadHistory(){
  try{
    const r = await (await fetch('/api/history')).json();
    const box = $('#hist');
    if (!r.history || !r.history.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<span class="lbl" style="font-size:12px;color:var(--muted)">最近：</span>'
      + r.history.map(h => `<span class="h" data-m="${esc(h.main)}" data-a="${esc(h.author)}">`
        + `${esc(h.main || h.author)}<span style="opacity:.55"> · ${h.hits}</span></span>`).join('');
    box.querySelectorAll('.h').forEach(el => el.onclick = () => {
      $('#main').value = el.dataset.m; $('#author').value = el.dataset.a; doSearch();
    });
  }catch(e){}
}
$('#clearCache').onclick = async () => {
  await fetch('/api/cache/clear');
  const b = $('#clearCache'); b.textContent = '已清除'; setTimeout(() => b.textContent = '清缓存', 1200);
};

function esc(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/* ---------- 启动 ---------- */
init().then(() => {
  const last = localStorage.getItem('pr-last');
  if (last) { try{ const o = JSON.parse(last); $('#main').value = o.main||''; $('#author').value = o.author||''; }catch(e){} }
  $('#main').focus();
});
