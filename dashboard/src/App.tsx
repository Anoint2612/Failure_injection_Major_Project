import { useState, useEffect, useRef } from 'react';

const CONTROLLER = 'http://localhost:8080/api/v1';

export default function App() {
  const [autopilot, setAutopilot] = useState(false);
  const [selectedNode, setSelectedNode] = useState<{agentId: string, name: string, type: string, cap: string[]} | null>(null);
  const [agents, setAgents] = useState<{ [key: string]: any }>({});
  const [aiReport, setAiReport] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<any[]>([]);
  const [autopilotCountdown, setAutopilotCountdown] = useState<number | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autopilotScenarioRef = useRef<any>(null);

  // Autopilot: fetch AI scenarios → auto-trigger first scenario after 5s countdown
  useEffect(() => {
    if (!autopilot) {
      setAiReport(null);
      setAutopilotCountdown(null);
      if (countdownRef.current) clearInterval(countdownRef.current);
      autopilotScenarioRef.current = null;
      return;
    }
    const fetchAI = async () => {
      try {
        setAiReport('LOADING');
        const res = await fetch(`${CONTROLLER}/ai/scenarios`);
        const data = await res.json();
        const suggestions = data.suggestions;
        setAiReport(typeof suggestions === 'string' ? suggestions : JSON.stringify(suggestions, null, 2));

        // Auto-fire the first AI-suggested scenario after a 5s countdown
        if (Array.isArray(suggestions) && suggestions.length > 0) {
          autopilotScenarioRef.current = suggestions[0];
          setAutopilotCountdown(5);
          countdownRef.current = setInterval(() => {
            setAutopilotCountdown((prev: number | null) => {
              if (prev === null || prev <= 1) {
                clearInterval(countdownRef.current!);
                // Fire the scenario
                if (autopilotScenarioRef.current) {
                  fetch(`${CONTROLLER}/ai/autopilot/run`, { method: 'POST' })
                    .then(r => r.json())
                    .then(d => showToast(`Autopilot fired: ${d.queued?.name || 'scenario'}`, 'success'))
                    .catch(() => showToast('Autopilot: failed to fire scenario', 'error'));
                }
                return null;
              }
              return prev - 1;
            });
          }, 1000);
        }
      } catch (e) {
        setAiReport("Network error connecting to Gemini Orchestrator.");
      }
    };
    fetchAI();
    return () => { if (countdownRef.current) clearInterval(countdownRef.current); };
  }, [autopilot]);

  const [apiStatus, setApiStatus] = useState<{message: string, type: 'success' | 'error' | 'info'} | null>(null);
  const [loadingActions, setLoadingActions] = useState<{[key: string]: boolean}>({});

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setApiStatus({message, type});
    setTimeout(() => setApiStatus(null), 4000);
  };

  const triggerFailure = async (cap: string) => {
    if (!selectedNode) return;
    setLoadingActions((prev: {[key: string]: boolean}) => ({...prev, [cap]: true}));
    try {
      showToast(`Initiating ${cap} payload...`);
      const payload = {
        name: `Interactive-${cap}`,
        // Include BOTH agent_id and container name so agent can resolve target
        target_selector: { agent_id: selectedNode.agentId, container: selectedNode.name },
        parameters: { action: cap, duration_seconds: "30" },
        auto_abort_threshold_ms: 1000
      };
      const res = await fetch(`${CONTROLLER}/experiments/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) showToast(`Deployed ${cap.replace(/_/g,' ')} → ${selectedNode.name}`, 'success');
      else showToast(`Controller rejected: ${await res.text()}`, 'error');
    } catch(err) {
      showToast(`Network error to Orchestrator: ${err}`, 'error');
    } finally {
      setLoadingActions((prev: {[key: string]: boolean}) => ({...prev, [cap]: false}));
    }
  };

  // Real-time agent topology polling
  useEffect(() => {
    const fetchTopology = async () => {
      try {
        const res = await fetch(`${CONTROLLER}/agents`);
        const data = await res.json();
        setAgents(data.agents || {});
      } catch (e) {
        console.error("Orchestrator unreachable. Is it running?", e);
      }
    };
    fetchTopology();
    const interval = setInterval(fetchTopology, 3000);
    return () => clearInterval(interval);
  }, []);

  // Experiment history polling
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${CONTROLLER}/experiments`);
        const data = await res.json();
        setExperiments(data.experiments || []);
      } catch (e) { /* controller may not be up yet */ }
    };
    fetchHistory();
    const interval = setInterval(fetchHistory, 3000);
    return () => clearInterval(interval);
  }, []);

  const statusColor = (s: string) => {
    if (s === 'completed') return 'text-green-400';
    if (s === 'failed') return 'text-red-400';
    if (s === 'running') return 'text-yellow-400 animate-pulse';
    return 'text-zinc-400';
  };

  return (
    <div className="min-h-screen p-8 max-w-7xl mx-auto space-y-8">
      {/* Toast */}
      {apiStatus && (
        <div className="fixed top-6 right-6 z-50 animate-in slide-in-from-right-8 fade-in duration-300">
          <div className={`shadow-xl px-6 py-4 rounded-xl flex items-center border ${apiStatus.type === 'success' ? 'bg-zinc-900 border-green-500/50' : apiStatus.type === 'error' ? 'bg-zinc-900 border-red-500/50' : 'bg-zinc-900 border-blue-500/50'}`}>
            {apiStatus.type === 'success' && <svg className="w-5 h-5 text-green-500 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>}
            {apiStatus.type === 'error' && <svg className="w-5 h-5 text-red-500 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            {apiStatus.type === 'info' && <svg className="w-5 h-5 text-blue-500 mr-3 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            <p className="text-zinc-200 text-sm font-medium">{apiStatus.message}</p>
          </div>
        </div>
      )}

      <header className="flex justify-between items-center pb-6 border-b border-border">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">ChaosCore</h1>
          <p className="text-zinc-400 text-sm mt-1">Dynamic Autonomous Resilience Platform</p>
        </div>
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-4 bg-zinc-900/50 px-5 py-2.5 rounded-full border border-zinc-800 shadow-inner">
            <span className="text-sm font-semibold tracking-wide text-zinc-300">Chaos Autopilot Engine</span>
            <button
              onClick={() => setAutopilot(!autopilot)}
              className={`w-12 h-6 rounded-full transition-colors relative cursor-pointer ${autopilot ? 'bg-primary shadow-[0_0_10px_rgba(59,130,246,0.6)]' : 'bg-zinc-700'}`}>
              <div className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-transform ${autopilot ? 'translate-x-7' : 'translate-x-1'}`}></div>
            </button>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Topology + AI overlay */}
        <div className="lg:col-span-2 space-y-6">
          <section className="glass-panel p-6 relative overflow-hidden min-h-[550px] bg-gradient-to-br from-surface to-zinc-900/40">
            <h2 className="text-lg font-semibold mb-6 flex items-center text-zinc-200">
              <svg className="w-5 h-5 mr-2 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>
              Live Discovered Architecture
            </h2>

            <div className="flex flex-wrap gap-8 justify-center mt-12 relative z-10">
              {Object.keys(agents).length === 0 ? (
                <p className="text-zinc-500 animate-pulse mt-20">Probing environment... waiting for agents to connect.</p>
              ) : (
                Object.entries(agents).map(([agentId, data]) => (
                  <div key={agentId} className="flex flex-col items-center">
                    <div className="p-4 rounded-xl border border-zinc-700 bg-zinc-900 mb-6 shadow-lg shadow-black/50">
                      <p className="font-bold text-center text-white">{data.hostname}</p>
                      <p className="text-xs text-zinc-500 font-mono text-center mt-1">HostOS: {data.profile?.os}</p>
                    </div>
                    <div className="flex space-x-6">
                      {data.profile?.containers?.slice(0,4).map((c: any) => (
                        <div key={c.id}
                          onClick={() => setSelectedNode({agentId, name: c.name, type: 'Container', cap: data.profile.capabilities})}
                          className={`cursor-pointer w-40 p-3 rounded-xl border-2 transition-all bg-zinc-900/80 hover:-translate-y-1 ${selectedNode?.name === c.name ? 'border-primary ring-2 ring-primary/30 shadow-[0_0_15px_rgba(59,130,246,0.3)]' : 'border-zinc-800'}`}>
                          <p className="font-bold text-sm text-center text-zinc-200 truncate">{c.name}</p>
                          <p className="text-[10px] uppercase tracking-widest text-success text-center mt-1">Online</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* AI Autopilot overlay */}
            {autopilot && (
              <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 bg-primary/10 border border-primary/30 backdrop-blur-md p-4 rounded-xl shadow-lg w-4/5 flex flex-col items-center z-20 max-h-72 overflow-y-auto">
                <div className="flex w-full items-center mb-2">
                  <div className="p-2 bg-primary/20 rounded-full mr-4">
                    <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-white tracking-wide uppercase">AI Profiling Network</p>
                    {aiReport && aiReport !== 'LOADING' ? (
                      <p className="text-sm text-green-400 mt-1">
                        Analysis Complete.
                        {autopilotCountdown !== null
                          ? <span className="text-yellow-400 ml-2 font-bold">Auto-firing in {autopilotCountdown}s...</span>
                          : <span className="text-zinc-400 ml-2">Scenario dispatched.</span>
                        }
                      </p>
                    ) : (
                      <p className="text-sm text-blue-400 mt-1 animate-pulse">Gemini sweeping discovered nodes against vulnerability vectors...</p>
                    )}
                  </div>
                </div>
                {aiReport && aiReport !== 'LOADING' && (
                  <pre className="mt-4 w-full text-[11px] whitespace-pre-wrap font-mono text-zinc-300 bg-black/60 p-4 rounded-xl border border-zinc-700 shadow-inner">{aiReport}</pre>
                )}
              </div>
            )}
          </section>

          {/* Experiment History Panel */}
          <section className="glass-panel p-6 bg-zinc-900/50">
            <h2 className="text-base font-semibold mb-4 text-zinc-300 flex items-center">
              <svg className="w-4 h-4 mr-2 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
              Experiment History
            </h2>
            {experiments.length === 0 ? (
              <p className="text-zinc-600 text-sm">No experiments run yet. Fire one above.</p>
            ) : (
              <div className="space-y-2">
                {experiments.slice(-8).reverse().map((exp: any) => (
                  <div key={exp.id} className="flex items-center justify-between px-4 py-2.5 rounded-lg bg-zinc-800/60 border border-zinc-700/50">
                    <div>
                      <p className="text-sm font-medium text-zinc-200 font-mono">{exp.name}</p>
                      <p className="text-xs text-zinc-500 mt-0.5">{exp.queued_at ? new Date(exp.queued_at).toLocaleTimeString() : ''}</p>
                    </div>
                    <span className={`text-xs font-bold uppercase tracking-widest px-2 py-1 rounded ${statusColor(exp.status)} bg-zinc-900`}>
                      {exp.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Right Sidebar: Node Inspector */}
        <div className="space-y-6">
          {selectedNode ? (
            <section className="glass-panel p-6 border-zinc-700 shadow-xl transition-all animate-in fade-in duration-300">
              <h2 className="text-lg font-bold mb-1 text-white">Live Node Inspector</h2>
              <p className="text-primary font-mono text-sm mb-6 pb-4 border-b border-zinc-800">{selectedNode.name}</p>

              <div className="space-y-3">
                <p className="text-xs text-zinc-500 font-bold uppercase tracking-widest">Execute Native Failure</p>
                {selectedNode.cap.map((cap: string) => {
                  const isFiring = loadingActions[cap];
                  return (
                    <button key={cap}
                      onClick={() => !isFiring && triggerFailure(cap)}
                      disabled={isFiring}
                      className={`w-full text-left px-4 py-3 rounded-lg ${isFiring ? 'bg-zinc-700 border-zinc-500 animate-pulse' : 'bg-zinc-800/80 hover:bg-zinc-700 border-zinc-700/50 hover:border-zinc-500'} border transition-all text-sm flex justify-between items-center group cursor-pointer`}>
                      <span className="font-medium text-zinc-200">{cap.replace(/_/g, ' ')}</span>
                      {isFiring ? (
                        <span className="text-yellow-500 text-xs font-bold tracking-widest px-2 py-1 bg-yellow-500/10 rounded flex items-center">
                          <svg className="animate-spin -ml-1 mr-2 h-3 w-3 text-yellow-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> INJECTING
                        </span>
                      ) : (
                        <span className="opacity-0 group-hover:opacity-100 text-red-500 text-xs font-bold tracking-widest transition-opacity px-2 py-1 bg-red-500/10 rounded">FIRE</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          ) : (
            <section className="glass-panel p-6 bg-zinc-900/50 border-dashed border-zinc-800 h-[300px] flex items-center justify-center text-center">
              <div><p className="text-sm text-zinc-500">Select any dynamically discovered subsystem container.</p></div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
