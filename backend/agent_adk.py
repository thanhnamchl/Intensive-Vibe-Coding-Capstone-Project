import re
from mcp_server import get_aggregated_metrics, run_agricultural_simulation, get_scenarios, data,  _score_batch
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import numpy as np
import pandas as pd

# ── Canonical lookup tables (shared by Agent + Orchestrator) ──────────────────
# Column names must exactly match the dataset headers.

DIMENSION_MAP = {
    # keyword            → DataFrame column
    "climate":           "Climate Type",
    "season":            "Season Type",
    "scenario":          "Scenario Group",
    "scenario name":     "Scenario Name",
    "awd":               "AWD Adoption",
    "resource":          "Resource Scenario",
    "year":              "Year",
}

METRIC_MAP = {
    # keyword(s)         → DataFrame column
    # — longer phrases first so _resolve_metrics sorts correctly —
    "emission intensity":  "Emission Intensity",
    "flood stress":        "Flood Stress",
    "salinity stress":     "Salinity Stress",
    "drought stress":      "Drought Stress",
    "water reliability":   "Water Reliability",
    "resilient varieties": "Resilient Varieties",
    "labor intensity":     "Labor Intensity",
    "max flood":           "Max Flood Continuous",
    "production cost":     "Production Cost",
    "straw value":         "Straw Value",
    "net income":          "Net Income",
    "profit margin":       "Profit Margin",
    "avg yield":           "Avg Yield",
    # — short / common aliases —
    "yield":              "Avg Yield",
    "methane":            "Methane Emissions",
    "emission":           "Methane Emissions",
    "profit":             "Profit Margin",
    "income":             "Net Income",
    "cost":               "Production Cost",
    "water":              "Water Usage",
    "fertilizer":         "Fertilizer Usage",
    "pesticide":          "Pesticide Usage",
    "salinity":           "Salinity Exposure",
    "flood":              "Max Flood Continuous",
    "drought":            "Drought Stress",
    "biodiversity":       "Biodiversity",
    "resilient":          "Resilient Varieties",
    "reliability":        "Water Reliability",
    "labor":              "Labor Intensity",
    "straw":              "Straw Value",
}

# Default metrics shown when user says "all metrics" or gives no specific metric
DEFAULT_METRICS = [
    "Avg Yield",
    "Methane Emissions",
    "Emission Intensity",
    "Profit Margin",
    "Net Income",
    "Water Usage",
    "Water Reliability",
    "Biodiversity",
    "Labor Intensity",
]

# Human-friendly display labels  (column → (icon, unit))
METRIC_LABELS = {
    "Avg Yield":              ("🌾", "t/ha"),
    "Methane Emissions":      ("💨", "kg CH4/ha"),
    "Emission Intensity":     ("💨", "kg CH4/t Rice"),
    "Profit Margin":          ("📈", "%"),
    "Net Income":             ("💰", "$/ha"),
    "Production Cost":        ("💸", "$/ha"),
    "Straw Value":            ("🌿", "$/ha"),
    "Water Usage":            ("💧", "mm/ha"),
    "Fertilizer Usage":       ("🧪", "kg NH4/ha"),
    "Pesticide Usage":        ("🧴", "kg/ha"),
    "Salinity Exposure":      ("🧂", "ppt"),
    "Max Flood Continuous":   ("🌊", "days"),
    "Flood Stress":           ("🌊", "index"),
    "Drought Stress":         ("☀️",  "index"),
    "Salinity Stress":        ("🧂", "index"),
    "Biodiversity":           ("🦋", "index"),
    "Resilient Varieties":    ("🌱", "%"),
    "Water Reliability":      ("💧", "%"),
    "Labor Intensity":        ("👷", "hours/ha"),
}

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}

# Keys returned by get_aggregated_metrics() → (display label, icon, unit)
AGG_KEY_LABELS = {
    "avg_yield":                 ("Avg Yield",            "🌾", "t/ha"),
    "avg_methane_emissions":     ("Methane Emissions",    "💨", "kg CH4/ha"),
    "avg_emission_intensity":    ("Emission Intensity",   "💨", "kg CH4/t Rice"),
    "avg_profit_margin":         ("Profit Margin",        "📈", "%"),
    "avg_net_income":            ("Net Income",           "💰", "$/ha"),
    "avg_production_cost":       ("Production Cost",      "💸", "$/ha"),
    "avg_straw_value":           ("Straw Value",          "🌿", "$/ha"),
    "avg_water_usage":           ("Water Usage",          "💧", "mm/ha"),
    "avg_fertilizer_usage":      ("Fertilizer Usage",     "🧪", "kg/ha"),
    "avg_pesticide_usage":       ("Pesticide Usage",      "🧴", "kg NH4/ha"),
    "avg_salinity_exposure":     ("Salinity Exposure",    "🧂", "ppt"),
    "avg_max_flood_continuous":  ("Max Flood Continuous", "🌊", "days"),
    "avg_flood_stress":          ("Flood Stress",         "🌊", "index"),
    "avg_drought_stress":        ("Drought Stress",       "☀️",  "index"),
    "avg_salinity_stress":       ("Salinity Stress",      "🧂", "index"),
    "avg_biodiversity":          ("Biodiversity",         "🦋", "index"),
    "avg_resilient_varieties":   ("Resilient Varieties",  "🌱", "%"),
    "avg_water_reliability":     ("Water Reliability",    "💧", "%"),
    "avg_labor_intensity":       ("Labor Intensity",      "👷", "hours/ha"),
}

# Keys returned by run_agricultural_simulation() → predictions dict
PRED_KEY_LABELS = {
    "Avg Yield":              ("🌾", "t/ha",          ".2f"),
    "Methane Emissions":      ("💨", "kg/ha",         ".1f"),
    "Emission Intensity":     ("💨", "kg CO₂e/t",    ".2f"),
    "Profit Margin":          ("📈", "%",              ".1f"),
    "Net Income":             ("💰", "$/ha",           ",.0f"),
    "Production Cost":        ("💸", "$/ha",           ",.0f"),
    "Straw Value":            ("🌿", "$/ha",           ",.0f"),
    "Water Reliability":      ("💧", "%",              ".1f"),
    "Biodiversity":           ("🦋", "index",          ".3f"),
    "Resilient Varieties":    ("🌱", "%",              ".1f"),
    "Labor Intensity":        ("👷", "hours/ha", ".1f"),
    "Flood Stress":           ("🌊", "index",          ".3f"),
    "Drought Stress":         ("☀️",  "index",          ".3f"),
    "Salinity Stress":        ("🧂", "index",          ".3f"),
}


# ── Shared helper functions ───────────────────────────────────────────────────

def _resolve_dimension(raw: str) -> str | None:
    """Map a free-text dimension phrase → DataFrame column name, or None."""
    raw = raw.strip().lower()
    # Check longer keys first
    for key in sorted(DIMENSION_MAP, key=len, reverse=True):
        if key in raw:
            return DIMENSION_MAP[key]
    return None


def _resolve_metrics(raw: str) -> list[str]:
    """Map a free-text metric phrase → deduplicated list of DataFrame column names.

    - "all" / "all metrics" / "everything"  → DEFAULT_METRICS
    - Otherwise match any keyword in METRIC_MAP; fall back to DEFAULT_METRICS.
    - Longer keywords are checked first to avoid "salinity" swallowing "salinity stress".
    """
    raw = raw.strip().lower()
    if any(word in raw for word in ("all", "everything", "every metric")):
        return list(DEFAULT_METRICS)

    seen, cols = set(), []
    for key in sorted(METRIC_MAP, key=len, reverse=True):
        if key in raw:
            col = METRIC_MAP[key]
            if col not in seen:
                seen.add(col)
                cols.append(col)

    return cols if cols else list(DEFAULT_METRICS)


def _resolve_metric_single(raw: str) -> str | None:
    """Map a raw metric string to a single DataFrame column name or None."""
    raw = raw.strip().lower()
    for key in sorted(METRIC_MAP, key=len, reverse=True):
        if key in raw:
            return METRIC_MAP[key]
    return None


def _fmt_val(val: float, fmt: str) -> str:
    """Format a numeric value with the given format spec."""
    try:
        return format(val, fmt)
    except (ValueError, TypeError):
        return str(val)


def _format_predictions(preds: dict) -> str:
    """Render a predictions dict (from run_agricultural_simulation) into labelled lines."""
    lines = []
    for col, (icon, unit, fmt) in PRED_KEY_LABELS.items():
        if col in preds:
            val = preds[col]
            lines.append(f"  {icon} {col}: {_fmt_val(val, fmt)} {unit}")
    return "\n".join(lines)


def _format_agg_summary(result: dict) -> str:
    """Render get_aggregated_metrics() result into labelled lines."""
    lines = [f"Historical statistics from {result.get('total_records', 0)} records:"]
    for key, (label, icon, unit) in AGG_KEY_LABELS.items():
        if key in result:
            val = result[key]
            # dollar values with comma, percentages/indices with 2dp
            if unit in ("$/ha",):
                lines.append(f"  {icon} {label}: ${val:,.0f} {unit.replace('$/ha', '/ha')}")
            elif unit in ("%", "index", "person-days/ha", "days", "ppt", "t/ha", "kg/ha", "kg CO₂e/t", "m³/ha"):
                lines.append(f"  {icon} {label}: {val:.2f} {unit}")
            else:
                lines.append(f"  {icon} {label}: {val}")
    return "\n".join(lines)


# ── Agent base class ──────────────────────────────────────────────────────────

class Agent:
    def __init__(self, name: str, role: str, description: str):
        self.name = name
        self.role = role
        self.description = description

    def execute(self, task: str, **kwargs) -> dict:
        raise NotImplementedError("Agents must implement execute method.")


# ── AggregationAgent ──────────────────────────────────────────────────────────

class AggregationAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agricultural Statistics Analyst",
            role="Data Aggregation & Scenario Comparison",
            description=(
                "Aggregates all performance metrics (yield, emissions, water reliability, "
                "biodiversity, labor, stress indices, financials) across climate, seasons, "
                "scenarios, and resource scenarios."
            )
        )

    def execute(self, task: str, **kwargs) -> dict:
        filters   = kwargs.get("filters",   {})
        dimension = kwargs.get("dimension")      # e.g. "Climate Type"
        metrics   = kwargs.get("metrics")        # e.g. ["Avg Yield", "Methane Emissions"]

        summary = get_aggregated_metrics(filters)

        global data
        if data is None or data.empty:
            return summary

        # ── Structured Compare X by Y path ───────────────────────────────────
        if dimension:
            temp_col = None
            if dimension not in data.columns:
                if dimension == "Year" and "datetime" in data.columns:
                    data["Year"] = data["datetime"].dt.year.dropna().astype(int).astype(str)
                    temp_col = "Year"
                else:
                    summary["compare_error"] = f"Column '{dimension}' not found in dataset."
                    return summary

            # Apply filters to the dataframe before grouping
            filtered_data = data
            for col, val in filters.items():
                if col in filtered_data.columns and val:
                    filtered_data = filtered_data[filtered_data[col] == val]

            # Use requested metrics; fall back to DEFAULT_METRICS; filter to existing cols only
            requested = metrics if metrics else list(DEFAULT_METRICS)
            cols_to_group = [c for c in requested if c in filtered_data.columns]

            if not cols_to_group:
                summary["compare_error"] = "None of the requested metric columns exist in the dataset."
                if temp_col:
                    data.drop(columns=[temp_col], inplace=True)
                return summary

            if filtered_data.empty:
                breakdown = {}
            else:
                breakdown = (
                    filtered_data.groupby(dimension)[cols_to_group]
                    .mean()
                    .round(3)
                    .to_dict(orient="index")
                )
            summary["compare_dimension"] = dimension
            summary["compare_metrics"]   = cols_to_group
            summary["compare_breakdown"] = breakdown

            if temp_col:
                data.drop(columns=[temp_col], inplace=True)
            return summary

        # ── Legacy keyword-based breakdown (backward-compatible) ─────────────
        breakdown_cols = [c for c in DEFAULT_METRICS if c in data.columns]

        if "by climate" in task.lower() or "climate" in task.lower():
            summary["climate_breakdown"] = (
                data.groupby("Climate Type")[breakdown_cols].mean().round(3).to_dict(orient="index")
            )
        if "by season" in task.lower() or "season" in task.lower():
            summary["season_breakdown"] = (
                data.groupby("Season Type")[breakdown_cols].mean().round(3).to_dict(orient="index")
            )
        if "by scenario" in task.lower() or "scenario" in task.lower():
            summary["scenario_breakdown"] = (
                data.groupby("Scenario Group")[breakdown_cols].mean().round(3).to_dict(orient="index")
            )

        return summary


# ── ModelingAgent ─────────────────────────────────────────────────────────────
class TaskType(Enum):
    SIMULATE     = "simulate"
    OPTIMIZE_RES = "optimize_resource"
    OPTIMIZE     = "optimize"
    UNKNOWN      = "unknown"

def _classify(task: str) -> TaskType:
    t = task.lower()
    if "optimize_resource" in t:
        return TaskType.OPTIMIZE_RES
    if "optimize" in t:
        return TaskType.OPTIMIZE
    if any(kw in t for kw in ("simulate", "run", "predict")):
        return TaskType.SIMULATE
    return TaskType.UNKNOWN
class ModelingAgent(Agent):
    AWD_OPTIONS = ["With AWD", "Without AWD"]
    FERT_GRID   = [50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0]
    WATER_GRID  = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0]
    PEST_GRID   = [1.0, 3.0, 5.0, 7.0, 10.0, 13.0, 15.0]
    SAL_GRID    = [0.001, 0.005, 0.01, 0.02, 0.03, 0.05]

    def __init__(self):                          # ← thêm lại
        super().__init__(
            name="Agricultural Yield & Emission Predictor",
            role="Predictive Modeling & Resource Optimizer",
            description=(
                "Simulates crop outcomes across all indicators and optimizes "
                "water/fertilizer/pesticide/salinity/AWD inputs to meet user-defined targets."
            )
        )

    def _build_combos(self, resources: list, fixed: dict) -> list[tuple]:
        awd  = self.AWD_OPTIONS if "awd"        in resources else [fixed.get("awd_adoption",     "With AWD")]
        fert = self.FERT_GRID   if "fertilizer" in resources else [fixed.get("fertilizer_usage", 100.0)]
        pest = self.PEST_GRID   if "pesticide"  in resources else [fixed.get("pesticide_usage",    5.0)]
        water= self.WATER_GRID  if "water"      in resources else [fixed.get("water_usage",       600.0)]
        sal  = self.SAL_GRID    if "salinity"   in resources else [fixed.get("salinity_exposure",  0.01)]
        return list(itertools.product(awd, fert, pest, water, sal))

    def _best_from_combos(self, combos: list[tuple], target_methane: float) -> tuple[dict, float]:
        preds    = run_agricultural_simulation(combos)
        scores   = _score_batch(preds, target_methane)
        best_idx = int(np.argmax(scores))
        best_combo = combos[best_idx]
        return {
            "inputs": {
                "AWD Adoption":      best_combo[0],
                "Fertilizer Usage":  best_combo[1],
                "Water Usage":       best_combo[3],
                "Pesticide Usage":   best_combo[2],
                "Salinity Exposure": best_combo[4],
            },
            "predictions": preds[best_idx],
        }, float(scores[best_idx])

    def execute(self, task: str, **kwargs) -> dict:
        match _classify(task):

            case TaskType.SIMULATE:
                combo = [(
                    kwargs.get("awd_adoption",     "With AWD"),
                    kwargs.get("fertilizer_usage", 100.0),
                    kwargs.get("pesticide_usage",    5.0),   # index 2
                    kwargs.get("water_usage",       600.0),  # index 3
                    kwargs.get("salinity_exposure",  0.01),  # index 4
                )]
                preds = run_agricultural_simulation(combo)
                return {
                    "inputs": {
                        "AWD Adoption":      combo[0][0],
                        "Fertilizer Usage":  combo[0][1],
                        "Pesticide Usage":   combo[0][2],
                        "Water Usage":       combo[0][3],
                        "Salinity Exposure": combo[0][4],
                    },
                    "predictions": preds[0],
                }

            case TaskType.OPTIMIZE_RES:
                resources      = kwargs.get("resources", [])
                fixed          = kwargs.get("fixed_inputs", {})
                target_methane = kwargs.get("target_methane", 500.0)
                combos         = self._build_combos(resources, fixed)
                best_sim, best_score = self._best_from_combos(combos, target_methane)
                label = " + ".join(r.title() for r in resources) or "All Inputs"
                return {
                    "optimization_target": f"Optimal {label} (Methane ceiling: {target_methane} kg/ha)",
                    "best_score":          best_score,
                    "optimized_inputs":    best_sim["inputs"],
                    "expected_outcomes":   best_sim["predictions"],
                }

            case TaskType.OPTIMIZE:
                target_methane = kwargs.get("target_methane", 200.0)
                fixed = {
                    "pesticide_usage":   kwargs.get("pesticide_usage",   5.0),
                    "salinity_exposure": kwargs.get("salinity_exposure", 0.01),
                }
                combos = self._build_combos(["awd", "fertilizer", "water"], fixed)
                best_sim, best_score = self._best_from_combos(combos, target_methane)
                return {
                    "optimization_target": f"Maximize performance with Methane Emissions <= {target_methane}",
                    "best_score":          best_score,
                    "optimized_inputs":    best_sim["inputs"],
                    "expected_outcomes":   best_sim["predictions"],
                }

            case _:
                return {"error": f"Task '{task}' not supported by {self.name}."}
# ── AgentOrchestrator ─────────────────────────────────────────────────────────

class AgentOrchestrator:
    def __init__(self):
        self.agg_agent   = AggregationAgent()
        self.model_agent = ModelingAgent()

    # ── Formatting helpers ────────────────────────────────────────────────────

    def _format_compare_text(self, result: dict) -> str:
        """Render compare_breakdown into a readable per-group report."""
        dimension = result.get("compare_dimension", "Group")
        metrics   = result.get("compare_metrics", [])
        breakdown = result.get("compare_breakdown", {})

        if not breakdown:
            return f"No data found to compare by {dimension}."

        lines = [f"Comparison by {dimension} ({result.get('total_records', 0)} records):", ""]
        for group, values in sorted(breakdown.items()):
            lines.append(f"▸ {group}")
            for metric in metrics:
                if metric in values:
                    icon, unit = METRIC_LABELS.get(metric, ("•", ""))
                    val = values[metric]
                    fmt = f"{val:,.0f}" if unit == "$/ha" else f"{val:.3f}"
                    lines.append(f"  {icon} {metric}: {fmt} {unit}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _format_inputs(self, inputs: dict) -> str:
        """Render simulation/optimization input parameters."""
        return (
            f"  • AWD Adoption:      {inputs.get('AWD Adoption', '-')}\n"
            f"  • Fertilizer:        {inputs.get('Fertilizer Usage', '-')} kg/ha\n"
            f"  • Water:             {inputs.get('Water Usage', '-')} m³/ha\n"
            f"  • Pesticide:         {inputs.get('Pesticide Usage', '-')} kg/ha\n"
            f"  • Salinity Exposure: {inputs.get('Salinity Exposure', 0) * 100:.3f}%"
        )

    def _format_agg_breakdown(self, result: dict) -> str:
        """Append legacy breakdown sections (climate / season / scenario)."""
        extra = ""
        sections = [
            ("climate_breakdown",  "Climate"),
            ("season_breakdown",   "Season"),
            ("scenario_breakdown", "Scenario"),
        ]
        for key, label in sections:
            if key in result:
                extra += f"\n\n{label} Breakdown:"
                for group, vals in result[key].items():
                    parts = []
                    for col in DEFAULT_METRICS:
                        if col in vals:
                            icon, unit = METRIC_LABELS.get(col, ("•", ""))
                            parts.append(f"{icon} {col}: {vals[col]:.2f} {unit}")
                    extra += f"\n▸ {group}\n  " + "\n  ".join(parts)
        return extra

    # ── Main router ───────────────────────────────────────────────────────────

    def process_query(self, query: str, context: dict = None) -> dict:
        query_lower = query.lower().strip()
        context     = context or {}

        # ── 0. Compare X by Y ─────────────────────────────────────────────────
        # Patterns:
        #   "Compare yield by climate"
        #   "Compare yield and profit by scenario"
        #   "Compare methane and water reliability by season in BAU"
        #   "Compare all metrics by AWD"
        compare_match = re.search(
            r'\bcompare\b\s+(.+?)\s+\bby\b\s+(.+?)(?:\s+\bin\b\s+(.+))?$',
            query_lower
        )
        if compare_match:
            raw_metrics   = compare_match.group(1)   # e.g. "yield and profit"
            raw_dimension = compare_match.group(2)   # e.g. "climate"
            raw_filter    = compare_match.group(3)   # e.g. "BAU" (optional)

            dimension = _resolve_dimension(raw_dimension)
            metrics   = _resolve_metrics(raw_metrics)

            if not dimension:
                available = ", ".join(DIMENSION_MAP.keys())
                return {
                    "agent":  self.agg_agent.name,
                    "role":   self.agg_agent.role,
                    "result": {"error": f"Unknown dimension '{raw_dimension}'."},
                    "text":   (
                        f"I don't recognise '{raw_dimension}' as a grouping dimension.\n"
                        f"Available options: {available}."
                    ),
                }

            filters = dict(context.get("filters", {}))
            if raw_filter:
                scenarios_info = get_scenarios()
                for key, options in scenarios_info.items():
                    col_name = key.replace("_", " ").title()
                    if col_name == "Scenario Groups":
                        col_name = "Scenario Group"
                    elif col_name == "Awd Options":
                        col_name = "AWD Adoption"
                    for opt in options:
                        if opt.lower() in raw_filter:
                            filters[col_name] = opt

            result = self.agg_agent.execute(
                query, filters=filters, dimension=dimension, metrics=metrics
            )
            return {
                "agent":  self.agg_agent.name,
                "role":   self.agg_agent.role,
                "result": result,
                "text":   self._format_compare_text(result),
            }

        # ── Time-based queries ────────────────────────────────────────────────
        # Pattern C.2: "average [metric] in [year]"
        # e.g., "average yield in 2026", "average water in 2025"
        year_match = re.search(
            r'average\s+(.+?)\s+in\s+(\d{4})',
            query_lower
        )
        if year_match:
            raw_metric = year_match.group(1).strip()
            year_str   = year_match.group(2).strip()
            metric = _resolve_metric_single(raw_metric)
            if metric and data is not None and not data.empty:
                year = int(year_str)
                mask = (data["datetime"].dt.year == year)
                subset = data[mask]
                if subset.empty:
                    text = f"No historical records found for year {year}."
                    mean_val = None
                else:
                    mean_val = float(subset[metric].mean())
                    icon, unit = METRIC_LABELS.get(metric, ("•", ""))
                    fmt = f"{mean_val:,.2f}" if unit == "$/ha" else f"{mean_val:.3f}"
                    text = (
                        f"The average **{metric}** in the year **{year}** "
                        f"(based on {len(subset)} records) is **{icon} {fmt} {unit}**."
                    )
                return {
                    "agent": self.agg_agent.name,
                    "role":  self.agg_agent.role,
                    "result": {"average": mean_val, "records_count": len(subset)},
                    "text":  text
                }


        # ── 1. Specific Agricultural Queries / Insights ──────────────────────
        # Pattern A: "Which scenario has the highest/lowest/best/worst [metric]?" or "What is the best scenario for [metric]?"
        best_worst_match = re.search(
            r'\b(highest|lowest|best|worst|maximum|minimum|max|min)\b\s+(?:scenario\s+(?:for|with|of)\s+)?(.+)',
            query_lower
        )
        if best_worst_match:
            op = best_worst_match.group(1)
            raw_metric = best_worst_match.group(2).strip("? ")
            metric = _resolve_metric_single(raw_metric)
            if metric and data is not None and not data.empty:
                is_lower_better = any(kw in metric.lower() for kw in ["methane", "emission", "intensity", "cost", "pesticide", "stress", "salinity"])
                
                if op in ["highest", "maximum", "max"] or (op == "best" and not is_lower_better) or (op == "worst" and is_lower_better):
                    idx = data[metric].idxmax()
                else:
                    idx = data[metric].idxmin()
                
                row = data.loc[idx]
                val = row[metric]
                icon, unit = METRIC_LABELS.get(metric, ("•", ""))
                fmt = f"{val:,.0f}" if unit == "$/ha" else f"{val:.3f}"
                
                text = (
                    f"The scenario with the {op} {metric} is **{row['Scenario Name']}** "
                    f"(Group: {row['Scenario Group']}, Climate: {row['Climate Type']}, Season: {row['Season Type']}).\n"
                    f"  {icon} {metric}: **{fmt} {unit}**\n\n"
                    f"Other key metrics for this scenario:\n"
                    f"  🌾 Avg Yield: {row.get('Avg Yield', '-')} t/ha\n"
                    f"  💨 Methane Emissions: {row.get('Methane Emissions', '-')} kg CH4/ha\n"
                    f"  💰 Net Income: {row.get('Net Income', '-')} $/ha\n"
                    f"  📈 Profit Margin: {row.get('Profit Margin', '-')} %"
                )
                return {
                    "agent": self.agg_agent.name,
                    "role": self.agg_agent.role,
                    "result": row.to_dict(),
                    "text": text
                }

        # Pattern B: "Scenarios with [metric] above/below/greater than/less than [value]"
        threshold_match = re.search(
            r'(?:scenarios|scenario)\s+with\s+(.+?)\s*(?:greater than|above|>|more than|less than|below|<|under)\s*([\d.]+)',
            query_lower
        )
        if threshold_match:
            raw_metric = threshold_match.group(1).strip()
            val_str = threshold_match.group(2)
            metric = _resolve_metric_single(raw_metric)
            if metric and data is not None and not data.empty:
                val = float(val_str)
                is_greater = any(kw in query_lower for kw in ["greater", "above", ">", "more"])
                
                if is_greater:
                    filtered_df = data[data[metric] > val]
                    comparison_str = f"greater than {val}"
                else:
                    filtered_df = data[data[metric] < val]
                    comparison_str = f"less than {val}"
                
                if filtered_df.empty:
                    text = f"No scenarios found with {metric} {comparison_str}."
                    result_list = []
                else:
                    if any(kw in metric.lower() for kw in ["methane", "emission", "intensity", "cost", "pesticide", "stress", "salinity"]):
                        sorted_df = filtered_df.sort_values(by=metric, ascending=True)
                    else:
                        sorted_df = filtered_df.sort_values(by=metric, ascending=False)
                    
                    top_5 = sorted_df.head(5)
                    icon, unit = METRIC_LABELS.get(metric, ("•", ""))
                    
                    lines = [f"Found {len(filtered_df)} scenarios with {metric} {comparison_str}. Here are the top 5:", ""]
                    for _, row in top_5.iterrows():
                        v_val = row[metric]
                        fmt = f"{v_val:,.0f}" if unit == "$/ha" else f"{v_val:.3f}"
                        lines.append(f"▸ **{row['Scenario Name']}** (Group: {row['Scenario Group']}): {icon} {metric} = {fmt} {unit}")
                    text = "\n".join(lines)
                    result_list = top_5.to_dict(orient="records")
                
                return {
                    "agent": self.agg_agent.name,
                    "role": self.agg_agent.role,
                    "result": {"scenarios": result_list, "total_found": len(filtered_df)},
                    "text": text
                }

        # ── 2. Simulation ─────────────────────────────────────────────────────
        elif (
            "simulate" in query_lower or "predict" in query_lower
            or "run" in query_lower or "forecast" in query_lower
        ):
            awd_match = re.search(r'(with awd|without awd)', query_lower)
            awd       = awd_match.group(1).title() if awd_match else context.get("awd_adoption", "With AWD")

            fert_m = re.search(r'fertilizer\s*[:=]?\s*(\d+)', query_lower)
            fert   = float(fert_m.group(1)) if fert_m else context.get("fertilizer_usage", 100.0)

            water_m = re.search(r'water\s*[:=]?\s*(\d+)', query_lower)
            water   = float(water_m.group(1)) if water_m else context.get("water_usage", 600.0)

            pest_m = re.search(r'pesticide\s*[:=]?\s*(\d+)', query_lower)
            pest   = float(pest_m.group(1)) if pest_m else context.get("pesticide_usage", 5.0)

            sal_m = re.search(r'salinity\s*[:=]?\s*([\d.]+)', query_lower)
            sal   = float(sal_m.group(1)) if sal_m else context.get("salinity_exposure", 0.01)

            result = self.model_agent.execute(
                "simulate",
                awd_adoption=awd, fertilizer_usage=fert,
                pesticide_usage=pest, water_usage=water, salinity_exposure=sal,
            )

            inputs = result["inputs"]
            preds  = result["predictions"]
            text_desc = (
                f"Simulation Inputs:\n{self._format_inputs(inputs)}\n\n"
                f"Predicted Outcomes:\n{_format_predictions(preds)}"
            )
            return {
                "agent":  self.model_agent.name,
                "role":   self.model_agent.role,
                "result": result,
                "text":   text_desc,
            }

        # ── 3. Optimization ───────────────────────────────────────────────────
        elif "optimize" in query_lower:
            resource_keywords = {
                "water": "water", "fertilizer": "fertilizer",
                "pesticide": "pesticide", "salinity": "salinity", "awd": "awd",
            }
            resources_to_optimize = [
                res for kw, res in resource_keywords.items() if kw in query_lower
            ]
            has_methane_target = bool(re.search(r'methane', query_lower))

            # ── Case A: specific resources, no methane ceiling ────────────────
            if resources_to_optimize and not has_methane_target:
                methane_m      = re.search(r'methane\s*(?:below|under|<=|less than)?\s*(\d+)', query_lower)
                target_methane = float(methane_m.group(1)) if methane_m else 500.0

                fixed_inputs = {
                    "awd_adoption":      context.get("awd_adoption",      "With AWD"),
                    "fertilizer_usage":  context.get("fertilizer_usage",  100.0),
                    "water_usage":       context.get("water_usage",       600.0),
                    "pesticide_usage":   context.get("pesticide_usage",   5.0),
                    "salinity_exposure": context.get("salinity_exposure", 0.01),
                }
                for param, key in [("water", "water_usage"), ("fertilizer", "fertilizer_usage"), ("pesticide", "pesticide_usage")]:
                    if param not in resources_to_optimize:
                        m = re.search(rf'{param}\s*(?:equal|to|=|at|:)?\s*(\d+)', query_lower)
                        if m:
                            fixed_inputs[key] = float(m.group(1))

                result = self.model_agent.execute(
                    "optimize_resource",
                    resources=resources_to_optimize,
                    fixed_inputs=fixed_inputs,
                    target_methane=target_methane,
                )

                inputs = result.get("optimized_inputs", {})
                preds  = result.get("expected_outcomes", {})
                label  = " + ".join(r.title() for r in resources_to_optimize)

                if inputs:
                    text_desc = (
                        f"Optimal {label} Settings:\n{self._format_inputs(inputs)}\n\n"
                        f"Expected Outcomes:\n{_format_predictions(preds)}"
                    )
                else:
                    text_desc = f"Could not find an optimal {label} configuration."

                return {
                    "agent":  self.model_agent.name,
                    "role":   self.model_agent.role,
                    "result": result,
                    "text":   text_desc,
                }

            # ── Case B: methane-ceiling optimization over all inputs ──────────
            methane_m      = re.search(r'methane\s*(?:below|under|<=|less than|equal|to|at)?\s*(\d+)', query_lower)
            target_methane = float(methane_m.group(1)) if methane_m else context.get("target_methane", 200.0)
            pest_val       = context.get("pesticide_usage",  5.0)
            sal_val        = context.get("salinity_exposure", 0.01)

            result = self.model_agent.execute(
                "optimize",
                target_methane=target_methane,
                pesticide_usage=pest_val,
                salinity_exposure=sal_val,
            )

            inputs = result.get("optimized_inputs", {})
            preds  = result.get("expected_outcomes", {})

            if inputs:
                text_desc = (
                    f"Optimized for Methane ≤ {target_methane} kg/ha:\n"
                    f"{self._format_inputs(inputs)}\n\n"
                    f"Expected Outcomes:\n{_format_predictions(preds)}"
                )
            else:
                text_desc = f"Could not find an allocation meeting Methane ≤ {target_methane} kg/ha."

            return {
                "agent":  self.model_agent.name,
                "role":   self.model_agent.role,
                "result": result,
                "text":   text_desc,
            }

        # ── 4. Default: aggregation / stats ───────────────────────────────────
        else:
            filters = dict(context.get("filters", {}))
            scenarios_info = get_scenarios()

            for key, options in scenarios_info.items():
                col_name = key.replace("_", " ").title()
                if col_name == "Scenario Groups":
                    col_name = "Scenario Group"
                elif col_name == "Awd Options":
                    col_name = "AWD Adoption"
                for opt in options:
                    if opt.lower() in query_lower:
                        filters[col_name] = opt

            result = self.agg_agent.execute(query, filters=filters)

            if "status" in result and result["status"] == "empty":
                text_desc = result.get("message", "No matching historical records found.")
            else:
                text_desc = _format_agg_summary(result)
                text_desc += self._format_agg_breakdown(result)

            return {
                "agent":  self.agg_agent.name,
                "role":   self.agg_agent.role,
                "result": result,
                "text":   text_desc,
            }


# ── Quick smoke-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    orchestrator = AgentOrchestrator()

    print("── Compare tests ──")
    print(orchestrator.process_query("Compare yield by climate")["text"])
    print(orchestrator.process_query("Compare yield and profit by scenario")["text"])
    print(orchestrator.process_query("Compare methane and water reliability by season")["text"])
    print(orchestrator.process_query("Compare all metrics by AWD")["text"])
    print(orchestrator.process_query("Compare biodiversity and labor by resource in BAU")["text"])

    print("\n── Aggregation test ──")
    print(orchestrator.process_query("Give me a summary of Business As Usual scenario")["text"])

    print("\n── Simulation test ──")
    print(orchestrator.process_query("Simulate with AWD adoption With AWD and fertilizer 120 and water 750")["text"])

    print("\n── Optimization tests ──")
    print(orchestrator.process_query("Optimize inputs for methane below 180")["text"])
    print(orchestrator.process_query("Optimize water and fertilizer")["text"])