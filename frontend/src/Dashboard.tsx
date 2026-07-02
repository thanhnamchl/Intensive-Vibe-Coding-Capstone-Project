import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
    ResponsiveContainer,
    BarChart,
    Bar,
    LineChart,
    Line,
    CartesianGrid,
    XAxis,
    YAxis,
    Tooltip,
    Legend
} from 'recharts';
import type { ScenarioInfo, SummaryMetrics, SimulationResult, OptimizationResult, ChatMessage } from './types';
import { TRANSLATIONS, SUGGESTED_TEMPLATES, SYNTAX_GUIDE_DATA } from './translations';
import { API_BASE, CHART_COLORS } from './config';

interface DashboardProps {
    lang: 'vi' | 'en';
    setLang: React.Dispatch<React.SetStateAction<'vi' | 'en'>>;
    onQuit: () => void;
}

export function Dashboard({ lang, setLang, onQuit }: DashboardProps) {
    const t = TRANSLATIONS[lang];
    const [scenariosInfo, setScenariosInfo] = useState<ScenarioInfo | null>(null);
    const [filters, setFilters] = useState({
        'Scenario Group': '',
        'Season Type': '',
        'Climate Type': '',
        'Resource Scenario': '',
        'AWD Adoption': '',
    });

    const [metrics, setMetrics] = useState<SummaryMetrics | null>(null);
    const [loadingMetrics, setLoadingMetrics] = useState(false);

    const [barChartCompareType, setBarChartCompareType] = useState<'scenario' | 'awd'>('scenario');
    const [barChartData, setBarChartData] = useState<any[]>([]);
    const [loadingBar, setLoadingBar] = useState(false);

    const [simInputs, setSimInputs] = useState({
        awd_adoption: 'With AWD',
        fertilizer_usage: 100,
        pesticide_usage: 5,
        water_usage: 600,
        salinity_exposure: 0.01,
    });
    const [simResults, setSimResults] = useState<SimulationResult | null>(null);
    const [loadingSim, setLoadingSim] = useState(false);

    const [optTargetMethane, setOptTargetMethane] = useState<number | ''>(200);
    const [optResults, setOptResults] = useState<OptimizationResult | null>(null);
    const [loadingOpt, setLoadingOpt] = useState(false);
    const [optError, setOptError] = useState<string | null>(null);

    const [yearlyData, setYearlyData] = useState<any[]>([]);
    const [loadingYearly, setLoadingYearly] = useState(false);
    const [chartMetric, setChartMetric] = useState<'yield' | 'methane' | 'income'>('yield');

    const [chatInput, setChatInput] = useState('');
    const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
    const [loadingChat, setLoadingChat] = useState(false);
    const [showSyntaxGuide, setShowSyntaxGuide] = useState(false);

    const chatEndRef = useRef<HTMLDivElement>(null);
    const chatInputRef = useRef<HTMLInputElement>(null);

    const isFirstRender = useRef(true);

    useEffect(() => {
        setChatHistory([
            {
                sender: 'agent',
                agentName: 'STAR-FARM System Orchestrator',
                role: 'Agri-AI Supervisor',
                text: ''
            }
        ]);
    }, [lang]);

    const fetchScenarios = async () => {
        try {
            const res = await fetch(`${API_BASE}/scenarios`);
            const data = await res.json();
            setScenariosInfo(data);
            await fetchYearlyData(filters, data);
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

    const fetchBarChartData = async (currentFilters = filters, compareType = barChartCompareType) => {
        setLoadingBar(true);
        try {
            const activeFilters = Object.fromEntries(
                Object.entries(currentFilters).filter(([, v]) => v !== '')
            );

            const dimension = compareType === 'scenario' ? 'Scenario Group' : 'AWD Adoption';

            const res = await fetch(`${API_BASE}/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    metrics: [],
                    dimension: dimension,
                    filters: activeFilters
                })
            });

            if (!res.ok) throw new Error('compare fetch failed');
            const data = await res.json();

            if (data.result && data.result.compare_breakdown) {
                const formatted = Object.entries(data.result.compare_breakdown).map(([name, vals]: any) => {
                    const avgYield = vals['Avg Yield'] !== undefined ? vals['Avg Yield'] : (vals['avg_yield'] !== undefined ? vals['avg_yield'] : 0);
                    const methane = vals['Methane Emissions'] !== undefined ? vals['Methane Emissions'] : (vals['avg_methane_emissions'] !== undefined ? vals['avg_methane_emissions'] : 0);
                    const profit = vals['Profit Margin'] !== undefined ? vals['Profit Margin'] : (vals['avg_profit_margin'] !== undefined ? vals['avg_profit_margin'] : 0);
                    // Lấy thêm trường Net Income
                    const netIncome = vals['Net Income'] !== undefined ? vals['Net Income'] : (vals['avg_net_income'] !== undefined ? vals['avg_net_income'] : 0);

                    return {
                        name,
                        'Avg Yield (t/ha)': parseFloat(Number(avgYield).toFixed(2)),
                        'Methane Emissions': parseFloat(Number(methane).toFixed(2)),
                        'Profit Margin (%)': parseFloat(Number(profit).toFixed(2)),
                        'Net Income ($)': parseFloat(Number(netIncome).toFixed(2)), // Đưa vào mảng dữ liệu cột
                    };
                });
                setBarChartData(formatted);
            } else {
                setBarChartData([]);
            }
        } catch (e) {
            console.error("Error loading bar chart data", e);
            setBarChartData([]);
        } finally {
            setLoadingBar(false);
        }
    };

    const fetchYearlyData = async (currentFilters = filters, currentScenariosInfo = scenariosInfo) => {
        if (!currentScenariosInfo) return;
        setLoadingYearly(true);
        try {
            const selectedGroup = currentFilters['Scenario Group'];
            const selectedAwd = currentFilters['AWD Adoption'];

            let combinations: { group: string; awd: string }[] = [];

            if (!selectedGroup && !selectedAwd) {
                const groupsInCsv = currentScenariosInfo.scenario_groups || [];
                const awdsInCsv = currentScenariosInfo.awd_options || [];

                const hasBAU = groupsInCsv.includes('BAU');
                const hasOMRH = groupsInCsv.includes('OMRH');
                const hasWithAWD = awdsInCsv.includes('With AWD');
                const hasWithoutAWD = awdsInCsv.includes('Without AWD');

                const bauName = hasBAU ? 'BAU' : (groupsInCsv[0] || 'BAU');
                const omrhName = hasOMRH ? 'OMRH' : (groupsInCsv[1] || 'OMRH');
                const withAwdName = hasWithAWD ? 'With AWD' : 'With AWD';
                const withoutAwdName = hasWithoutAWD ? 'Without AWD' : 'Without AWD';

                combinations = [
                    { group: bauName, awd: withAwdName },
                    { group: omrhName, awd: withAwdName },
                    { group: bauName, awd: withoutAwdName }
                ];
            } else {
                const groups = selectedGroup
                    ? [selectedGroup]
                    : (currentScenariosInfo.scenario_groups || []);

                const awds = selectedAwd
                    ? [selectedAwd]
                    : (currentScenariosInfo.awd_options && currentScenariosInfo.awd_options.length > 0
                        ? currentScenariosInfo.awd_options
                        : ['With AWD', 'Without AWD']);

                for (const g of groups) {
                    for (const a of awds) {
                        combinations.push({ group: g, awd: a });
                    }
                }
            }

            const baseFilters = Object.fromEntries(
                Object.entries(currentFilters).filter(([k, v]) => v !== '' && k !== 'Scenario Group' && k !== 'AWD Adoption')
            );

            const fetchedResults = [];

            for (const comb of combinations) {
                try {
                    const res = await fetch(`${API_BASE}/compare`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            metrics: [],
                            dimension: "Year",
                            filters: { ...baseFilters, "Scenario Group": comb.group, "AWD Adoption": comb.awd }
                        })
                    });
                    if (!res.ok) throw new Error('compare fetch failed');
                    const data = await res.json();
                    fetchedResults.push({ group: comb.group, awd: comb.awd, data: data.result?.compare_breakdown || {} });
                } catch (e) {
                    console.error(`Error loading compare for ${comb.group} + ${comb.awd}`, e);
                    fetchedResults.push({ group: comb.group, awd: comb.awd, data: {} });
                }
                await new Promise(resolve => setTimeout(resolve, 250));
            }

            const yearsSet = new Set<string>();
            fetchedResults.forEach(r => {
                Object.keys(r.data).forEach(yr => yearsSet.add(yr));
            });

            const merged = Array.from(yearsSet).map(year => {
                const row: any = { year };
                fetchedResults.forEach(r => {
                    const val = r.data[year];
                    if (val) {
                        const avgYield = val['Avg Yield'] !== undefined ? val['Avg Yield'] : (val['avg_yield'] !== undefined ? val['avg_yield'] : 0);
                        const methane = val['Methane Emissions'] !== undefined ? val['Methane Emissions'] : (val['avg_methane_emissions'] !== undefined ? val['avg_methane_emissions'] : 0);
                        const netIncome = val['Net Income'] !== undefined ? val['Net Income'] : (val['avg_net_income'] !== undefined ? val['avg_net_income'] : 0);

                        row[`${r.group} (${r.awd}) - Yield`] = avgYield;
                        row[`${r.group} (${r.awd}) - Methane`] = methane;
                        row[`${r.group} (${r.awd}) - Income`] = netIncome; // Lưu thêm khóa Income
                    }
                });
                return row;
            }).sort((a, b) => Number(a.year) - Number(b.year));

            setYearlyData(merged);
        } catch (e) {
            console.error("Error loading yearly metrics", e);
            setYearlyData([]);
        } finally {
            setLoadingYearly(false);
        }
    };

    const handleFilterChange = async (col: string, val: string) => {
        const updated = { ...filters, [col]: val };
        setFilters(updated);
        try {
            await fetchMetrics(updated);
            await fetchYearlyData(updated, scenariosInfo);
            await new Promise(resolve => setTimeout(resolve, 250));
            await fetchBarChartData(updated, barChartCompareType);
        } catch (e) {
            console.error("Error updating filtered data", e);
        }
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

            if (!res.ok) {
                setOptError(
                    data.message ||
                    data.detail?.message ||
                    (typeof data.detail === 'string' ? data.detail : null) ||
                    'Cannot be optimized.'
                );
                return;
            }

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
                text: data.text || (typeof data.result === 'string' ? data.result : 'Processed successfully.'),
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

    const getMessageText = (msg: ChatMessage) => {
        if (msg.sender === 'agent' && msg.role === 'Agri-AI Supervisor' && !msg.text) {
            return lang === 'vi'
                ? 'Chào mừng! Tôi điều phối các agent làm sạch, tổng hợp và mô hình hóa dự báo chuyên biệt. Bạn có thể truy vấn thống kê, mô phỏng các kịch bản hoặc yêu cầu tối ưu hóa chính sách tại đây.'
                : 'Welcome! I coordinate our specialized Data Cleaning, Aggregation, and Predictive Modeling agents. You can query statistics, simulate scenarios, or request policy optimization here.';
        }
        return msg.text;
    };

    const handleApplyTemplate = (text: string) => {
        setChatInput(text);
        chatInputRef.current?.focus();
    };

    // Cuộn mượt nội bộ bên trong khung chat, không làm nhảy toàn trang
    useEffect(() => {
        const container = chatEndRef.current?.parentElement;
        if (container) {
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        }
    }, [chatHistory, loadingChat]);

    // Quản lý chuyển đổi kiểu hiển thị của Bar Chart
    useEffect(() => {
        if (isFirstRender.current) {
            isFirstRender.current = false;
            return;
        }
        fetchBarChartData(filters, barChartCompareType);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [barChartCompareType]);

    // Thiết lập luồng khởi động tuần tự
    useEffect(() => {
        const loadInitialData = async () => {
            try {
                await fetchScenarios();
                await fetchMetrics();
                await runSimulation();
                await new Promise(resolve => setTimeout(resolve, 250));
                await fetchBarChartData(filters, barChartCompareType);
            } catch (e) {
                console.error("Error performing coordinated dashboard load", e);
            }
        };
        loadInitialData();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const metricSuffix = chartMetric === 'yield' ? 'Yield' : (chartMetric === 'methane' ? 'Methane' : 'Income');

    const yAxisLabel = chartMetric === 'yield'
        ? 'Yield (t/ha)'
        : (chartMetric === 'methane' ? 'Methane Emissions (kg/ha)' : 'Net Income ($/ha)');

    const filteredYearlyData = useMemo(() => {
        const currentYear = new Date().getFullYear(); // Lấy năm hiện tại động
        return yearlyData.filter(d => {
            const yr = Number(d.year);
            return !isNaN(yr) && yr >= currentYear && yr <= 2050;
        });
    }, [yearlyData]);
    const availableSeries = useMemo(() => {
        const keys = new Set<string>();
        filteredYearlyData.forEach(row => {
            Object.keys(row).forEach(k => {
                if (k !== 'year' && k.endsWith(`- ${metricSuffix}`)) {
                    keys.add(k);
                }
            });
        });
        return Array.from(keys);
    }, [filteredYearlyData, metricSuffix]);
    // 1. Tính toán miền và mảng vạch chia cho trục Y bên trái (Yield, Methane, Profit)
    const leftSymmetricDomain = useMemo(() => {
        const keys = ["Avg Yield (t/ha)", "Methane Emissions", "Profit Margin (%)"];
        let maxVal = 0;
        barChartData.forEach(item => {
            keys.forEach(key => {
                const val = Number(item[key]);
                if (!isNaN(val)) {
                    const abs = Math.abs(val);
                    if (abs > maxVal) maxVal = abs;
                }
            });
        });
        const limit = Math.ceil(maxVal * 1.1) || 10;
        return [-limit, limit];
    }, [barChartData]);

    const leftTicks = useMemo(() => {
        const limit = -leftSymmetricDomain[0];
        const half = Math.round(limit / 2);
        return [-limit, -half, 0, half, limit]; // Ép hiển thị mốc 0 ở chính giữa
    }, [leftSymmetricDomain]);

    // 2. Tính toán miền và mảng vạch chia cho trục Y bên phải (Net Income)
    const rightSymmetricDomain = useMemo(() => {
        const keys = ["Net Income ($)"];
        let maxVal = 0;
        barChartData.forEach(item => {
            keys.forEach(key => {
                const val = Number(item[key]);
                if (!isNaN(val)) {
                    const abs = Math.abs(val);
                    if (abs > maxVal) maxVal = abs;
                }
            });
        });
        const limit = Math.ceil(maxVal * 1.1) || 10;
        return [-limit, limit];
    }, [barChartData]);

    const rightTicks = useMemo(() => {
        const limit = -rightSymmetricDomain[0];
        const half = Math.round(limit / 2);
        return [-limit, -half, 0, half, limit]; // Ép hiển thị mốc 0 ở chính giữa
    }, [rightSymmetricDomain]);

    const parsedYears = filteredYearlyData.map(d => Number(d.year)).filter(y => !isNaN(y) && y > 0);
    const minYear = parsedYears.length > 0 ? Math.min(...parsedYears) : new Date().getFullYear();
    const maxYear = parsedYears.length > 0 ? Math.max(...parsedYears) : 2050;

    const periodText = (lang === 'vi' ? `từ năm ${minYear} đến ${maxYear}` : `from ${minYear} to ${maxYear}`);

    const trendsDescription = t.yearlyPerformanceDesc.replace('{period}', periodText);
    return (
        <div className="dashboard-container">
            <header>
                <div className="header-title">
                    <h1>{t.title}</h1>
                    <p>{t.subtitle}</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div className="lang-toggle-container">
                        <button
                            type="button"
                            className={`lang-toggle-btn ${lang === 'vi' ? 'active' : ''}`}
                            onClick={() => setLang('vi')}
                        >
                            VI
                        </button>
                        <button
                            type="button"
                            className={`lang-toggle-btn ${lang === 'en' ? 'active' : ''}`}
                            onClick={() => setLang('en')}
                        >
                            EN
                        </button>
                    </div>
                    <div className="agent-status-badge">
                        <div className="status-pulse"></div>
                        <span>{t.coreActive}</span>
                    </div>
                    <button
                        type="button"
                        className="btn btn-outline btn-quit"
                        onClick={onQuit}
                    >
                        [-] {t.quitReset}
                    </button>
                </div>
            </header>

            {/* Filter Bar */}
            <section className="glass-panel">
                <h2>[=] {t.scenarioFiltration}</h2>
                <div className="filter-grid">
                    <div>
                        <label className="filter-label">{t.scenarioGroup}</label>
                        <select
                            className="select-input"
                            value={filters['Scenario Group']}
                            onChange={(e) => handleFilterChange('Scenario Group', e.target.value)}
                        >
                            <option value="">{t.allScenarioGroups}</option>
                            {scenariosInfo?.scenario_groups.map(g => <option key={g} value={g}>{g}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="filter-label">{t.seasonType}</label>
                        <select
                            className="select-input"
                            value={filters['Season Type']}
                            onChange={(e) => handleFilterChange('Season Type', e.target.value)}
                        >
                            <option value="">{t.allSeasons}</option>
                            {scenariosInfo?.season_types.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="filter-label">{t.climateType}</label>
                        <select
                            className="select-input"
                            value={filters['Climate Type']}
                            onChange={(e) => handleFilterChange('Climate Type', e.target.value)}
                        >
                            <option value="">{t.allClimates}</option>
                            {scenariosInfo?.climate_types.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="filter-label">{t.resourceScenario}</label>
                        <select
                            className="select-input"
                            value={filters['Resource Scenario']}
                            onChange={(e) => handleFilterChange('Resource Scenario', e.target.value)}
                        >
                            <option value="">{t.allResources}</option>
                            {scenariosInfo?.resource_scenarios.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="filter-label">{t.awdAdoption}</label>
                        <select
                            className="select-input"
                            value={filters['AWD Adoption']}
                            onChange={(e) => handleFilterChange('AWD Adoption', e.target.value)}
                        >
                            <option value="">{t.allAwd}</option>
                            {scenariosInfo?.awd_options.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                    </div>
                </div>
            </section>

            {metrics?.status === 'empty' && (
                <div className="empty-warning-banner">
                    ⚠️ <strong>{t.noRecordsFound}</strong>
                </div>
            )}

            {/* Main Stats Row */}
            <section className="glass-panel">
                <div className="metrics-row">
                    <div className="metric-card">
                        <span className="label">{t.avgYield}</span>
                        <span className="value">
                            {loadingMetrics ? t.loading : (metrics && metrics.avg_yield !== undefined) ? `${metrics.avg_yield.toFixed(2)} t/ha` : 'N/A'}
                        </span>
                        <span className="subtext">
                            [-] {t.standardTarget}
                        </span>
                    </div>
                    <div className="metric-card">
                        <span className="label">{t.methaneEmissions}</span>
                        <span className="value text-danger">
                            {loadingMetrics ? t.loading : (metrics && metrics.avg_methane_emissions !== undefined) ? `${metrics.avg_methane_emissions.toFixed(1)} kg/ha` : 'N/A'}
                        </span>
                        <span className="subtext text-danger">[-] {t.carbonEquivalent}</span>
                    </div>
                    <div className="metric-card">
                        <span className="label">{t.profitMargin}</span>
                        <span className="value text-success">
                            {loadingMetrics ? t.loading : (metrics && metrics.avg_profit_margin !== undefined) ? `${metrics.avg_profit_margin.toFixed(1)}%` : 'N/A'}
                        </span>
                        <span className="subtext text-success">[-] {t.financialYield}</span>
                    </div>
                    <div className="metric-card">
                        <span className="label">{t.netIncome}</span>
                        <span className="value">
                            {loadingMetrics ? t.loading : (metrics && metrics.avg_net_income !== undefined) ? `$${metrics.avg_net_income.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : 'N/A'}
                        </span>
                        <span className="subtext">[-] {t.perHectare}</span>
                    </div>
                </div>
            </section>

            {/* Visual Analytics */}
            <div className="dashboard-grid">
                <div className="glass-panel col-8">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <h2>[Trend] {t.impactComparison}</h2>
                        <div className="metric-toggle">
                            <button
                                type="button"
                                className={`btn ${barChartCompareType === 'scenario' ? '' : 'btn-ghost'}`}
                                style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
                                onClick={() => setBarChartCompareType('scenario')}
                            >
                                {t.scenarioGroups}
                            </button>
                            <button
                                type="button"
                                className={`btn ${barChartCompareType === 'awd' ? '' : 'btn-ghost'}`}
                                style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
                                onClick={() => setBarChartCompareType('awd')}
                            >
                                {t.awdPractices}
                            </button>
                        </div>
                    </div>

                    <div className="chart-container-height">
                        {loadingBar ? (
                            <div className="centered-fallback">
                                <span className="spinner-text">(o)</span>
                                <span style={{ marginLeft: '0.5rem' }}>{t.loading}</span>
                            </div>
                        ) : barChartData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={barChartData}>
                                    <XAxis dataKey="name" stroke="#9ca3af" />

                                    {/* Trục Y bên trái: áp dụng miền đối xứng */}
                                    {/* Trục Y bên trái */}
                                    <YAxis
                                        stroke="#9ca3af"
                                        yAxisId="left"
                                        domain={leftSymmetricDomain}
                                        ticks={leftTicks} // Thêm dòng này
                                    />

                                    {/* Trục Y bên phải */}
                                    <YAxis
                                        stroke="#eab308"
                                        yAxisId="right"
                                        orientation="right"
                                        domain={rightSymmetricDomain}
                                        ticks={rightTicks} // Thêm dòng này
                                    />

                                    <Tooltip contentStyle={{ background: '#0b1510', border: '1px solid var(--panel-border)', borderRadius: '8px' }} />
                                    <Legend />
                                    <Bar yAxisId="left" dataKey="Avg Yield (t/ha)" fill="#22c55e" radius={[4, 4, 0, 0]} />
                                    <Bar yAxisId="left" dataKey="Methane Emissions" fill="#ef4444" radius={[4, 4, 0, 0]} />
                                    <Bar yAxisId="left" dataKey="Profit Margin (%)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                    <Bar yAxisId="right" dataKey="Net Income ($)" fill="#eab308" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="centered-fallback">{t.noData}</div>
                        )}
                    </div>
                </div>

                {/* Optimizer Workspace */}
                <div className="glass-panel col-4 flex-col">
                    <div>
                        <h2>[*] {t.methanePolicyOptimizer}</h2>
                        <p className="optimizer-desc">
                            {t.optimizerDesc}
                        </p>
                        <div className="optimizer-form-row">
                            <div style={{ flex: 1 }}>
                                <label className="filter-label">{t.methaneCeiling}</label>
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
                                    <p role="alert" className="optimizer-error-msg">
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
                                {loadingOpt ? <span className="spinner-text">(o)</span> : t.optimize}
                            </button>
                        </div>

                        {optResults && (
                            <div className="optimizer-results-box">
                                <h4 className="text-success" style={{ marginBottom: '0.5rem' }}>{t.optimizedAllocation}</h4>
                                <div className="results-grid">
                                    <div>AWD: <strong>{optResults.optimized_inputs['AWD Adoption']}</strong></div>
                                    <div>Water: <strong>{optResults.optimized_inputs['Water Usage']} m³</strong></div>
                                    <div>Fertilizer: <strong>{optResults.optimized_inputs['Fertilizer Usage']} kg</strong></div>
                                    <div>Pesticides: <strong>{optResults.optimized_inputs['Pesticide Usage']} kg</strong></div>
                                </div>
                                <h4 className="text-success" style={{ marginBottom: '0.5rem' }}>{t.expectedOutcomes}</h4>
                                <div className="results-grid">
                                    <div>Yield: <strong>{optResults.expected_outcomes['Avg Yield']?.toFixed(2)} t/ha</strong></div>
                                    <div className="text-danger">Methane: <strong>{optResults.expected_outcomes['Methane Emissions']?.toFixed(1)} kg</strong></div>
                                    <div>Profit Margin: <strong>{optResults.expected_outcomes['Profit Margin']?.toFixed(1)}%</strong></div>
                                    <div>Net Income: <strong>${optResults.expected_outcomes['Net Income']?.toFixed(0)}</strong></div>
                                </div>
                                <button
                                    className="btn"
                                    style={{ width: '100%', fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                                    onClick={applyOptimizedInputs}
                                >
                                    {t.applySliders}
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="dashboard-grid">
                {/* Input Simulation Controls */}
                <div className="glass-panel col-4">
                    <h2>[=] {t.inputSimulationControls}</h2>
                    <div className="slider-group" style={{ marginTop: '1rem' }}>
                        <div className="slider-item">
                            <label className="filter-label">{t.awdAdoptionPractice}</label>
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
                                <span className="name">{t.fertilizerUsage}</span>
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
                                <span className="name">{t.pesticideUsage}</span>
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
                                <span className="name">{t.waterUsage}</span>
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
                                <span className="name">{t.salinityExposure}</span>
                                <span className="value">{(simInputs.salinity_exposure * 100).toFixed(2)}%</span>
                            </div>
                            <input
                                type="range" min="0" max="0.05" step="0.001"
                                value={simInputs.salinity_exposure}
                                onChange={(e) => setSimInputs(prev => ({ ...prev, salinity_exposure: Number(e.target.value) }))}
                            />
                        </div>

                        <button className="btn" style={{ width: '100%', marginTop: '0.5rem' }} onClick={() => runSimulation()} disabled={loadingSim}>
                            {loadingSim ? <span className="spinner-text">(o)</span> : t.simulateButton}
                        </button>

                        {simResults && (
                            <div className="simulation-estimates-box">
                                <h4 className="text-success" style={{ marginBottom: '0.5rem', fontSize: '0.9rem' }}>{t.simulationEstimates}</h4>
                                <div className="results-grid-small">
                                    <div>Yield: <strong>{simResults.predictions['Avg Yield']?.toFixed(2)} t/ha</strong></div>
                                    <div className="text-danger">Methane: <strong>{simResults.predictions['Methane Emissions']?.toFixed(1)} kg</strong></div>
                                    <div>Profit Margin: <strong>{simResults.predictions['Profit Margin']?.toFixed(1)}%</strong></div>
                                    <div>Net Income: <strong>${simResults.predictions['Net Income']?.toFixed(0)}</strong></div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Multi-Agent Chat Workspace */}
                <div className="glass-panel col-8 flex-col" style={{ display: 'flex', flexDirection: 'column' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <h2>[AI] {t.multiAgentChat}</h2>
                        <button
                            type="button"
                            className="btn btn-ghost"
                            style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem' }}
                            onClick={() => setShowSyntaxGuide(!showSyntaxGuide)}
                        >
                            {showSyntaxGuide ? `[-] ${t.hideGuide}` : `[?] ${t.showGuide}`}
                        </button>
                    </div>

                    {/* Interactive Chat Syntax Guide */}
                    {showSyntaxGuide && (
                        <div className="query-guide-panel">
                            <h4 style={{ color: '#22c55e', marginBottom: '0.4rem' }}>{t.queryGuideTitle}</h4>
                            <div className="query-guide-grid">
                                {SYNTAX_GUIDE_DATA.map((item, index) => (
                                    <div key={index} className="query-guide-item">
                                        <div style={{ fontWeight: 600, color: '#f0fdf4' }}>{item.title}</div>
                                        <div className="query-guide-syntax">{item.syntax}</div>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                                            {item.examples.map((ex, i) => (
                                                <span
                                                    key={i}
                                                    className="query-guide-example"
                                                    onClick={() => handleApplyTemplate(ex)}
                                                    title="Click to load"
                                                >
                                                    &rarr; {ex}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="chat-messages">
                        {chatHistory.map((msg, i) => (
                            <div key={i} className={`message ${msg.sender}`}>
                                {msg.sender === 'agent' && (
                                    <div className="agent-header">
                                        <span>[AI]</span>
                                        <span style={{ fontWeight: 600, marginLeft: '0.3rem' }}>{msg.agentName}</span>
                                        <span className="badge-info">{msg.role}</span>
                                    </div>
                                )}
                                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{getMessageText(msg)}</div>
                                {msg.data && (
                                    <pre className="agent-data-pre">
                                        {JSON.stringify(msg.data, null, 2)}
                                    </pre>
                                )}
                            </div>
                        ))}
                        {loadingChat && (
                            <div className="message agent">
                                <div className="agent-header">
                                    <span className="spinner-text">(o)</span>
                                    <span style={{ marginLeft: '0.3rem' }}>Agent Core thinking...</span>
                                </div>
                            </div>
                        )}
                        <div ref={chatEndRef} />
                    </div>

                    {/* Suggested Templates Strip */}
                    <div style={{ marginTop: 'auto', paddingTop: '4px' }}>
                        {/* Suggested Templates Strip */}
                        <div style={{ marginTop: 'auto', paddingTop: '8px' }}>
                            <div className="chat-suggestions-title">{t.suggestedQueries}</div>
                            <div className="chat-suggestions">
                                {SUGGESTED_TEMPLATES.map((item, idx) => (
                                    <button
                                        key={idx}
                                        type="button"
                                        className="suggestion-chip"
                                        onClick={() => handleApplyTemplate(item.text)}
                                    >
                                        <span className="category">[{item.category}]</span>
                                        <strong style={{ color: '#f0fdf4' }}>{item.text}</strong>
                                        <div style={{ fontSize: '0.68rem', color: '#9ca3af', marginTop: '3px', fontWeight: 'normal' }}>
                                            &rarr; {lang === 'vi' ? item.viFull : item.enFull}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    <form className="chat-input-row" onSubmit={sendChatMessage}>
                        <input
                            ref={chatInputRef}
                            type="text"
                            placeholder={t.chatPlaceholder}
                            value={chatInput}
                            onChange={(e) => { setChatInput(e.target.value); }}
                            disabled={loadingChat}
                        />
                        <button className="btn" type="submit" disabled={loadingChat}>
                            [{'>'}] {t.send}
                        </button>
                    </form>
                </div>
            </div>

            {/* Yearly Trends Section */}
            <section className="glass-panel" style={{ marginTop: '2rem' }}>
                <div className="trends-header">
                    <div>
                        <h2>[Trend] {t.yearlyPerformance}</h2>
                        <p className="trends-desc">
                            {trendsDescription}
                        </p>
                    </div>
                    <div className="metric-toggle">
                        <button
                            type="button"
                            className={`btn ${chartMetric === 'yield' ? '' : 'btn-ghost'}`}
                            style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
                            onClick={() => setChartMetric('yield')}
                        >
                            {t.avgYieldLabel}
                        </button>
                        <button
                            type="button"
                            className={`btn ${chartMetric === 'methane' ? '' : 'btn-ghost'}`}
                            style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
                            onClick={() => setChartMetric('methane')}
                        >
                            {t.methaneLabel}
                        </button>
                        <button
                            type="button"
                            className={`btn ${chartMetric === 'income' ? '' : 'btn-ghost'}`}
                            style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
                            onClick={() => setChartMetric('income')}
                        >
                            {lang === 'vi' ? 'Thu nhập ròng ($/ha)' : 'Net Income ($/ha)'}
                        </button>
                    </div>
                </div>

                <div className="line-chart-container">
                    {filteredYearlyData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                            {/* Thay đổi nguồn data ở đây */}
                            <LineChart data={filteredYearlyData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                <XAxis dataKey="year" stroke="#9ca3af" />
                                <YAxis
                                    stroke="#9ca3af"
                                    label={{
                                        value: yAxisLabel, // Sử dụng nhãn động thay thế
                                        angle: -90,
                                        position: 'insideLeft',
                                        fill: '#9ca3af',
                                        offset: 10
                                    }}
                                />
                                <Tooltip
                                    contentStyle={{
                                        background: '#0b1510',
                                        border: '1px solid var(--panel-border)',
                                        borderRadius: '8px',
                                        color: '#f0fdf4'
                                    }}
                                />
                                <Legend />
                                {availableSeries.map((seriesKey, idx) => {
                                    const color = CHART_COLORS[idx % CHART_COLORS.length];
                                    const displayName = seriesKey.replace(` - ${chartMetric === 'yield' ? 'Yield' : 'Methane'}`, '');
                                    return (
                                        <Line
                                            key={seriesKey}
                                            type="monotone"
                                            dataKey={seriesKey}
                                            name={displayName}
                                            stroke={color}
                                            strokeWidth={2}
                                            dot={{ r: 3 }}
                                            activeDot={{ r: 5 }}
                                        />
                                    );
                                })}
                            </LineChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="centered-fallback">
                            {loadingYearly ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <span className="spinner-text">(o)</span>
                                    <span>Aggregating scenario data streams...</span>
                                </div>
                            ) : t.noData}
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}