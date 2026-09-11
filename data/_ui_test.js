// 带 DOM 桩的前端集成测试。
// 覆盖：顺藤摸瓜（原有）+ 质量标签 / 提取码复制 / 跨网盘聚合视图（新增）。
// 不是语法检查 —— 是真的执行 doSearch / renderStatus / renderResults / clusterCard 这条链路。
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)];
const js = blocks.map(m => m[1]).join('\n;\n');

/* ---------------- 极简 DOM 桩 ---------------- */
function makeEl(sel) {
  const el = {
    _sel: sel, children: [], style: {}, dataset: {}, _adj: null,
    className: '', textContent: '', _html: '',
    title: '', value: '', checked: false, disabled: false, href: '', download: '',
    appendChild(c) {
      this.children.push(c);
      // 同步 innerHTML：否则 innerHTML getter 读不到追加的内容，测试看不到错误块
      const tag = c.className ? '<div class="' + c.className + '">' : '<div>';
      this._html += tag + (c.textContent || '') + '</div>';
      return c;
    },
    insertAdjacentElement(_pos, node) { this._adj = node; return node; },
    remove() { this._removed = true; },
    setAttribute() {}, focus() {}, blur() {}, click() { if (this.onclick) this.onclick(); },
    addEventListener() {}, removeEventListener() {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle() {}, contains(c) { return this._s.has(c); },
    },
    select() {}, setSelectionRange() {},
    // 从 innerHTML 里粗略还原带目标属性的元素，让 bindActions 的绑定可被断言
    querySelectorAll(s) {
      const src = this.innerHTML || '';
      const out = [];
      const attr = (s.startsWith('[') && s.endsWith(']')) ? s.slice(1, -1) : null;
      if (!attr) return out;
      const rx = /<(\w+)([^>]*)>/g;
      let m;
      while ((m = rx.exec(src))) {
        const a = new RegExp(attr + '="([^"]*)"').exec(m[2]);
        if (!a) continue;
        const e = makeEl(s);
        const key = attr.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        if (key === 'dataCopy') e.dataset.copy = a[1];
        else if (key === 'dataOpen') e.dataset.open = a[1];
        out.push(e);
      }
      return out;
    },
  };
  Object.defineProperty(el, 'id', {
    get() { return el._id || ''; },
    set(v) { el._id = v; registry.set('#' + v, el); },
  });
  // 真实浏览器里给 innerHTML 赋值会重建子节点，桩必须还原，否则 children 会越积越多
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(v) { el._html = v; el.children = []; },
  });
  return el;
}
const registry = new Map();
const document = {
  querySelector(sel) {
    if (!registry.has(sel)) registry.set(sel, makeEl(sel));
    return registry.get(sel);
  },
  createElement(tag) { return makeEl('<' + tag + '>'); },
  documentElement: { dataset: {} },
  execCommand() { return true; },
};

/* ---------------- 测试数据 ---------------- */
const TAG_HD = [{ t: '1080P', k: 'good' }, { t: '完结', k: 'good' }];
const IT_Q = {
  id: 'a1', cloud: 'quark', cloud_label: '夸克网盘',
  title: '马老师的Java高级工程师就业班', url: 'https://pan.quark.cn/s/aaa',
  pwd: '', rel: 1.0, low: false, score: 99, size: 0, images: [],
  age_days: 3, dt_display: '2026-09-08', source: 'tg', tags: TAG_HD,
};
const IT_B = {
  id: 'a2', cloud: 'baidu', cloud_label: '百度网盘',
  title: '马老师的Java高级工程师就业班【完整版】', url: 'https://pan.baidu.com/s/bbb',
  pwd: 'rb2v', rel: 1.0, low: false, score: 95, size: 0, images: [],
  age_days: 8, dt_display: '2026-09-03', source: 'tg', tags: TAG_HD,
};

const SEARCH_CALLS = [];
const SEARCH_RESP = {
  ok: true, queries: ['风间影月'],
  suggest: ['Java高级工程师'],
  items: [IT_Q, IT_B],
  groups: [
    { cloud: 'quark', label: '夸克网盘', color: '#4f7cff', items: [IT_Q] },
    { cloud: 'baidu', label: '百度网盘', color: '#2b6cff', items: [IT_B] },
  ],
  clusters: [{
    title: '马老师的Java高级工程师就业班', items: [IT_Q, IT_B], n: 2,
    cloud_labels: ['夸克', '百度'], cloud_colors: ['#4f7cff', '#2b6cff'],
    tags: TAG_HD, rel: 1.0, score: 99,
  }],
  stats: {
    total: 2, shown: 2, raw: 2, secs: 1.2, queries: 1, degraded: false, tokens: [],
    cached: false, sources: { 'PanSou · pansou.app': { ok: true, items: 2, cached: false } },
  },
};
/* Response 桩：必须同时提供 text() 与 json()。
   新的 apiGet() 走「先读文本 → 判空 → 判状态 → 再解析」，只给 json() 不够。
   同时保留 json()，因为 loadHistory 等旧路径还在直接调它。 */
function mkResp(text, status) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
    json: async () => JSON.parse(text),
  };
}

// FETCH_MODE 用来模拟各种故障：ok / empty / badjson / http500 / throw / abort / failOnce / hang
let FETCH_MODE = 'ok';
let _failOnceUsed = false;

const fetch = async (url) => {
  const u = String(url);
  if (u.startsWith('/api/search')) SEARCH_CALLS.push(u);

  if (FETCH_MODE === 'throw') throw new TypeError('Failed to fetch');
  if (FETCH_MODE === 'abort') {
    const e = new Error('The user aborted a request.'); e.name = 'AbortError'; throw e;
  }
  if (FETCH_MODE === 'failOnce') {
    if (!_failOnceUsed) { _failOnceUsed = true; throw new TypeError('Failed to fetch'); }
    _failOnceUsed = false;                       // 第二次放行，模拟瞬时抖动恢复
  }
  if (FETCH_MODE === 'empty') return mkResp('', 200);            // 空响应体（用户遇到的场景）
  if (FETCH_MODE === 'http500') return mkResp('', 500);          // 5xx 且无 body
  if (FETCH_MODE === 'http404') return mkResp('', 404);          // 静态服务托管的页面对 /api/* 的 404
  if (FETCH_MODE === 'badjson') return mkResp('<html>Internal Server Error</html>', 500);
  if (FETCH_MODE === 'hang') await new Promise(r => setTimeout(r, 1200));

  if (u.startsWith('/api/search'))
    return mkResp(JSON.stringify(SEARCH_RESP), 200);
  if (u.startsWith('/api/history'))
    return mkResp(JSON.stringify({ ok: true, history: [] }), 200);
  return mkResp(JSON.stringify({ clouds: [], sources: [], version: 'test',
                                 cloud_priority: [] }), 200);
};

const store = {};
const localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
};

/* ---------------- 执行 ---------------- */
const sandbox = {
  document, fetch, localStorage, URLSearchParams,
  navigator: { clipboard: null, userAgent: 'node' },
  location: { href: 'http://127.0.0.1:8931/' },
  window: { isSecureContext: false, open() {} },
  Blob: function () {}, URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
  confirm: () => false, alert() {},
  setTimeout, clearTimeout, console,
  AbortController,          // apiGet 的超时控制依赖它
};
let fail = 0;
function chk(name, cond, extra) {
  if (!cond) { fail++; console.log('FAIL ' + name + (extra ? '  →  ' + extra : '')); }
  else console.log('OK   ' + name);
}

(async () => {
  const fn = new Function(...Object.keys(sandbox),
    js + '\n;return {renderSuggest, renderStatus, renderResults, renderViewbar,'
       + ' clusterCard, tagHtml, allPayload, doSearch, state,'
       + ' apiGet, apiGetRetry, showError, showWaiting, bumpWaiting};');
  const api = fn(...Object.values(sandbox));
  api.state.clouds = [
    { key: 'quark', label: '夸克网盘', color: '#4f7cff' },
    { key: 'baidu', label: '百度网盘', color: '#2b6cff' },
  ];

  /* ---- 一、搜索链路 ---- */
  console.log('[一、搜索链路]');
  registry.get('#main').value = '风间影月';
  await api.doSearch(false);
  chk('搜索后 state.items 有内容', api.state.items.length === 2);
  chk('记录上次查询（供「再挖一次」用）',
      !!api.state.lastQuery && api.state.lastQuery.main === '风间影月');
  chk('缓存了完整响应（供视图切换重渲染）',
      !!api.state.lastResult && api.state.lastResult.groups.length === 2);

  const status = registry.get('#status');
  const box = status._adj;
  chk('建议框已插入状态栏之后', !!box && box.className === 'suggest');
  const chips = box ? box.children.filter(c => c.className === 'chip') : [];
  chk('渲染出 1 个建议按钮', chips.length === 1);
  chk('按钮文字是认出的课程名', chips[0] && chips[0].textContent === 'Java高级工程师',
      chips[0] ? chips[0].textContent : '');
  chk('状态栏有「复制全部」按钮', status.innerHTML.indexOf('id="copyAll"') >= 0);
  chk('状态栏有「再挖一次」按钮', status.innerHTML.indexOf('id="dig"') >= 0);

  SEARCH_CALLS.length = 0;
  chips[0].onclick();
  await new Promise(r => setTimeout(r, 30));
  chk('点击建议后主输入框换词', registry.get('#main').value === 'Java高级工程师');
  chk('点击建议后清掉作者名', registry.get('#author').value === '');
  chk('点击建议后发出新搜索', SEARCH_CALLS.length === 1);

  await api.doSearch(false);   // 回到「风间影月」结果，继续后面的渲染测试

  /* ---- 二、视图切换 ---- */
  console.log('');
  console.log('[二、跨网盘聚合视图]');
  const vbar = registry.get('#viewbar');
  chk('默认视图是按资源聚合', api.state.view === 'resource', api.state.view);
  chk('视图栏显示出来了', vbar.style.display === 'flex');
  const vtabs = vbar.children.filter(c => c.className.indexOf('vtab') >= 0);
  chk('渲染出 2 个视图按钮', vtabs.length === 2);
  chk('默认高亮「按资源聚合」', vtabs[0] && vtabs[0].className.indexOf('on') >= 0);
  chk('视图按钮带数量', vtabs[0] && vtabs[0].textContent === '按资源聚合 1',
      vtabs[0] ? vtabs[0].textContent : '');

  const results = registry.get('#results');
  chk('资源视图渲染出 cluster 块', results.innerHTML.indexOf('class="cluster"') >= 0);
  chk('资源视图不渲染网盘分组', results.innerHTML.indexOf('class="group"') < 0);
  chk('资源视图里两个网盘都在同一块内',
      results.innerHTML.indexOf('夸克网盘') >= 0 && results.innerHTML.indexOf('百度网盘') >= 0);

  vtabs[1].onclick();
  chk('点「按网盘分组」后视图切换', api.state.view === 'cloud');
  chk('视图偏好写进了 localStorage', store['pr-view'] === 'cloud');
  chk('网盘视图渲染出 group 块', results.innerHTML.indexOf('class="group"') >= 0);
  chk('网盘视图不再有 cluster 块', results.innerHTML.indexOf('class="cluster"') < 0);

  const vbar2 = registry.get('#viewbar');
  vbar2.children.filter(c => c.dataset.v === 'resource')[0].onclick();
  chk('切回资源视图', api.state.view === 'resource');
  chk('切回后重新渲染出 cluster', results.innerHTML.indexOf('class="cluster"') >= 0);

  /* ---- 三、质量标签 ---- */
  console.log('');
  console.log('[三、质量标签]');
  chk('tagHtml 生成徽章', api.tagHtml(TAG_HD).indexOf('class="tag good"') >= 0);
  chk('tagHtml 含标签文字', api.tagHtml(TAG_HD).indexOf('1080P') >= 0);
  chk('tagHtml 空输入返回空串', api.tagHtml([]) === '' && api.tagHtml(null) === '');
  chk('warn 标签用 warn 样式',
      api.tagHtml([{ t: '更新中', k: 'warn' }]).indexOf('tag warn') >= 0);
  chk('资源卡里渲染出标签', results.innerHTML.indexOf('>1080P<') >= 0);
  chk('资源卡里渲染出「完结」标签', results.innerHTML.indexOf('>完结<') >= 0);

  /* ---- 四、提取码复制 ---- */
  console.log('');
  console.log('[四、提取码复制]');
  const cc = api.clusterCard(SEARCH_RESP.clusters[0]);
  chk('组内列出网盘名', cc.indexOf('百度网盘') >= 0 && cc.indexOf('夸克网盘') >= 0);
  chk('提取码做成可点击复制', cc.indexOf('data-copy="rb2v"') >= 0);
  chk('有码的按钮写「复制链接+码」', cc.indexOf('复制链接+码') >= 0);
  chk('无码的按钮写「复制链接」', cc.indexOf('>复制链接<') >= 0);
  chk('链接+码 payload 正确',
      cc.indexOf('https://pan.baidu.com/s/bbb 提取码:rb2v') >= 0);
  chk('有「复制本组全部」按钮', cc.indexOf('复制本组全部') >= 0);
  chk('本组全部 payload 含两个网盘',
      cc.indexOf('&#10;') >= 0 && cc.indexOf('夸克网盘') >= 0
      && cc.indexOf('百度网盘') >= 0);
  chk('组头显示分享数与网盘清单', cc.indexOf('2 个分享') >= 0);
  chk('组头显示匹配度', cc.indexOf('匹配 100%') >= 0);

  const cp = api.allPayload(SEARCH_RESP);
  const lines = cp.split('\n');
  chk('复制全部的 payload 有 2 行', lines.length === 2);
  chk('每行含 标题 / 链接 / 提取码',
      lines[1].indexOf('马老师的Java高级工程师就业班') >= 0
      && lines[1].indexOf('https://pan.baidu.com/s/bbb') >= 0
      && lines[1].indexOf('提取码:rb2v') >= 0);

  /* ---- 五、空结果 ---- */
  console.log('');
  console.log('[五、空结果与降级]');
  SEARCH_RESP.groups = []; SEARCH_RESP.clusters = [];
  await api.doSearch(false);
  chk('空结果隐藏视图栏', vbar.style.display === 'none');
  chk('空结果给出引导文案', results.innerHTML.indexOf('都没有命中') >= 0);

  /* ---- 六、请求健壮性（本次修复的核心） ---- */
  console.log('');
  console.log('[六、请求健壮性：断连 / 空响应 / 非 JSON / 超时]');
  // 上一组为测空结果清空了数据，这里恢复
  SEARCH_RESP.groups = [
    { cloud: 'quark', label: '夸克网盘', color: '#4f7cff', items: [IT_Q] },
    { cloud: 'baidu', label: '百度网盘', color: '#2b6cff', items: [IT_B] },
  ];
  SEARCH_RESP.clusters = [{
    title: '马老师的Java高级工程师就业班', items: [IT_Q, IT_B], n: 2,
    cloud_labels: ['夸克', '百度'], cloud_colors: ['#4f7cff', '#2b6cff'],
    tags: TAG_HD, rel: 1.0, score: 99,
  }];
  registry.get('#main').value = '风间影月';
  const errBoxOf = () => results.children.filter(c => c.className === 'err')[0];

  // 1) 空响应体 —— 用户这次遇到的就是它
  FETCH_MODE = 'empty';
  await api.doSearch(false);
  let errBox = errBoxOf();
  chk('空响应时渲染出错误块', !!errBox);
  chk('错误块不再出现 JSON 天书',
      !!errBox && errBox.textContent.indexOf('Unexpected end of JSON') < 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');
  chk('空响应文案说明服务可能正在重启',
      !!errBox && errBox.textContent.indexOf('空响应') >= 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');
  chk('错误块带「重试」按钮',
      !!errBox && errBox.children.some(c => c.id === 'retry'));

  // 2) 点「重试」应重新发起搜索并恢复结果
  FETCH_MODE = 'ok';
  SEARCH_CALLS.length = 0;
  const retryBtn = errBox.children.filter(c => c.id === 'retry')[0];
  retryBtn.onclick();
  await new Promise(r => setTimeout(r, 80));
  chk('点「重试」重新发起了搜索', SEARCH_CALLS.length >= 1, '实际 ' + SEARCH_CALLS.length);
  chk('重试成功后渲染出结果', api.state.items.length === 2);
  chk('重试成功后错误块消失', !errBoxOf());

  // 3) 后端返回 HTML 错误页（非 JSON）
  FETCH_MODE = 'badjson';
  await api.doSearch(false);
  errBox = errBoxOf();
  chk('非 JSON 响应给出「不是合法 JSON」',
      !!errBox && errBox.textContent.indexOf('不是合法 JSON') >= 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');

  // 4) 5xx 且空 body
  FETCH_MODE = 'http500';
  await api.doSearch(false);
  errBox = errBoxOf();
  chk('5xx 空 body 给出可读提示',
      !!errBox && errBox.textContent.indexOf('空响应') >= 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');

  // 5) 连不上后端（服务没起来）
  FETCH_MODE = 'throw';
  await api.doSearch(false);
  errBox = errBoxOf();
  chk('连不上后端时提示确认服务在运行',
      !!errBox && errBox.textContent.indexOf('无法连接后端服务') >= 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');

  // 6) 超时（AbortError）
  FETCH_MODE = 'abort';
  await api.doSearch(false);
  errBox = errBoxOf();
  chk('超时提示「请求超时」并建议重试',
      !!errBox && errBox.textContent.indexOf('请求超时') >= 0,
      errBox ? errBox.textContent.slice(0, 70) : '无');

  // 7) 瞬时失败一次 → 自动重试成功（服务刚重启时的典型场景）
  FETCH_MODE = 'failOnce'; _failOnceUsed = false;
  SEARCH_CALLS.length = 0;
  await api.doSearch(false);
  chk('瞬时断连自动重试（共 2 次请求）', SEARCH_CALLS.length === 2,
      '实际 ' + SEARCH_CALLS.length);
  chk('自动重试后正常渲染，不弹错误', !errBoxOf() && api.state.items.length === 2);

  // 8) 等待期间的进度提示（长搜索不能看起来像卡死）
  FETCH_MODE = 'hang';
  const pending = api.doSearch(false);
  await new Promise(r => setTimeout(r, 80));
  const waitEl = registry.get('#waitmsg');
  chk('搜索中渲染出等待提示', !!waitEl && waitEl.textContent.indexOf('正在') >= 0,
      waitEl ? waitEl.textContent : '无');
  await new Promise(r => setTimeout(r, 1150));
  chk('等待超过 1 秒后显示「已等待 N 秒」',
      !!waitEl && waitEl.textContent.indexOf('已等待') >= 0,
      waitEl ? waitEl.textContent : '无');
  await pending;
  chk('等待结束后正常渲染结果', api.state.items.length === 2);
  FETCH_MODE = 'ok';

  /* —— 故障场景：/api/* 返回 404（页面被静态预览托管） —— */
  console.log('-- http404（页面被静态预览托管） --');
  FETCH_MODE = 'http404';
  SEARCH_CALLS.length = 0;
  await api.doSearch(false);
  const err404 = registry.get('#results');
  const html404 = err404 ? err404.innerHTML : '';
  chk('404 时结果区渲染错误块', err404 && html404.indexOf('err') >= 0, html404.slice(0, 120));
  chk('错误提示提到「不是由 panradar.py 提供」',
      err404 && html404.indexOf('panradar.py') >= 0);
  chk('错误提示提到默认地址 8931（引导用户开对地址）',
      err404 && html404.indexOf('8931') >= 0);
  chk('404 时不调用 apiGetRetry 重试（避免无效循环）',
      SEARCH_CALLS.length === 1, '实际 ' + SEARCH_CALLS.length);
  FETCH_MODE = 'ok';

  console.log('-'.repeat(60));
  console.log('失败用例数: ' + fail);
  process.exit(fail ? 1 : 0);
})();
