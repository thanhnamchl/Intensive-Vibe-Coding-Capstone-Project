export interface ScenarioInfo {
    scenario_groups: string[];
    season_types: string[];
    climate_types: string[];
    resource_scenarios: string[];
    awd_options: string[];
}

export interface SummaryMetrics {
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
}

export interface ChatMessage {
    sender: 'user' | 'agent';
    agentName?: string;
    role?: string;
    text: string;
    data?: Record<string, unknown> | null;
}

export interface SimulationResult {
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

export interface OptimizationResult {
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

export interface DataStatus {
    data_loaded: boolean;
    rows_loaded: number;
    models_ready: boolean;
    trained_targets: string[];
    required_columns: string[];
    categorical_columns: string[];
}