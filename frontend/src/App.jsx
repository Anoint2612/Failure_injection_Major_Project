import { useState, useEffect, useRef } from 'react';
import './index.css';

const API = 'http://localhost:5050';

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('chaos-theme') || 'dark');
  const [services, setServices] = useState([]);
  const [faults, setFaults] = useState([]);
  const [target, setTarget] = useState(null);
  const [runningType, setRunningType] = useState(null);
  const [results, setResults] = useState(null);
  const [probeUrl, setProbeUrl] = useState('');
  const [params, setParams] = useState({});
  const [logs, setLogs] = useState([{ id: 0, ts: now(), type: 'info', msg: 'System initialized. Awaiting service discovery.' }]);
  const [toasts, setToasts] = useState([]);
  const poll = useRef(null);

  function now() { return new Date().toLocaleTimeString('en-US', { hour12: false }); }
  const log = (type, msg) => setLogs(p => [{ id: Date.now(), ts: now(), type, msg }, ...p].slice(0, 100));
  const toast = (type, msg) => { const id = Date.now(); setToasts(p => [...p, { id, type, msg }]); setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000); };

  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('chaos-theme', theme); }, [theme]);

  useEffect(() => {
    fetch(`${API}/faults`).then(r => r.json()).then(d => {
      setFaults(d.faults || []);
      const defs = {};
      (d.faults || []).forEach(f => { defs[f.name] = {}; (f.parameters || []).forEach(p => { defs[f.name][p.name] = p.default; }); });
      setParams(defs);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const tick = async () => {
      try {
        const d = await (await fetch(`${API}/status`)).json();
        setServices(d.services || []);
        if (!target && d.services?.length > 0) {
          const s = d.services.find(s => !['prometheus', 'grafana'].includes(s.service));
          if (s) { setTarget(s.service); const p = Object.values(s.ports || {})[0]; if (p) setProbeUrl(`http://localhost:${p}/health`); }
        }
      } catch (_) {}
    };
    tick();
    poll.current = setInterval(tick, 3000);
    return () => clearInterval(poll.current);
  }, [target]);

  const api = async (ep, method = 'POST', body = null) => {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(`${API}/${ep}`, opts);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Request failed');
    return d;
  };

  const inject = async (name) => {
    const p = params[name] || {};
    const qs = Object.entries(p).filter(([,v]) => v !== '' && v !== undefined).map(([k,v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    log('info', `INJECT ${name.toUpperCase()} → ${target}`);
    try { const r = await api(`inject/${name}/${target}${qs ? '?' + qs : ''}`); toast('success', r.action); log('success', r.action); }
    catch (e) { toast('error', e.message); log('error', e.message); }
  };

  const recover = async (name) => {
    log('info', `RECOVER ${name.toUpperCase()} → ${target}`);
    try {
      const r = await api(`recover/${name}/${target}`);
      toast('success', r.action || 'Recovered');
      log('success', r.action || 'Recovered');
      // Reset parameters to defaults
      const fault = faults.find(f => f.name === name);
      if (fault) {
        const defaults = {};
        (fault.parameters || []).forEach(p => { defaults[p.name] = p.default; });
        setParams(prev => ({ ...prev, [name]: defaults }));
      }
    }
    catch (e) { toast('error', e.message); log('error', e.message); }
  };

  const experiment = async (type) => {
    if (!probeUrl) { toast('error', 'Probe URL required'); return; }
    setRunningType(type); setResults(null);
    log('info', `EXPERIMENT ${type.toUpperCase()} → ${target} | probe: ${probeUrl}`);
    try {
      const r = await api('experiment/run', 'POST', {
        target_service: target, probe_url: probeUrl, fault_type: type,
        ...(params[type === 'latency' ? 'latency' : 'cpu_stress'] || {}), num_requests: 5,
      });
      setResults(r); toast('success', 'Experiment complete'); log('success', `Experiment ${type} completed on ${target}`);
    } catch (e) { toast('error', e.message); log('error', e.message); }
    finally { setRunningType(null); }
  };

  const setParam = (fault, key, val) => setParams(p => ({ ...p, [fault]: { ...p[fault], [key]: val } }));

  const appSvcs = services.filter(s => !['prometheus', 'grafana'].includes(s.service));
  const byCategory = faults.reduce((a, f) => { a[f.category] = a[f.category] || []; a[f.category].push(f); return a; }, {});
  const catLabels = { infrastructure: 'INFRASTRUCTURE', network: 'NETWORK', resource: 'RESOURCE' };

  const renderControl = (fault, p) => {
    const v = params[fault]?.[p.name] ?? p.default;
    if (p.type === 'range') return (
      <div className="ctrl" key={p.name}>
        <div className="ctrl-label"><span>{p.description}</span><code>{v}</code></div>
        <input type="range" min={p.min} max={p.max} step={p.step} value={v} onChange={e => setParam(fault, p.name, e.target.value)} />
      </div>
    );
    if (p.type === 'select') return (
      <div className="ctrl" key={p.name}>
        <div className="ctrl-label"><span>{p.description}</span></div>
        <select value={v} onChange={e => setParam(fault, p.name, e.target.value)}>
          {p.options.map((o, i) => <option key={o} value={o}>{p.labels ? p.labels[i] : o}</option>)}
        </select>
      </div>
    );
    if (p.type === 'text') return (
      <div className="ctrl" key={p.name}>
        <div className="ctrl-label"><span>{p.description}</span></div>
        <input type="text" value={v} onChange={e => setParam(fault, p.name, e.target.value)} placeholder={p.description} />
      </div>
    );
    return null;
  };

  const avgLatency = (rows) => rows?.length ? (rows.reduce((s, r) => s + (typeof r.latency === 'number' ? r.latency : 0), 0) / rows.length).toFixed(3) : '—';

  return (
    <div className="shell">
      {/* ── TOPBAR ─────────────────────────── */}
      <header className="topbar">
        <div className="topbar-left">
          <div className="brand-mark">CC</div>
          <div className="brand-text">
            <span className="brand-name">ChaosController</span>
            <span className="brand-sub">Failure Injection Platform</span>
          </div>
        </div>
        <div className="topbar-right">
          <div className="stat-chip">{faults.length} fault types</div>
          <div className="stat-chip">{appSvcs.length} targets</div>
          <div className="stat-chip live"><span className="live-indicator" />LIVE</div>
          <div className="divider" />
          <button className="icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} title="Toggle theme">
            {theme === 'dark' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
            )}
          </button>
        </div>
      </header>

      {/* ── STATUS STRIP ───────────────────── */}
      <div className="status-strip">
        {services.map(s => (
          <div key={s.container_name} className={`status-cell ${s.status === 'up' ? 'up' : 'down'}`}>
            <span className="status-dot" />
            <span className="status-name">{s.service}</span>
            <span className="status-val">{s.status === 'up' ? `${s.latency_ms}ms` : 'DOWN'}</span>
          </div>
        ))}
      </div>

      {/* ── MAIN ───────────────────────────── */}
      <div className="main">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-heading">TARGETS</div>
            {appSvcs.map(s => (
              <button key={s.container_name}
                className={`target-btn ${target === s.service ? 'selected' : ''}`}
                onClick={() => { setTarget(s.service); const p = Object.values(s.ports||{})[0]; if(p) setProbeUrl(`http://localhost:${p}/health`); }}>
                <span className={`target-dot ${s.status === 'up' ? 'up' : 'down'}`} />
                <span className="target-name">{s.service}</span>
                <span className="target-port">{Object.values(s.ports||{}).filter(Boolean)[0] || '—'}</span>
              </button>
            ))}
          </div>
        </aside>

        {/* Content */}
        <div className="content">
          {/* Fault Catalog */}
          <section className="panel">
            <div className="panel-header">
              <h2>Fault Catalog</h2>
              <span className="panel-tag">TARGET: {target || 'none'}</span>
            </div>
            {Object.entries(byCategory).map(([cat, list]) => (
              <div key={cat} className="cat-group">
                <div className="cat-label">{catLabels[cat] || cat.toUpperCase()}</div>
                <div className="fault-grid">
                  {list.map(f => (
                    <div key={f.name} className="fault-card">
                      <div className="fc-top">
                        <h4 className="fc-name">{f.name.replace(/_/g, ' ')}</h4>
                        <span className={`fc-cat-dot cat-${cat}`} />
                      </div>
                      <p className="fc-desc">{f.description}</p>
                      {f.parameters.length > 0 && <div className="fc-controls">{f.parameters.map(p => renderControl(f.name, p))}</div>}
                      <div className="fc-actions">
                        <button className="btn-inject" onClick={() => inject(f.name)} disabled={!target}>Inject</button>
                        <button className="btn-recover" onClick={() => recover(f.name)} disabled={!target}>Recover</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>

          {/* Experiment Runner */}
          <section className="panel">
            <div className="panel-header">
              <h2>Experiment Runner</h2>
              <span className="panel-tag">TARGET: {target || 'none'}</span>
            </div>
            <div className="exp-section">
              <div className="exp-config">
                <div className="exp-field">
                  <label className="field-label">Probe URL</label>
                  <input className="field-input" type="text" value={probeUrl} onChange={e => setProbeUrl(e.target.value)} placeholder="http://localhost:8000/dashboard" />
                </div>
                <p className="field-hint">Inject on a downstream service. Probe via an upstream endpoint that calls it to observe latency impact through the Docker network.</p>
                <div className="exp-btns">
                  <button className="btn-exp btn-lat" onClick={() => experiment('latency')} disabled={runningType || !target}>
                    {runningType === 'latency' ? 'Running...' : 'Latency Test'}
                  </button>
                  <button className="btn-exp btn-str" onClick={() => experiment('stress')} disabled={runningType || !target}>
                    {runningType === 'stress' ? 'Running...' : 'Stress Test'}
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* Results */}
          {results && (
            <section className="panel">
              <div className="panel-header">
                <h2>Experiment Results</h2>
                {results.config && <span className="panel-tag">{results.config.target_service} &middot; {results.config.delay_ms ? `${results.config.delay_ms}ms delay` : `${results.config.cpu} CPU`}</span>}
              </div>
              <div className="phase-grid">
                {[
                  { key: 'baseline', label: 'BASELINE', cls: 'ph-base' },
                  { key: 'during_fault', label: 'DURING FAULT', cls: 'ph-fault' },
                  { key: 'post_recovery', label: 'POST RECOVERY', cls: 'ph-recov' },
                ].map(({ key, label, cls }) => {
                  const rows = results[key];
                  if (!Array.isArray(rows)) return null;
                  return (
                    <div key={key} className={`phase-card ${cls}`}>
                      <div className="ph-header">
                        <span className="ph-label">{label}</span>
                        <span className="ph-avg">{avgLatency(rows)}s avg</span>
                      </div>
                      <table className="data-table">
                        <thead><tr><th>REQ</th><th>LATENCY</th><th>STATUS</th></tr></thead>
                        <tbody>
                          {rows.map(r => (
                            <tr key={r.request} className={r.status === 'timeout' ? 'row-err' : ''}>
                              <td>{r.request}</td><td className="mono">{r.latency}s</td><td>{r.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Log */}
          <section className="panel">
            <div className="panel-header"><h2>Event Log</h2><span className="panel-tag">{logs.length} events</span></div>
            <div className="log-scroll">
              {logs.map(l => (
                <div key={l.id} className={`log-row log-${l.type}`}>
                  <span className="log-ts">{l.ts}</span>
                  <span className="log-type">{l.type.toUpperCase()}</span>
                  <span className="log-msg">{l.msg}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* Toasts */}
      <div className="toast-stack">
        {toasts.map(t => <div key={t.id} className={`toast t-${t.type}`}>{t.msg}</div>)}
      </div>
    </div>
  );
}

export default App;
