import React, { useState, useEffect, useCallback } from 'react';
import { 
  Zap, 
  ArrowUp, 
  Cpu, 
  Play, 
  StopCircle, 
  Activity,
  Server,
  Database,
  HardDrive,
  Clock,
  AlertTriangle,
  Beaker,
  History,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  XCircle
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ReferenceDot, 
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar
} from 'recharts';

function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-gray-900 text-gray-100 flex flex-col justify-between z-50">
      <div className="px-6 py-6">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold text-lg">
              FI
            </div>
            <span className="absolute -bottom-1 -right-1 w-3 h-3 bg-green-400 rounded-full border-2 border-gray-900 animate-pulse" />
          </div>
          <div>
            <span className="text-lg font-bold block">Failure</span>
            <span className="text-xs text-gray-400">Injection</span>
          </div>
        </div>

        <nav className="mt-8 space-y-1">
          <a href="#" className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-indigo-600 text-white">
            <span className="flex items-center gap-2">
              <Activity size={18} />
              Dashboard
            </span>
          </a>
          <a href="#" className="flex items-center justify-between px-3 py-2.5 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white transition-colors">
            <span className="flex items-center gap-2">
              <Beaker size={18} />
              Experiments
            </span>
          </a>
          <a href="#" className="flex items-center justify-between px-3 py-2.5 rounded-lg text-gray-400 hover:bg-gray-800 hover:text-white transition-colors">
            <span className="flex items-center gap-2">
              <History size={18} />
              History
            </span>
          </a>
        </nav>
      </div>

      <div className="px-6 py-4 border-t border-gray-800">
        <div className="text-xs text-gray-500">v1.0.0</div>
      </div>
    </aside>
  );
}

function TopNav({ onRefresh }) {
  return (
    <header className="sticky top-0 left-64 right-0 h-16 bg-gray-900/80 backdrop-blur-md flex items-center justify-between px-6 z-40 border-b border-gray-800">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold text-white">Resilience Dashboard</h1>
      </div>
      <div className="flex items-center gap-3">
        <button 
          onClick={onRefresh}
          className="p-2 rounded-lg bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
        >
          <RefreshCw size={18} />
        </button>
        <div className="w-8 h-8 bg-indigo-600 rounded-full flex items-center justify-center text-white font-medium">
          A
        </div>
      </div>
    </header>
  );
}

function StatCard({ label, value, icon, trend }) {
  return (
    <div className="flex items-center gap-4 rounded-xl bg-gray-800/50 p-4 border border-gray-700/50">
      <div className="p-3 bg-gray-700/50 rounded-lg text-indigo-400">
        {icon}
      </div>
      <div>
        <p className="text-sm text-gray-400">{label}</p>
        <div className="flex items-center gap-2">
          <p className="text-2xl font-bold text-white">{value}</p>
          {trend && (
            <span className={`text-xs flex items-center ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
              {trend > 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {Math.abs(trend)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function Hero({ onRunExperiment, running }) {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-gray-800 via-gray-900 to-gray-800 p-8 text-white border border-gray-700/50">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,_rgba(255,255,255,0.05)_0.5px,_transparent_0)] opacity-40" />
      <div className="relative z-10">
        <h2 className="text-4xl font-extrabold mb-3">Real-Time Failure Injection & Analysis</h2>
        <p className="text-gray-400 mb-6 max-w-2xl text-lg">
          Inject, observe, and remediate faults across your micro-service architecture — all from one unified UI.
        </p>
        <button 
          onClick={onRunExperiment}
          disabled={running}
          className={`inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold transition-all ${
            running 
              ? 'bg-gray-600 cursor-not-allowed' 
              : 'bg-indigo-600 hover:bg-indigo-500 focus:ring-2 focus:ring-indigo-400'
          }`}
        >
          {running ? (
            <>
              <RefreshCw size={20} className="animate-spin" />
              Running Experiment...
            </>
          ) : (
            <>
              <Zap size={20} />
              Run New Experiment
            </>
          )}
        </button>
      </div>
    </section>
  );
}

function InsightStability({ metrics, latencyData }) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <section className="rounded-xl bg-gray-800/50 p-4 border border-gray-700/50">
        <h3 className="text-lg font-semibold text-white mb-4">Request Latency (P99)</h3>
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={latencyData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
            <XAxis dataKey="time" stroke="#9ca3af" fontSize={12} />
            <YAxis stroke="#9ca3af" fontSize={12} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }} 
              itemStyle={{ color: '#fff' }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Area 
              type="monotone" 
              dataKey="value" 
              stroke="#6366f1" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorValue)" 
            />
            {latencyData.find(d => d.value > 1000) && (
              <ReferenceDot 
                x={latencyData.find(d => d.value > 1000)?.time} 
                y={latencyData.find(d => d.value > 1000)?.value} 
                r={6} 
                fill="#ef4444" 
                stroke="#fff" 
                strokeWidth={2} 
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </section>

      <section className="rounded-xl bg-gray-800/50 p-6 border border-gray-700/50 text-white">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="text-6xl font-bold text-white">{metrics.stability || '99.42%'}</p>
            <div className="flex items-center gap-2 mt-2">
              <ArrowUp className="w-5 h-5 text-green-400" />
              <span className="text-green-400 font-medium">+0.12%</span>
              <span className="text-gray-400 text-sm ml-2">vs last 24h</span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-400">Overall System Stability</p>
          </div>
        </div>

        <div className="mt-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-300">Uptime</span>
            <span className="text-gray-300">{metrics.uptime || '99.5%'}</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div className="bg-green-500 h-2 rounded-full" style={{ width: metrics.uptime || '99.5%' }} />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mt-6 pt-6 border-t border-gray-700">
          <div className="text-center">
            <p className="text-2xl font-bold text-white">{metrics.mttr || '2.3s'}</p>
            <p className="text-sm text-gray-400">MTTR</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-white">{metrics.incidents || '3'}</p>
            <p className="text-sm text-gray-400">Incidents</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-white">{metrics.avgLatency || '820ms'}</p>
            <p className="text-sm text-gray-400">Avg Latency</p>
          </div>
        </div>
      </section>
    </div>
  );
}

function StatusPill({ status }) {
  const colors = {
    UP: 'bg-green-500/20 text-green-400 border-green-500/30',
    DOWN: 'bg-red-500/20 text-red-400 border-red-500/30',
    TESTING: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  };
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-medium border ${colors[status] || colors.TESTING}`}>
      {status}
    </span>
  );
}

function Microservices({ services, onInjectFault }) {
  const serviceIcons = {
    gateway: Server,
    auth: Database,
    data: HardDrive,
    cache: Activity,
    worker: Cpu,
  };

  return (
    <section className="grid grid-cols-1 md:grid-cols-5 gap-4">
      {services.map((svc, i) => {
        const IconComponent = serviceIcons[svc.name] || Server;
        return (
          <div key={i} className="rounded-xl bg-gray-800/50 p-4 border border-gray-700/50 text-white hover:border-gray-600 transition-colors">
            <div className="flex items-center justify-between mb-3">
              <div className="p-2 bg-gray-700/50 rounded-lg">
                <IconComponent size={20} className="text-indigo-400" />
              </div>
              <StatusPill status={svc.status} />
            </div>
            <h3 className="capitalize font-medium text-lg">{svc.name}</h3>
            <p className="text-sm text-gray-400 mt-1">Service</p>
            
            {/* Quick action buttons */}
            <div className="flex gap-2 mt-3">
              <button 
                onClick={() => onInjectFault('stop_service', svc.name)}
                className="flex-1 text-xs py-1.5 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30 transition-colors"
              >
                Stop
              </button>
              <button 
                onClick={() => onInjectFault('latency', svc.name, 500)}
                className="flex-1 text-xs py-1.5 bg-yellow-600/20 text-yellow-400 rounded hover:bg-yellow-600/30 transition-colors"
              >
                Latency
              </button>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function HistorySection({ experiments }) {
  return (
    <section className="relative pl-8">
      {experiments.length === 0 ? (
        <p className="text-gray-500 text-sm">No experiments yet</p>
      ) : (
        experiments.slice(0, 5).map((exp, i) => (
          <div key={i} className="relative pb-8 last:pb-0">
            <div className={`absolute -left-4 top-1 w-3 h-3 rounded-full ring-4 ring-gray-900 ${
              exp.action === 'rolled_back' ? 'bg-green-500' : 
              exp.action === 'injected' ? 'bg-red-500' : 'bg-yellow-500'
            }`} />
            {i < Math.min(experiments.length, 5) - 1 && (
              <div className="absolute left-[-1px] top-4 bottom-0 w-0.5 bg-gray-700" />
            )}
            <time className="text-xs text-gray-500">
              {exp.timestamp ? new Date(exp.timestamp).toLocaleString() : 'Just now'}
            </time>
            <pre className="mt-2 bg-gray-900/50 p-3 rounded-lg text-sm text-gray-300 font-mono overflow-x-auto border border-gray-700/50">
              {exp.fault_type}: {exp.target_service} {exp.value ? `@ ${exp.value}ms` : ''}
            </pre>
          </div>
        ))
      )}
    </section>
  );
}

function Automate({ onInjectCustom }) {
  const [selectedService, setSelectedService] = useState('gateway');
  const [faultType, setFaultType] = useState('latency');
  const [value, setValue] = useState(500);
  const [duration, setDuration] = useState(30);

  const handleInject = () => {
    onInjectCustom(faultType, selectedService, value, duration);
  };

  return (
    <section className="relative rounded-xl bg-gray-800/50 p-6 border border-gray-700/50 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_3px_3px,_rgba(255,255,255,0.04)_0.5px,_transparent_0)] opacity-30" />
      <div className="absolute inset-0 rounded-xl ring-1 ring-indigo-500/30 pointer-events-none" />
      
      <div className="relative z-10">
        <h3 className="text-lg font-semibold text-white mb-4">Custom Fault Injection</h3>
        
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-2">Target Service</label>
            <select 
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 border border-gray-600 focus:outline-none focus:border-indigo-500"
            >
              <option value="gateway">Gateway</option>
              <option value="auth">Auth</option>
              <option value="data">Data</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">Fault Type</label>
            <div className="grid grid-cols-3 gap-2">
              {['latency', 'cpu', 'stop_service', 'network_partition'].map(type => (
                <button
                  key={type}
                  onClick={() => setFaultType(type)}
                  className={`py-2 text-xs font-medium rounded-lg transition-colors ${
                    faultType === type 
                      ? 'bg-indigo-600 text-white' 
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {type.replace('_', ' ').toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {(faultType === 'latency' || faultType === 'cpu') && (
            <div>
              <label className="text-sm text-gray-400 block mb-2">
                {faultType === 'latency' ? 'Latency (ms)' : 'CPU Limit (%)'}
              </label>
              <input 
                type="number" 
                value={value}
                onChange={(e) => setValue(parseInt(e.target.value))}
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 border border-gray-600 focus:outline-none focus:border-indigo-500"
              />
            </div>
          )}

          <div>
            <label className="text-sm text-gray-400 block mb-2">Duration (seconds)</label>
            <input 
              type="number" 
              value={duration}
              onChange={(e) => setDuration(parseInt(e.target.value))}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 border border-gray-600 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <button 
            onClick={handleInject}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-indigo-600 py-3 text-sm font-medium hover:bg-indigo-500 transition-colors"
          >
            <Zap size={18} />
            Inject Fault
          </button>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [services, setServices] = useState([
    { name: 'gateway', status: 'UNKNOWN' },
    { name: 'auth', status: 'UNKNOWN' },
    { name: 'data', status: 'UNKNOWN' },
    { name: 'cache', status: 'UNKNOWN' },
    { name: 'worker', status: 'UNKNOWN' },
  ]);
  const [experiments, setExperiments] = useState([]);
  const [running, setRunning] = useState(false);
  const [metrics, setMetrics] = useState({
    stability: '99.42%',
    uptime: '99.5%',
    mttr: '2.3s',
    incidents: '3',
    avgLatency: '820ms'
  });
  const [latencyData, setLatencyData] = useState([
    { time: '14:00', value: 820 },
    { time: '15:00', value: 932 },
    { time: '16:00', value: 1240 },
    { time: '17:00', value: 1100 },
    { time: '18:00', value: 880 },
    { time: '19:00', value: 960 },
  ]);

  const fetchServicesStatus = useCallback(async () => {
    try {
      const resp = await fetch('/services/status');
      const data = await resp.json();
      if (data.services) {
        setServices(data.services);
      }
    } catch (e) {
      console.error('Failed to fetch services status', e);
    }
  }, []);

  const fetchExperiments = useCallback(async () => {
    try {
      const resp = await fetch('/experiments/history?limit=10');
      const data = await resp.json();
      if (data.experiments) {
        setExperiments(data.experiments);
      }
    } catch (e) {
      console.error('Failed to fetch experiments', e);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const resp = await fetch('/metrics/realtime');
      const data = await resp.json();
      
      // Calculate some metrics from real data
      if (data.gateway_requests) {
        setMetrics(prev => ({
          ...prev,
          // You can calculate real values here
        }));
      }
    } catch (e) {
      console.error('Failed to fetch metrics', e);
    }
  }, []);

  const runExperiment = async () => {
    try {
      setRunning(true);
      const resp = await fetch('/run_ai_experiment', { method: 'POST' });
      const data = await resp.json();
      alert(`Experiment started!\nReturn code: ${data.rc}`);
      
      // Refresh data after experiment
      setTimeout(() => {
        fetchExperiments();
        fetchServicesStatus();
      }, 3000);
    } catch (e) {
      alert('Failed to start experiment: ' + e);
    } finally {
      setRunning(false);
    }
  };

  const injectCustomFault = async (faultType, targetService, value = null, duration = 30) => {
    try {
      const payload = {
        fault_type: faultType,
        target_service: targetService,
        value: value,
        duration: duration
      };
      
    const resp = await fetch('/inject/custom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const text = await resp.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      console.error('Non-JSON response:', text);
      throw new Error(`Server error: ${text || resp.status} ${resp.statusText}`);
    }
    
    if (!resp.ok || data.error) {
      throw new Error(data.error || `Failed: ${resp.status} ${resp.statusText}`);
    }
    
    console.log('Fault injected:', data);
      
      // Refresh status
      setTimeout(() => {
        fetchServicesStatus();
        fetchExperiments();
      }, 2000);
      
    } catch (e) {
      console.error('Failed to inject fault:', e);
      alert('Failed to inject fault: ' + e);
    }
  };

  const handleInjectFault = (faultType, serviceName, value = null) => {
    injectCustomFault(faultType, serviceName, value, 30);
  };

  // Initial data fetch
  useEffect(() => {
    fetchServicesStatus();
    fetchExperiments();
    fetchMetrics();

    // Set up polling intervals
    const servicesInterval = setInterval(fetchServicesStatus, 5000);
    const metricsInterval = setInterval(fetchMetrics, 10000);

    return () => {
      clearInterval(servicesInterval);
      clearInterval(metricsInterval);
    };
  }, [fetchServicesStatus, fetchExperiments, fetchMetrics]);

  const handleRefresh = () => {
    fetchServicesStatus();
    fetchExperiments();
    fetchMetrics();
  };

  return (
    <div className="flex min-h-screen bg-gray-900 text-gray-100">
      <Sidebar />
      
      <div className="flex-1 ml-64 flex flex-col overflow-hidden">
        <TopNav onRefresh={handleRefresh} />
        
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          <Hero onRunExperiment={runExperiment} running={running} />
          
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <StatCard label="Active Experiments" value={experiments.length} icon={<Play className="w-5 h-5" />} />
            <StatCard label="Avg P99 Latency" value={metrics.avgLatency} icon={<Zap className="w-5 h-5" />} />
            <StatCard label="Services Up" value={`${services.filter(s => s.status === 'UP').length}/${services.length}`} icon={<Activity className="w-5 h-5" />} />
            <StatCard label="Total Incidents" value={metrics.incidents} icon={<AlertTriangle className="w-5 h-5" />} />
          </div>
          
          <InsightStability metrics={metrics} latencyData={latencyData} />
          
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Microservices</h3>
            <Microservices services={services} onInjectFault={handleInjectFault} />
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="rounded-xl bg-gray-800/50 p-4 border border-gray-700/50">
              <h3 className="text-lg font-semibold text-white mb-4">Simulation History</h3>
              <HistorySection experiments={experiments} />
            </div>
            <Automate onInjectCustom={injectCustomFault} />
          </div>
        </main>
      </div>
    </div>
  );
}