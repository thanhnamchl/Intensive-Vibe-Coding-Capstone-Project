import os
import pandas as pd
from mcp.server.fastmcp import FastMCP
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import numpy as np
import itertools

# ── FastMCP Server ────────────────────────────────────────────────────────────
mcp = FastMCP("AI Agents Agricultural Modeling")

# ── CSV path ──────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Simulation_Data.csv",
)

# ── Global state ──────────────────────────────────────────────────────────────
data            = None
models          = {}
label_encoders  = {}

# ── All numeric columns that can be predicted / aggregated ───────────────────
# Features used as model inputs
INPUT_FEATURES = [
    "AWD Adoption",
    "Fertilizer Usage",
    "Pesticide Usage",
    "Water Usage",
    "Salinity Exposure",
]

# Targets the RandomForest models will be trained to predict
PREDICTION_TARGETS = [
    "Avg Yield",
    "Methane Emissions",
    "Emission Intensity",
    "Profit Margin",
    "Net Income",
    "Production Cost",
    "Straw Value",
    "Water Reliability",
    "Biodiversity",
    "Resilient Varieties",
    "Labor Intensity",
    "Flood Stress",
    "Drought Stress",
    "Salinity Stress",
]

# All numeric columns we want to surface in aggregations
# (superset of PREDICTION_TARGETS + raw input metrics)
AGG_NUMERIC_COLS = [
    "Avg Yield",
    "Methane Emissions",
    "Emission Intensity",
    "Profit Margin",
    "Net Income",
    "Production Cost",
    "Straw Value",
    "Water Usage",
    "Fertilizer Usage",
    "Pesticide Usage",
    "Salinity Exposure",
    "Max Flood Continuous",
    "Flood Stress",
    "Drought Stress",
    "Salinity Stress",
    "Biodiversity",
    "Resilient Varieties",
    "Water Reliability",
    "Labor Intensity",
]

# Mapping from AGG_NUMERIC_COLS → key name in the returned summary dict
# (snake_case prefixed with "avg_")
def _agg_key(col: str) -> str:
    normalized = col.lower().replace(" ", "_")
    if normalized.startswith("avg_"):
        return normalized
    return f"avg_{normalized}"


# ── Categorical string columns to strip on load ───────────────────────────────
CATEGORICAL_COLS = [
    "AWD Adoption",
    "Scenario Group",
    "Season Type",
    "Climate Type",
    "Resource Scenario",
    "Scenario Name",
]


# ── Initialisation ────────────────────────────────────────────────────────────

def init_data_and_models():
    global data, models, label_encoders

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Simulation CSV file not found at {CSV_PATH}")

    # ── Ingest ────────────────────────────────────────────────────────────────
    data = pd.read_csv(CSV_PATH)

    # Datetime
    if "datetime" in data.columns:
        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")

    # Strip whitespace from categorical columns (only those present in the file)
    for col in CATEGORICAL_COLS:
        if col in data.columns:
            data[col] = data[col].astype(str).str.strip()

    # ── Label-encode AWD Adoption ─────────────────────────────────────────────
    le_awd = LabelEncoder()
    data["AWD_encoded"] = le_awd.fit_transform(data["AWD Adoption"])
    label_encoders["AWD Adoption"] = le_awd

    X_all = data[
        ["AWD_encoded", "Fertilizer Usage", "Pesticide Usage",
         "Water Usage", "Salinity Exposure"]
    ]

    # ── Train one RandomForest per prediction target ──────────────────────────
    trained = []
    skipped = []
    for target in PREDICTION_TARGETS:
        if target not in data.columns:
            skipped.append(target)
            continue

        mask    = data[target].notna()
        X_train = X_all[mask]
        y_train = data.loc[mask, target]

        if len(y_train) < 10:
            skipped.append(target)
            continue

        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)
        models[target] = model
        trained.append(target)

    print(
        f"[mcp_server] Data ingested ({len(data)} rows). "
        f"Models trained: {trained}. "
        + (f"Skipped (column absent or too few rows): {skipped}." if skipped else "")
    )


# Run on import
init_data_and_models()


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_scenarios() -> dict:
    """
    Return all distinct categorical filter values available in the dataset:
    scenario groups, season types, climate types, resource scenarios,
    AWD options, and scenario names.
    """
    global data
    result = {
        "scenario_groups":    data["Scenario Group"].dropna().unique().tolist(),
        "season_types":       data["Season Type"].dropna().unique().tolist(),
        "climate_types":      data["Climate Type"].dropna().unique().tolist(),
        "resource_scenarios": data["Resource Scenario"].dropna().unique().tolist(),
        "awd_options":        data["AWD Adoption"].dropna().unique().tolist(),
    }
    if "Scenario Name" in data.columns:
        result["scenario_names"] = data["Scenario Name"].dropna().unique().tolist()
    return result


@mcp.tool()
def get_aggregated_metrics(filters: dict = None) -> dict:
    """
    Return aggregated means for all 19 agricultural indicators, with optional
    pre-filtering.

    Supported filter keys:
        Scenario Group, Season Type, Climate Type, Resource Scenario,
        AWD Adoption, Scenario Name

    Returns a dict with keys of the form "avg_<snake_case_column_name>",
    plus "total_records" and "awd_comparison".

    Example returned keys:
        avg_yield, avg_methane_emissions, avg_emission_intensity,
        avg_profit_margin, avg_net_income, avg_production_cost,
        avg_straw_value, avg_water_usage, avg_fertilizer_usage,
        avg_pesticide_usage, avg_salinity_exposure, avg_max_flood_continuous,
        avg_flood_stress, avg_drought_stress, avg_salinity_stress,
        avg_biodiversity, avg_resilient_varieties, avg_water_reliability,
        avg_labor_intensity
    """
    global data
    filtered = data.copy()

    if filters:
        for col, val in filters.items():
            if col in filtered.columns and val:
                filtered = filtered[filtered[col] == val]

    if filtered.empty:
        return {"status": "empty", "message": "No data matches the current filters."}

    summary: dict = {"total_records": len(filtered)}

    # Aggregate every numeric indicator that exists in the filtered data
    for col in AGG_NUMERIC_COLS:
        if col in filtered.columns:
            summary[_agg_key(col)] = float(filtered[col].mean())

    # AWD breakdown across the three core indicators
    core_breakdown_cols = [
        c for c in ["Avg Yield", "Methane Emissions", "Profit Margin"]
        if c in filtered.columns
    ]
    if core_breakdown_cols and "AWD Adoption" in filtered.columns:
        summary["awd_comparison"] = (
            filtered.groupby("AWD Adoption")[core_breakdown_cols]
            .mean()
            .round(3)
            .to_dict(orient="index")
        )

    return summary


@mcp.tool()
def run_agricultural_simulation(combos: list[tuple]) -> list[dict]:
    """
    combos: list of (awd_str, fert, pest, water, sal)
    """
    global models, label_encoders

    awd_strings = [c[0] for c in combos]
    try:
        awd_encoded = label_encoders["AWD Adoption"].transform(awd_strings)
    except Exception:
        awd_encoded = np.array([1 if a == "With AWD" else 0 for a in awd_strings])

    raw = {
        "AWD_encoded":       awd_encoded,
        "Fertilizer Usage":  [c[1] for c in combos],
        "Pesticide Usage":   [c[2] for c in combos],
        "Water Usage":       [c[3] for c in combos],
        "Salinity Exposure": [c[4] for c in combos],
    }

    # Reorder columns theo đúng thứ tự model đã train — tránh mọi lỗi thứ tự
    first_model = next(iter(models.values()))
    feature_order = list(first_model.feature_names_in_)
    X = pd.DataFrame(raw)[feature_order]

    results = {}
    for target, model in models.items():
        results[target] = model.predict(X).astype(float)

    return pd.DataFrame(results).to_dict(orient="records")


# ── Scoring vectorized ────────────────────────────────────────────────────────

def _score_batch(preds: list[dict], target_methane: float) -> np.ndarray:
    yields   = np.array([p["Avg Yield"]         for p in preds])
    margins  = np.array([p["Profit Margin"]      for p in preds])
    methanes = np.array([p["Methane Emissions"]  for p in preds])

    scores  = yields * 2.0 + margins
    overage = methanes - target_methane
    scores -= np.maximum(overage, 0) * 10.0
    return scores


if __name__ == "__main__":
    mcp.run()