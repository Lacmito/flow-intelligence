// FLOW Intelligence - Billing / Cost Allocation Module

var PROJ_COLORS = {};
PROJECTS.forEach(function(p) {
  var cm = { 'proj-cdr':'#fb923c','proj-c2b':'#38bdf8','proj-nat':'#f472b6','proj-met':'#4ade80','proj-notif':'#a78bfa','proj-pay':'#fbbf24','proj-cons':'#22d3ee','proj-mud':'#a78bfa','proj-dcc':'#ec4899','proj-cjs':'#f59e0b','proj-ver':'#10b981' };
  PROJ_COLORS[p.id] = cm[p.tag_class] || '#94a3b8';
});

function getWeights(svcId, projIds) {
  var fb = getSvcFeedback(svcId);
  if (fb.weights && Object.keys(fb.weights).length > 0) return fb.weights;
  if (typeof DEFAULT_WEIGHTS !== 'undefined' && DEFAULT_WEIGHTS[svcId]) return DEFAULT_WEIGHTS[svcId];
  var w = {};
  projIds.forEach(function(pid) { w[pid] = Math.round(100 / projIds.length); });
  return w;
}

function computeBilling() {
  var pc = {};
  PROJECTS.forEach(function(p) { pc[p.id] = { project: p, services: [], total: 0 }; });
  pc['_none'] = { project: { id:'_none', name:'Sin proyecto', tag_label:'N/A', tag_class:'proj-none', client:'-', billable:false }, services: [], total: 0 };

  SCAN_DATA.forEach(function(svc) {
    var cost = getEffectiveCost(svc);
    var pr = svc.projects || [];
    if (pr.length === 0) {
      pc['_none'].services.push({ id: svc.id, name: svc.name, cost: cost, share: cost, pct: 100, category: svc.category });
      pc['_none'].total += cost;
      return;
    }
    var w = getWeights(svc.id, pr);
    var totalW = 0;
    pr.forEach(function(pid) { totalW += (w[pid] || 0); });
    if (totalW === 0) totalW = 100;

    pr.forEach(function(pid) {
      if (!pc[pid]) return;
      var pct = (w[pid] || 0);
      var share = cost * pct / totalW;
      pc[pid].services.push({
        id: svc.id, name: svc.name, cost: cost, share: share,
        pct: Math.round(pct * 100 / totalW), category: svc.category,
        shared: pr.length > 1, projCount: pr.length
      });
      pc[pid].total += share;
    });
  });
  return pc;
}

function renderBilling() {
  var billing = computeBilling();
  var totalBillable = 0, totalInternal = 0;
  PROJECTS.forEach(function(p) {
    var b = billing[p.id];
    if (p.billable) totalBillable += b.total; else totalInternal += b.total;
  });
  var realTotal = SCAN_DATA.reduce(function(s, svc) { return s + getEffectiveCost(svc); }, 0);

  var sumEl = document.getElementById('billingSummary');
  if (!sumEl) return;

  sumEl.innerHTML =
    '<div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap">' +
    '<h2 style="margin:0;font-size:1rem;color:var(--accent)">Resumen de facturaci\u00f3n</h2>' +
    '<span style="font-size:0.78rem;color:var(--muted)">Click en el % para editar la asignaci\u00f3n</span></div>' +
    '<div class="billing-summary-grid">' +
    '<div class="billing-summary-item"><div class="number" style="color:var(--red)">$' + realTotal.toFixed(0) + '</div><div class="label">Gasto total/mes</div></div>' +
    '<div class="billing-summary-item"><div class="number" style="color:var(--green)">$' + totalBillable.toFixed(0) + '</div><div class="label">Facturable a clientes</div></div>' +
    '<div class="billing-summary-item"><div class="number" style="color:var(--yellow)">$' + totalInternal.toFixed(0) + '</div><div class="label">Costo interno</div></div>' +
    '<div class="billing-summary-item"><div class="number" style="color:var(--muted)">$' + billing['_none'].total.toFixed(0) + '</div><div class="label">Sin asignar</div></div></div>';

  var projectOrder = PROJECTS.filter(function(p) { return billing[p.id].services.length > 0; })
    .sort(function(a, b) { return billing[b.id].total - billing[a.id].total; });

  var gh = '';
  projectOrder.forEach(function(p) {
    var b = billing[p.id];
    var color = PROJ_COLORS[p.id] || '#94a3b8';
    var bt = p.billable
      ? '<span class="billing-badge-billable">FACTURABLE</span>'
      : '<span class="billing-badge-internal">INTERNO</span>';

    var sh = b.services.sort(function(a, bb) { return bb.share - a.share; }).map(function(s) {
      var pctHtml;
      if (s.shared) {
        pctHtml = '<span class="editable" onclick="editWeight(\'' + s.id + '\',\'' + p.id + '\')" ' +
          'style="color:var(--accent);font-size:0.68rem;cursor:pointer;border-bottom:1px dashed rgba(56,189,248,0.4)" ' +
          'title="Click para editar asignaci\u00f3n">' + s.pct + '%</span>';
      } else {
        pctHtml = '<span style="font-size:0.68rem;color:var(--muted)">100%</span>';
      }
      var catDot = '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:' +
        (CATEGORY_COLORS[s.category] || '#94a3b8') + ';margin-right:4px"></span>';
      return '<div class="billing-svc-row">' +
        '<span class="billing-svc-name">' + catDot + s.name + ' ' + pctHtml + '</span>' +
        '<span class="billing-svc-cost" style="color:' + color + '">$' + s.share.toFixed(0) + '</span></div>';
    }).join('');

    gh += '<div class="billing-card">' +
      '<div class="billing-card-header">' +
      '<h3><span class="proj-tag ' + p.tag_class + '">' + p.tag_label + '</span> ' + p.name + '</h3>' +
      '<div class="billing-card-total" style="color:' + color + '">$' + b.total.toFixed(0) + '/mes</div></div>' +
      '<div class="billing-card-client">' + bt + ' Cliente: <strong>' + p.client + '</strong></div>' +
      sh + '</div>';
  });

  if (billing['_none'].services.length > 0) {
    var ns = billing['_none'].services.sort(function(a, b) { return b.cost - a.cost; }).map(function(s) {
      return '<div class="billing-svc-row">' +
        '<span class="billing-svc-name">' + s.name + '</span>' +
        '<span class="billing-svc-cost" style="color:var(--red)">$' + s.cost.toFixed(0) + '</span></div>';
    }).join('');
    gh += '<div class="billing-card" style="border-color:rgba(248,113,113,0.3)">' +
      '<div class="billing-card-header"><h3 style="color:var(--red)">Sin proyecto</h3>' +
      '<div class="billing-card-total" style="color:var(--red)">$' + billing['_none'].total.toFixed(0) + '</div></div>' +
      '<div class="billing-card-client"><span class="billing-badge-internal">REVISAR</span></div>' +
      ns + '</div>';
  }

  document.getElementById('billingGrid').innerHTML = gh;
}

function editWeight(svcId, projId) {
  var svc = SCAN_DATA.find(function(s) { return s.id === svcId; });
  if (!svc) return;
  var pr = svc.projects || [];
  var w = getWeights(svcId, pr);

  var lines = pr.map(function(pid) {
    var p = PROJECTS.find(function(x) { return x.id === pid; });
    return (p ? p.tag_label : pid) + ': ' + (w[pid] || 0) + '%';
  }).join('\n');

  var projLabels = pr.map(function(pid) {
    var p = PROJECTS.find(function(x) { return x.id === pid; });
    return p ? p.tag_label : pid;
  }).join(', ');

  var input = prompt(
    'Asignaci\u00f3n de costo para "' + svc.name + '"\n' +
    '(costo total: $' + getEffectiveCost(svc).toFixed(0) + '/mes)\n\n' +
    lines + '\n\n' +
    'Ingres\u00e1 los nuevos % separados por coma\n(' + projLabels + '):'
  );
  if (!input) return;

  var vals = input.split(',').map(function(v) { return parseInt(v.trim()) || 0; });
  if (vals.length !== pr.length) {
    alert('Necesit\u00e1s ' + pr.length + ' valores, uno por proyecto (' + projLabels + ')');
    return;
  }

  var newW = {};
  pr.forEach(function(pid, i) { newW[pid] = vals[i]; });
  saveFeedback(svcId, { weights: newW });
  setTimeout(renderBilling, 300);
}
