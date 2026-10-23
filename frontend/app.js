/* 飞税税务管理系统 · 框架层 */
var TOKEN = localStorage.getItem('tax_token') || '';
var ME = JSON.parse(localStorage.getItem('tax_user') || '{}');
var PERMS = ME.perms || [];

function api(method, path, body, raw) {
  return fetch(PREFIX + path, {
    method: method,
    headers: Object.assign({'Content-Type': 'application/json'},
      TOKEN ? {Authorization: 'Bearer ' + TOKEN} : {}),
    body: method === 'POST' ? JSON.stringify(body || {}) : undefined
  }).then(function (r) {
    if (r.status === 401) { localStorage.clear(); location.href = 'login.html'; throw new Error('unauth'); }
    if (r.status >= 400) {
      return r.text().then(function (t) {
        var msg = 'HTTP ' + r.status;
        try { msg = (JSON.parse(t) || {}).message || msg; } catch (e) { /* 非 JSON */ }
        throw new Error(msg);
      });
    }
    return raw ? r.text() : r.json();
  }).then(function (j) {
    if (raw) return j;
    if (j && j.code && j.code !== 200) throw new Error(j.message || ('错误 ' + j.code));
    return j;
  });
}
function GET(p) { return api('GET', p); }
function POST(p, b) { return api('POST', p, b); }
function CSV(p) { return api('GET', p, null, true); }

function toast(msg, err) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = err ? '#cf2f4b' : '#1c2b2d';
  t.classList.remove('hidden');
  clearTimeout(t._tm);
  t._tm = setTimeout(function () { t.classList.add('hidden'); }, 2600);
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
  });
}
function perm(p) { return PERMS.indexOf('*') >= 0 || PERMS.indexOf(p) >= 0; }

/* ---------- 格式化 ---------- */
function fmtMoney(n, noSym) {
  if (n == null || n === '') return '—';
  var v = Number(n);
  var s = Math.abs(v) >= 10000
    ? v.toLocaleString('zh-CN', {maximumFractionDigits: 2})
    : v.toFixed(2);
  return (noSym ? '' : '¥') + s;
}
function fmtWan(n) {
  if (n == null || n === '') return '—';
  var v = Number(n);
  if (Math.abs(v) >= 100000000) return (v / 100000000).toFixed(2) + ' 亿';
  if (Math.abs(v) >= 10000) return (v / 10000).toFixed(2) + ' 万';
  return v.toFixed(2);
}
function fmtPct(x, digits) {
  if (x == null || x === '') return '—';
  return Number(x).toFixed(digits == null ? 2 : digits) + '%';
}
function fmtRate(r) {
  if (r == null || r === '') return '—';
  var v = Number(r);
  if (isNaN(v)) return String(r);
  if (v < 1) return (v * 100).toFixed(2).replace(/\.?0+$/, '') + '%';
  return v.toFixed(2) + '%';
}
function fmtDate(s) { return s ? String(s).slice(0, 10) : '—'; }
function todayStr() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}
function curPeriod() { return todayStr().slice(0, 7); }

var NAV = [
  ['dash', '工作台', '◱'],
  ['invoice', '发票管理', '▤'],
  ['input', '进项抵扣', '◨'],
  ['declare', '纳税申报', '◇'],
  ['calc', '税种计算器', '∑'],
  ['reports', '税负分析', '◔'],
  ['risk', '风险预警', '⚠'],
  ['entity', '纳税主体', '▣'],
  ['voucher', '凭证台账', '⌸'],
  ['policy', '政策法规', '❏'],
  ['system', '系统管理', '⚙']
];

function boot() {
  if (!TOKEN) { location.href = 'login.html'; return; }
  GET('/api/auth/me').then(function (r) {
    ME = r.data || {}; PERMS = ME.perms || [];
    localStorage.setItem('tax_user', JSON.stringify(ME));
    document.getElementById('who').textContent = ME.name + ' · ' + (ME.roleLabel || ME.role);
    var nav = document.getElementById('nav');
    nav.innerHTML = NAV.map(function (n) {
      return '<a href="#/' + n[0] + '" data-k="' + n[0] + '">' +
        '<span class="ic">' + n[2] + '</span>' + n[1] + '</a>';
    }).join('');
    nav.onclick = function (e) {
      var a = e.target.closest('a'); if (!a) return;
      e.preventDefault();
      go(a.getAttribute('data-k'));
    };
    var key = (location.hash || '#/dash').replace('#/', '');
    go(PAGES[key] ? key : 'dash');
    document.getElementById('btn-logout').onclick = function () {
      POST('/api/auth/logout').then(function () {
        localStorage.clear(); location.href = 'login.html';
      }).catch(function () { localStorage.clear(); location.href = 'login.html'; });
    };
    window.addEventListener('hashchange', function () {
      var k = (location.hash || '#/dash').replace('#/', '');
      if (PAGES[k] && k !== CUR) go(k);
    });
    // 未读风险角标
    if (perm('risk.read')) {
      GET('/api/dashboard').then(function (d) {
        var n = ((d.data || {}).kpi || {}).riskOpen || 0;
        if (!n) return;
        var a = document.querySelector('#nav a[data-k="risk"]');
        if (a) a.insertAdjacentHTML('beforeend', '<b class="badge">' + n + '</b>');
      }).catch(function () {});
    }
  }).catch(function (e) {
    if (e.message !== 'unauth') location.href = 'login.html';
  });
}

var CUR = null;
function go(key) {
  CUR = key;
  if (location.hash !== '#/' + key) location.hash = '#/' + key;
  document.querySelectorAll('#nav a').forEach(function (a) {
    a.classList.toggle('on', a.getAttribute('data-k') === key);
  });
  var main = document.getElementById('main');
  main.innerHTML = '<div class="empty">加载中…</div>';
  var task;
  try {
    task = PAGES[key](main);
  } catch (e) {
    task = Promise.reject(e);
  }
  Promise.resolve(task).catch(function (e) {
    if (e && e.message === 'unauth') return;
    main.innerHTML = '<div class="empty">加载失败：' + esc(e && e.message) + '</div>';
  });
}

function modal(html, wide) {
  var mask = document.getElementById('modal-mask');
  var box = document.getElementById('modal');
  box.innerHTML = html;
  box.className = 'modal' + (wide ? ' wide' : '');
  mask.classList.remove('hidden');
  mask.onclick = function (e) { if (e.target === mask) closeModal(); };
}
function closeModal() {
  document.getElementById('modal-mask').classList.add('hidden');
}

function table(headers, rows, rowHtml, empty) {
  if (!rows || !rows.length) return '<div class="empty">' + (empty || '暂无数据') + '</div>';
  return '<div class="tw"><table><thead><tr>' + headers.map(function (h) {
    if (h && h.charAt(0) === '~') return '<th class="num">' + h.slice(1) + '</th>';
    return '<th>' + h + '</th>';
  }).join('') + '</tr></thead><tbody>' + rows.map(rowHtml).join('') + '</tbody></table></div>';
}

function tag(text, cls) {
  return '<span class="tag ' + (cls || '') + '">' + esc(text) + '</span>';
}
function statusTag(s) {
  var m = {'已申报': 'ok', '已缴款': 'ok', '待申报': 'warn', '草稿': '',
           '正常': 'ok', '作废': 'err', '已作废': 'err', '已红冲': 'err',
           '已认证': 'ok', '未认证': 'warn', '已转出': 'err',
           '待处理': 'err', '已处理': 'ok', '已忽略': '',
           '启用': 'ok', '停用': '', '通过': 'ok', '驳回': 'err'};
  return tag(s, m[s] || '');
}
function levelTag(l) {
  var m = {'险': 'err', '警': 'warn', '提': 'pri', '高': 'err', '中': 'warn', '低': 'pri'};
  return tag(l, m[l] || '');
}
function kpi(v, label, cls) {
  return '<div class="kpi ' + (cls || '') + '"><b>' + esc(v) + '</b><span>' + esc(label) + '</span></div>';
}
function field(label, input, hint) {
  return '<label class="fld"><span>' + esc(label) + '</span>' + input +
    (hint ? '<i>' + esc(hint) + '</i>' : '') + '</label>';
}
function bar(pct, cls) {
  var w = Math.max(0, Math.min(100, pct));
  return '<div class="bar"><i class="' + (cls || '') + '" style="width:' + w + '%"></i></div>';
}
function dl(p, name) {
  CSV(p).then(function (t) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([t], {type: 'text/csv;charset=utf-8'}));
    a.download = name || 'export.csv';
    a.click();
  }).catch(function (e) { toast(e.message, true); });
}

/* 期间下拉：近 12 个月滚动 */
function periodOptions(sel, n) {
  n = n || 12;
  var out = [], d = new Date();
  d.setDate(1);
  for (var i = 0; i < n; i++) {
    var p = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
    out.push('<option value="' + p + '"' + (p === sel ? ' selected' : '') + '>' + p + '</option>');
    d.setMonth(d.getMonth() - 1);
  }
  return out.join('');
}

/* 竖向双柱图 */
function barChart(rows, labelKey, series, opts) {
  opts = opts || {};
  if (!rows || !rows.length) return '<div class="empty">暂无数据</div>';
  var max = 0;
  rows.forEach(function (r) {
    series.forEach(function (s) {
      max = Math.max(max, Math.abs(Number(r[s.key]) || 0));
    });
  });
  if (!max) max = 1;
  return '<div class="chart">' + rows.map(function (r) {
    var bars = series.map(function (s, i) {
      var v = Math.abs(Number(r[s.key]) || 0);
      var h = Math.max(2, Math.round(v / max * 148));
      return '<i class="' + (i ? 'b2' : '') + '" style="height:' + h + 'px" title="' +
        esc(s.name) + ' ' + fmtWan(v) + '"></i>';
    }).join('');
    return '<div class="col"><div class="vv">' + fmtWan(Number(r[series[0].key]) || 0) +
      '</div><div class="bars">' + bars + '</div><div class="lb">' +
      esc(String(r[labelKey]).slice(2)) + '</div></div>';
  }).join('') + '</div>' +
    '<div class="toolbar" style="margin-top:6px;font-size:12px;color:var(--sub)">' +
    series.map(function (s, i) {
      return '<span style="display:inline-flex;align-items:center;gap:5px">' +
        '<i style="width:10px;height:10px;border-radius:2px;display:inline-block;background:' +
        (i ? '#9ecfc9' : 'var(--pri)') + '"></i>' + esc(s.name) + '</span>';
    }).join('') + '</div>';
}

/* 横向排行 */
function rankList(rows, labelKey, valKey, money) {
  if (!rows || !rows.length) return '<div class="empty">暂无数据</div>';
  var max = 0;
  rows.forEach(function (r) { max = Math.max(max, Math.abs(Number(r[valKey]) || 0)); });
  if (!max) max = 1;
  return '<div class="rank">' + rows.map(function (r) {
    var v = Number(r[valKey]) || 0;
    return '<div class="r"><span class="n" title="' + esc(r[labelKey]) + '">' +
      esc(r[labelKey]) + '</span><span class="b">' + bar(Math.abs(v) / max * 100) +
      '</span><span class="v">' + (money === false ? fmtWan(v) : fmtMoney(v)) + '</span></div>';
  }).join('') + '</div>';
}
