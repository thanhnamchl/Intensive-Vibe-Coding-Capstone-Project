import React, { useState, useEffect, useRef, Component } from 'react';

// ── React Error Boundary ───────────────────────────────────────────────────────
// Catches any render-time error in the tree below and shows a recovery UI
// instead of letting the whole app go blank / black.
interface ErrorBoundaryState { hasError: boolean; message: string; }
class ErrorBoundary extends Component<React.PropsWithChildren, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren) {
    super(props);
    this.state = { hasError: false, message: '' };
  }
  static getDerivedStateFromError(err: unknown): ErrorBoundaryState {
    const msg = err instanceof Error ? err.message : String(err);
    return { hasError: true, message: msg };
  }
  componentDidCatch(err: unknown, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] Caught render error:', err, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          background: '#0b1510', color: '#f0fdf4', padding: '2rem', textAlign: 'center'
        }}>
          <h2 style={{ color: '#ef4444', marginBottom: '1rem' }}>⚠️ Something went wrong</h2>
          <p style={{ color: '#9ca3af', marginBottom: '1.5rem', maxWidth: 480 }}>
            {this.state.message || 'An unexpected rendering error occurred.'}
          </p>
          <button
            style={{
              padding: '0.6rem 1.4rem', borderRadius: '0.5rem',
              background: '#22c55e', color: '#000', border: 'none',
              cursor: 'pointer', fontWeight: 600
            }}
            onClick={() => this.setState({ hasError: false, message: '' })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
export { ErrorBoundary };
import {
  Leaf,
  TrendingUp,
  Send,
  Cpu,
  Upload,
  Sliders,
  RefreshCw,
  Sparkles
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend
} from 'recharts';

// Read API base URL from Vite environment variable (set in frontend/.env)
// Falls back to localhost:8000 for convenience during local development.
const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  'http://localhost:8000/api';

// Maximum upload size enforced on the client before the file is sent.
const MAX_UPLOAD_BYTES: number =
  Number(import.meta.env.VITE_MAX_UPLOAD_BYTES) || 10 * 1024 * 1024; // 10 MB default

interface ScenarioInfo {
  scenario_groups: string[];
  season_types: string[];
  climate_types: string[];
  resource_scenarios: string[];
  awd_options: string[];
}

interface SummaryMetrics {
  status?: string;
  message?: string;
  total_records: number;
  avg_yield: number;
  avg_methane_emissions: number;
  avg_profit_margin: number;
  avg_net_income: number;
  avg_water_usage: number;
  avg_fertilizer_usage: number;
  avg_pesticide_usage: number;
  avg_salinity_exposure: number;
  awd_comparison?: Record<string, {
    'Avg Yield': number;
    'Methane Emissions': number;
    'Profit Margin': number;
  }>;
  climate_breakdown?: Record<string, Record<string, number>>;
  season_breakdown?: Record<string, Record<string, number>>;
  scenario_breakdown?: Record<string, Record<string, number>>;
}

interface ChatMessage {
  sender: 'user' | 'agent';
  agentName?: string;
  role?: string;
  text: string;
  data?: Record<string, unknown> | null;
}

interface SimulationResult {
  inputs: {
    'AWD Adoption': string;
    'Fertilizer Usage': number;
    'Pesticide Usage': number;
    'Water Usage': number;
    'Salinity Exposure': number;
  };
  predictions: {
    'Avg Yield': number;
    'Methane Emissions': number;
    'Profit Margin': number;
    'Net Income': number;
  };
}

interface OptimizationResult {
  optimization_target: string;
  best_score: number;
  optimized_inputs: {
    'AWD Adoption': string;
    'Fertilizer Usage': number;
    'Pesticide Usage': number;
    'Water Usage': number;
    'Salinity Exposure': number;
  };
  expected_outcomes: {
    'Avg Yield': number;
    'Methane Emissions': number;
    'Profit Margin': number;
    'Net Income': number;
  };
}

interface CleaningResult {
  // Present on both success and error responses
  status: string;
  message?: string;
  // Present only on successful cleans
  records_processed?: number;
  original_columns?: string[];
  renamed_columns?: Record<string, string>;
  converted_types?: string[];
  missing_values?: Record<string, number>;
  preview?: Record<string, unknown>[];
}

export default function App() {
  // Scenario Configurations & Filter state
  const [scenariosInfo, setScenariosInfo] = useState<ScenarioInfo | null>(null);
  const [filters, setFilters] = useState({
    'Scenario Group': '',
    'Season Type': '',
    'Climate Type': '',
    'Resource Scenario': '',
    'AWD Adoption': '',
  });

  // Data summaries
  const [metrics, setMetrics] = useState<SummaryMetrics | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  // Simulation Sliders state
  const [simInputs, setSimInputs] = useState({
    awd_adoption: 'With AWD',
    fertilizer_usage: 100,
    pesticide_usage: 5,
    water_usage: 600,
    salinity_exposure: 0.01,
  });
  const [simResults, setSimResults] = useState<SimulationResult | null>(null);
  const [loadingSim, setLoadingSim] = useState(false);

  // Optimization Target state
  const [optTargetMethane, setOptTargetMethane] = useState<number | ''>(200);
  const [optResults, setOptResults] = useState<OptimizationResult | null>(null);
  const [loadingOpt, setLoadingOpt] = useState(false);
  const [optError, setOptError] = useState<string | null>(null);
  // Chat/Query Box state
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([
    {
      sender: 'agent',
      agentName: 'STAR-FARM System Orchestrator',
      role: 'Agri-AI Supervisor',
      text: 'Welcome! I coordinate our specialized Data Cleaning, Aggregation, and Predictive Modeling agents. You can query statistics, simulate scenarios, or request policy optimization here.'
    }
  ]);
  const [loadingChat, setLoadingChat] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // File Upload state
  const [loadingUpload, setLoadingUpload] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [cleaningResult, setCleaningResult] = useState<CleaningResult | null>(null);


  const fetchScenarios = async () => {
    try {
      const res = await fetch(`${API_BASE}/scenarios`);
      const data = await res.json();
      setScenariosInfo(data);
    } catch (e) {
      console.error("Error loading scenarios", e);
    }
  };

  const fetchMetrics = async (currentFilters = filters) => {
    setLoadingMetrics(true);
    try {
      const activeFilters = Object.fromEntries(
        Object.entries(currentFilters).filter(([, v]) => v !== '')
      );
      const res = await fetch(`${API_BASE}/metrics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filters: activeFilters })
      });
      const data = await res.json();
      setMetrics(data);
    } catch (e) {
      console.error("Error loading metrics", e);
    } finally {
      setLoadingMetrics(false);
    }
  };

  const handleFilterChange = (col: string, val: string) => {
    const updated = { ...filters, [col]: val };
    setFilters(updated);
    fetchMetrics(updated);
  };

  const runSimulation = async (inputs = simInputs) => {
    setLoadingSim(true);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputs)
      });
      const data = await res.json();
      setSimResults(data);
    } catch (e) {
      console.error("Error running simulation", e);
    } finally {
      setLoadingSim(false);
    }
  };

  // const runOptimization = async () => {
  //   setLoadingOpt(true);
  //   try {
  //     const res = await fetch(`${API_BASE}/optimize`, {
  //       method: 'POST',
  //       headers: { 'Content-Type': 'application/json' },
  //       body: JSON.stringify({
  //         target_methane: optTargetMethane === '' ? 200.0 : optTargetMethane,
  //         pesticide_usage: simInputs.pesticide_usage,
  //         salinity_exposure: simInputs.salinity_exposure
  //       })
  //     });
  //     const data = await res.json();
  //     setOptResults(data);
  //   } catch (e) {
  //     console.error("Error running optimization", e);
  //   } finally {
  //     setLoadingOpt(false);
  //   }
  // };
  const runOptimization = async () => {
    setLoadingOpt(true);
    setOptError(null);
    setOptResults(null);

    try {
      const res = await fetch(`${API_BASE}/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_methane: optTargetMethane === '' ? null : optTargetMethane,
          pesticide_usage: simInputs.pesticide_usage,
          salinity_exposure: simInputs.salinity_exposure,
        }),
      });

      const data = await res.json();

      // API trả 400 / 422 / 500 thì không set kết quả
      if (!res.ok) {
        setOptError(
          data.message ||
          data.detail?.message ||
          (typeof data.detail === 'string' ? data.detail : null) ||
          'Cannot be optimized.'
        );
        return;
      }

      // Phòng trường hợp backend trả HTTP 200 nhưng không có kết quả tối ưu
      if (!data?.optimized_inputs || !data?.expected_outcomes) {
        setOptError(data?.message || 'Cannot be optimized.');
        return;
      }

      setOptResults(data);
    } catch (e) {
      console.error('Error running optimization', e);
      setOptError('Cannot be optimized. Please Try Again.');
    } finally {
      setLoadingOpt(false);
    }
  };

  const applyOptimizedInputs = () => {
    if (!optResults) return;
    const targetInputs = {
      awd_adoption: optResults.optimized_inputs['AWD Adoption'],
      fertilizer_usage: optResults.optimized_inputs['Fertilizer Usage'],
      pesticide_usage: optResults.optimized_inputs['Pesticide Usage'],
      water_usage: optResults.optimized_inputs['Water Usage'],
      salinity_exposure: optResults.optimized_inputs['Salinity Exposure'],
    };
    setSimInputs(targetInputs);
    runSimulation(targetInputs);
  };

  const sendChatMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg = chatInput;
    setChatInput('');
    setChatHistory(prev => [...prev, { sender: 'user', text: userMsg }]);
    setLoadingChat(true);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg })
      });
      const data = await res.json();

      setChatHistory(prev => [...prev, {
        sender: 'agent',
        agentName: data.agent,
        role: data.role,
        text: data.text || (typeof data.result === 'string' ? data.result : 'Processed successfully. Here is what I found:'),
        data: data.text ? null : (typeof data.result === 'object' ? data.result : null)
      }]);
    } catch (e) {
      console.error("Error processing agent query", e);
      setChatHistory(prev => [...prev, {
        sender: 'agent',
        agentName: 'System Error',
        text: 'Sorry, I encountered an error communicating with the agent backplane.'
      }]);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset previous results
    setCleaningResult(null);
    setUploadError(null);

    // ── Client-side security guards ──────────────────────────────────────────
    // 1. File type validation: accept CSV only
    const allowedTypes = ['text/csv', 'application/csv', 'text/plain'];
    const hasValidMime = allowedTypes.includes(file.type);
    const hasValidExt = file.name.toLowerCase().endsWith('.csv');
    if (!hasValidMime && !hasValidExt) {
      setUploadError('Invalid file type. Please upload a .csv file.');
      // Reset the input so the same file can be re-selected after fixing
      e.target.value = '';
      return;
    }

    // 2. File size validation: reject files above the configured limit
    if (file.size > MAX_UPLOAD_BYTES) {
      const limitMB = (MAX_UPLOAD_BYTES / (1024 * 1024)).toFixed(0);
      setUploadError(`File too large. Maximum allowed size is ${limitMB} MB.`);
      e.target.value = '';
      return;
    }

    // ─────────────────────────────────────────────────────────────────────────
    setLoadingUpload(true);
    const reader = new FileReader();
    reader.onload = async (event) => {
      const text = event.target?.result as string;
      try {
        const res = await fetch(`${API_BASE}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_content: text })
        });
        if (!res.ok) {
          let detail = 'Upload failed';
          try {
            const errData = await res.json();
            detail = errData.detail || detail;
          } catch { /* non-JSON error body */ }
          throw new Error(detail);
        }
        const data = await res.json();
        setCleaningResult(data);
      } catch (err) {
        console.error('Upload error', err);
        setUploadError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingUpload(false);
      }
    };
    reader.onerror = () => {
      setUploadError('Failed to read the file. Please try again.');
      setLoadingUpload(false);
    };
    reader.readAsText(file);
  };

  // Auto-scroll chat to bottom on new message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, loadingChat]);

  // Ingestion metrics
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchScenarios();
    fetchMetrics();
    runSimulation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  // Format Recharts Data
  const awdChartData = metrics?.awd_comparison
    ? Object.entries(metrics.awd_comparison).map(([name, vals]) => ({
      name,
      'Avg Yield (t/ha)': parseFloat(vals['Avg Yield'].toFixed(2)),
      'Methane Emissions': parseFloat(vals['Methane Emissions'].toFixed(2)),
      'Profit Margin (%)': parseFloat(vals['Profit Margin'].toFixed(2)),
    }))
    : [];

  return (
    <div className="dashboard-container">
      <header>
        <div className="header-title">
          <h1>AI-Agents Agricultural Decision Support System</h1>
          <p>AI Agent-Driven Decision Support & Predictive Modeling Dashboard</p>
        </div>
        <div className="agent-status-badge">
          <div className="status-pulse"></div>
          <span>Agri-Agent Core Active</span>
        </div>
      </header>

      {/* Top Filter Bar */}
      <section className="glass-panel">
        <h2><Sliders size={20} /> Scenario Filtration</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem', marginTop: '0.5rem' }}>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Scenario Group</label>
            <select
              className="select-input"
              value={filters['Scenario Group']}
              onChange={(e) => handleFilterChange('Scenario Group', e.target.value)}
            >
              <option value="">All Scenario Groups</option>
              {scenariosInfo?.scenario_groups.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Season Type</label>
            <select
              className="select-input"
              value={filters['Season Type']}
              onChange={(e) => handleFilterChange('Season Type', e.target.value)}
            >
              <option value="">All Seasons</option>
              {scenariosInfo?.season_types.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Climate Type</label>
            <select
              className="select-input"
              value={filters['Climate Type']}
              onChange={(e) => handleFilterChange('Climate Type', e.target.value)}
            >
              <option value="">All Climates</option>
              {scenariosInfo?.climate_types.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Resource Scenario</label>
            <select
              className="select-input"
              value={filters['Resource Scenario']}
              onChange={(e) => handleFilterChange('Resource Scenario', e.target.value)}
            >
              <option value="">All Resources</option>
              {scenariosInfo?.resource_scenarios.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>AWD Adoption</label>
            <select
              className="select-input"
              value={filters['AWD Adoption']}
              onChange={(e) => handleFilterChange('AWD Adoption', e.target.value)}
            >
              <option value="">All AWD Practices</option>
              {scenariosInfo?.awd_options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        </div>
      </section>

      {/* Warning banner when no data matches filters */}
      {metrics?.status === 'empty' && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: '1rem', borderRadius: '0.5rem', margin: '1rem 0', color: '#fca5a5', fontSize: '0.9rem' }}>
          ⚠️ <strong>No records found:</strong> {metrics.message || "No historical data matches the selected filters."}
        </div>
      )}

      {/* Main Stats Row */}
      <section className="glass-panel">
        <div className="metrics-row">
          <div className="metric-card">
            <span className="label">Average Yield</span>
            <span className="value">
              {loadingMetrics ? 'Loading...' : (metrics && metrics.avg_yield !== undefined) ? `${metrics.avg_yield.toFixed(2)} t/ha` : 'N/A'}
            </span>
            <span className="subtext">
              <Leaf size={12} /> Standard Target
            </span>
          </div>
          <div className="metric-card">
            <span className="label">Methane Emissions</span>
            <span className="value" style={{ color: '#ef4444' }}>
              {loadingMetrics ? 'Loading...' : (metrics && metrics.avg_methane_emissions !== undefined) ? `${metrics.avg_methane_emissions.toFixed(1)} kg/ha` : 'N/A'}
            </span>
            <span className="subtext" style={{ color: '#ef4444' }}>
              Carbon Equivalent
            </span>
          </div>
          <div className="metric-card">
            <span className="label">Profit Margin</span>
            <span className="value" style={{ color: '#10b981' }}>
              {loadingMetrics ? 'Loading...' : (metrics && metrics.avg_profit_margin !== undefined) ? `${metrics.avg_profit_margin.toFixed(1)}%` : 'N/A'}
            </span>
            <span className="subtext" style={{ color: '#10b981' }}>
              Financial Yield
            </span>
          </div>
          <div className="metric-card">
            <span className="label">Net Income</span>
            <span className="value">
              {loadingMetrics ? 'Loading...' : (metrics && metrics.avg_net_income !== undefined) ? `$${metrics.avg_net_income.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : 'N/A'}
            </span>
            <span className="subtext">
              Per Hectare
            </span>
          </div>
        </div>
      </section>

      {/* Dashboard Visual Analytics */}
      <div className="dashboard-grid">
        <div className="glass-panel col-8">
          <h2><TrendingUp size={20} /> AWD Practice Impacts Comparison</h2>
          <div style={{ height: 280, marginTop: '1rem' }}>
            {awdChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={awdChartData}>
                  <XAxis dataKey="name" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip contentStyle={{ background: '#0b1510', border: '1px solid var(--panel-border)', borderRadius: '8px' }} />
                  <Legend />
                  <Bar dataKey="Avg Yield (t/ha)" fill="#22c55e" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Methane Emissions" fill="#ef4444" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Profit Margin (%)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>No Data Available</div>
            )}
          </div>
        </div>

        {/* Dynamic AI Agent Optimization Workspace */}
        <div className="glass-panel col-4 flex-col">
          <div>
            <h2><Sparkles size={20} /> Methane Policy Optimizer</h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Instruct the ModelingAgent to run statistical optimizations to satisfy carbon ceiling targets.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Methane Ceiling (kg/ha)</label>
                <input
                  type="number"
                  className="select-input"
                  value={optTargetMethane}
                  onChange={(e) => {
                    const val = e.target.value;
                    setOptTargetMethane(val === '' ? '' : Number(val));
                    setOptError(null);
                  }}
                />
                {optError && (
                  <p
                    role="alert"
                    style={{
                      marginTop: '0.4rem',
                      marginBottom: 0,
                      color: '#f87171',
                      fontSize: '0.78rem',
                      lineHeight: 1.35,
                    }}
                  >
                    {optError}
                  </p>
                )}
              </div>
              <button
                type="button"
                className="btn"
                style={{ alignSelf: 'flex-end' }}
                onClick={runOptimization}
                disabled={loadingOpt}
              >
                {loadingOpt ? <RefreshCw className="animate-spin" size={16} /> : 'Optimize'}
              </button>
            </div>

            {optResults && (
              <div style={{ fontSize: '0.85rem', background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.05)' }}>
                <h4 style={{ color: '#4ade80', marginBottom: '0.5rem' }}>Optimized Allocation:</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <div>AWD practice: <strong>{optResults.optimized_inputs['AWD Adoption']}</strong></div>
                  <div>Water input: <strong>{optResults.optimized_inputs['Water Usage']} m³</strong></div>
                  <div>Fertilizer: <strong>{optResults.optimized_inputs['Fertilizer Usage']} kg</strong></div>
                  <div>Pesticides: <strong>{optResults.optimized_inputs['Pesticide Usage']} kg</strong></div>
                </div>
                <h4 style={{ color: '#4ade80', marginBottom: '0.5rem' }}>Expected Outcomes:</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '1rem' }}>
                  <div>Yield: <strong>{optResults.expected_outcomes['Avg Yield']?.toFixed(2)} t/ha</strong></div>
                  <div style={{ color: '#ef4444' }}>Methane: <strong>{optResults.expected_outcomes['Methane Emissions']?.toFixed(1)} kg</strong></div>
                  <div>Profit Margin: <strong>{optResults.expected_outcomes['Profit Margin']?.toFixed(1)}%</strong></div>
                  <div>Net Income: <strong>${optResults.expected_outcomes['Net Income']?.toFixed(0)}</strong></div>
                </div>
                <button
                  className="btn"
                  style={{ width: '100%', fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                  onClick={applyOptimizedInputs}
                >
                  Apply to Simulation Sliders &rarr;
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Dynamic Simulator Sliders */}
        <div className="glass-panel col-4">
          <h2><Sliders size={20} /> Input Simulation Controls</h2>
          <div className="slider-group" style={{ marginTop: '1rem' }}>
            <div className="slider-item">
              <label style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>AWD Adoption Practice</label>
              <select
                className="select-input"
                value={simInputs.awd_adoption}
                onChange={(e) => {
                  setSimInputs(prev => ({ ...prev, awd_adoption: e.target.value }));
                }}
              >
                <option value="With AWD">With AWD</option>
                <option value="Without AWD">Without AWD</option>
              </select>
            </div>

            <div className="slider-item">
              <div className="slider-label-row">
                <span className="name">Fertilizer Usage</span>
                <span className="value">{simInputs.fertilizer_usage} kg/ha</span>
              </div>
              <input
                type="range" min="50" max="250"
                value={simInputs.fertilizer_usage}
                onChange={(e) => setSimInputs(prev => ({ ...prev, fertilizer_usage: Number(e.target.value) }))}
              />
            </div>

            <div className="slider-item">
              <div className="slider-label-row">
                <span className="name">Pesticide Usage</span>
                <span className="value">{simInputs.pesticide_usage} kg/ha</span>
              </div>
              <input
                type="range" min="1" max="15"
                value={simInputs.pesticide_usage}
                onChange={(e) => setSimInputs(prev => ({ ...prev, pesticide_usage: Number(e.target.value) }))}
              />
            </div>

            <div className="slider-item">
              <div className="slider-label-row">
                <span className="name">Water Usage</span>
                <span className="value">{simInputs.water_usage} m³/ha</span>
              </div>
              <input
                type="range" min="200" max="1200"
                value={simInputs.water_usage}
                onChange={(e) => setSimInputs(prev => ({ ...prev, water_usage: Number(e.target.value) }))}
              />
            </div>

            <div className="slider-item">
              <div className="slider-label-row">
                <span className="name">Salinity Exposure</span>
                <span className="value">{(simInputs.salinity_exposure * 100).toFixed(2)}%</span>
              </div>
              <input
                type="range" min="0" max="0.05" step="0.001"
                value={simInputs.salinity_exposure}
                onChange={(e) => setSimInputs(prev => ({ ...prev, salinity_exposure: Number(e.target.value) }))}
              />
            </div>

            <button className="btn" style={{ width: '100%', marginTop: '0.5rem' }} onClick={() => runSimulation()} disabled={loadingSim}>
              {loadingSim ? <RefreshCw className="animate-spin" size={16} /> : 'Simulate Scenario Outcomes'}
            </button>

            {simResults && (
              <div style={{ marginTop: '0.5rem', padding: '1rem', background: 'rgba(0,0,0,0.2)', borderRadius: '0.5rem' }}>
                <h4 style={{ color: '#4ade80', marginBottom: '0.5rem', fontSize: '0.9rem' }}>Simulation Estimates:</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.85rem' }}>
                  <div>Yield: <strong>{simResults.predictions['Avg Yield']?.toFixed(2)} t/ha</strong></div>
                  <div style={{ color: '#ef4444' }}>Methane: <strong>{simResults.predictions['Methane Emissions']?.toFixed(1)} kg</strong></div>
                  <div>Profit Margin: <strong>{simResults.predictions['Profit Margin']?.toFixed(1)}%</strong></div>
                  <div>Net Income: <strong>${simResults.predictions['Net Income']?.toFixed(0)}</strong></div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Multi-Agent Orchestration Chat Workspace */}
        <div className="glass-panel col-8 flex-col">
          <h2><Cpu size={20} /> Multi-Agent Chat Workspace</h2>
          <div className="chat-messages" style={{ height: 360 }}>
            {chatHistory.map((msg, i) => (
              <div key={i} className={`message ${msg.sender}`}>
                {msg.sender === 'agent' && (
                  <div className="agent-header">
                    <Cpu size={12} />
                    <span>{msg.agentName}</span>
                    <span className="badge-info">{msg.role}</span>
                  </div>
                )}
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{msg.text}</div>
                {msg.data && (
                  <pre style={{ fontSize: '0.75rem', marginTop: '0.5rem', background: '#000', padding: '0.5rem', borderRadius: '4px', overflowX: 'auto' }}>
                    {JSON.stringify(msg.data, null, 2)}
                  </pre>
                )}
              </div>
            ))}
            {loadingChat && (
              <div className="message agent">
                <div className="agent-header">
                  <RefreshCw className="animate-spin" size={12} />
                  <span>Agent Core thinking...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input-row" onSubmit={sendChatMessage}>
            <input
              type="text"
              placeholder="Ask an agent: e.g. 'Compare yields by Climate Type' or 'Optimize water inputs'"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={loadingChat}
            />
            <button className="btn" type="submit" disabled={loadingChat}>
              <Send size={16} /> Send
            </button>
          </form>
        </div>
      </div>

      {/* CSV Ingestion, Standardization, & Quality Audit Panel */}
      <section className="glass-panel">
        <h2><Upload size={20} /> Data Cleaning, Standardization & Ingestion (DataCleaningAgent)</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem', marginTop: '1rem' }}>
          <div>
            <div className="upload-area" onClick={() => document.getElementById('csv-file-input')?.click()}>
              <Upload size={32} style={{ color: 'var(--primary)', marginBottom: '0.5rem' }} />
              <h3>Choose agricultural simulation CSV</h3>
              <p>Standardize columns, conversions, and missing values report.</p>
              <input
                id="csv-file-input"
                type="file"
                accept=".csv"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
              />
            </div>
            {loadingUpload && <p style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>Processing CSV file...</p>}
            {uploadError && <p style={{ marginTop: '0.5rem', color: '#ef4444', fontSize: '0.85rem' }}>{uploadError}</p>}
          </div>

          <div>
            {cleaningResult ? (
              cleaningResult.status === 'error' ? (
                // Backend returned a processing error — show it clearly
                <div style={{
                  padding: '1rem', borderRadius: '0.5rem',
                  background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444'
                }}>
                  <h4 style={{ color: '#ef4444', marginBottom: '0.5rem' }}>⚠️ CSV Processing Error</h4>
                  <p style={{ color: '#fca5a5', fontSize: '0.85rem' }}>
                    {cleaningResult.message || 'An unknown error occurred while processing the CSV.'}
                  </p>
                </div>
              ) : (
                // Successful clean — render the audit report
                <div style={{ fontSize: '0.85rem' }}>
                  <h3 style={{ color: '#4ade80', marginBottom: '0.5rem' }}>✅ Ingestion & Audit Report</h3>
                  <p>Records Ingested: <strong>{cleaningResult.records_processed ?? 'N/A'}</strong></p>
                  {cleaningResult.converted_types && cleaningResult.converted_types.length > 0 && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                      Numeric columns standardised: {cleaningResult.converted_types.join(', ')}
                    </p>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.75rem' }}>
                    <div>
                      <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Renamed Columns:</h4>
                      {Object.keys(cleaningResult.renamed_columns ?? {}).length > 0 ? (
                        <ul style={{ paddingLeft: '1.2rem' }}>
                          {Object.entries(cleaningResult.renamed_columns ?? {}).map(([k, v]) => (
                            <li key={k} style={{ marginBottom: '0.2rem' }}>
                              <code>{k}</code> &rarr; <code>{v}</code>
                            </li>
                          ))}
                        </ul>
                      ) : <p style={{ color: 'var(--text-muted)' }}>None — columns already standard ✓</p>}
                    </div>
                    <div>
                      <h4 style={{ color: 'var(--text-muted)', marginBottom: '0.25rem' }}>Null Values per Column:</h4>
                      {Object.keys(cleaningResult.missing_values ?? {}).length > 0 ? (
                        <ul style={{ paddingLeft: '1.2rem' }}>
                          {Object.entries(cleaningResult.missing_values ?? {}).map(([k, v]) => (
                            <li key={k} style={{
                              marginBottom: '0.2rem',
                              color: v > 0 ? '#fca5a5' : 'inherit'
                            }}>
                              {k}: <strong>{v}</strong>
                            </li>
                          ))}
                        </ul>
                      ) : <p style={{ color: 'var(--text-muted)' }}>No null values detected ✓</p>}
                    </div>
                  </div>
                </div>
              )
            ) : (
              <div style={{
                color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                justifyContent: 'center', height: '100%',
                border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px',
                padding: '2rem', textAlign: 'center'
              }}>
                No active CSV files uploaded yet. Ingest a file to see quality reports.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
