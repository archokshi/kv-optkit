from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def quickview_index():
    # Simple, dependency-free QuickView to visualize telemetry and advisor recs
    html = """
    <!doctype html>
    <html lang=\"en\">
    <head>
      <meta charset=\"utf-8\" />
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
      <title>KV-OptKit QuickView</title>
      <style>
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 20px; color: #222; }
        h1 { font-size: 20px; margin: 0 0 12px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
        .card { border: 1px solid #e3e3e3; border-radius: 8px; padding: 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
        .kpi { font-size: 28px; font-weight: 600; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 6px 8px; border-bottom: 1px solid #eee; text-align: left; font-size: 14px; }
        th { background: #fafafa; }
        .muted { color: #666; font-size: 12px; }
        .badge { display: inline-block; padding: 2px 6px; border-radius: 12px; font-size: 12px; }
        .low { background: #e6f7f1; color: #0a7e55; }
        .medium { background: #fff7e6; color: #ad6b00; }
        .high { background: #fdecea; color: #a8071a; }
      </style>
    </head>
    <body>
      <div style=\"display:flex;align-items:center;gap:12px;justify-content:space-between\">
        <h1 style=\"margin:0\">KV-OptKit QuickView</h1>
        <div style=\"display:flex;align-items:center;gap:8px\">
          <span id=\"cap-badge\" class=\"badge low\" title=\"Adapter capability level\">L0</span>
          <label class=\"muted\">Allowed actions:</label>
          <select id=\"sel-allowed\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px\">
            <option value=\"all\" selected>All</option>
            <option value=\"QUANTIZE\">QUANTIZE</option>
            <option value=\"OFFLOAD\">OFFLOAD</option>
            <option value=\"EVICT\">EVICT</option>
          </select>
          <button id=\"btn-apply\" style=\"padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#f0fff4;cursor:pointer\">Apply from Advisor</button>
          <label class=\"muted\" style=\"margin-left:8px; user-select:none;\">
            <input type=\"checkbox\" id=\"apply-toggle\" style=\"vertical-align:middle\"> Enable Apply
          </label>
          <button id=\"btn-refresh\" style=\"padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#fafafa;cursor:pointer\">Refresh now</button>
          <label class=\"muted\" style=\"margin-left:8px; user-select:none;\">
            <input type=\"checkbox\" id=\"auto-refresh\" checked style=\"vertical-align:middle\"> Auto Refresh
          </label>
          <select id=\"refresh-interval\" title=\"Auto refresh interval\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px\">
            <option value=\"1000\">1s</option>
            <option value=\"3000\" selected>3s</option>
            <option value=\"5000\">5s</option>
            <option value=\"10000\">10s</option>
          </select>
        </div>
      </div>
      <div id=\"error-banner\" class=\"muted\" style=\"display:none;color:#a8071a;background:#fdecea;border:1px solid #f5c2c7;padding:8px;border-radius:6px;margin:10px 0\"></div>
      <div id=\"plan-banner\" class=\"muted\" style=\"display:none;color:#0a7e55;background:#e6f7f1;border:1px solid #b7eb8f;padding:8px;border-radius:6px;margin:10px 0\"></div>
      <div id=\"guard-banner\" class=\"muted\" style=\"display:none;color:#0a7e55;background:#e6f7f1;border:1px solid #b7eb8f;padding:8px;border-radius:6px;margin:10px 0\"></div>
      <div id=\"mode-banner\" class=\"muted\" style=\"display:none;color:#094482;background:#e6f4ff;border:1px solid #91caff;padding:8px;border-radius:6px;margin:10px 0\"></div>
      <div id=\"apply-stats\" class=\"muted\" style=\"display:block;color:#5a5a5a;background:#fafafa;border:1px solid #eee;padding:6px 8px;border-radius:6px;margin:6px 0\">Applies: success 0, fail 0</div>
      <div id=\"gov-stats\" class=\"muted\" style=\"display:block;color:#5a5a5a;background:#fafafa;border:1px solid #eee;padding:6px 8px;border-radius:6px;margin:6px 0\">Governor: throttle_events 0, governed_bytes 0</div>
      <details style=\"margin:6px 0\">
        <summary class=\"muted\" style=\"cursor:pointer\">Legend: Adapter Capability Levels</summary>
        <div class=\"muted\" style=\"margin-top:6px\">
          <div><b>L0</b>: Observe-only (no mutating actions)</div>
          <div><b>L1</b>: Limited advisory hooks (may include REUSE)</div>
          <div><b>L2</b>: Autopilot-light (safe EVICT and OFFLOAD)</div>
          <div><b>L3</b>: Full Autopilot (EVICT, OFFLOAD, QUANTIZE with rollback)</div>
        </div>
      </details>

      <div class=\"grid\">
        <div class=\"card\">
          <div class=\"muted\">HBM Utilization</div>
          <div id=\"kpi-hbm\" class=\"kpi\">--</div>
          <div class=\"muted\" id=\"kpi-hbm-detail\"></div>
        </div>
        <div class=\"card\">
          <div class=\"muted\">Latency (p95, ms)</div>
          <div id=\"kpi-lat\" class=\"kpi\">--</div>
        </div>
        <div class=\"card\">
          <div class=\"muted\">DDR Utilization</div>
          <div id=\"kpi-ddr\" class=\"kpi\">--</div>
          <div class=\"muted\" id=\"kpi-ddr-detail\"></div>
        </div>
        <div class=\"card\">
          <div class=\"muted\">Sequences</div>
          <div id=\"kpi-seq\" class=\"kpi\">--</div>
          <div class=\"muted\">Total active sequences</div>
        </div>
        <div class=\"card\">
          <div class=\"muted\">Engine Activity</div>
          <div class=\"kpi\" id=\"kpi-eng\">--</div>
          <div class=\"muted\" id=\"kpi-eng-detail\"></div>
        </div>
      </div>

      <div class=\"grid\" style=\"margin-top:16px\">
        <div class=\"card\">
          <div class=\"muted\" style=\"margin-bottom:6px\">Sequences</div>
          <table id=\"seq-table\">
            <thead><tr><th>Sequence</th><th>Tokens</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class=\"card\">
          <div class=\"muted\" style=\"margin-bottom:6px\">Advisor Recommendations</div>
          <table id=\"rec-table\">
            <thead><tr><th>Action</th><th>Target</th><th>Savings (GB)</th><th>Risk</th><th>Detail</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class=\"card\" id=\"dev-hooks\" style=\"display:none\">
          <div class=\"muted\" style=\"margin-bottom:6px\">Dev Hooks (KVOPT_DEV)</div>
          <div style=\"display:flex;gap:8px;flex-wrap:wrap;align-items:center\">
            <input id=\"dh-seq\" placeholder=\"sequence_id\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px\" />
            <input id=\"dh-bytes\" placeholder=\"bytes\" type=\"number\" min=\"0\" step=\"1\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px;width:120px\" />
            <select id=\"dh-src\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px\">
              <option>HBM</option>
              <option>DDR</option>
            </select>
            <select id=\"dh-dst\" style=\"padding:6px;border:1px solid #ccc;border-radius:6px\">
              <option>DDR</option>
              <option>HBM</option>
            </select>
            <button id=\"btn-alloc\" style=\"padding:6px 10px;border:1px solid #ccc;border-radius:6px\">Alloc</button>
            <button id=\"btn-move\" style=\"padding:6px 10px;border:1px solid #ccc;border-radius:6px\">Move</button>
            <button id=\"btn-free\" style=\"padding:6px 10px;border:1px solid #ccc;border-radius:6px\">Free</button>
          </div>
          <div id=\"dh-msg\" class=\"muted\" style=\"margin-top:6px\"></div>
        </div>
      </div>

      <script>
        function fmt(n, d=4) { try { return Number(n).toFixed(d); } catch { return String(n); } }
        function capLevel(caps) {
          const s = new Set(caps || []);
          const has = x => s.has(x);
          if (has('EVICT') && has('OFFLOAD') && has('QUANTIZE')) return 'L3';
          if (has('EVICT') && has('OFFLOAD')) return 'L2';
          if (s.size > 0) return 'L1';
          return 'L0';
        }

        let _refreshTimer = null;
        function _clearTimer() { try { if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; } } catch {}
        }
        function _schedule() {
          _clearTimer();
          try {
            const auto = document.getElementById('auto-refresh');
            const sel = document.getElementById('refresh-interval');
            const ms = parseInt(sel?.value || '3000') || 3000;
            if (auto && auto.checked) {
              _refreshTimer = setInterval(load, ms);
            }
          } catch {}
        }

        async function load() {
          try {
            // Adapter info for capability badge
            let info = {name: 'unknown', capabilities: []};
            try { info = await fetch('/adapter/info').then(r => r.json()); } catch {}
            const level = capLevel(info.capabilities);
            const cap = document.getElementById('cap-badge');
            cap.textContent = level;
            cap.className = 'badge ' + (level==='L3'?'low':level==='L2'?'medium':'high');
            // Disable unsupported actions in the selector
            try {
              const sel = document.getElementById('sel-allowed');
              const caps = new Set(info.capabilities || []);
              if (sel) {
                for (const opt of sel.options) {
                  if (opt.value === 'all') { opt.disabled = false; continue; }
                  opt.disabled = !caps.has(opt.value);
                }

          // Dev Hooks actions
          const dh = document.getElementById('dev-hooks');
          function val(id) { const x = document.getElementById(id); return x ? x.value : ''; }
          async function postHook(kind) {
            try {
              const seq = val('dh-seq') || `seq-${Date.now()}`;
              const bytes = parseInt(val('dh-bytes')||'0')||0;
              const src = val('dh-src');
              const dst = val('dh-dst');
              const body = kind==='move' ? {sequence_id: seq, bytes, src, dst} : {sequence_id: seq, bytes};
              const resp = await fetch(`/dev/hooks/${kind}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
              const ok = resp.ok;
              const el = document.getElementById('dh-msg');
              if (el) el.textContent = ok ? `OK ${kind}` : `Error ${kind}: HTTP ${resp.status}`;
              await load();
            } catch (e) {
              const el = document.getElementById('dh-msg');
              if (el) el.textContent = 'Error: ' + (e?.message || String(e));
            }
          }
          if (dh) {
            const ba = document.getElementById('btn-alloc'); if (ba) ba.onclick = () => postHook('alloc');
            const bm = document.getElementById('btn-move');  if (bm) bm.onclick = () => postHook('move');
            const bf = document.getElementById('btn-free');  if (bf) bf.onclick = () => postHook('free');
          }
              }
            } catch {}

            // Guard + Last apply banners
            try {
              const guard = await fetch('/guard/status').then(r => r.json());
              const gb = document.getElementById('guard-banner');
              const mt = guard?.metrics || {};
              gb.textContent = `Guard: paused=${guard?.paused?'yes':'no'} | total_plans=${mt.total_plans ?? 0} | rollback_rate=${fmt(mt.rollback_rate ?? 0, 2)}`;
              gb.style.display = 'block';
            } catch {}
            try {
              const st = await fetch('/server/status').then(r => r.json());
              const mb = document.getElementById('mode-banner');
              mb.textContent = `Mode: adapter=${st.adapter} | caps=${(st.capabilities||[]).join(',')} | demo_seqs=${st.demo_sequences?'on':'off'} | seqs=${st.sequence_count ?? 0} | allow_apply=${st.allow_apply?'true':'false'}`;
              mb.style.display = 'block';
              // Reflect allow_apply in UI
              const toggle = document.getElementById('apply-toggle');
              const applyBtn = document.getElementById('btn-apply');
              if (toggle) toggle.checked = !!st.allow_apply;
              if (applyBtn) applyBtn.disabled = !st.allow_apply;
            } catch {}
            try {
              const last = await fetch('/apply/last').then(r => r.json());
              if (last && (last.plan_id || last.ok !== undefined)) {
                const pb = document.getElementById('plan-banner');
                pb.textContent = `Last Apply: plan=${last.plan_id || ''} | ok=${last.ok ? 'yes' : 'no'}${last.guard_reason?(' | guard='+last.guard_reason):''}${last.error?(' | error='+last.error):''}`;
                pb.style.display = 'block';
              }
            } catch {}

            const t = await fetch('/telemetry').then(r => r.json());
            let r = {recommendations: [], sequences: []};
            let advErr = null;
            try {
              r = await fetch('/advisor/report').then(resp => {
                if (!resp.ok) throw new Error('advisor/report HTTP ' + resp.status);
                return resp.json();
              });
            } catch (e) {
              advErr = e;
            }

            // KPIs
            const hbm = (t.hbm_utilization ?? r.hbm_utilization ?? 0);
            document.getElementById('kpi-hbm').textContent = fmt(hbm, 4);
            const used = t.hbm_used_gb ?? r.hbm_used_gb;
            if (used !== undefined) {
              document.getElementById('kpi-hbm-detail').textContent = `${fmt(used, 3)} GB used`;
            } else { document.getElementById('kpi-hbm-detail').textContent = ''; }
            const p95 = (t.p95_latency_ms ?? r.p95_latency_ms ?? 0);
            document.getElementById('kpi-lat').textContent = fmt(p95, 2);

            // DDR KPIs (best-effort)
            const ddrUtil = (t.ddr_utilization ?? r.ddr_utilization);
            const ddrUsed = (t.ddr_used_gb ?? r.ddr_used_gb);
            document.getElementById('kpi-ddr').textContent = ddrUtil !== undefined ? fmt(ddrUtil, 4) : '--';
            document.getElementById('kpi-ddr-detail').textContent = ddrUsed !== undefined ? `${fmt(ddrUsed, 3)} GB used` : '';

            // Engine Activity box (requires /metrics snapshot support)
            try {
              const snap = await fetch('/metrics/snapshot').then(r => r.json());
              const allocB = snap.engine_alloc_bytes_total || 0;
              const freeB = snap.engine_free_bytes_total || 0;
              const moves = snap.engine_page_moves_total || 0;
              const movedB = snap.engine_page_moved_bytes_total || 0;
              const capB = snap.offload_tick_cap_bytes || 0;
              document.getElementById('kpi-eng').textContent = `${moves} moves`;
              document.getElementById('kpi-eng-detail').textContent = `alloc=${allocB}B, free=${freeB}B, moved=${movedB}B, cap=${capB}B/tick`;
              // Governor stats line
              try {
                const thr = snap.governor_throttle_events_total || 0;
                const govB = snap.offload_governed_bytes_total || 0;
                const gs = document.getElementById('gov-stats');
                if (gs) gs.textContent = `Governor: throttle_events ${thr}, governed_bytes ${govB}`;
              } catch {}
            } catch {}

            // Sequences
            const seqs = (t.sequences || r.sequences || []);
            document.getElementById('kpi-seq').textContent = String(seqs.length);
            const st = document.querySelector('#seq-table tbody');
            st.innerHTML = '';
            seqs.forEach(s => {
              const tr = document.createElement('tr');
              const id = s.sequence_id || s.seq_id || s.id || 'unknown';
              const len = s.total_tokens || s.length_tokens || 0;
              tr.innerHTML = `<td>${id}</td><td>${len}</td>`;
              st.appendChild(tr);
            });

            // Recs
            const recs = r.recommendations || [];
            const rt = document.querySelector('#rec-table tbody');
            rt.innerHTML = '';
            recs.forEach(x => {
              const tr = document.createElement('tr');
              const riskClass = (x.risk || 'low').toLowerCase();
              const target = (x.details && x.details.target_sequence) ? x.details.target_sequence : 'N/A';
              const extra = (x.details && (x.details.range || x.details.range_tokens || x.details.suggested_factor))
                ? ` [${x.details.range || (x.details.range_tokens + ' tokens') || ('factor=' + x.details.suggested_factor)}]` : '';
              tr.innerHTML = `<td>${x.action}</td><td>${target}</td><td>${fmt(x.estimated_hbm_savings_gb||0, 4)}</td>`+
                             `<td><span class=\"badge ${riskClass}\">${x.risk||'low'}</span></td>`+
                             `<td>${(x.detail||'') + extra}</td>`;
              rt.appendChild(tr);
            });

            // Error banner handling
            const banner = document.getElementById('error-banner');
            if (advErr) {
              banner.textContent = 'Warning: advisor/report is currently unavailable. Showing telemetry only.';
              banner.style.display = 'block';
            } else {
              banner.textContent = '';
              banner.style.display = 'none';
            }

            // Show Dev Hooks panel if routes exist
            try {
              const routes = await fetch('/debug/routes').then(r => r.json());
              const haveDev = Array.isArray(routes) && routes.some(p => String(p).startsWith('/dev/hooks'));
              const dh = document.getElementById('dev-hooks');
              if (dh) dh.style.display = haveDev ? 'block' : 'none';
            } catch {}
          } catch (e) {
            // Top-level load() failure: surface in error banner
            const banner = document.getElementById('error-banner');
            if (banner) {
              banner.textContent = 'QuickView error: ' + (e && (e.message || String(e)));
              banner.style.display = 'block';
            }
          }
        }

        // Wire up UI controls after DOM is ready
        document.addEventListener('DOMContentLoaded', () => {
          const btnRefresh = document.getElementById('btn-refresh');
          if (btnRefresh) {
            btnRefresh.addEventListener('click', () => load());
          }
          // Auto-refresh controls
          const auto = document.getElementById('auto-refresh');
          const intervalSel = document.getElementById('refresh-interval');
          if (auto) auto.addEventListener('change', _schedule);
          if (intervalSel) intervalSel.addEventListener('change', _schedule);

          const toggle = document.getElementById('apply-toggle');
          if (toggle) {
            toggle.addEventListener('change', async (ev) => {
              try {
                const allow = !!ev.target.checked;
                const r = await fetch('/server/allow_apply', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ allow })
                });
                // Reflect in Apply button state
                try {
                  const applyBtn = document.getElementById('btn-apply');
                  if (applyBtn) applyBtn.disabled = !allow;
                } catch {}
              } catch (e) {
                const banner = document.getElementById('error-banner');
                if (banner) { banner.textContent = 'Failed to toggle apply: ' + (e?.message || e); banner.style.display = 'block'; }
              }
            });
          }

          const btnApply = document.getElementById('btn-apply');
          if (btnApply) {
            btnApply.addEventListener('click', async () => {
              try {
                // Build payload from Allowed Actions selector
                const sel = document.getElementById('sel-allowed');
                let allowed_actions = null;
                if (sel && sel.value && sel.value !== 'all') {
                  allowed_actions = [sel.value];
                }
                const resp = await fetch('/advisor/apply', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ allowed_actions })
                });
                const data = await resp.json();
                const pb = document.getElementById('plan-banner');
                if (pb) {
                  const plan = (data && (data.plan || data)) || {};
                  const pid = plan.plan_id || (plan.plan && plan.plan.plan_id) || '';
                  pb.textContent = 'Applied plan ' + pid + ' (see /apply/last)';
                  pb.style.display = 'block';
                }
                // Refresh view after apply
                await load();
              } catch (e) {
                const banner = document.getElementById('error-banner');
                if (banner) { banner.textContent = 'Failed to apply: ' + (e?.message || e); banner.style.display = 'block'; }
              }
            });
          }

          // Initial load and scheduling
          load();
          _schedule();

          // JSON modal handlers
          const modal = document.getElementById('json-modal');
          const btnPrev = document.getElementById('btn-preview-json');
          const btnCopy = document.getElementById('btn-json-copy');
          const btnDown = document.getElementById('btn-json-download');
          const btnClose = document.getElementById('btn-json-close');
          const pre = document.getElementById('json-content');
          async function openModal() {
            try {
              const snap = await fetch('/metrics/snapshot').then(r => r.json());
              pre.textContent = JSON.stringify(snap, null, 2);
              modal.style.display = 'block';
            } catch (e) {
              pre.textContent = 'Error loading /metrics/snapshot: ' + (e?.message || String(e));
              modal.style.display = 'block';
            }
          }
          function closeModal() { modal.style.display = 'none'; }
          async function copyJSON() {
            try { await navigator.clipboard.writeText(pre.textContent || ''); } catch {}
          }
          function downloadJSON() {
            try {
              const blob = new Blob([pre.textContent || ''], {type:'application/json'});
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = 'metrics_snapshot.json';
              document.body.appendChild(a); a.click(); a.remove();
              URL.revokeObjectURL(url);
            } catch {}
          }
          if (btnPrev) btnPrev.addEventListener('click', openModal);
          if (btnClose) btnClose.addEventListener('click', closeModal);
          if (btnCopy) btnCopy.addEventListener('click', copyJSON);
          if (btnDown) btnDown.addEventListener('click', downloadJSON);
        });
      </script>
      <div style="margin-top:16px;text-align:right" class="muted">
        <button id="btn-preview-json" style="padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#f5faff;cursor:pointer;margin-right:8px">Preview JSON</button>
        <a href="/metrics" target="_blank" rel="noopener" style="text-decoration:none;color:#094482">Open Metrics</a>
      </div>
      <!-- JSON Modal -->
      <div id="json-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9999;">
        <div style="background:#fff;max-width:800px;width:90%;margin:60px auto;border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,0.2);">
          <div style="padding:10px 12px;border-bottom:1px solid #eee;display:flex;align-items:center;justify-content:space-between">
            <div class="muted">/metrics/snapshot</div>
            <div>
              <button id="btn-json-copy" style="padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#f0fff4;cursor:pointer;margin-right:6px">Copy</button>
              <button id="btn-json-download" style="padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#fafafa;cursor:pointer;margin-right:6px">Download</button>
              <button id="btn-json-close" style="padding:6px 10px;border:1px solid #ccc;border-radius:6px;background:#fdecea;cursor:pointer">Close</button>
            </div>
          </div>
          <div style="padding:10px 12px">
            <pre id="json-content" style="max-height:60vh;overflow:auto;background:#0b1021;color:#e6edf3;padding:10px;border-radius:6px;font-size:12px"></pre>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
