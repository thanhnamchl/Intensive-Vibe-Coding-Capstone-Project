import re
from mcp_server import get_aggregated_metrics, run_agricultural_simulation, get_scenarios, data

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


# ── DataCleaningAgent ─────────────────────────────────────────────────────────

class DataCleaningAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agronomist Data Cleaner",
            role="Data Standardization & Quality Audit",
            description="Audits raw CSV data, fixes column naming inconsistencies, handles null values, and converts types."
        )

    def execute(self, task: str, **kwargs) -> dict:
        if "clean" in task.lower() or "standardize" in task.lower():
            file_content = kwargs.get("file_content")
            file_path    = kwargs.get("file_path")
            if not file_content and file_path:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                except Exception as e:
                    return {"error": f"Failed to read file at {file_path}: {str(e)}"}
            if not file_content:
                return {"error": "Missing file_content or file_path parameter for cleaning."}
            from mcp_server import clean_and_standardize_csv
            return clean_and_standardize_csv(file_content)
        return {"error": f"Task '{task}' not supported by {self.name}."}


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
            if dimension not in data.columns:
                summary["compare_error"] = f"Column '{dimension}' not found in dataset."
                return summary

            # Use requested metrics; fall back to DEFAULT_METRICS; filter to existing cols only
            requested = metrics if metrics else list(DEFAULT_METRICS)
            cols_to_group = [c for c in requested if c in data.columns]

            if not cols_to_group:
                summary["compare_error"] = "None of the requested metric columns exist in the dataset."
                return summary

            breakdown = (
                data.groupby(dimension)[cols_to_group]
                .mean()
                .round(3)
                .to_dict(orient="index")
            )
            summary["compare_dimension"] = dimension
            summary["compare_metrics"]   = cols_to_group
            summary["compare_breakdown"] = breakdown
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

class ModelingAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agricultural Yield & Emission Predictor",
            role="Predictive Modeling & Resource Optimizer",
            description=(
                "Simulates crop outcomes across all indicators (yield, methane, emission intensity, "
                "profit, water reliability, biodiversity, labor, stress indices) and optimizes "
                "water/fertilizer/pesticide/salinity/AWD inputs to meet user-defined targets."
            )
        )

    def _score_sim(self, pred: dict, target_methane: float) -> float:
        """Score = maximize yield + profit, penalize methane overage."""
        score = pred.get("Avg Yield", 0) * 2.0 + pred.get("Profit Margin", 0)
        if pred.get("Methane Emissions", 0) > target_methane:
            score -= (pred["Methane Emissions"] - target_methane) * 10.0
        return score

    def execute(self, task: str, **kwargs) -> dict:
        task_lower = task.lower()

        # ── Simulation ────────────────────────────────────────────────────────
        if "simulate" in task_lower or "run" in task_lower or "predict" in task_lower:
            return run_agricultural_simulation(
                awd_adoption      = kwargs.get("awd_adoption",      "With AWD"),
                fertilizer_usage  = kwargs.get("fertilizer_usage",  100.0),
                pesticide_usage   = kwargs.get("pesticide_usage",   5.0),
                water_usage       = kwargs.get("water_usage",       600.0),
                salinity_exposure = kwargs.get("salinity_exposure", 0.01),
            )

        # ── Resource-specific optimization ────────────────────────────────────
        elif "optimize_resource" in task_lower:
            resources      = kwargs.get("resources", [])
            fixed          = kwargs.get("fixed_inputs", {})
            target_methane = kwargs.get("target_methane", 500.0)

            awd_options  = ["With AWD", "Without AWD"]
            fert_grid    = [50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0]
            water_grid   = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0]
            pest_grid    = [1.0, 3.0, 5.0, 7.0, 10.0, 13.0, 15.0]
            sal_grid     = [0.001, 0.005, 0.01, 0.02, 0.03, 0.05]

            awd_search   = awd_options if "awd"        in resources else [fixed.get("awd_adoption",    "With AWD")]
            fert_search  = fert_grid   if "fertilizer" in resources else [fixed.get("fertilizer_usage", 100.0)]
            water_search = water_grid  if "water"      in resources else [fixed.get("water_usage",      600.0)]
            pest_search  = pest_grid   if "pesticide"  in resources else [fixed.get("pesticide_usage",    5.0)]
            sal_search   = sal_grid    if "salinity"   in resources else [fixed.get("salinity_exposure",  0.01)]

            best_sim, best_score = None, -float("inf")
            for awd_val in awd_search:
                for fert_val in fert_search:
                    for water_val in water_search:
                        for pest_val in pest_search:
                            for sal_val in sal_search:
                                sim = run_agricultural_simulation(
                                    awd_adoption=awd_val, fertilizer_usage=fert_val,
                                    pesticide_usage=pest_val, water_usage=water_val,
                                    salinity_exposure=sal_val,
                                )
                                sc = self._score_sim(sim["predictions"], target_methane)
                                if sc > best_score:
                                    best_score, best_sim = sc, sim

            label = " + ".join(r.title() for r in resources) if resources else "All Inputs"
            return {
                "optimization_target": f"Optimal {label} (Methane ceiling: {target_methane} kg/ha)",
                "best_score":          best_score,
                "optimized_inputs":    best_sim["inputs"]      if best_sim else {},
                "expected_outcomes":   best_sim["predictions"] if best_sim else {},
            }

        # ── Full methane-ceiling optimization ─────────────────────────────────
        elif "optimize" in task_lower:
            target_methane = kwargs.get("target_methane", 200.0)
            pest_val       = kwargs.get("pesticide_usage",   5.0)
            sal_val        = kwargs.get("salinity_exposure", 0.01)

            fert_grid  = [50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0]
            water_grid = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0]

            best_sim, best_score = None, -float("inf")
            for awd_option in ["With AWD", "Without AWD"]:
                for fert_val in fert_grid:
                    for water_val in water_grid:
                        sim = run_agricultural_simulation(
                            awd_adoption=awd_option, fertilizer_usage=fert_val,
                            pesticide_usage=pest_val, water_usage=water_val,
                            salinity_exposure=sal_val,
                        )
                        sc = self._score_sim(sim["predictions"], target_methane)
                        if sc > best_score:
                            best_score, best_sim = sc, sim

            return {
                "optimization_target": f"Maximize performance with Methane Emissions <= {target_methane}",
                "best_score":          best_score,
                "optimized_inputs":    best_sim["inputs"]      if best_sim else {},
                "expected_outcomes":   best_sim["predictions"] if best_sim else {},
            }

        return {"error": f"Task '{task}' not supported by {self.name}."}


# ── AgentOrchestrator ─────────────────────────────────────────────────────────

class AgentOrchestrator:
    def __init__(self):
        self.clean_agent = DataCleaningAgent()
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

        # ── 1. Cleaning & Ingestion ───────────────────────────────────────────
        if "clean" in query_lower or "standardize" in query_lower or "upload" in query_lower:
            return {
                "agent":  self.clean_agent.name,
                "role":   self.clean_agent.role,
                "result": self.clean_agent.execute("clean", **context),
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