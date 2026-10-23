/* 飞税税务管理系统 · 业务页面 */

var PAGES = {};
var TAX_TYPES = ['增值税', '附加税费', '企业所得税', '个人所得税', '印花税',
                 '房产税', '城镇土地使用税', '其他税费'];

function pageHead(title, desc, acts) {
  return '<h2 class="page">' + esc(title) + '</h2>' +
    '<div class="page-desc">' + esc(desc) + '</div>' +
    (acts ? '<div class="toolbar">' + acts + '</div>' : '');
}

/* ==================================================== 工作台 */
PAGES.dash = function (el) {
  return Promise.all([GET('/api/dashboard'), GET('/api/notices')]).then(function (rs) {
    var d = rs[0].data || {}, k = d.kpi || {};
    var notices = rs[1].data || {};
    var list = notices.list || [];

    el.innerHTML = pageHead('工作台', '当前期间 ' + d.period + ' · 全集团税务运行总览') +
      '<div class="kpis">' +
      kpi(k.entities, '纳税主体', 'pri') +
      kpi(fmtWan(k.outputTax), '销项税额') +
      kpi(fmtWan(k.inputTax), '进项税额') +
      kpi(fmtWan(k.vatPayable), '应纳增值税', k.vatPayable > 0 ? 'warn' : 'ok') +
      kpi(fmtWan(k.declared), '申报税额') +
      kpi(fmtWan(k.unpaid), '待缴税额', k.unpaid > 0 ? 'err' : 'ok') +
      kpi(k.pendingCount + ' / ' + k.overdueCount, '待申报 / 逾期',
        k.overdueCount > 0 ? 'err' : 'warn') +
      kpi(k.riskOpen, '待处理风险', k.riskHigh > 0 ? 'err' : 'warn') +
      '</div>' +
      '<div class="card"><h3>近 6 期税负趋势<span class="sub">销项 / 进项 / 实缴</span></h3>' +
      barChart(d.trend || [], 'period',
        [{key: 'output', name: '销项'}, {key: 'total', name: '申报税额'}]) +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>本期税额构成</h3>' +
      ((d.byType || []).length
        ? rankList(d.byType, 'name', 'amount')
        : '<div class="empty">本期暂无申报数据</div>') +
      '</div>' +
      '<div class="card"><h3>待办申报<span class="sub">' + ((d.pending || []).length) +
      ' 项</span></h3>' +
      ((d.pending || []).length
        ? '<div class="tw"><table><thead><tr><th>单号</th><th>税种</th><th>期限</th><th class="num">税额</th></tr></thead><tbody>' +
          d.pending.map(function (p) {
            var late = p.due_date && p.due_date < todayStr();
            return '<tr class="click" data-no="' + esc(p.no) + '"><td>' + esc(p.no) +
              '</td><td>' + esc(p.tax_type) + '</td><td>' +
              (late ? '<span style="color:var(--err)">' + esc(p.due_date) + ' 逾期</span>'
                    : esc(p.due_date || '—')) +
              '</td><td class="num">' + fmtMoney(p.tax_amount) + '</td></tr>';
          }).join('') + '</tbody></table></div>'
        : '<div class="empty">本期申报已全部完成</div>') +
      '</div></div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>纳税主体概况</h3>' +
      table(['主体', '纳税人身份', '行业', '小微', '高新'],
        d.entities || [],
        function (e) {
          return '<tr><td><b>' + esc(e.name) + '</b><br><small style="color:var(--sub)">' +
            esc(e.code) + '</small></td><td>' + esc(e.taxpayer_type) + '</td><td>' +
            esc(e.industry) + '</td><td>' + (Number(e.small_profit) ? tag('是', 'ok') : '—') +
            '</td><td>' + (Number(e.high_tech) ? tag('是', 'pri') : '—') + '</td></tr>';
        }) +
      '</div>' +
      '<div class="card"><h3>风险提示<span class="sub">未处理</span></h3>' +
      ((d.risks || []).length
        ? '<div class="risk-list">' + d.risks.map(function (r) {
            return '<div class="risk-item ' + (r.level === '险' ? 'lv-hi' : 'lv-mid') + '">' +
              '<div class="h">' + levelTag(r.level) + '<b>' + esc(r.title) + '</b></div>' +
              '<div class="d">' + esc(r.entity) + ' · ' + esc(r.status) + '</div></div>';
          }).join('') + '</div>'
        : '<div class="empty">暂无未处理风险</div>') +
      '</div></div>' +
      '<div class="card"><h3>通知公告</h3>' +
      (list.length
        ? '<div class="tl">' + list.map(function (n) {
            return '<div class="tl-item' + (n.top ? ' pass' : '') + '">' +
              '<div class="t">' + esc(fmtDate(n.created_at)) + ' · ' + esc(n.author) + '</div>' +
              '<div class="h">' + esc(n.title) + (n.top ? ' ' + tag('置顶', 'pri') : '') + '</div>' +
              '<div class="d">' + esc(String(n.body || '').slice(0, 90)) + '</div></div>';
          }).join('') + '</div>'
        : '<div class="empty">暂无公告</div>') +
      '</div>';

    el.querySelectorAll('tr[data-no]').forEach(function (tr) {
      tr.onclick = function () { location.hash = '#/declare'; };
    });
  });
};

/* ==================================================== 发票管理 */
PAGES.invoice = function (el) {
  var st = {kind: '销项', period: '', entity: '', kw: '', page: 1, size: 20};
  el.innerHTML = pageHead('发票管理', '销项开票与进项收票台账，支持三流一致校验',
    '<button class="btn" id="new-inv">+ 新增发票</button>' +
    '<button class="btn ghost" id="exp-inv">导出 CSV</button>');

  var filter = document.createElement('div');
  filter.className = 'card';
  filter.innerHTML = '<div class="toolbar" style="margin:0">' +
    '<select id="f-kind"><option>销项</option><option>进项</option><option value="">全部</option></select>' +
    '<select id="f-period"><option value="">全部期间</option>' + periodOptions('') + '</select>' +
    '<select id="f-entity"><option value="">全部主体</option></select>' +
    '<input id="f-kw" placeholder="发票号 / 销方 / 购方" style="width:200px">' +
    '<button class="btn sm" id="f-go">查询</button>' +
    '<span id="f-sum" style="margin-left:auto;color:var(--sub);font-size:12.5px"></span>' +
    '</div>';
  el.appendChild(filter);

  var box = document.createElement('div');
  box.className = 'card';
  el.appendChild(box);

  GET('/api/entities').then(function (r) {
    var ents = (r.data || {}).list || [];
    var sel = filter.querySelector('#f-entity');
    ents.forEach(function (e) {
      sel.insertAdjacentHTML('beforeend',
        '<option value="' + e.code + '">' + esc(e.name) + '</option>');
    });
  }).catch(function () {});

  function load() {
    var q = '/api/invoices?kind=' + encodeURIComponent(st.kind) +
      (st.period ? '&period=' + st.period : '') +
      (st.entity ? '&entity=' + st.entity : '') +
      (st.kw ? '&kw=' + encodeURIComponent(st.kw) : '');
    box.innerHTML = '<div class="empty">加载中…</div>';
    GET(q).then(function (r) {
      var d = r.data || {}, rows = d.list || [];
      filter.querySelector('#f-sum').textContent =
        '共 ' + (d.total || 0) + ' 张 · 金额 ' + fmtMoney(d.sumAmount) +
        ' · 税额 ' + fmtMoney(d.sumTax);
      var all = rows;
      var pages = Math.max(1, Math.ceil(all.length / st.size));
      if (st.page > pages) st.page = pages;
      var cur = all.slice((st.page - 1) * st.size, st.page * st.size);
      box.innerHTML = '<h3>发票列表<span class="sub">' + esc(st.kind || '全部') +
        ' · 第 ' + st.page + '/' + pages + ' 页</span></h3>' +
        table(['发票号', '票种', '主体', '销方', '购方', '~金额', '税率', '~税额',
               '开票日期', '状态', '认证'],
          cur,
          function (v) {
            return '<tr class="click" data-no="' + esc(v.no) + '"><td><b>' + esc(v.no) +
              '</b><br><small style="color:var(--sub)">' + esc(v.number || '') + '</small></td>' +
              '<td>' + esc(v.invoice_type) + '</td><td>' + esc(v.entity) + '</td>' +
              '<td class="wrap">' + esc(v.seller_name) + '</td>' +
              '<td class="wrap">' + esc(v.buyer_name) + '</td>' +
              '<td class="num">' + fmtMoney(v.amount) + '</td>' +
              '<td>' + esc(v.tax_rate) + '</td>' +
              '<td class="num">' + fmtMoney(v.tax) + '</td>' +
              '<td>' + esc(fmtDate(v.biz_date)) + '</td>' +
              '<td>' + statusTag(v.status) + '</td>' +
              '<td>' + statusTag(v.verify_status) + '</td></tr>';
          }) +
        '<div class="toolbar" style="margin-top:10px">' +
        '<button class="btn sm ghost" id="pg-prev"' + (st.page <= 1 ? ' disabled' : '') +
        '>上一页</button><button class="btn sm ghost" id="pg-next"' +
        (st.page >= pages ? ' disabled' : '') + '>下一页</button></div>';
      box.querySelectorAll('tr[data-no]').forEach(function (tr) {
        tr.onclick = function () { showInvoice(tr.getAttribute('data-no')); };
      });
      var pv = box.querySelector('#pg-prev'), nx = box.querySelector('#pg-next');
      if (pv) pv.onclick = function () { st.page--; load(); };
      if (nx) nx.onclick = function () { st.page++; load(); };
    }).catch(function (e) {
      box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  filter.querySelector('#f-go').onclick = function () {
    st.kind = filter.querySelector('#f-kind').value;
    st.period = filter.querySelector('#f-period').value;
    st.entity = filter.querySelector('#f-entity').value;
    st.kw = filter.querySelector('#f-kw').value.trim();
    st.page = 1;
    load();
  };
  filter.querySelector('#f-kw').onkeydown = function (e) {
    if (e.key === 'Enter') filter.querySelector('#f-go').click();
  };
  el.querySelector('#exp-inv').onclick = function () {
    dl('/api/reports/export?type=invoice' + (st.period ? '&period=' + st.period : ''),
       '发票台账_' + (st.period || '全部') + '.csv');
  };
  el.querySelector('#new-inv').onclick = function () { editInvoice(null, load); };
  load();
};

function showInvoice(no) {
  GET('/api/invoices/' + encodeURIComponent(no)).then(function (r) {
    var v = r.data || {};
    var risks = v.risks || [];
    var tf = v.three_flow;
    modal('<h3>发票详情 · ' + esc(v.no) + '</h3>' +
      '<div class="grid2">' +
      field('发票种类', '<input value="' + esc(v.invoice_type) + '" disabled>') +
      field('所属主体', '<input value="' + esc(v.entity + ' ' + (v.entity_name || '')) + '" disabled>') +
      field('开票日期', '<input value="' + esc(v.biz_date) + '" disabled>') +
      field('所属期间', '<input value="' + esc(v.period) + '" disabled>') +
      field('金额（不含税）', '<input value="' + fmtMoney(v.amount, true) + '" disabled>') +
      field('税率', '<input value="' + esc(v.tax_rate) + '" disabled>') +
      field('税额', '<input value="' + fmtMoney(v.tax, true) + '" disabled>') +
      field('价税合计', '<input value="' + fmtMoney(v.total, true) + '" disabled>') +
      field('销售方', '<input value="' + esc(v.seller_name) + '" disabled>') +
      field('购买方', '<input value="' + esc(v.buyer_name) + '" disabled>') +
      '</div>' +
      '<div style="margin-top:6px">' +
      '<b style="font-size:13px">三流一致校验</b>' +
      (tf
        ? '<div style="margin-top:6px;font-size:12.5px">' +
          (tf.ok ? tag('合同流 / 发票流 / 资金流 一致', 'ok')
                 : (tf.issues || []).map(function (i) { return tag(i, 'err'); }).join(' ')) +
          '</div>'
        : '<div style="margin-top:6px;color:var(--sub);font-size:12.5px">' +
          '未关联合同，无法校验合同流</div>') +
      '</div>' +
      '<div style="margin-top:12px"><b style="font-size:13px">风险提示</b>' +
      (risks.length
        ? '<div class="risk-list" style="margin-top:6px">' + risks.map(function (x) {
            return '<div class="risk-item ' +
              (x.level === '险' ? 'lv-hi' : (x.level === '警' ? 'lv-mid' : 'lv-lo')) + '">' +
              '<div class="h">' + levelTag(x.level) + '<b>' + esc(x.title || x.code) + '</b></div>' +
              (x.detail ? '<div class="d">' + esc(x.detail) + '</div>' : '') + '</div>';
          }).join('') + '</div>'
        : '<div style="margin-top:6px;color:var(--ok);font-size:12.5px">未发现风险</div>') +
      '</div>' +
      '<div class="acts">' +
      (perm('invoice.void') && v.status === '正常'
        ? '<button class="btn danger sm" id="m-void">作废</button>' : '') +
      '<button class="btn ghost" onclick="closeModal()">关闭</button></div>', true);

    var vb = document.getElementById('m-void');
    if (vb) vb.onclick = function () {
      if (!confirm('确认作废发票 ' + v.no + '？')) return;
      POST('/api/invoices/' + encodeURIComponent(v.no) + '/void', {reason: '手工作废'})
        .then(function () { toast('已作废'); closeModal(); go('invoice'); })
        .catch(function (e) { toast(e.message, true); });
    };
  }).catch(function (e) { toast(e.message, true); });
}

function editInvoice(v, done) {
  GET('/api/entities').then(function (r) {
    var ents = (r.data || {}).list || [];
    modal('<h3>' + (v ? '编辑发票' : '新增发票') + '</h3>' +
      '<div class="grid2">' +
      field('类型', '<select id="i-kind"><option>销项</option><option>进项</option></select>') +
      field('纳税主体', '<select id="i-entity">' + ents.map(function (e) {
        return '<option value="' + e.code + '">' + esc(e.name) + '</option>';
      }).join('') + '</select>') +
      field('票种', '<select id="i-type"><option>增值税专用发票</option>' +
        '<option>增值税普通发票</option><option>电子发票</option></select>') +
      field('税率', '<select id="i-rate"><option>13%</option><option>9%</option>' +
        '<option>6%</option><option>0%</option><option>3%</option><option>1%</option></select>') +
      field('金额', '<input id="i-amount" type="number" step="0.01" placeholder="0.00">') +
      field('含税', '<select id="i-incl"><option value="">否（金额不含税）</option>' +
        '<option value="1">是（金额为价税合计）</option></select>') +
      field('开票日期', '<input id="i-date" type="date" value="' + todayStr() + '">') +
      field('对方名称', '<input id="i-name" placeholder="销方或购方">') +
      '</div>' +
      field('备注', '<input id="i-memo">') +
      '<div class="acts"><button class="btn ghost" onclick="closeModal()">取消</button>' +
      '<button class="btn" id="i-save">保存</button></div>');

    document.getElementById('i-save').onclick = function () {
      var b = {
        kind: document.getElementById('i-kind').value,
        entity: document.getElementById('i-entity').value,
        invoice_type: document.getElementById('i-type').value,
        rate: document.getElementById('i-rate').value,
        amount: document.getElementById('i-amount').value,
        inclusive: !!document.getElementById('i-incl').value,
        biz_date: document.getElementById('i-date').value,
        remark: document.getElementById('i-memo').value
      };
      var nm = document.getElementById('i-name').value.trim();
      if (b.kind === '销项') b.buyer_name = nm; else b.seller_name = nm;
      if (!b.amount || Number(b.amount) <= 0) { toast('请填写金额', true); return; }
      var btn = this; btn.disabled = true;
      POST('/api/invoices/save', b).then(function (res) {
        toast('已保存 ' + res.data.no);
        closeModal();
        if (done) done();
      }).catch(function (e) { toast(e.message, true); btn.disabled = false; });
    };
  }).catch(function (e) { toast(e.message, true); });
}

/* ==================================================== 进项抵扣 */
PAGES.input = function (el) {
  el.innerHTML = pageHead('进项抵扣', '进项发票认证、抵扣与转出管理');
  var box = document.createElement('div');
  el.appendChild(box);

  var period = curPeriod();
  Promise.all([GET('/api/reports/input?period=' + period),
               GET('/api/invoices?kind=' + encodeURIComponent('进项'))])
    .then(function (rs) {
      var d = rs[0].data || {}, inv = (rs[1].data || {}).list || [];
      var byRate = d.byRate || [], byVerify = d.byVerify || [], bySup = d.bySupplier || [];
      var tIn = byRate.reduce(function (a, b) { return a + Number(b.tax || 0); }, 0);
      var cert = byVerify.filter(function (x) { return x.status === '已认证'; })
        .reduce(function (a, b) { return a + Number(b.tax || 0); }, 0);
      var pend = byVerify.filter(function (x) { return x.status !== '已认证'; })
        .reduce(function (a, b) { return a + Number(b.tax || 0); }, 0);

      box.innerHTML =
        '<div class="kpis">' +
        kpi(fmtWan(tIn), '进项税额合计') +
        kpi(fmtWan(cert), '已认证可抵扣', 'ok') +
        kpi(fmtWan(pend), '待认证', 'warn') +
        kpi(inv.length, '进项发票张数') +
        '</div>' +
        '<div class="grid2">' +
        '<div class="card"><h3>按税率分布</h3>' +
        table(['税率', '张数', '~金额', '~税额'], byRate, function (r) {
          return '<tr><td><b>' + esc(r.rate) + '</b></td><td>' + r.cnt +
            '</td><td class="num">' + fmtMoney(r.amount) + '</td>' +
            '<td class="num">' + fmtMoney(r.tax) + '</td></tr>';
        }) + '</div>' +
        '<div class="card"><h3>认证状态</h3>' +
        table(['状态', '张数', '~税额'], byVerify, function (r) {
          return '<tr><td>' + statusTag(r.status) + '</td><td>' + r.cnt +
            '</td><td class="num">' + fmtMoney(r.tax) + '</td></tr>';
        }) + '</div></div>' +
        '<div class="card"><h3>供应商集中度 Top10</h3>' +
        rankList(bySup, 'name', 'tax') + '</div>' +
        '<div class="card"><h3>进项发票明细<span class="sub">可勾选认证</span></h3>' +
        table(['发票号', '销方', '主体', '~金额', '~税额', '日期', '认证状态', '操作'],
          inv.slice(0, 40),
          function (r) {
            var can = r.verify_status !== '已认证' && r.status === '正常';
            return '<tr><td>' + esc(r.no) + '</td><td class="wrap">' + esc(r.seller_name) +
              '</td><td>' + esc(r.entity) + '</td>' +
              '<td class="num">' + fmtMoney(r.amount) + '</td>' +
              '<td class="num">' + fmtMoney(r.tax) + '</td>' +
              '<td>' + esc(fmtDate(r.biz_date)) + '</td>' +
              '<td>' + statusTag(r.verify_status) + '</td>' +
              '<td>' + (can && perm('input.verify')
                ? '<button class="btn sm" data-cert="' + esc(r.no) + '">认证</button>' : '—') +
              '</td></tr>';
          }) + '</div>';

      box.querySelectorAll('[data-cert]').forEach(function (b) {
        b.onclick = function () {
          var no = b.getAttribute('data-cert');
          b.disabled = true;
          POST('/api/invoices/verify', {no: no}).then(function () {
            toast('已认证 ' + no);
            go('input');
          }).catch(function (e) { toast(e.message, true); b.disabled = false; });
        };
      });
    }).catch(function (e) {
      box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
};

/* ==================================================== 纳税申报 */
PAGES.declare = function (el) {
  var st = {period: '', entity: '', status: ''};
  el.innerHTML = pageHead('纳税申报', '各主体分税种申报单管理：试算、填报、缴款',
    '<button class="btn" id="new-decl">+ 新建申报</button>' +
    '<button class="btn ghost" id="exp-decl">导出 CSV</button>');

  var f = document.createElement('div');
  f.className = 'card';
  f.innerHTML = '<div class="toolbar" style="margin:0">' +
    '<select id="d-period"><option value="">全部期间</option>' + periodOptions('') + '</select>' +
    '<select id="d-entity"><option value="">全部主体</option></select>' +
    '<select id="d-status"><option value="">全部状态</option><option>草稿</option>' +
    '<option>待申报</option><option>已申报</option><option>已缴款</option></select>' +
    '<button class="btn sm" id="d-go">查询</button>' +
    '<span id="d-sum" style="margin-left:auto;color:var(--sub);font-size:12.5px"></span></div>';
  el.appendChild(f);

  var box = document.createElement('div');
  box.className = 'card';
  el.appendChild(box);

  GET('/api/entities').then(function (r) {
    ((r.data || {}).list || []).forEach(function (e) {
      f.querySelector('#d-entity').insertAdjacentHTML('beforeend',
        '<option value="' + e.code + '">' + esc(e.name) + '</option>');
    });
  }).catch(function () {});

  function load() {
    var q = '/api/declarations?' + (st.period ? 'period=' + st.period + '&' : '') +
      (st.entity ? 'entity=' + st.entity + '&' : '') +
      (st.status ? 'status=' + encodeURIComponent(st.status) : '');
    box.innerHTML = '<div class="empty">加载中…</div>';
    GET(q).then(function (r) {
      var d = r.data || {}, rows = d.list || [];
      f.querySelector('#d-sum').textContent =
        '共 ' + (d.total || 0) + ' 单 · 应纳税额 ' + fmtMoney(d.sumTax) +
        ' · 待缴 ' + fmtMoney(d.sumUnpaid);
      box.innerHTML = '<h3>申报单列表</h3>' +
        table(['单号', '主体', '税种', '所属期', '~计税依据', '~应纳税额', '~已缴',
               '申报期限', '状态', '操作'],
          rows,
          function (v) {
            return '<tr><td><b>' + esc(v.no) + '</b></td>' +
              '<td class="wrap">' + esc(v.entity_name || v.entity) + '</td>' +
              '<td>' + esc(v.tax_type) + '</td><td>' + esc(v.period) + '</td>' +
              '<td class="num">' + fmtMoney(v.base_amount) + '</td>' +
              '<td class="num"><b>' + fmtMoney(v.tax_amount) + '</b></td>' +
              '<td class="num">' + fmtMoney(v.paid_amount) + '</td>' +
              '<td>' + (v.overdue
                ? '<span style="color:var(--err)">' + esc(v.due_date) + ' 逾期</span>'
                : esc(v.due_date || '—')) + '</td>' +
              '<td>' + statusTag(v.status) + '</td>' +
              '<td><button class="btn sm ghost" data-detail="' + esc(v.no) +
              '">详情</button>' +
              (v.status === '待申报' && perm('tax.declare')
                ? ' <button class="btn sm" data-file="' + esc(v.no) + '">申报</button>' : '') +
              (v.status === '已申报' && perm('tax.declare')
                ? ' <button class="btn sm ok" data-pay="' + esc(v.no) + '">缴款</button>' : '') +
              '</td></tr>';
          });

      box.querySelectorAll('[data-detail]').forEach(function (b) {
        b.onclick = function () { showDecl(b.getAttribute('data-detail')); };
      });
      box.querySelectorAll('[data-file]').forEach(function (b) {
        b.onclick = function () {
          var no = b.getAttribute('data-file');
          if (!confirm('确认申报 ' + no + '？')) return;
          b.disabled = true;
          POST('/api/declarations/' + encodeURIComponent(no) + '/file', {})
            .then(function () { toast('已申报 ' + no); load(); })
            .catch(function (e) { toast(e.message, true); b.disabled = false; });
        };
      });
      box.querySelectorAll('[data-pay]').forEach(function (b) {
        b.onclick = function () {
          var no = b.getAttribute('data-pay');
          var amt = prompt('缴款金额', '');
          if (amt === null) return;
          POST('/api/declarations/' + encodeURIComponent(no) + '/pay',
               {amount: amt === '' ? null : amt})
            .then(function () { toast('已缴款 ' + no); load(); })
            .catch(function (e) { toast(e.message, true); });
        };
      });
    }).catch(function (e) {
      box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  f.querySelector('#d-go').onclick = function () {
    st.period = f.querySelector('#d-period').value;
    st.entity = f.querySelector('#d-entity').value;
    st.status = f.querySelector('#d-status').value;
    load();
  };
  el.querySelector('#exp-decl').onclick = function () {
    dl('/api/reports/export?type=declaration' + (st.period ? '&period=' + st.period : ''),
       '纳税申报_' + (st.period || '全部') + '.csv');
  };
  el.querySelector('#new-decl').onclick = function () { newDecl(load); };
  load();
};

function showDecl(no) {
  GET('/api/declarations/' + encodeURIComponent(no)).then(function (r) {
    var d = r.data || {};
    var detail = d.detail || {};
    modal('<h3>申报单 · ' + esc(d.no) + '</h3>' +
      '<div class="settle"><div class="row">' +
      '<div><b>' + fmtMoney(d.tax_amount) + '</b><span>应纳税额</span></div>' +
      '<div><b>' + fmtMoney(d.base_amount) + '</b><span>计税依据</span></div>' +
      '<div><b>' + fmtMoney(d.relief_amount || 0) + '</b><span>减免税额</span></div>' +
      '<div><b>' + fmtMoney(d.paid_amount || 0) + '</b><span>已缴税额</span></div>' +
      '</div><div class="note">' + esc(d.entity_name || d.entity) + ' · ' +
      esc(d.tax_type) + ' · ' + esc(d.period) + ' · 期限 ' + esc(d.due_date || '—') +
      '</div></div>' +
      '<div class="grid2">' +
      field('状态', '<input value="' + esc(d.status) + '" disabled>') +
      field('申报时间', '<input value="' + esc(d.filed_at || '—') + '" disabled>') +
      '</div>' +
      '<b style="font-size:13px">计税明细</b>' +
      table(['项目', '值'], Object.keys(detail).map(function (k) {
        return {k: k, v: detail[k]};
      }), function (r) {
        return '<tr><td>' + esc(r.k) + '</td><td class="num">' +
          esc(typeof r.v === 'object' ? JSON.stringify(r.v) : r.v) + '</td></tr>';
      }, '无明细') +
      '<div class="acts"><button class="btn ghost" onclick="closeModal()">关闭</button></div>', true);
  }).catch(function (e) { toast(e.message, true); });
}

function newDecl(done) {
  GET('/api/entities').then(function (r) {
    var ents = (r.data || {}).list || [];
    modal('<h3>新建申报单</h3>' +
      '<div class="grid2">' +
      field('纳税主体', '<select id="n-entity">' + ents.map(function (e) {
        return '<option value="' + e.code + '">' + esc(e.name) + '（' + e.taxpayer_type + '）</option>';
      }).join('') + '</select>') +
      field('税种', '<select id="n-type">' + TAX_TYPES.map(function (t) {
        return '<option>' + t + '</option>';
      }).join('') + '</select>') +
      field('所属期', '<select id="n-period">' + periodOptions(curPeriod()) + '</select>') +
      '</div>' +
      '<div class="toolbar"><button class="btn ghost" id="n-calc">试算</button>' +
      '<span id="n-tip" style="color:var(--sub);font-size:12.5px">先试算再保存</span></div>' +
      '<div id="n-result"></div>' +
      '<div class="acts"><button class="btn ghost" onclick="closeModal()">取消</button>' +
      '<button class="btn" id="n-save">保存</button></div>');

    var calcData = null;
    document.getElementById('n-calc').onclick = function () {
      POST('/api/declarations/calc', {
        entity: document.getElementById('n-entity').value,
        tax_type: document.getElementById('n-type').value,
        period: document.getElementById('n-period').value
      }).then(function (res) {
        calcData = res.data || {};
        var rows = Object.keys(calcData).filter(function (k) {
          return typeof calcData[k] !== 'object';
        }).map(function (k) { return {k: k, v: calcData[k]}; });
        document.getElementById('n-tip').textContent = '试算完成，可保存为申报单';
        document.getElementById('n-result').innerHTML =
          '<div class="card" style="margin-bottom:8px">' +
          table(['项目', '值'], rows, function (r) {
            return '<tr><td>' + esc(r.k) + '</td><td class="num">' + esc(r.v) + '</td></tr>';
          }) + '</div>';
      }).catch(function (e) {
        document.getElementById('n-tip').textContent = '试算失败：' + e.message;
      });
    };

    document.getElementById('n-save').onclick = function () {
      var b = {
        entity: document.getElementById('n-entity').value,
        tax_type: document.getElementById('n-type').value,
        period: document.getElementById('n-period').value
      };
      if (calcData) b.detail = calcData;
      var btn = this; btn.disabled = true;
      POST('/api/declarations/save', b).then(function (res) {
        toast('已创建 ' + res.data.no);
        closeModal();
        if (done) done();
      }).catch(function (e) { toast(e.message, true); btn.disabled = false; });
    };
  }).catch(function (e) { toast(e.message, true); });
}

/* ==================================================== 税种计算器 */
PAGES.calc = function (el) {
  var cur = 'vat';
  el.innerHTML = pageHead('税种计算器', '按现行税法口径即时试算，不入库，可反复调整');
  var wrap = document.createElement('div');
  el.appendChild(wrap);

  var FORMS = {
    vat: {name: '增值税 · 单票税额', fields: [
      {k: 'amount', t: '金额', d: '100000'},
      {k: 'rate', t: '税率', sel: ['13%', '9%', '6%', '0%', '3%', '1%']},
      {k: 'inclusive', t: '含税口径', sel: [['', '否（金额不含税）'], ['1', '是（价税合计）']]}
    ]},
    vat_small: {name: '增值税 · 小规模简易计税', fields: [
      {k: 'sales', t: '销售额', d: '250000'},
      {k: 'quarterly', t: '计税周期', sel: [['1', '按季'], ['', '按月']]},
      {k: 'has_realestate', t: '含不动产销售', sel: [['', '否'], ['1', '是']]}
    ]},
    vat_general: {name: '增值税 · 一般计税', fields: [
      {k: 'out_amount', t: '销项金额（不含税）', d: '1000000'},
      {k: 'out_rate', t: '销项税率', sel: ['13%', '9%', '6%']},
      {k: 'in_amount', t: '进项金额（不含税）', d: '500000'},
      {k: 'in_rate', t: '进项税率', sel: ['13%', '9%', '6%']},
      {k: 'prior_credit', t: '上期留抵', d: '0'}
    ]},
    surtax: {name: '附加税费', fields: [
      {k: 'vat_payable', t: '增值税应纳税额', d: '100000'},
      {k: 'city_type', t: '所在地', sel: ['市区', '县城/镇', '其他']},
      {k: 'halve', t: '六税两费减半', sel: [['1', '享受'], ['', '不享受']]}
    ]},
    cit: {name: '企业所得税 · 年度', fields: [
      {k: 'profit', t: '应纳税所得额', d: '2800000'},
      {k: 'small_profit', t: '小型微利企业', sel: [['1', '是（实际 5%）'], ['', '否（25%）']]},
      {k: 'adjust_add', t: '纳税调增', d: '0'},
      {k: 'adjust_less', t: '纳税调减', d: '0'},
      {k: 'loss_carry', t: '弥补以前年度亏损', d: '0'}
    ]},
    iit: {name: '个人所得税 · 综合所得', fields: [
      {k: 'taxable_income', t: '应纳税所得额（年）', d: '200000'}
    ]},
    iit_salary: {name: '个人所得税 · 工资薪金', fields: [
      {k: 'gross', t: '年收入合计', d: '360000'},
      {k: 'social_insurance', t: '专项扣除（三险一金）', d: '54000'},
      {k: 'special_deduct', t: '专项附加扣除', d: '24000'},
      {k: 'other_deduct', t: '其他扣除', d: '0'}
    ]},
    iit_bonus: {name: '全年一次性奖金', fields: [
      {k: 'bonus', t: '奖金金额', d: '100000'},
      {k: 'mode', t: '计税方式', sel: [['best', '自动比较择优'], ['separate', '单独计税'], ['merge', '并入综合所得']]},
      {k: 'salary_taxable', t: '工资应纳税所得额', d: '0'}
    ]},
    stamp: {name: '印花税', fields: [
      {k: 'type', t: '合同/凭证类型', sel: ['买卖合同', '借款合同', '融资租赁合同', '承揽合同',
        '建设工程合同', '运输合同', '技术合同', '租赁合同', '保管合同', '仓储合同',
        '财产保险合同', '土地使用权出让书据', '不动产转让书据', '股权转让书据',
        '知识产权转让书据', '营业账簿', '证券交易']},
      {k: 'amount', t: '计税金额', d: '1000000'},
      {k: 'vat_excluded', t: '是否不含税', sel: [['1', '不含税金额'], ['', '含税金额']]}
    ]},
    house: {name: '房产税', fields: [
      {k: 'mode', t: '计税方式', sel: [['value', '从价计征 1.2%'], ['rent', '从租计征 12%']]},
      {k: 'original_value', t: '房产原值', d: '5000000'},
      {k: 'deduct_ratio', t: '减除比例', d: '0.30'},
      {k: 'rent', t: '年租金收入', d: '0'}
    ]},
    land: {name: '城镇土地使用税', fields: [
      {k: 'area', t: '占地面积（㎡）', d: '1000'},
      {k: 'grade', t: '土地等级', sel: [['1', '一级 30 元'], ['2', '二级 24 元'],
        ['3', '三级 18 元'], ['4', '四级 12 元'], ['5', '五级 6 元'], ['6', '六级 1.5 元']]}
    ]},
    burden: {name: '综合税负率', fields: [
      {k: 'revenue', t: '营业收入', d: '4000000'},
      {k: 'vat', t: '增值税', d: '120000'},
      {k: 'surtax', t: '附加税费', d: '14400'},
      {k: 'cit', t: '企业所得税', d: '0'},
      {k: 'stamp', t: '印花税', d: '0'}
    ]},
    late_fee: {name: '滞纳金', fields: [
      {k: 'tax', t: '滞纳税款', d: '10000'},
      {k: 'days', t: '滞纳天数', d: '10'}
    ]}
  };

  var KEYMAP = {
    vat_general: function (v) {
      return {kind: 'vat_general',
        outputs: [{amount: v.out_amount, rate: v.out_rate}],
        inputs: [{amount: v.in_amount, rate: v.in_rate}],
        prior_credit: v.prior_credit || 0};
    }
  };

  function render() {
    var f = FORMS[cur];
    wrap.innerHTML =
      '<div class="toolbar">' + Object.keys(FORMS).map(function (k) {
        return '<button class="btn sm ' + (k === cur ? '' : 'ghost') + '" data-k="' + k + '">' +
          esc(FORMS[k].name) + '</button>';
      }).join('') + '</div>' +
      '<div class="grid2" style="align-items:start">' +
      '<div class="card"><h3>' + esc(f.name) + '</h3>' +
      f.fields.map(function (x) {
        var input;
        if (x.sel) {
          input = '<select data-f="' + x.k + '">' + x.sel.map(function (o) {
            var val = Array.isArray(o) ? o[0] : o;
            var nm = Array.isArray(o) ? o[1] : o;
            var df = Array.isArray(o) ? (o[0] === '' || o[0] === '1') : false;
            return '<option value="' + val + '"' + (df && !x.def ? ' selected' : '') + '>' +
              esc(nm) + '</option>';
          }).join('') + '</select>';
        } else {
          input = '<input data-f="' + x.k + '" type="number" step="0.01" value="' +
            (x.d || '0') + '">';
        }
        return field(x.t, input);
      }).join('') +
      '<button class="btn" id="c-go" style="width:100%">计 算</button></div>' +
      '<div class="card" id="c-out"><h3>计算结果</h3>' +
      '<div class="empty">填写左侧参数后点击「计算」</div></div></div>';

    wrap.querySelectorAll('[data-k]').forEach(function (b) {
      b.onclick = function () { cur = b.getAttribute('data-k'); render(); };
    });
    wrap.querySelector('#c-go').onclick = function () {
      var vals = {};
      var ok = true;
      wrap.querySelectorAll('[data-f]').forEach(function (inp) {
        var k = inp.getAttribute('data-f');
        var v = inp.value;
        if (v !== '' && !isNaN(Number(v)) && inp.tagName === 'INPUT') v = Number(v);
        vals[k] = v;
      });
      if (!ok) return;
      var payload;
      if (KEYMAP[cur]) payload = KEYMAP[cur](vals);
      else {
        payload = {kind: cur};
        Object.keys(vals).forEach(function (k) {
          if (k === 'inclusive' || k === 'quarterly' || k === 'has_realestate' ||
              k === 'halve' || k === 'small_profit' || k === 'vat_excluded') {
            payload[k] = !!vals[k];
          } else payload[k] = vals[k];
        });
        if (cur === 'vat') payload.kind = 'vat';
      }
      var out = wrap.querySelector('#c-out');
      out.innerHTML = '<h3>计算结果</h3><div class="empty">计算中…</div>';
      POST('/api/calc', payload).then(function (r) {
        var d = r.data || {};
        var main = null, keys = ['tax', 'payable', 'total', 'fee', 'amount', 'burden'];
        for (var i = 0; i < keys.length; i++) {
          if (d[keys[i]] != null && typeof d[keys[i]] !== 'object') { main = keys[i]; break; }
        }
        var html = '';
        if (main) {
          var val = d[main];
          html += '<div class="settle"><div class="row"><div><b>' +
            (main === 'burden' ? fmtPct(val) : fmtMoney(val)) + '</b><span>' +
            ({tax: '应纳税额', payable: '本期应纳', total: '合计', fee: '滞纳金',
              amount: '金额', burden: '综合税负率'}[main] || '结果') +
            '</span></div></div>' +
            (d.note ? '<div class="note">' + esc(d.note) + '</div>' : '') + '</div>';
        }
        var rows = [];
        (function walk(o, pre) {
          Object.keys(o).forEach(function (k) {
            var v = o[k];
            if (v && typeof v === 'object') {
              if (Array.isArray(v)) {
                v.forEach(function (it, i) { walk(it, pre + k + '[' + (i + 1) + '].'); });
              } else walk(v, pre + k + '.');
            } else if (k !== 'note') {
              rows.push({k: pre + k, v: v});
            }
          });
        })(d, '');
        out.innerHTML = '<h3>计算结果</h3>' + html +
          table(['字段', '值'], rows, function (x) {
            return '<tr><td>' + esc(x.k) + '</td><td class="num">' + esc(x.v) + '</td></tr>';
          });
      }).catch(function (e) {
        out.innerHTML = '<h3>计算结果</h3><div class="empty">' +
          esc(e.message) + '</div>';
      });
    };
  }
  render();
};

/* ==================================================== 税负分析 */
PAGES.reports = function (el) {
  var period = curPeriod();
  el.innerHTML = pageHead('税负分析', '税负率、税额结构与进项抵扣的多维分析',
    '<button class="btn ghost" id="r-exp">导出发票台账</button>');
  var box = document.createElement('div');
  el.appendChild(box);
  el.querySelector('#r-exp').onclick = function () {
    dl('/api/reports/export?type=invoice', '发票台账.csv');
  };

  box.innerHTML = '<div class="card"><div class="toolbar" style="margin:0">' +
    '<select id="r-period">' + periodOptions(period) + '</select>' +
    '<button class="btn sm" id="r-go">切换期间</button></div></div>' +
    '<div id="r-body"><div class="empty">加载中…</div></div>';

  function load(p) {
    GET('/api/reports/summary?period=' + p).then(function (r) {
      var d = r.data || {};
      var byType = d.byType || [], byEnt = d.byEntity || [], trend = d.trend || [];
      var inp = d.input || {};
      document.getElementById('r-body').innerHTML =
        '<div class="kpis">' +
        kpi(fmtWan(d.revenue), '营业收入') +
        kpi(fmtWan(d.taxTotal), '税额合计', 'pri') +
        kpi(fmtPct(d.burden), '综合税负率', d.burden > 5 ? 'err' : 'ok') +
        kpi(byType.length, '涉及税种') +
        '</div>' +
        '<div class="card"><h3>税额趋势<span class="sub">近 6 期</span></h3>' +
        barChart(trend, 'period',
          [{key: 'output', name: '销项税额'}, {key: 'declared', name: '申报税额'}]) +
        '</div>' +
        '<div class="grid2">' +
        '<div class="card"><h3>税额构成</h3>' +
        table(['税种', '~税额', '占比'], byType, function (r) {
          return '<tr><td>' + esc(r.name) + '</td><td class="num">' + fmtMoney(r.amount) +
            '</td><td>' + bar(Number(r.share) || 0) + ' <small>' +
            fmtPct(r.share, 1) + '</small></td></tr>';
        }) + '</div>' +
        '<div class="card"><h3>主体税负排行</h3>' +
        table(['主体', '~税额', '税负率'], byEnt, function (r) {
          return '<tr><td class="wrap">' + esc(r.entity_name || r.entity) +
            '</td><td class="num">' + fmtMoney(r.total || r.tax) + '</td><td>' +
            fmtPct(r.burden) + '</td></tr>';
        }) + '</div></div>' +
        '<div class="grid2">' +
        '<div class="card"><h3>进项税率结构</h3>' +
        table(['税率', '张数', '~金额', '~税额'], inp.byRate || [], function (r) {
          return '<tr><td>' + esc(r.rate) + '</td><td>' + r.cnt +
            '</td><td class="num">' + fmtMoney(r.amount) + '</td>' +
            '<td class="num">' + fmtMoney(r.tax) + '</td></tr>';
        }) + '</div>' +
        '<div class="card"><h3>进项供应商 Top10</h3>' +
        rankList(inp.bySupplier || [], 'name', 'tax') + '</div></div>';
    }).catch(function (e) {
      document.getElementById('r-body').innerHTML =
        '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }
  document.getElementById('r-go').onclick = function () {
    load(document.getElementById('r-period').value);
  };
  load(period);
};

/* ==================================================== 风险预警 */
PAGES.risk = function (el) {
  var st = {status: '', level: ''};
  el.innerHTML = pageHead('风险预警', '基于规则引擎的税务风险扫描与处置',
    '<button class="btn" id="k-scan">重新扫描</button>');

  var f = document.createElement('div');
  f.className = 'card';
  f.innerHTML = '<div class="toolbar" style="margin:0">' +
    '<select id="k-status"><option value="">全部状态</option><option>待处理</option>' +
    '<option>已处理</option><option>已忽略</option></select>' +
    '<select id="k-level"><option value="">全部等级</option><option>险</option>' +
    '<option>警</option><option>提</option></select>' +
    '<button class="btn sm" id="k-go">筛选</button>' +
    '<span id="k-sum" style="margin-left:auto;color:var(--sub);font-size:12.5px"></span></div>';
  el.appendChild(f);

  var box = document.createElement('div');
  box.className = 'card';
  el.appendChild(box);

  function load() {
    var q = '/api/risks?' + (st.status ? 'status=' + encodeURIComponent(st.status) + '&' : '') +
      (st.level ? 'level=' + encodeURIComponent(st.level) : '');
    GET(q).then(function (r) {
      var d = r.data || {}, rows = d.list || [];
      var sc = d.openScore;
      if (sc != null && typeof sc === 'object') sc = sc.score != null ? sc.score : JSON.stringify(sc);
      f.querySelector('#k-sum').textContent =
        '共 ' + (d.total || 0) + ' 条 · 风险指数 ' + (sc == null ? '—' : sc);
      if (!rows.length) {
        box.innerHTML = '<h3>风险清单</h3><div class="empty">暂无风险记录</div>';
        return;
      }
      box.innerHTML = '<h3>风险清单<span class="sub">' + rows.length + ' 条</span></h3>' +
        '<div class="risk-list">' + rows.map(function (r) {
          var cls = r.level === '险' ? 'lv-hi' : (r.level === '警' ? 'lv-mid' : 'lv-lo');
          return '<div class="risk-item ' + cls + '">' +
            '<div class="h">' + levelTag(r.level) + '<b>' + esc(r.title) + '</b>' +
            '<span style="margin-left:auto">' + statusTag(r.status) + '</span></div>' +
            '<div class="d">' + esc(r.entity_name || r.entity) + ' · ' +
            esc(r.period) + ' · 规则 ' + esc(r.code) + ' · 权重 ' + r.weight + '</div>' +
            '<div class="d">' + esc(r.detail) + '</div>' +
            (r.status === '待处理' && perm('risk.read')
              ? '<div class="toolbar" style="margin:8px 0 0">' +
                '<input placeholder="处置说明" data-memo="' + r.id + '" style="width:240px">' +
                '<button class="btn sm" data-close="' + r.id + '">标记已处理</button>' +
                '<button class="btn sm ghost" data-ignore="' + r.id + '">忽略</button></div>'
              : '') +
            '</div>';
        }).join('') + '</div>';

      box.querySelectorAll('[data-close]').forEach(function (b) {
        b.onclick = function () { closeRisk(b.getAttribute('data-close'), '已处理', box); };
      });
      box.querySelectorAll('[data-ignore]').forEach(function (b) {
        b.onclick = function () { closeRisk(b.getAttribute('data-ignore'), '已忽略', box); };
      });
    }).catch(function (e) {
      box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }

  function closeRisk(id, status, box) {
    var memo = box.querySelector('[data-memo="' + id + '"]');
    POST('/api/risks/' + id + '/close',
         {status: status, memo: memo ? memo.value : ''})
      .then(function () { toast('已' + status); load(); })
      .catch(function (e) { toast(e.message, true); });
  }

  f.querySelector('#k-go').onclick = function () {
    st.status = f.querySelector('#k-status').value;
    st.level = f.querySelector('#k-level').value;
    load();
  };
  el.querySelector('#k-scan').onclick = function () {
    var b = this;
    b.disabled = true; b.textContent = '扫描中…';
    POST('/api/risks/scan', {period: curPeriod()}).then(function (r) {
      toast('扫描完成，新增 ' + (((r.data || {}).created) || []).length + ' 条风险');
      b.disabled = false; b.textContent = '重新扫描';
      load();
    }).catch(function (e) {
      toast(e.message, true);
      b.disabled = false; b.textContent = '重新扫描';
    });
  };
  load();
};

/* ==================================================== 纳税主体 */
PAGES.entity = function (el) {
  el.innerHTML = pageHead('纳税主体', '集团下属各纳税主体的登记信息与税务属性');
  var box = document.createElement('div');
  el.appendChild(box);

  GET('/api/entities').then(function (r) {
    var list = (r.data || {}).list || [];
    var normal = list.filter(function (e) { return e.taxpayer_type === '一般纳税人'; }).length;
    var small = list.filter(function (e) { return e.taxpayer_type !== '一般纳税人'; }).length;
    var micro = list.filter(function (e) { return Number(e.small_profit); }).length;
    var hi = list.filter(function (e) { return Number(e.high_tech); }).length;

    box.innerHTML =
      '<div class="kpis">' +
      kpi(list.length, '主体总数', 'pri') +
      kpi(normal, '一般纳税人') +
      kpi(small, '小规模纳税人') +
      kpi(micro, '小型微利企业', 'ok') +
      kpi(hi, '高新技术企业', 'ok') +
      '</div>' +
      '<div class="card"><h3>主体档案</h3>' +
      table(['编码', '主体名称', '纳税人识别号', '身份', '行业', '所在地', '法人',
             '人员', '~资产总额', '小微', '高新', '状态'],
        list,
        function (e) {
          return '<tr class="click" data-code="' + esc(e.code) + '">' +
            '<td><b>' + esc(e.code) + '</b></td>' +
            '<td>' + esc(e.name) + '</td>' +
            '<td><small>' + esc(e.tax_no) + '</small></td>' +
            '<td>' + tag(e.taxpayer_type,
              e.taxpayer_type === '一般纳税人' ? 'pri' : 'warn') + '</td>' +
            '<td>' + esc(e.industry) + '</td>' +
            '<td>' + esc(e.city_type) + '</td>' +
            '<td>' + esc(e.legal_person) + '</td>' +
            '<td>' + esc(e.staff_count) + '</td>' +
            '<td class="num">' + fmtWan(e.asset_total) + '</td>' +
            '<td>' + (Number(e.small_profit) ? tag('是', 'ok') : '—') + '</td>' +
            '<td>' + (Number(e.high_tech) ? tag('是', 'pri') : '—') + '</td>' +
            '<td>' + statusTag(e.status) + '</td></tr>';
        }) + '</div>';

    box.querySelectorAll('tr[data-code]').forEach(function (tr) {
      tr.onclick = function () { showEntity(tr.getAttribute('data-code')); };
    });
  }).catch(function (e) {
    box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
  });
};

function showEntity(code) {
  GET('/api/entities/' + encodeURIComponent(code)).then(function (r) {
    var e = r.data || {}, s = e.stats || {};
    modal('<h3>' + esc(e.name) + '</h3>' +
      '<div class="settle"><div class="row">' +
      '<div><b>' + fmtMoney(s.outputTax) + '</b><span>当期销项</span></div>' +
      '<div><b>' + fmtMoney(s.inputTax) + '</b><span>当期进项</span></div>' +
      '<div><b>' + fmtMoney(s.vatPayable) + '</b><span>应纳增值税</span></div>' +
      '<div><b>' + (s.invoices || 0) + '</b><span>发票总数</span></div>' +
      '</div><div class="note">' + esc(s.period || '') + ' 期间数据</div></div>' +
      '<div class="grid2">' +
      field('纳税人识别号', '<input value="' + esc(e.tax_no) + '" disabled>') +
      field('纳税人身份', '<input value="' + esc(e.taxpayer_type) + '" disabled>') +
      field('所属行业', '<input value="' + esc(e.industry) + '" disabled>') +
      field('所在地', '<input value="' + esc(e.city_type) + '" disabled>') +
      field('法定代表人', '<input value="' + esc(e.legal_person) + '" disabled>') +
      field('联系电话', '<input value="' + esc(e.phone) + '" disabled>') +
      field('注册地址', '<input value="' + esc(e.reg_address) + '" disabled>') +
      field('注册资本', '<input value="' + fmtMoney(e.reg_capital, true) + '" disabled>') +
      field('从业人数', '<input value="' + esc(e.staff_count) + '" disabled>') +
      field('资产总额', '<input value="' + fmtMoney(e.asset_total, true) + '" disabled>') +
      '</div>' +
      '<div style="font-size:12.5px;color:var(--sub)">' +
      '小型微利：' + (Number(e.small_profit) ? '是（实际税负 5%）' : '否') + ' · ' +
      '高新技术：' + (Number(e.high_tech) ? '是（15% 优惠税率）' : '否') + '</div>' +
      '<div class="acts"><button class="btn ghost" onclick="closeModal()">关闭</button></div>',
      true);
  }).catch(function (e) { toast(e.message, true); });
}

/* ==================================================== 凭证台账 */
PAGES.voucher = function (el) {
  el.innerHTML = pageHead('凭证台账', '涉税凭证与合同台账，含印花税计提情况');
  var box = document.createElement('div');
  el.appendChild(box);

  Promise.all([GET('/api/vouchers'), GET('/api/contracts')]).then(function (rs) {
    var vou = (rs[0].data || {}).list || [];
    var con = (rs[1].data || {}).list || [];
    var stampTotal = con.reduce(function (a, c) { return a + Number(c.stamp_tax || 0); }, 0);
    var unpaid = con.filter(function (c) { return !Number(c.stamp_paid); }).length;

    box.innerHTML =
      '<div class="kpis">' +
      kpi(vou.length, '涉税凭证') +
      kpi(con.length, '合同数') +
      kpi(fmtWan(stampTotal), '印花税合计', 'pri') +
      kpi(unpaid, '印花税待缴', unpaid ? 'warn' : 'ok') +
      '</div>' +
      '<div class="card"><h3>涉税凭证</h3>' +
      table(['凭证号', '主体', '期间', '日期', '摘要', '科目', '~借方', '~贷方', '税种', '来源'],
        vou.slice(0, 60),
        function (v) {
          return '<tr><td><b>' + esc(v.no) + '</b></td><td>' + esc(v.entity) +
            '</td><td>' + esc(v.period) + '</td><td>' + esc(fmtDate(v.vdate)) + '</td>' +
            '<td class="wrap">' + esc(v.summary) + '</td><td>' + esc(v.account) + '</td>' +
            '<td class="num">' + fmtMoney(v.debit) + '</td>' +
            '<td class="num">' + fmtMoney(v.credit) + '</td>' +
            '<td>' + esc(v.tax_type) + '</td><td>' + esc(v.src) + '</td></tr>';
        }) + '</div>' +
      '<div class="card"><h3>合同与印花税</h3>' +
      table(['合同号', '主体', '类型', '对方', '~金额', '~印花税', '签订日期', '状态'],
        con,
        function (c) {
          return '<tr><td><b>' + esc(c.no) + '</b></td><td>' + esc(c.entity) +
            '</td><td>' + esc(c.ctype) + '</td><td class="wrap">' + esc(c.party) + '</td>' +
            '<td class="num">' + fmtMoney(c.amount) + '</td>' +
            '<td class="num">' + fmtMoney(c.stamp_tax) + '</td>' +
            '<td>' + esc(fmtDate(c.sign_date)) + '</td>' +
            '<td>' + statusTag(c.status) + (Number(c.stamp_paid)
              ? ' ' + tag('已缴', 'ok') : ' ' + tag('待缴', 'warn')) + '</td></tr>';
        }) + '</div>';
  }).catch(function (e) {
    box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
  });
};

/* ==================================================== 政策法规 */
PAGES.policy = function (el) {
  el.innerHTML = pageHead('政策法规', '现行有效的税收法规与优惠政策汇编');
  var box = document.createElement('div');
  el.appendChild(box);

  var f = document.createElement('div');
  f.className = 'card';
  f.innerHTML = '<div class="toolbar" style="margin:0">' +
    '<select id="p-type"><option value="">全部税种</option>' +
    TAX_TYPES.map(function (t) { return '<option>' + t + '</option>'; }).join('') +
    '</select><input id="p-kw" placeholder="标题 / 摘要 / 标签" style="width:220px">' +
    '<button class="btn sm" id="p-go">检索</button>' +
    '<span style="margin-left:auto;color:var(--sub);font-size:12.5px">' +
    '税率速查见下方卡片</span></div>';
  el.insertBefore(f, box);

  function load() {
    var t = f.querySelector('#p-type').value;
    var kw = f.querySelector('#p-kw').value.trim();
    GET('/api/policies?' + (t ? 'tax_type=' + encodeURIComponent(t) + '&' : '') +
        (kw ? 'kw=' + encodeURIComponent(kw) : '')).then(function (r) {
      var list = (r.data || {}).list || [];
      box.innerHTML =
        '<div class="card"><h3>税率速查</h3><div class="rate-grid">' +
        [['13%', '销售货物 / 加工修理修配 / 有形动产租赁'],
         ['9%', '交通运输 / 邮政 / 基础电信 / 建筑 / 不动产租赁销售'],
         ['6%', '现代服务 / 金融 / 生活服务 / 无形资产'],
         ['3%', '小规模纳税人征收率'],
         ['1%', '小规模 3% 减按 1%（至 2027-12-31）'],
         ['5%', '小型微利企业所得税实际税负'],
         ['0.03%', '买卖合同印花税'],
         ['1.2%', '房产税从价计征']].map(function (x) {
          return '<div class="rate-card"><b>' + x[0] + '</b><span>' + esc(x[1]) + '</span></div>';
        }).join('') + '</div></div>' +
        '<div class="card"><h3>政策清单<span class="sub">' + list.length + ' 条</span></h3>' +
        table(['文号', '标题', '税种', '类别', '生效日期', '状态'], list,
          function (p) {
            return '<tr class="click" data-pid="' + p.id + '"><td><small>' +
              esc(p.doc_no || '—') + '</small></td><td class="wrap"><b>' + esc(p.title) +
              '</b><br><small style="color:var(--sub)">' +
              esc(String(p.summary || '').slice(0, 60)) + '</small></td>' +
              '<td>' + esc(p.tax_type) + '</td><td>' + esc(p.category) + '</td>' +
              '<td>' + esc(fmtDate(p.effect_date)) + '</td>' +
              '<td>' + statusTag(p.status) + '</td></tr>';
          }) + '</div>';
      box.querySelectorAll('tr[data-pid]').forEach(function (tr) {
        tr.onclick = function () { showPolicy(tr.getAttribute('data-pid')); };
      });
    }).catch(function (e) {
      box.innerHTML = '<div class="empty">加载失败：' + esc(e.message) + '</div>';
    });
  }
  f.querySelector('#p-go').onclick = load;
  f.querySelector('#p-kw').onkeydown = function (e) { if (e.key === 'Enter') load(); };
  load();
};

function showPolicy(id) {
  GET('/api/policies/' + id).then(function (r) {
    var p = r.data || {};
    modal('<h3>' + esc(p.title) + '</h3>' +
      '<div style="font-size:12.5px;color:var(--sub);margin-bottom:12px">' +
      esc(p.doc_no || '—') + ' · ' + esc(p.tax_type) + ' · ' + esc(p.category) +
      ' · 生效 ' + esc(fmtDate(p.effect_date)) +
      (p.expire_date ? ' · 失效 ' + esc(fmtDate(p.expire_date)) : '') + '</div>' +
      '<div class="card" style="background:#f7fbfa">' + esc(p.summary || '') + '</div>' +
      '<div style="white-space:pre-wrap;font-size:13px;line-height:1.8">' +
      esc(p.content || '（正文略）') + '</div>' +
      (p.tags ? '<div style="margin-top:12px">' + String(p.tags).split(',').map(function (t) {
        return tag(t, 'pri');
      }).join(' ') + '</div>' : '') +
      '<div class="acts"><button class="btn ghost" onclick="closeModal()">关闭</button></div>',
      true);
  }).catch(function (e) { toast(e.message, true); });
}

/* ==================================================== 系统管理 */
PAGES.system = function (el) {
  el.innerHTML = pageHead('系统管理', '组织、用户、角色权限、税务参数与接口密钥');
  var tabs = ['组织用户', '角色权限', '税务参数', '接口密钥', '操作日志'];
  var cur = 0;
  var bar = document.createElement('div');
  bar.className = 'toolbar';
  bar.innerHTML = tabs.map(function (t, i) {
    return '<button class="btn sm ' + (i === 0 ? '' : 'ghost') + '" data-t="' + i + '">' +
      t + '</button>';
  }).join('');
  el.appendChild(bar);
  var box = document.createElement('div');
  el.appendChild(box);

  function switchTo(i) {
    cur = i;
    bar.querySelectorAll('[data-t]').forEach(function (b) {
      b.className = 'btn sm ' + (Number(b.getAttribute('data-t')) === i ? '' : 'ghost');
    });
    box.innerHTML = '<div class="card"><div class="empty">加载中…</div></div>';
    if (i === 0) {
      Promise.all([GET('/api/depts'), GET('/api/users')]).then(function (rs) {
        var depts = (rs[0].data || {}).list || [];
        var users = (rs[1].data || {}).list || [];
        box.innerHTML =
          '<div class="card"><h3>部门<span class="sub">' + depts.length + ' 个</span></h3>' +
          table(['编码', '部门', '负责人', '人数', '说明'], depts, function (d) {
            return '<tr><td>' + esc(d.code) + '</td><td><b>' + esc(d.name) +
              '</b></td><td>' + esc(d.leaderName || d.leader || '—') + '</td>' +
              '<td>' + d.headcount + '</td><td class="wrap">' + esc(d.memo || '—') +
              '</td></tr>';
          }) + '</div>' +
          '<div class="card"><h3>用户<span class="sub">' + users.length + ' 人</span></h3>' +
          table(['用户名', '姓名', '部门', '岗位', '角色', '手机', '邮箱', '状态'],
            users, function (u) {
              return '<tr><td><b>' + esc(u.username) + '</b></td><td>' + esc(u.name) +
                '</td><td>' + esc(u.deptName || u.dept) + '</td><td>' + esc(u.title) +
                '</td><td>' + tag(u.role, 'pri') + '</td><td>' + esc(u.phone) +
                '</td><td><small>' + esc(u.email) + '</small></td>' +
                '<td>' + statusTag(u.status) + '</td></tr>';
            }) + '</div>';
      }).catch(function (e) {
        box.innerHTML = '<div class="card"><div class="empty">' + esc(e.message) + '</div></div>';
      });
    } else if (i === 1) {
      GET('/api/roles').then(function (r) {
        var list = (r.data || {}).list || [];
        box.innerHTML = '<div class="card"><h3>角色与权限</h3>' +
          table(['角色', '说明', '人数', '权限项'], list, function (x) {
            return '<tr><td><b>' + esc(x.label) + '</b><br><small style="color:var(--sub)">' +
              esc(x.code) + '</small></td><td>' + esc(x.label) + '</td><td>' + x.users +
              '</td><td class="wrap">' + (x.perms || []).map(function (p) {
                return tag(p, p === '*' ? 'err' : '');
              }).join(' ') + '</td></tr>';
          }) + '</div>';
      }).catch(function (e) {
        box.innerHTML = '<div class="card"><div class="empty">' + esc(e.message) + '</div></div>';
      });
    } else if (i === 2) {
      GET('/api/rules').then(function (r) {
        var rules = r.data || {};
        box.innerHTML = '<div class="card"><h3>税务参数</h3>' +
          '<div class="grid2">' + Object.keys(rules).map(function (k) {
            return field(k, '<input data-rule="' + esc(k) + '" value="' +
              esc(rules[k]) + '"' + (perm('system.write') ? '' : ' disabled') + '>');
          }).join('') + '</div>' +
          (perm('system.write')
            ? '<button class="btn" id="save-rules">保存参数</button>' : '') +
          '</div>' +
          '<div class="card"><h3>说明</h3><div style="font-size:12.5px;color:var(--sub);line-height:1.9">' +
          'city_type：城建税所在地分类（市区 7% / 县城·镇 5% / 其他 1%）<br>' +
          'surtax_halve：六税两费减半开关（2023-01-01 ~ 2027-12-31）<br>' +
          'fund_exempt_sales：教育费附加免征的月销售额门槛<br>' +
          'burden_tolerance：税负率偏离行业均值的容差<br>' +
          'invoice_amount_limit：单张发票金额预警上限<br>' +
          'late_fee_rate：滞纳金按日加收比率（万分之五）<br>' +
          'declare_warn_days：申报到期前提醒天数</div></div>';

        var sb = document.getElementById('save-rules');
        if (sb) sb.onclick = function () {
          var payload = {};
          box.querySelectorAll('[data-rule]').forEach(function (inp) {
            payload[inp.getAttribute('data-rule')] = inp.value;
          });
          POST('/api/rules/save', {rules: payload}).then(function () {
            toast('已保存');
          }).catch(function (e) { toast(e.message, true); });
        };
      }).catch(function (e) {
        box.innerHTML = '<div class="card"><div class="empty">' + esc(e.message) + '</div></div>';
      });
    } else if (i === 3) {
      GET('/api/api-keys').then(function (r) {
        var list = (r.data || {}).list || [];
        box.innerHTML = '<div class="card"><h3>接口密钥<span class="sub">' +
          list.length + ' 个</span></h3>' +
          (perm('system.write')
            ? '<div class="toolbar"><input id="k-name" placeholder="密钥名称" style="width:200px">' +
              '<select id="k-scope"><option value="read">只读</option>' +
              '<option value="write">读写</option><option value="full">全部</option></select>' +
              '<button class="btn sm" id="k-new">创建密钥</button></div>'
            : '') +
          table(['ID', '名称', '前缀', '范围', '创建人', '状态', '创建时间'], list,
            function (k) {
              return '<tr><td>' + k.id + '</td><td><b>' + esc(k.name) +
                '</b></td><td><code>' + esc(k.prefix) + '…</code></td><td>' +
                esc(k.scope) + '</td><td>' + esc(k.owner) + '</td>' +
                '<td>' + statusTag(k.status) + '</td>' +
                '<td>' + esc(fmtDate(k.created_at)) + '</td></tr>';
            }, '暂无密钥') + '</div>' +
          '<div class="card"><h3>对接说明</h3><div style="font-size:12.5px;line-height:1.9">' +
          '鉴权支持五种通道：<code>Authorization: Bearer &lt;token&gt;</code>、' +
          '<code>X-Tax-Token</code>、<code>Cookie: tax_token</code>、' +
          '<code>?token=</code>、<code>X-Tax-Key: &lt;api key&gt;</code>。<br>' +
          '写接口建议带 <code>Idempotency-Key</code> 头做幂等；' +
          '增量同步用 <code>GET /api/sync?version=invoices:3</code>。<br>' +
          '完整契约见 <a href="../api.md" target="_blank">docs/api.md</a>，' +
          '在线 OpenAPI 见 <a href="' + PREFIX + '/api/apidoc" target="_blank">/api/apidoc</a>。' +
          '</div></div>';

        var nb = document.getElementById('k-new');
        if (nb) nb.onclick = function () {
          var name = document.getElementById('k-name').value.trim();
          if (!name) { toast('请填写名称', true); return; }
          POST('/api/api-keys/create', {name: name, scope: document.getElementById('k-scope').value})
            .then(function (res) {
              var k = res.data.key;
              modal('<h3>密钥已创建</h3>' +
                '<p style="color:var(--sub);font-size:12.5px">' +
                '密钥仅显示这一次，请立即复制保存。</p>' +
                '<textarea readonly style="font-family:monospace;min-height:70px">' +
                esc(k) + '</textarea>' +
                '<div class="acts"><button class="btn ghost" id="cp">复制</button>' +
                '<button class="btn" onclick="closeModal()">完成</button></div>');
              document.getElementById('cp').onclick = function () {
                var ta = document.querySelector('#modal textarea');
                ta.select(); document.execCommand('copy');
                toast('已复制');
              };
              switchTo(3);
            }).catch(function (e) { toast(e.message, true); });
        };
      }).catch(function (e) {
        box.innerHTML = '<div class="card"><div class="empty">' + esc(e.message) + '</div></div>';
      });
    } else {
      GET('/api/logs').then(function (r) {
        var list = (r.data || {}).list || [];
        box.innerHTML = '<div class="card"><h3>操作日志<span class="sub">最近 ' +
          list.length + ' 条</span></h3>' +
          table(['时间', '用户', '动作', '对象', '详情'], list, function (l) {
            return '<tr><td>' + esc(l.created_at) + '</td><td>' + esc(l.username) +
              '</td><td>' + esc(l.action) + '</td><td>' + esc(l.target || '—') +
              '</td><td class="wrap">' + esc(l.memo || '—') + '</td></tr>';
          }, '暂无日志') + '</div>';
      }).catch(function (e) {
        box.innerHTML = '<div class="card"><div class="empty">' + esc(e.message) + '</div></div>';
      });
    }
  }

  bar.querySelectorAll('[data-t]').forEach(function (b) {
    b.onclick = function () { switchTo(Number(b.getAttribute('data-t'))); };
  });
  switchTo(0);
};
