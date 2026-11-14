'use strict';
// Bunny Save UI: vanilla JS. DOM is built with h() (never innerHTML) so file names can't inject markup.
const $ = (s, r = document) => r.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
const P = { // 24x24 stroke icons (18px, 1.8 stroke, round caps) - no emoji, no icon fonts
  plus: 'M12 5v14M5 12h14', x: 'M18 6 6 18M6 6l12 12', check: 'M20 6 9 17l-5-5', chev: 'm9 18 6-6-6-6',
  trash: 'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6', download: 'M12 3v12M7 10l5 5 5-5M5 21h14', upload: 'M12 15V3M7 8l5-5 5 5M5 21h14',
  play: 'M7 4l13 8-13 8z', stop: 'M6 6h12v12H6z', save: 'M5 3h11l3 3v15H5zM8 3v5h7V3M8 21v-7h8v7',
  folder: 'M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
  filetext: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6',
  filecode: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M10 13l-2 2 2 2M14 13l2 2-2 2',
  image: 'M4 5h16v14H4zM8.5 10.5h.01M20 16l-5-5-8 8', film: 'M3 5h18v14H3zM7 5v14M17 5v14M3 10h4M3 14h4M17 10h4M17 14h4',
  music: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  archive: 'M3 4h18v4H3zM5 8v12h14V8M10 12h4', pkg: 'M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4', key: 'M14 10a4 4 0 1 0-3.5 4L14 17.5V20h2.5v-2.5H19V15l-2-2z',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  restore: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5', shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4',
  shieldx: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9.5 9.5l5 5M14.5 9.5l-5 5',
  server: 'M3 4h18v6H3zM3 14h18v6H3zM7 7h.01M7 17h.01', drive: 'M3 14l3-9h12l3 9v5H3zM3 14h18M7 17h.01',
  globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2', term: 'M4 5h16v14H4zM8 10l3 2-3 2M13 15h4',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4', alert: 'M12 3l10 18H2zM12 10v5M12 18h.01',
  plug: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM8 12l3 3 5-6', pin: 'M12 17v5M8 3h8l-1 6 3 3H6l3-3z', copy: 'M9 9h11v11H9zM5 15V4h11',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01', pencil: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4', skip: 'M5 4l10 8-10 8zM19 5v14',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8h.01', db: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  box: 'M4 4h16v16H4zM9 4v6h6V4',
};
function ico(n) {
  const s = document.createElementNS(NS, 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'i'); s.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS(NS, 'path'); p.setAttribute('d', P[n] || P.file); s.append(p); return s;
}
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'value') e.value = v;
    else if (k === 'checked') e.checked = !!v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}
const api = async (method, url, body) => {
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
};
const fmtSize = n => { if (n == null) return ''; const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + ' ' + u[i]; };
// Mobile Chrome offers its password manager on text inputs that sit near a password field, and the soft keyboard's
// "Next" action moves focus instead of firing Enter. These attributes opt out of both.
const NOAUTO = { autocomplete: 'off', autocapitalize: 'off', autocorrect: 'off', spellcheck: 'false', enterkeyhint: 'done', 'data-lpignore': 'true', 'data-1p-ignore': 'true', 'data-form-type': 'other' };
const MASK_OK = typeof CSS !== 'undefined' && CSS.supports && CSS.supports('-webkit-text-security', 'disc');
// masked text field that Chrome does not treat as a login password (falls back to type=password elsewhere)
const secretInput = (attrs = {}) => h('input', { ...NOAUTO, ...attrs, type: MASK_OK ? 'text' : 'password', class: (attrs.class || '') + (MASK_OK ? ' secret' : ''), ...(MASK_OK ? {} : { autocomplete: 'new-password' }) });
const state = { info: null, setups: [], cur: null, tab: 'setup', poll: null };

// ------------------------------------------------------------ building blocks
const btn = (icon, label, o = {}) => h('button', { type: 'button', class: 'btn ' + (o.cls || ''), onclick: o.onclick, title: o.title, disabled: o.disabled }, icon ? ico(icon) : null, label ? h('span', {}, label) : null);
const ib = (icon, title, onclick, cls = '') => h('button', { type: 'button', class: 'ib ' + cls, title, 'aria-label': title, onclick }, ico(icon));
function sec(title, icon, body, { open = false, summary = '', inner = false } = {}) {
  const sum = h('span', { class: 'sum' }, summary);
  const d = h('details', { class: 'sec' + (inner ? ' inner' : ''), open }, h('summary', {}, icon ? ico(icon) : null, title, sum, h('span', { class: 'chev' }, ico('chev'))), h('div', { class: 'body' }, body));
  d.setSummary = t => { sum.textContent = t; }; return d;
}
function seg(opts, value, onchange) {
  let cur = value; const el = h('div', { class: 'seg', role: 'group' });
  const bs = opts.map(o => { const b = h('button', { type: 'button', 'aria-pressed': String(o.v === cur), title: o.title || o.label, onclick: () => { cur = o.v; bs.forEach(x => x.b.setAttribute('aria-pressed', String(x.v === cur))); if (onchange) onchange(cur); } }, ico(o.icon), h('span', {}, o.label)); el.append(b); return { v: o.v, b }; });
  return { el, get: () => cur };
}
function toast(msg, kind = '', ms = 3500) {
  const t = h('div', { class: 'toast ' + kind }, ico(kind === 'err' ? 'alert' : kind === 'ok' ? 'check' : 'info'), h('span', {}, msg)); $('#toasts').append(t); setTimeout(() => t.remove(), ms);
}
function modal(title, icon, ...body) {
  const d = $('#modal'); $('#modal-body').replaceChildren(h('div', { class: 'mh' }, ico(icon), title), h('div', { class: 'mb' }, ...body)); if (!d.open) d.showModal();
}
function alertMsg(msg) { const a = $('#alert'); a.replaceChildren(); a.hidden = !msg; a.className = msg ? 'alert' : ''; if (msg) { a.append(ico('alert'), h('span', {}, msg)); a.scrollIntoView({ block: 'nearest' }); } }
const guard = fn => async ev => {
  const b = ev && ev.currentTarget && ev.currentTarget.tagName === 'BUTTON' ? ev.currentTarget : null;
  if (b) { b.disabled = true; b.classList.add('busy'); }
  try { alertMsg(''); await fn(ev); } catch (e) { alertMsg(e.message); toast(e.message, 'err', 6000); }
  finally { if (b) { b.disabled = false; b.classList.remove('busy'); } }
};
const spinner = text => h('p', { class: 'muted' }, h('span', { class: 'spin' }), text);

// ------------------------------------------------------------ sidebar / tabs
const TABS = [['setup', 'sliders', 'Setup'], ['run', 'play', 'Run'], ['history', 'archive', 'Backups']];
async function loadSetups(selectId) {
  state.setups = await api('GET', '/api/setups');
  const ul = $('#setup-list'); ul.replaceChildren();
  for (const s of state.setups) ul.append(h('li', {}, h('button', { 'aria-current': String(!!state.cur && state.cur.id === s.id), onclick: () => openSetup(s.id) },
    s.name, s.next_run ? h('div', { class: 'sub' }, ico('clock'), new Date(s.next_run).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })) : null)));
  if (selectId) openSetup(selectId);
}
function openSetup(id) {
  state.cur = id ? state.setups.find(s => s.id === id) : null;
  if (id && !state.cur) return;
  clearInterval(state.poll);
  $('#empty').hidden = true; $('#work').hidden = false;
  $('#title').textContent = state.cur ? state.cur.name : 'New setup';
  state.setups.forEach((s, i) => $('#setup-list').children[i].firstChild.setAttribute('aria-current', String(!!state.cur && s.id === state.cur.id)));
  showTab(state.cur ? state.tab : 'setup');
}
function showTab(t) {
  state.tab = t; alertMsg('');
  for (const b of $('.tabs').children) { b.setAttribute('aria-selected', String(b.dataset.tab === t)); b.disabled = !state.cur && b.dataset.tab !== 'setup'; }
  for (const n of ['setup', 'run', 'history']) $('#tab-' + n).hidden = n !== t;
  ({ setup: renderEditor, run: renderRun, history: renderHistory })[t]();
}

// ------------------------------------------------------------ path list (one entry per row)
function parsePathLines(text, allowSkeleton) {
  const out = [];
  for (let l of text.split(/\r?\n/)) {
    l = l.trim(); if (!l || l.startsWith('#') || l.startsWith('//')) continue;
    let skel = false; if (allowSkeleton && /^skeleton:/i.test(l)) { skel = true; l = l.slice(9).trim(); }
    if (l) out.push({ path: l, skeleton: skel });
  }
  return out;
}
function pathList(items, { skeleton, placeholder, onchange }) {
  const rows = [], list = h('div', { class: 'prows' }), changed = () => onchange && onchange(rows.length);
  function add(path, skel) {
    path = path.trim(); if (!path || rows.some(r => r.path === path)) return false;
    const r = { path, skel: !!skel, badge: h('span', { class: 'badge muted' }) };
    r.el = h('div', { class: 'prow' + (skeleton ? '' : ' noskel') },
      h('input', { ...NOAUTO, class: 'mono', value: path, 'aria-label': 'Path', oninput: e => { r.path = e.target.value; r.badge.textContent = ''; } }),
      skeleton ? h('label', { title: 'Store only the directory itself and its permissions, no contents', class: 'small' }, h('input', { type: 'checkbox', checked: r.skel, onchange: e => { r.skel = e.target.checked; } }), 'skeleton') : null,
      r.badge, ib('x', 'Remove', () => { r.el.remove(); rows.splice(rows.indexOf(r), 1); changed(); }));
    list.append(r.el); rows.push(r); return true;
  }
  const addText = text => { let n = 0; for (const e of parsePathLines(text, skeleton)) if (add(e.path, e.skeleton)) n++; changed(); return n; };
  (items || []).forEach(i => add(typeof i === 'string' ? i : i.path, i.skeleton));
  const commit = () => { if (!quick.value.trim()) return; if (!addText(quick.value)) toast('Already in the list'); quick.value = ''; list.scrollTop = list.scrollHeight; quick.focus(); };
  const quick = h('input', { ...NOAUTO, class: 'mono', placeholder, 'aria-label': 'Add path',
    onkeydown: e => { if (e.key === 'Enter' || e.keyCode === 13) { e.preventDefault(); commit(); } },
    onpaste: e => { const t = e.clipboardData.getData('text'); if (/\n/.test(t)) { e.preventDefault(); toast(`Added ${addText(t)} path(s)`, 'ok'); } } });
  const file = h('input', { type: 'file', accept: '.txt,text/plain', hidden: true, onchange: async e => { const f = e.target.files[0]; if (f) toast(`Imported ${addText(await f.text())} path(s) from ${f.name}`, 'ok'); e.target.value = ''; } });
  const el = h('div', {}, list, h('div', { class: 'row' }, h('div', { class: 'grow', style: 'min-width:200px' }, quick), ib('plus', 'Add path', commit), ib('upload', 'Import a .txt list (skips blank lines and lines starting with # or //)', () => file.click()), file));
  return { el, count: () => rows.length,
    get: () => rows.map(r => ({ path: r.path.trim(), skeleton: r.skel })).filter(r => r.path).map(r => skeleton ? r : r.path),
    results(items) {
      for (const r of rows) {
        const it = items.find(i => i.path === r.path.trim()); if (!it) continue; let t, c;
        if (it.error) { t = it.error; c = 'bad'; } else if (!it.exists) { t = 'not found'; c = 'bad'; }
        else if (it.skeleton) { t = it.dirs ? 'directory' : 'not a directory'; c = it.dirs ? 'ok' : 'warn'; }
        else { t = `${it.matches > 1 ? it.matches + ' matches · ' : ''}${fmtSize(it.bytes)}${it.partial ? '+' : ''} · ${it.files} files`; c = 'ok'; }
        r.badge.textContent = (c === 'ok' ? '✓ ' : c === 'bad' ? '✗ ' : '⚠ ') + t; r.badge.className = 'badge small ' + c;
      }
    } };
}

// ------------------------------------------------------------ editor
const blankCfg = () => ({ name: '', format: 'tar.gz', level: 6, preserve_permissions: false, target_dir: '', space_ratio: 1,
  sources: [{ type: 'local', includes: [], excludes: [] }], encryption: { enabled: false, tool: 'gpg', mode: 'passphrase', secret_mode: 'prompt' },
  schedule: { type: 'none', hours: 24, time: '03:00' }, retention: { type: 'keep_all', n: 7, daily: 7, weekly: 4, monthly: 12, yearly: 0 },
  hooks: { pre: { command: '', timeout: 300 }, post: { command: '', timeout: 300 } }, post_restore: [] });
const lines = t => t.split('\n').map(l => l.trim()).filter(Boolean);

function renderEditor() {
  const root = $('#tab-setup'); root.replaceChildren();
  const cfg = JSON.parse(JSON.stringify(state.cur ? state.cur.config : blankCfg()));
  const cap = state.info.capabilities, F = {};
  const inp = (key, label, attrs = {}) => { F[key] = h('input', attrs); return h('label', {}, label, F[key]); };
  const sel = (key, label, opts, val, on) => { F[key] = h('select', { onchange: on }, opts.map(o => h('option', { value: o[0], selected: o[0] === val }, o[1]))); return h('label', {}, label, F[key]); };
  const sums = [];

  // General
  F.perm = h('input', { type: 'checkbox', checked: cfg.preserve_permissions });
  const general = sec('General', 'sliders', [
    h('div', { class: 'grid' }, inp('name', 'Name', { value: cfg.name, required: true }),
      sel('format', 'Format', [['tar.gz', 'tar.gz'], ['tar.zst', 'tar.zst' + (cap.zstd ? '' : ' (zstd missing)')], ['tar.bz2', 'tar.bz2'], ['zip', 'zip' + (cap.zip_aes ? '' : ' (pyzipper missing)')]], cfg.format, () => { encSync(); sumSync(); }),
      inp('level', 'Compression level', { type: 'number', value: cfg.level, min: 0, max: 19, title: 'gz/bz2 1-9, zst 1-19, zip 0-9' })),
    h('label', { class: 'chk' }, F.perm, 'Preserve permissions (mode, owner/group where possible)'),
    sec('Advanced', null, h('div', { class: 'grid' },
      inp('target_dir', 'Target directory', { value: cfg.target_dir, placeholder: '/data/backups' }),
      inp('space_ratio', 'Expected size ratio (free-space check)', { type: 'number', step: '0.05', min: '0.05', max: '1.5', value: cfg.space_ratio, title: '1 = worst case, no compression assumed' })), { inner: true }),
  ], { open: true });

  // Sources
  const srcBox = h('div'), srcCards = [];
  const addSource = (s, open) => {
    const f = { id: s.id };
    let type = s.type || 'local', auth = s.auth || 'password';
    const typeOpts = [{ v: 'local', icon: 'box', label: 'Container', title: "This container's filesystem" }];
    if (cap.host_root || type === 'host') typeOpts.push({ v: 'host', icon: 'drive', label: 'Host', title: 'Host filesystem (mounted into the container)' });
    typeOpts.push({ v: 'sftp', icon: 'globe', label: 'SFTP', title: 'SFTP server (also over Tailscale)' });
    f.type = seg(typeOpts, type, v => { type = v; rebuild(); });
    f.auth = seg([{ v: 'password', icon: 'lock', label: 'Password' }, { v: 'key', icon: 'key', label: 'Key file' }, { v: 'tailscale', icon: 'globe', label: 'Tailscale SSH', title: 'No credentials: the tailnet identity authenticates' }], auth, v => { auth = v; rebuild(); });
    f.host = h('input', { ...NOAUTO, value: s.host || '', placeholder: '100.x.y.z or name.tailnet.ts.net', oninput: () => sync() });
    f.port = h('input', { type: 'number', value: s.port || 22 }); f.username = h('input', { ...NOAUTO, value: s.username || '', oninput: () => sync() });
    f.key_path = h('input', { ...NOAUTO, value: s.key_path || '', placeholder: '/data/keys/id_ed25519' });
    f.secret_mode = h('select', {}, [['prompt', 'Prompt on each run'], ['keyring', 'OS keyring']].map(o => h('option', { value: o[0], selected: o[0] === (s.secret_mode || 'prompt') }, o[1])));
    f.testpw = secretInput({ placeholder: 'only used for the test, never saved' });
    f.includes = pathList(s.includes, { skeleton: true, placeholder: '/opt/myapp/*  (Enter adds, then type the next path)', onchange: () => sync() });
    f.excludes = pathList(s.excludes, { skeleton: false, placeholder: '*.tmp   or   /opt/myapp/cache', onchange: () => sync() });
    f.status = h('span', { class: 'small', 'aria-live': 'polite' });
    f.sftp = h('div', {}, h('div', { class: 'grid' }, h('label', {}, 'Host', f.host), h('label', {}, 'Port', f.port), h('label', {}, 'Username', f.username)),
      h('div', { class: 'row', style: 'margin-bottom:12px' }, f.auth.el), (f.keyrow = h('label', {}, 'Key file (inside the container)', f.key_path)),
      (f.secretrow = h('label', {}, 'Secret source', f.secret_mode)));
    f.testpwrow = h('label', {}, 'Password / key passphrase for the test', f.testpw);
    f.collect = () => ({ id: f.id, type, host: f.host.value, port: +f.port.value, username: f.username.value, auth, key_path: f.key_path.value, secret_mode: f.secret_mode.value, includes: f.includes.get(), excludes: f.excludes.get() });
    const rebuild = () => { const sftp = type === 'sftp'; f.sftp.hidden = !sftp; f.keyrow.hidden = auth !== 'key'; f.secretrow.hidden = auth === 'tailscale'; f.testpwrow.hidden = !(sftp && auth !== 'tailscale'); sync(); };
    const test = guard(async () => {
      f.status.replaceChildren(h('span', { class: 'spin' }), 'Checking paths…');
      let r; try { r = await api('POST', '/api/test-source', { source: f.collect(), secrets: auth === 'key' ? { key_passphrase: f.testpw.value } : { password: f.testpw.value } }); } catch (e) { f.status.replaceChildren(h('span', { class: 'bad' }, e.message)); throw e; }
      if (!r.connected) { f.status.replaceChildren(h('span', { class: 'bad' }, 'Connection failed: ' + r.error)); toast('Connection failed', 'err'); return; }
      f.includes.results(r.items);
      const bad = r.items.filter(i => !i.exists || i.error).length, tot = r.items.reduce((a, i) => a + i.bytes, 0);
      f.status.replaceChildren(h('span', { class: bad ? 'warn' : 'ok' }, `${r.items.length - bad}/${r.items.length} paths found · ~${fmtSize(tot)}`));
      toast(bad ? `${bad} path(s) not found` : 'All paths valid', bad ? 'err' : 'ok');
    });
    const sync = () => { const n = f.includes.count(); card.setSummary(`${type === 'sftp' ? (f.username.value ? f.username.value + '@' : '') + (f.host.value || 'sftp') : type === 'host' ? 'host' : 'container'} · ${n} path${n === 1 ? '' : 's'}`); };
    const exSec = sec('Excludes', null, f.excludes.el, { inner: true });
    const body = [f.type.el, h('div', { style: 'height:14px' }), f.sftp, h('div', { class: 'hint' }, ico('info'), type === 'host' ? 'Host paths, as on the host.' : 'Paths as seen by the source.'), f.includes.el, h('div', { style: 'height:10px' }), exSec, f.testpwrow,
      h('div', { class: 'row', style: 'margin-top:12px' }, btn('plug', 'Test validity', { onclick: test, cls: 'sm', title: 'Connect, check every path and estimate its size' }), f.status,
        h('span', { class: 'grow' }), btn('trash', '', { cls: 'sm danger', title: 'Remove source', onclick: () => { card.remove(); srcCards.splice(srcCards.indexOf(f), 1); toast('Source removed'); } }))];
    const card = sec('Source', null, body, { open, inner: true }); card.classList.add('src');
    f.card = card; srcCards.push(f); srcBox.append(card); rebuild();
  };
  cfg.sources.forEach((s, i) => addSource(s, i === 0 && cfg.sources.length === 1));
  const sources = h('div', { class: 'card span-all' }, h('h3', {}, ico('server'), 'Sources'), srcBox, btn('plus', 'Add source', { cls: 'sm', onclick: () => addSource({ type: 'local', includes: [], excludes: [] }, true) }));

  // Encryption (details only when relevant)
  const e = cfg.encryption; let tool = e.tool || 'gpg', mode = e.mode || 'passphrase';
  F.enc = h('input', { type: 'checkbox', checked: e.enabled, onchange: () => encSync() });
  const toolSeg = seg([{ v: 'gpg', icon: 'lock', label: 'gpg' }, { v: 'age', icon: 'key', label: 'age' }], tool, v => { tool = v; encSync(); });
  const modeSeg = seg([{ v: 'passphrase', icon: 'key', label: 'Password' }, { v: 'recipient', icon: 'shield', label: 'Public key' }], mode, v => { mode = v; encSync(); });
  const encBox = h('div', {}, h('div', { class: 'row', style: 'margin-bottom:12px' }, toolSeg.el, modeSeg.el),
    h('div', { class: 'grid' }, inp('recipient', 'Recipient (age1… or gpg key id)', { value: e.recipient || '' }), inp('identity', 'age identity file (in keys dir)', { value: e.identity_file || '' }),
      sel('secret_mode', 'Password source', [['prompt', 'Prompt on each run'], ['env', 'Derived from master key' + (cap.master_key ? '' : ' (not set)')], ['keyring', 'OS keyring']], e.secret_mode || 'prompt')));
  const encryption = sec('Encryption', 'lock', [h('label', { class: 'chk' }, F.enc, 'Encrypt archives'), encBox], { open: e.enabled });
  const encSync = () => {
    const zip = F.format.value === 'zip', on = F.enc.checked;
    encBox.hidden = !on; toolSeg.el.hidden = zip; modeSeg.el.hidden = zip; const key = !zip && mode === 'recipient';
    F.recipient.parentElement.hidden = !key; F.identity.parentElement.hidden = !(key && tool === 'age'); sumSync();
  };

  // Schedule + retention
  const sc = cfg.schedule, rt = cfg.retention;
  const ext = () => { F.hours.parentElement.hidden = F.sctype.value !== 'interval'; F.time.parentElement.hidden = F.sctype.value !== 'daily'; const t = F.rttype.value; F.rn.parentElement.hidden = !(t === 'last' || t === 'days'); for (const k of ['daily', 'weekly', 'monthly', 'yearly']) F[k].parentElement.hidden = t !== 'gfs'; sumSync(); };
  const schedule = sec('Schedule & retention', 'clock', [h('div', { class: 'grid' },
    sel('sctype', 'Schedule', [['none', 'Manual only'], ['interval', 'Every N hours'], ['daily', 'Daily at…']], sc.type, ext), inp('hours', 'Every N hours', { type: 'number', min: 1, value: sc.hours || 24 }), inp('time', 'Time', { type: 'time', value: sc.time || '03:00' }),
    sel('rttype', 'Retention', [['keep_all', 'Keep everything'], ['last', 'Keep last N'], ['days', 'Keep younger than N days'], ['gfs', 'GFS']], rt.type, ext), inp('rn', 'N', { type: 'number', min: 1, value: rt.n || 7 }),
    inp('daily', 'Daily', { type: 'number', min: 0, value: rt.daily ?? 7 }), inp('weekly', 'Weekly', { type: 'number', min: 0, value: rt.weekly ?? 4 }), inp('monthly', 'Monthly', { type: 'number', min: 0, value: rt.monthly ?? 12 }), inp('yearly', 'Yearly', { type: 'number', min: 0, value: rt.yearly ?? 0 })),
    h('div', { class: 'hint' }, ico('info'), 'Scheduled runs are unattended: use a master-key-derived password or the OS keyring.' + (cap.scheduler ? '' : ' APScheduler is not installed: schedules are disabled.'))]);

  // Hooks
  const hooks = sec('Hooks & post-restore', 'term', [
    h('div', { class: 'hint' }, ico('info'), 'Run in the container (/bin/sh -c) with BUNNYSAVE_JOB_ID, BUNNYSAVE_ARCHIVE, BUNNYSAVE_SOURCE. A failing pre-hook aborts the backup.'),
    h('div', { class: 'grid' }, inp('pre', 'Pre-backup command', { value: cfg.hooks.pre.command }), inp('pret', 'Timeout (s)', { type: 'number', value: cfg.hooks.pre.timeout }), inp('post', 'Post-backup command', { value: cfg.hooks.post.command }), inp('postt', 'Timeout (s)', { type: 'number', value: cfg.hooks.post.timeout })),
    h('label', {}, 'Post-restore commands, one per line (stored in the manifest, never run without confirmation)', (F.prc = h('textarea', {}, cfg.post_restore.map(c => c.command).join('\n')))), inp('prct', 'Post-restore timeout (s)', { type: 'number', value: (cfg.post_restore[0] || {}).timeout || 300 })]);

  const sumSync = () => {
    const zip = F.format.value === 'zip';
    general.setSummary(`${F.format.value}${F.perm.checked ? ' · permissions' : ''}`);
    encryption.setSummary(F.enc.checked ? (zip ? 'AES-256 zip' : `${tool} · ${mode === 'recipient' ? 'public key' : 'password'}`) : 'off');
    const st = F.sctype.value, rtp = F.rttype.value;
    schedule.setSummary((st === 'none' ? 'manual' : st === 'interval' ? `every ${F.hours.value} h` : `daily ${F.time.value}`) + ' · ' + (rtp === 'keep_all' ? 'keep all' : rtp === 'last' ? `last ${F.rn.value}` : rtp === 'days' ? `${F.rn.value} days` : 'GFS'));
    hooks.setSummary([F.pre.value && 'pre', F.post.value && 'post', F.prc.value.trim() && 'post-restore'].filter(Boolean).join(' · ') || 'none');
  };
  root.append(h('div', { class: 'cols' }, general, schedule, sources, encryption, hooks));
  root.addEventListener('input', sumSync); root.addEventListener('change', sumSync);
  encSync(); ext(); sumSync();

  const save = guard(async () => {
    const body = { name: F.name.value, format: F.format.value, level: +F.level.value, preserve_permissions: F.perm.checked, target_dir: F.target_dir.value, space_ratio: +F.space_ratio.value,
      sources: srcCards.map(f => f.collect()), encryption: { enabled: F.enc.checked, tool, mode, recipient: F.recipient.value, identity_file: F.identity.value, secret_mode: F.secret_mode.value },
      schedule: { type: F.sctype.value, hours: +F.hours.value, time: F.time.value }, retention: { type: F.rttype.value, n: +F.rn.value, daily: +F.daily.value, weekly: +F.weekly.value, monthly: +F.monthly.value, yearly: +F.yearly.value },
      hooks: { pre: { command: F.pre.value, timeout: +F.pret.value }, post: { command: F.post.value, timeout: +F.postt.value } }, post_restore: lines(F.prc.value).map(c => ({ command: c, timeout: +F.prct.value })) };
    const s = state.cur ? await api('PUT', '/api/setups/' + state.cur.id, body) : await api('POST', '/api/setups', body);
    await loadSetups(s.id); toast('Setup saved', 'ok');
  });
  root.append(h('div', { class: 'savebar' }, state.cur ? btn('trash', 'Delete', { cls: 'danger', onclick: guard(async () => { if (!confirm('Delete this setup? Existing archives stay on disk.')) return; await api('DELETE', '/api/setups/' + state.cur.id); state.cur = null; $('#work').hidden = true; $('#empty').hidden = false; await loadSetups(); toast('Setup deleted'); }) }) : null,
    btn('save', 'Save', { cls: 'primary', onclick: save })));
}

// ------------------------------------------------------------ run
function secretFields(cfg) {
  const f = {}, nodes = [], e = cfg.encryption;
  if (e.enabled && e.secret_mode === 'prompt') { f.archive = h('input', { type: 'password', autocomplete: 'off' }); nodes.push(h('label', {}, e.mode === 'recipient' && cfg.format !== 'zip' ? 'Key passphrase (if the key is protected)' : 'Archive password', f.archive)); }
  f.sftp = {};
  for (const s of cfg.sources.filter(x => x.type === 'sftp' && x.auth !== 'tailscale' && x.secret_mode === 'prompt')) { f.sftp[s.id] = h('input', { type: 'password', autocomplete: 'off' }); nodes.push(h('label', {}, `SFTP ${s.auth === 'key' ? 'key passphrase (optional)' : 'password'} · ${s.username}@${s.host}`, f.sftp[s.id])); }
  f.collect = () => ({ archive_password: f.archive ? f.archive.value : undefined, sftp: Object.fromEntries(cfg.sources.filter(s => f.sftp[s.id]).map(s => [s.id, s.auth === 'key' ? { key_passphrase: f.sftp[s.id].value } : { password: f.sftp[s.id].value }])) });
  f.clear = () => { if (f.archive) f.archive.value = ''; for (const k in f.sftp) f.sftp[k].value = ''; };
  return [f, nodes];
}
function renderRun() {
  const root = $('#tab-run'); root.replaceChildren();
  const cfg = state.cur.config, [sf, nodes] = secretFields(cfg), panel = h('div');
  const done = j => { if (j.state === 'done') toast('Backup complete · verified', 'ok', 6000); else if (j.state === 'failed') toast('Backup failed', 'err', 6000); else toast('Backup cancelled'); };
  root.append(h('div', { class: 'stack' }, h('div', { class: 'card' }, h('h3', {}, ico('play'), 'Run backup'), ...nodes,
    nodes.length ? h('div', { class: 'hint' }, ico('lock'), 'Passwords are held in memory for this job only.') : null,
    btn('play', 'Run backup', { cls: 'primary', onclick: guard(async () => { const job = await api('POST', `/api/setups/${state.cur.id}/run`, sf.collect()); sf.clear(); toast('Backup started'); watchJob(job.id, panel, done); }) })), panel));
  api('GET', '/api/jobs').then(js => { const j = js.find(x => x.setup_id === state.cur.id && x.kind === 'backup' && ['running', 'queued'].includes(x.state)); if (j) watchJob(j.id, panel, done); });
}
function watchJob(id, panel, onDone) {
  clearInterval(state.poll);
  const bar = h('i'), progress = h('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': 0 }, bar);
  const status = h('div', { 'aria-live': 'polite' }), meta = h('div', { class: 'kv' }), cur = h('div', { class: 'mono muted', style: 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap' }), log = h('pre'), hooks = h('div'), res = h('div');
  const cancel = ib('stop', 'Cancel job', guard(async () => { await api('POST', `/api/jobs/${id}/cancel`); toast('Cancel requested…'); }), 'danger');
  panel.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'row' }, h('h3', { class: 'grow', style: 'margin:0' }, ico('list'), 'Job'), cancel), status, progress, meta, cur, res, hooks, sec('Log', null, log, { inner: true, open: true })));
  let finished = false;
  const tick = async () => {
    const j = await api('GET', '/api/jobs/' + id);
    bar.style.width = j.percent + '%'; progress.setAttribute('aria-valuenow', j.percent);
    status.replaceChildren(h('b', {}, j.state === 'running' ? j.phase : j.state), h('span', { class: 'muted' }, ` · ${j.percent}%`));
    meta.replaceChildren(h('span', {}, `${fmtSize(j.done_bytes)} / ${fmtSize(j.total_bytes)}`), h('span', {}, `${j.files_done}/${j.files_total} entries`));
    cur.textContent = j.current || ''; log.textContent = j.log.join('\n'); log.scrollTop = log.scrollHeight;
    hooks.replaceChildren(...j.hooks.map(k => sec(`${k.which}: ${k.command}`, 'term', h('pre', {}, 'stdout:\n' + k.stdout + '\nstderr:\n' + k.stderr), { inner: true, summary: `exit ${k.exit_code}${k.timed_out ? ' (timeout)' : ''}` })));
    res.replaceChildren(...(j.error ? [h('p', { class: 'bad' }, j.error)] : []), ...(j.kind === 'backup' && j.result && j.result.sha256 ? [h('div', { class: 'mono muted', style: 'word-break:break-all' }, 'SHA-256 ' + j.result.sha256), h('div', { class: 'small ok' }, 'Verified: ' + j.result.verify)] : []));
    if (!['running', 'queued'].includes(j.state) && !finished) { finished = true; clearInterval(state.poll); cancel.disabled = true; if (onDone) onDone(j); }
  };
  state.poll = setInterval(() => tick().catch(e => alertMsg(e.message)), 1000); tick();
}

// ------------------------------------------------------------ history
async function renderHistory() {
  const root = $('#tab-history'); root.replaceChildren(spinner('Loading…'));
  const list = await api('GET', '/api/backups?setup_id=' + state.cur.id);
  const head = h('div', { class: 'hrow hh' }, ...['When', 'Size', 'Format', '', 'SHA-256', 'Verified', ''].map((x, i) => h('div', { class: i === 3 || i === 5 ? 'c' : '' }, x)));
  head.children[3].append(ico('lock'));
  const rows = list.map(b => h('div', { class: 'hrow' },
    h('div', {}, new Date(b.created).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }), b.status === 'failed' ? h('div', { class: 'bad small' }, b.error) : null),
    h('div', { class: 'muted' }, fmtSize(b.size)), h('div', {}, h('span', { class: 'pill' }, b.fmt)),
    h('div', { class: 'c', title: b.encrypted ? 'Encrypted (' + (b.enc_tool || '') + ')' : 'Not encrypted' }, b.encrypted ? h('span', { class: 'acc', style: 'color:var(--acc-text)' }, ico('lock')) : h('span', { class: 'muted' }, '–')),
    h('div', { class: 'hash' }, h('span', { class: 'mono muted', title: b.sha256 }, (b.sha256 || '').slice(0, 12) + '…'), ib('copy', 'Copy SHA-256', () => navigator.clipboard.writeText(b.sha256).then(() => toast('SHA-256 copied', 'ok')))),
    h('div', { class: 'vstat ' + (b.verify_status === 'ok' ? 'ok' : 'bad'), title: b.verify_status === 'ok' ? 'Verified after write' : 'Verification failed' }, ico(b.verify_status === 'ok' ? 'shield' : 'shieldx')),
    h('div', { class: 'acts' }, ib('eye', 'Browse & restore', () => openBackup(b), 'acc'),
      h('a', { class: 'ib', href: `/api/backups/${b.id}/download`, download: b.filename, title: 'Download archive', 'aria-label': 'Download archive', onclick: () => toast('Download started') }, ico('download')),
      ib('trash', 'Delete backup', guard(async () => { if (!confirm('Delete this backup archive from disk? This cannot be undone.')) return; await api('DELETE', '/api/backups/' + b.id); toast('Backup deleted'); renderHistory(); }), 'danger'))));
  root.replaceChildren(list.length ? h('div', { class: 'list' }, head, ...rows) : h('div', { class: 'empty', style: 'margin-top:10vh' }, ico('archive'), 'No backups yet'), h('div', { id: 'browse', style: 'margin-top:16px' }));
}

// ------------------------------------------------------------ browse + restore
const CAT = { code: ['filecode', 'var(--code)'], doc: ['filetext', 'var(--doc)'], image: ['image', 'var(--image)'], video: ['film', 'var(--video)'], audio: ['music', 'var(--audio)'], archive: ['archive', 'var(--archive)'], app: ['pkg', 'var(--app)'] };
const EXT = { code: 'py js ts sh bash cs xaml json yml yaml toml ini conf cfg xml html css sql service timer env csproj sln ps1 bat php rb go rs c h cpp java', doc: 'md txt rst pdf doc docx odt rtf log csv', image: 'png jpg jpeg gif webp svg ico bmp avif', video: 'mp4 mkv avi mov webm', audio: 'mp3 flac ogg wav m4a', archive: 'zip tar gz tgz bz2 zst xz 7z rar', app: 'exe dll so bin appimage deb rpm' };
const catOf = name => { const e = (name.split('.').pop() || '').toLowerCase(); for (const k in EXT) if (EXT[k].split(' ').includes(e)) return k; return null; };
function tico(kind, name) {
  let icon = 'file', col = 'var(--def)';
  if (kind === 'dir') { icon = 'folder'; col = 'var(--acc-text)'; } else if (kind === 'symlink') icon = 'link'; else { const c = catOf(name); if (c) [icon, col] = CAT[c]; }
  return h('span', { class: 'tico', style: `--c:${col}` }, ico(icon));
}
function buildTree(entries) {
  const root = { children: new Map(), info: null, path: '' };
  for (const e of entries) { let n = root, p = ''; const parts = e.name.split('/').filter(Boolean); parts.forEach((part, i) => { p += (p ? '/' : '') + part; if (!n.children.has(part)) n.children.set(part, { children: new Map(), info: null, path: p }); n = n.children.get(part); if (i === parts.length - 1) n.info = e; }); }
  const sum = n => { let t = n.info && n.info.type === 'file' ? n.info.size : 0; for (const c of n.children.values()) t += sum(c); return (n.total = t); };
  sum(root);
  return root;
}
function openBackup(b) {
  const box = $('#browse'); box.replaceChildren();
  const body = h('div');
  const load = guard(async () => {
    body.replaceChildren(spinner('Reading archive (decrypt / decompress)…'));
    try { const data = await api('POST', `/api/backups/${b.id}/entries`, { archive_password: pw ? pw.value : undefined }); renderBrowser(b, data, pw ? pw.value : undefined, body); toast(`Archive opened · ${data.entries.length} entries${data.indexed ? ' · index' : ''}`, 'ok'); } catch (e) { body.replaceChildren(); throw e; }
  });
  const pw = b.encrypted ? h('input', { type: 'password', autocomplete: 'off', 'aria-label': 'Archive password', placeholder: 'Archive password / key passphrase', onkeydown: e => { if (e.key === 'Enter') load(e); } }) : null;
  box.append(h('div', { class: 'card' }, h('div', { class: 'row', style: 'margin-bottom:12px' }, h('h3', { class: 'grow', style: 'margin:0' }, ico('archive'), b.filename), ib('x', 'Close', () => box.replaceChildren())),
    pw ? h('div', { class: 'row' }, h('div', { class: 'grow' }, pw), btn('lock', 'Open', { cls: 'primary', onclick: load })) : null, body));
  if (!pw) load(); box.scrollIntoView({ behavior: 'smooth' });
}
function renderBrowser(b, data, password, body) {
  const m = data.manifest || {}, selected = new Set(); let start = '';
  const hasHost = (m.sources || []).some(s => s.type === 'host');
  const scopeSum = () => (start ? `start: ${start}` : 'whole archive') + (selected.size ? ` · ${selected.size} selected` : '');
  const scope = sec('Scope', 'pin', null, { inner: true });
  const startIn = h('input', { class: 'mono', placeholder: 'e.g. sftp/s1   (blank = whole archive)', oninput: e => { start = e.target.value.replace(/^\/+|\/+$/g, ''); refreshScope(); } });
  const chips = h('div', { class: 'chips' }), sels = h('div', { class: 'chips' });
  const sftpSrc = (m.sources || []).filter(s => s.type === 'sftp');
  const refreshScope = () => { scope.setSummary(scopeSum()); startIn.value = start; sels.replaceChildren(...[...selected].map(p => h('span', { class: 'chip mono' }, p, ib('x', 'Remove', () => { selected.delete(p); refreshScope(); })))); };
  chips.append(btn(null, 'whole archive', { cls: 'sm', onclick: () => { start = ''; refreshScope(); } }), ...sftpSrc.map(s => btn('globe', `sftp/${s.id}`, { cls: 'sm', title: `${s.username}@${s.host}`, onclick: () => { start = 'sftp/' + s.id; refreshScope(); toast('Start point: sftp/' + s.id, 'ok'); } })));
  scope.querySelector('.body').append(h('label', {}, 'Start point inside the archive (this prefix is stripped on restore)', startIn), chips, h('div', { class: 'muted small' }, 'Only restore these paths (use + in the tree):'), sels);

  const preview = h('div', { class: 'preview muted' }, 'Select a file to preview it.'); let token = 0, lastSel = null;
  const showPreview = async (n, el) => {
    const t = ++token; if (lastSel) lastSel.classList.remove('sel'); el.classList.add('sel'); lastSel = el;
    preview.className = 'preview'; preview.replaceChildren(h('div', { class: 'row' }, tico('file', n.name), h('b', {}, n.name)), spinner('Loading preview…'));
    try {
      const p = await api('POST', `/api/backups/${b.id}/preview`, { path: n.path, archive_password: password }); if (t !== token) return; const i = p.info;
      preview.replaceChildren(h('div', { class: 'row' }, tico('file', n.name), h('b', { style: 'word-break:break-all' }, n.name)), h('div', { class: 'kv', style: 'margin:6px 0' }, h('span', {}, fmtSize(i.size)), h('span', {}, 'mode ' + (i.mode & 0o7777).toString(8)), h('span', {}, `uid ${i.uid} / gid ${i.gid}`), i.mtime ? h('span', {}, new Date(i.mtime * 1000).toLocaleString()) : null),
        p.text != null ? h('pre', {}, p.text) : h('div', { class: 'hint' }, ico('info'), p.reason));
    } catch (e) { if (t === token) preview.replaceChildren(h('div', { class: 'bad' }, 'Preview failed: ' + e.message)); }
  };
  const rowOf = (n, folder) => { const isFile = n.info && n.info.type === 'file';
    const r = h('div', { class: 'trow', onclick: isFile ? () => showPreview(n, r) : null },
      folder ? h('span', { class: 'chev' }, ico('chev')) : h('span', { class: 'ind' }), tico(folder ? 'dir' : (n.info ? n.info.type : 'file'), n.name), h('span', { class: 'nm', title: n.name }, n.name),
      isFile ? h('span', { class: 'sz' }, fmtSize(n.info.size)) : folder ? h('span', { class: 'sz' }, fmtSize(n.total)) : null, n.info && n.info.type === 'symlink' ? h('span', { class: 'sz' }, '→ ' + n.info.linkname) : null,
      h('span', { class: 'acts' }, ib('plus', 'Restore only this path', ev => { ev.stopPropagation(); ev.preventDefault(); selected.add(n.path); refreshScope(); toast('Added to selection'); }),
        folder ? ib('pin', 'Use as start point (strip this prefix)', ev => { ev.stopPropagation(); ev.preventDefault(); start = n.path; refreshScope(); toast('Start point: ' + n.path, 'ok'); }) : null));
    return r; };
  const renderNode = (name, n) => {
    n.name = name; if (!n.children.size) return h('li', {}, rowOf(n, false));
    const ul = h('ul'); let filled = false;
    const d = h('details', { ontoggle: () => { if (d.open && !filled) { filled = true; for (const [k, c] of [...n.children].sort((a, b) => (b[1].children.size > 0) - (a[1].children.size > 0) || a[0].localeCompare(b[0]))) ul.append(renderNode(k, c)); } } }, h('summary', {}, rowOf(n, true)), ul);
    return h('li', {}, d);
  };
  const top = buildTree(data.entries), treeUl = h('ul'); for (const [k, c] of [...top.children].sort((a, b) => a[0].localeCompare(b[0]))) treeUl.append(renderNode(k, c));

  // restore panel
  let dest = 'origin', conflictV = 'skip';
  const destSeg = seg([{ v: 'origin', icon: 'server', label: 'Original locations', title: hasHost ? 'Back onto the host filesystem mount' : 'Local files to /, SFTP sources to their own server' }, { v: 'local', icon: 'folder', label: 'Local folder' }, { v: 'sftp', icon: 'globe', label: 'SFTP server' }], dest, v => { dest = v; setMode(); });
  const local = h('input', { class: 'mono', value: '/restore' }), d0 = sftpSrc[0] || {}, dAuthState = { v: d0.auth || 'password' };
  const dHost = h('input', { ...NOAUTO, value: d0.host || '' }), dPort = h('input', { type: 'number', value: d0.port || 22 }), dUser = h('input', { ...NOAUTO, value: d0.username || '' }), dKey = h('input', { ...NOAUTO, value: d0.key_path || '', placeholder: '/data/keys/id_ed25519' }), dPw = secretInput(), dPath = h('input', { ...NOAUTO, class: 'mono', value: '/' });
  const dAuth = seg([{ v: 'password', icon: 'lock', label: 'Password' }, { v: 'key', icon: 'key', label: 'Key file' }, { v: 'tailscale', icon: 'globe', label: 'Tailscale SSH' }], dAuthState.v, v => { dAuthState.v = v; setMode(); });
  const dStatus = h('span', { class: 'small', 'aria-live': 'polite' });
  const dSecret = () => dAuthState.v === 'key' ? { key_passphrase: dPw.value } : { password: dPw.value };
  const dCfg = () => ({ host: dHost.value, port: +dPort.value, username: dUser.value, auth: dAuthState.v, key_path: dKey.value, path: dPath.value });
  const dTest = guard(async () => {
    dStatus.replaceChildren(h('span', { class: 'spin' }), 'Connecting…');
    const r = await api('POST', '/api/test-source', { source: { type: 'sftp', host: dHost.value, port: +dPort.value, username: dUser.value, auth: dAuthState.v, key_path: dKey.value, includes: [{ path: dPath.value || '/', skeleton: true }] }, secrets: dSecret() });
    if (!r.connected) { dStatus.replaceChildren(h('span', { class: 'bad' }, r.error)); toast('Connection failed', 'err'); return; }
    const ok = r.items[0] && r.items[0].exists; dStatus.replaceChildren(h('span', { class: ok ? 'ok' : 'warn' }, ok ? 'Connected · directory exists' : 'Connected · directory will be created')); toast('Connected', 'ok');
  });
  const sftpBox = h('div', {}, h('div', { class: 'grid' }, h('label', {}, 'Host', dHost), h('label', {}, 'Port', dPort), h('label', {}, 'Username', dUser)), h('div', { class: 'row', style: 'margin-bottom:12px' }, dAuth.el),
    (dKey.row = h('label', {}, 'Key file', dKey)), (dPw.row = h('label', {}, 'Password / key passphrase', dPw)), h('label', {}, 'Destination directory', dPath), h('div', { class: 'row' }, btn('plug', 'Test connection', { cls: 'sm', onclick: dTest }), dStatus));
  const localBox = h('label', {}, 'Target directory (inside the container)', local);
  const originBox = h('div', {}, ...sftpSrc.filter(s => s.auth !== 'tailscale').map(s => { s.__in = h('input', { type: 'password', autocomplete: 'off' }); return h('label', {}, `${s.auth === 'key' ? 'Key passphrase' : 'Password'} · ${s.username}@${s.host}`, s.__in); }),
    h('div', { class: 'hint' }, ico('info'), hasHost ? 'Files go back onto the host filesystem mount; SFTP-sourced files go back to their server.' : 'Local files go back to their original paths inside the container; SFTP-sourced files go back to their server.'));
  const setMode = () => { originBox.hidden = dest !== 'origin'; localBox.hidden = dest !== 'local'; sftpBox.hidden = dest !== 'sftp'; dKey.row.hidden = dAuthState.v !== 'key'; dPw.row.hidden = dAuthState.v === 'tailscale'; scope.hidden = dest === 'origin'; };
  const conflict = seg([{ v: 'skip', icon: 'skip', label: 'Skip existing' }, { v: 'overwrite', icon: 'copy', label: 'Overwrite' }, { v: 'rename', icon: 'pencil', label: 'Rename old', title: 'Rename existing files (append .bak-timestamp)' }], conflictV, v => { conflictV = v; });

  const prCmds = m.post_restore_commands || [];
  const prOn = h('input', { type: 'checkbox' }), prConfirm = h('input', { placeholder: 'type RUN to confirm' }), prChecks = prCmds.map(() => h('input', { type: 'checkbox' }));
  const prBox = prCmds.length ? sec('Post-restore commands', 'alert', [h('div', { class: 'hint' }, ico('alert'), 'These shell commands come from the archive and run inside the container. Disabled by default; only run what you recognise.'),
    ...prCmds.map((c, i) => h('label', { class: 'chk' }, prChecks[i], h('code', {}, c.command), h('span', { class: 'muted' }, ` · ${c.timeout}s`))), h('label', { class: 'chk' }, prOn, 'Enable execution of the checked commands'), prConfirm], { inner: true, summary: `${prCmds.length} in archive · off` }) : null;
  const planBox = h('div'), jobPanel = h('div'), runBtn = btn('restore', 'Restore', { cls: 'primary', disabled: true });
  const params = () => ({ mode: dest, target: local.value || '/', start: dest === 'origin' ? '' : start, dest: dCfg(), conflict: conflictV, selection: [...selected], archive_password: password,
    sftp: Object.fromEntries(sftpSrc.filter(s => s.auth !== 'tailscale').map(s => [s.id, s.auth === 'key' ? { key_passphrase: s.__in.value } : { password: s.__in.value }])), dest_secret: dSecret(),
    post_restore: { enabled: prOn.checked, confirm: prConfirm.value, indices: prChecks.map((c, i) => c.checked ? i : -1).filter(i => i >= 0) } });
  const plan = guard(async () => {
    planBox.replaceChildren(spinner('Computing plan (reading the archive)…')); let p;
    try { p = await api('POST', `/api/backups/${b.id}/restore/plan`, params()); } catch (e) { planBox.replaceChildren(); throw e; }
    planBox.replaceChildren(h('div', { class: 'row', style: 'margin:12px 0 8px' }, h('b', {}, 'Plan'), ico('chev'), h('span', { class: 'mono' }, p.target), ...Object.entries(p.summary).map(([k, v]) => h('span', { class: 'pill' }, `${k} ${v}`))),
      ...p.warnings.map(w => h('div', { class: 'warn small' }, w)),
      h('div', { style: 'max-height:280px;overflow:auto;border:1px solid var(--line);border-radius:10px' }, h('table', {}, h('thead', {}, h('tr', {}, ['Archive path', 'Destination', 'Size', 'Action'].map(x => h('th', {}, x)))),
        h('tbody', {}, p.rows.map(r => h('tr', {}, h('td', { class: 'mono' }, r.path + (r.skeleton ? ' · skeleton' : '')), h('td', { class: 'mono' }, r.dest), h('td', {}, r.type === 'dir' ? '' : fmtSize(r.size)), h('td', {}, r.action)))))), p.truncated ? h('p', { class: 'muted small' }, 'Row list truncated; counts are complete.') : null);
    runBtn.disabled = false; toast(Object.keys(p.summary).length ? 'Plan ready · nothing written yet' : 'Nothing to restore with these settings', Object.keys(p.summary).length ? 'ok' : 'err');
  });
  runBtn.onclick = guard(async () => {
    if (!confirm(`Restore to ${dest === 'origin' ? 'original locations' : dest === 'sftp' ? dHost.value + ':' + dPath.value : local.value} (policy: ${conflictV})?`)) return;
    if (prOn.checked && !confirm('You are about to RUN post-restore shell commands from this archive inside the container. Continue?')) return;
    const job = await api('POST', `/api/backups/${b.id}/restore/run`, params()); toast('Restore started');
    watchJob(job.id, jobPanel, j => {
      if (j.state === 'done') { const s = (j.result && j.result.summary) || {}, n = Object.values(s).reduce((a, v) => a + v, 0);
        modal('Restore complete', 'check', h('p', { style: 'margin-top:0' }, `${n} entries processed → ${j.result.target}`), h('div', { class: 'row' }, ...Object.entries(s).map(([k, v]) => h('span', { class: 'pill' }, `${k} ${v}`))), ...(j.result.warnings || []).map(w => h('p', { class: 'warn small' }, w)), ...j.hooks.map(k => h('p', { class: 'small' }, `post-restore: ${k.command} → exit ${k.exit_code}`))); }
      else if (j.state === 'failed') modal('Restore failed', 'alert', h('p', { class: 'bad', style: 'margin:0' }, j.error || 'unknown error')); else toast('Restore cancelled');
    });
  });
  refreshScope(); setMode();
  const restore = h('div', { class: 'card', style: 'margin:16px 0 0' }, h('h3', {}, ico('restore'), 'Restore'), h('div', { class: 'row', style: 'margin-bottom:14px' }, destSeg.el),
    originBox, localBox, sftpBox, scope, h('div', { class: 'row', style: 'margin:12px 0' }, h('span', { class: 'muted small' }, 'If a file exists:'), conflict.el), prBox,
    h('div', { class: 'row', style: 'margin-top:14px' }, btn('list', 'Plan', { onclick: plan, title: 'Show what would happen without writing anything' }), runBtn), planBox, jobPanel);
  body.replaceChildren(h('div', { class: 'kv', style: 'margin-bottom:12px' }, h('span', {}, m.name), h('span', {}, m.timestamp), h('span', {}, 'host ' + m.hostname), h('span', {}, `Bunny Save ${m.bunnysave_version}`), h('span', {}, m.preserve_permissions ? 'permissions preserved' : 'permissions not preserved'), data.truncated ? h('span', { class: 'warn' }, 'listing truncated') : null),
    h('div', { class: 'browse' }, h('div', { class: 'tree', role: 'tree' }, treeUl), preview), restore);
}

// ------------------------------------------------------------ boot
$('.tabs').append(...TABS.map(([k, i, l]) => h('button', { role: 'tab', 'data-tab': k, onclick: () => showTab(k) }, ico(i), h('span', { class: 't' }, l))));
$('#new-setup').append(ico('plus')); $('#new-setup').addEventListener('click', () => { state.cur = null; state.tab = 'setup'; openSetup(null); });
$('#empty').append(ico('archive'), h('div', {}, 'Select a setup, or add one with +'));
(async () => {
  try {
    state.info = await api('GET', '/api/info');
    $('#caps').append(...Object.entries(state.info.capabilities).map(([k, v]) => h('span', { class: v ? '' : 'off', title: v ? 'available' : 'not available' }, k.replace('_', ' '))), h('span', {}, 'v' + state.info.version));
    await loadSetups();
  } catch (e) { alertMsg(e.message); }
})();
