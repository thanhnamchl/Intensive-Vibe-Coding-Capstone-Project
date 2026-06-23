import os
import pandas as pd
from mcp.server.fastmcp import FastMCP
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

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
    return "avg_" + col.lower().replace(" ", "_")


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
def run_agricultural_simulation(
    awd_adoption: str,
    fertilizer_usage: float,
    pesticide_usage: float,
    water_usage: float,
    salinity_exposure: float,
) -> dict:
    """
    Predict all agricultural output indicators given a set of agronomic inputs.

    Inputs:
        awd_adoption       : 'With AWD' or 'Without AWD'
        fertilizer_usage   : Fertilizer applied (kg/ha), e.g. 50–250
        pesticide_usage    : Pesticide applied (kg/ha), e.g. 0.5–15
        water_usage        : Irrigation water (m³/ha), e.g. 100–1500
        salinity_exposure  : Salinity level (ppt), e.g. 0.0–0.1

    Returns:
        inputs      : Echo of the provided inputs
        predictions : Dict of predicted values for every trained target:
                      Avg Yield, Methane Emissions, Emission Intensity,
                      Profit Margin, Net Income, Production Cost, Straw Value,
                      Water Reliability, Biodiversity, Resilient Varieties,
                      Labor Intensity, Flood Stress, Drought Stress, Salinity Stress
    """
    global models, label_encoders

    # Encode AWD
    try:
        awd_encoded = label_encoders["AWD Adoption"].transform([awd_adoption])[0]
    except Exception:
        # Fallback encoding if label not seen during training
        awd_encoded = 1 if awd_adoption == "With AWD" else 0

    X_input = pd.DataFrame([{
        "AWD_encoded":      awd_encoded,
        "Fertilizer Usage": fertilizer_usage,
        "Pesticide Usage":  pesticide_usage,
        "Water Usage":      water_usage,
        "Salinity Exposure": salinity_exposure,
    }])

    predictions: dict = {}
    for target, model in models.items():
        predictions[target] = float(model.predict(X_input)[0])

    return {
        "inputs": {
            "AWD Adoption":      awd_adoption,
            "Fertilizer Usage":  fertilizer_usage,
            "Pesticide Usage":   pesticide_usage,
            "Water Usage":       water_usage,
            "Salinity Exposure": salinity_exposure,
        },
        "predictions": predictions,
    }


@mcp.tool()
def clean_and_standardize_csv(file_content: str) -> dict:
    """
    Accept a raw CSV string, standardize column names to match the master
    schema, coerce numeric types, and return a quality report with a data
    preview.

    Recognised column aliases (case-insensitive, substring match):
        yield              → Avg Yield
        methane            → Methane Emissions
        emission_intensity → Emission Intensity
        profit             → Profit Margin
        net_income         → Net Income
        production_cost    → Production Cost
        straw              → Straw Value
        water              → Water Usage
        fertilizer         → Fertilizer Usage
        pesticide          → Pesticide Usage
        salinity_exposure  → Salinity Exposure
        max_flood          → Max Flood Continuous
        flood_stress       → Flood Stress
        drought            → Drought Stress
        salinity_stress    → Salinity Stress
        biodiversity       → Biodiversity
        resilient          → Resilient Varieties
        reliability        → Water Reliability
        labor              → Labor Intensity
        awd                → AWD Adoption
        scenario_group     → Scenario Group
        season             → Season Type
        climate            → Climate Type
        resource_scenario  → Resource Scenario
        scenario_name      → Scenario Name
    """
    from io import StringIO
    import csv

    if not file_content or not file_content.strip():
        return {"status": "error", "message": "Input content is empty."}

    try:
        dialect = csv.Sniffer().sniff(file_content[:2048])
        df = pd.read_csv(StringIO(file_content), sep=dialect.delimiter)
    except csv.Error:
        # Fallback: try comma
        try:
            df = pd.read_csv(StringIO(file_content))
        except Exception as e:
            return {"status": "error", "message": f"Could not parse CSV: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Processing failed: {str(e)}"}

    if df.empty:
        return {"status": "error", "message": "The provided CSV file contains no data."}

    original_cols = df.columns.tolist()

    # ── Column name standardisation ───────────────────────────────────────────
    # Order matters: longer/more specific substrings checked first
    ALIAS_MAP = [
        ("emission_intensity",  "Emission Intensity"),
        ("production_cost",     "Production Cost"),
        ("max_flood",           "Max Flood Continuous"),
        ("flood_stress",        "Flood Stress"),
        ("salinity_stress",     "Salinity Stress"),
        ("drought_stress",      "Drought Stress"),
        ("salinity_exposure",   "Salinity Exposure"),
        ("water_reliability",   "Water Reliability"),
        ("resilient_varieties", "Resilient Varieties"),
        ("labor_intensity",     "Labor Intensity"),
        ("straw_value",         "Straw Value"),
        ("net_income",          "Net Income"),
        ("profit_margin",       "Profit Margin"),
        ("avg_yield",           "Avg Yield"),
        ("scenario_group",      "Scenario Group"),
        ("resource_scenario",   "Resource Scenario"),
        ("scenario_name",       "Scenario Name"),
        ("season_type",         "Season Type"),
        ("climate_type",        "Climate Type"),
        # Short aliases last
        ("yield",               "Avg Yield"),
        ("methane",             "Methane Emissions"),
        ("emission",            "Methane Emissions"),
        ("profit",              "Profit Margin"),
        ("income",              "Net Income"),
        ("cost",                "Production Cost"),
        ("straw",               "Straw Value"),
        ("water",               "Water Usage"),
        ("fertilizer",          "Fertilizer Usage"),
        ("pesticide",           "Pesticide Usage"),
        ("salinity",            "Salinity Exposure"),
        ("flood",               "Max Flood Continuous"),
        ("drought",             "Drought Stress"),
        ("biodiversity",        "Biodiversity"),
        ("resilient",           "Resilient Varieties"),
        ("reliability",         "Water Reliability"),
        ("labor",               "Labor Intensity"),
        ("awd",                 "AWD Adoption"),
        ("scenario",            "Scenario Group"),
        ("season",              "Season Type"),
        ("climate",             "Climate Type"),
        ("resource",            "Resource Scenario"),
    ]

    renamed: dict = {}
    for col in list(df.columns):
        col_lower = col.lower().replace(" ", "_")
        for alias, standard in ALIAS_MAP:
            if alias in col_lower and col != standard:
                df.rename(columns={col: standard}, inplace=True)
                renamed[col] = standard
                break

    # ── Numeric type coercion ─────────────────────────────────────────────────
    NUMERIC_COLS = [
        "Avg Yield", "Methane Emissions", "Emission Intensity",
        "Profit Margin", "Net Income", "Production Cost", "Straw Value",
        "Water Usage", "Fertilizer Usage", "Pesticide Usage", "Salinity Exposure",
        "Max Flood Continuous", "Flood Stress", "Drought Stress", "Salinity Stress",
        "Biodiversity", "Resilient Varieties", "Water Reliability", "Labor Intensity",
    ]
    conversions = []
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            conversions.append(col)

    # ── Categorical strip ─────────────────────────────────────────────────────
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # ── Quality report ────────────────────────────────────────────────────────
    missing_counts   = df.isnull().sum().to_dict()
    missing_counts   = {k: int(v) for k, v in missing_counts.items() if v > 0}
    unrecognised     = [c for c in df.columns if c not in (NUMERIC_COLS + CATEGORICAL_COLS + ["datetime"])]

    return {
        "status":           "success",
        "records_processed": len(df),
        "original_columns": original_cols,
        "final_columns":    df.columns.tolist(),
        "renamed_columns":  renamed,
        "converted_types":  conversions,
        "missing_values":   missing_counts,
        "unrecognised_columns": unrecognised,
        "preview":          df.head(10).to_dict(orient="records"),
    }


if __name__ == "__main__":
    mcp.run()