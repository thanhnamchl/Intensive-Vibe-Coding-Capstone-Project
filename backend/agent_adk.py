import re
from mcp_server import get_aggregated_metrics, run_agricultural_simulation, get_scenarios, data

class Agent:
    def __init__(self, name: str, role: str, description: str):
        self.name = name
        self.role = role
        self.description = description

    def execute(self, task: str, **kwargs) -> dict:
        raise NotImplementedError("Agents must implement execute method.")

class DataCleaningAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agronomist Data Cleaner",
            role="Data Standardization & Quality Audit",
            description="Audits raw CSV data, fixes column naming inconsistencies, handles null values, and converts types."
        )

    def execute(self, task: str, **kwargs) -> dict:
        if "clean" in task.lower() or "standardize" in task.lower():
            # Support both direct CSV content and file path
            file_content = kwargs.get("file_content")
            file_path = kwargs.get("file_path")
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

class AggregationAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agricultural Statistics Analyst",
            role="Data Aggregation & Scenario Comparison",
            description="Aggregates performance metrics (yields, water reliability, emissions) across climate, seasons, and scenarios."
        )

    def execute(self, task: str, **kwargs) -> dict:
        filters = kwargs.get("filters", {})
        summary = get_aggregated_metrics(filters)
        
        # Additional statistics calculation for seasons/climates
        global data
        if data is not None and not data.empty:
            if "by climate" in task.lower() or "climate" in task.lower():
                climate_group = data.groupby('Climate Type')[['Avg Yield', 'Methane Emissions', 'Profit Margin']].mean().to_dict(orient='index')
                summary["climate_breakdown"] = climate_group
            if "by season" in task.lower() or "season" in task.lower():
                season_group = data.groupby('Season Type')[['Avg Yield', 'Methane Emissions', 'Profit Margin']].mean().to_dict(orient='index')
                summary["season_breakdown"] = season_group
            if "by scenario" in task.lower() or "scenario" in task.lower():
                scenario_group = data.groupby('Scenario Group')[['Avg Yield', 'Methane Emissions', 'Profit Margin']].mean().to_dict(orient='index')
                summary["scenario_breakdown"] = scenario_group
                
        return summary

class ModelingAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Agricultural Yield & Emission Predictor",
            role="Predictive Modeling & Resource Optimizer",
            description="Uses machine learning models to simulate crop outcomes and optimize water/fertilizer inputs to minimize emissions while maximizing profit."
        )

    def _score_sim(self, pred: dict, target_methane: float) -> float:
        """Compute optimization score: maximize yield + profit, penalize methane overage."""
        score = pred["Avg Yield"] * 2.0 + pred["Profit Margin"]
        if pred["Methane Emissions"] > target_methane:
            score -= (pred["Methane Emissions"] - target_methane) * 10.0
        return score

    def execute(self, task: str, **kwargs) -> dict:
        task_lower = task.lower()

        # ── Simulation ────────────────────────────────────────────────
        if "simulate" in task_lower or "run" in task_lower or "predict" in task_lower:
            awd = kwargs.get("awd_adoption", "With AWD")
            fert = kwargs.get("fertilizer_usage", 100.0)
            pest = kwargs.get("pesticide_usage", 5.0)
            water = kwargs.get("water_usage", 600.0)
            salinity = kwargs.get("salinity_exposure", 0.01)
            return run_agricultural_simulation(awd, fert, pest, water, salinity)

        # ── Resource-specific optimization ────────────────────────────
        elif "optimize_resource" in task_lower:
            # Which resources to search over, rest are fixed
            resources = kwargs.get("resources", [])          # list of resource names to optimize
            fixed = kwargs.get("fixed_inputs", {})           # fixed values for non-optimized inputs
            target_methane = kwargs.get("target_methane", 500.0)  # lenient ceiling unless specified

            awd_options  = ["With AWD", "Without AWD"]
            fert_grid    = [50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0]
            water_grid   = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0]
            pest_grid    = [1.0, 3.0, 5.0, 7.0, 10.0, 13.0, 15.0]
            sal_grid     = [0.001, 0.005, 0.01, 0.02, 0.03, 0.05]

            # Build search space for each resource
            awd_search  = awd_options if "awd" in resources else [fixed.get("awd_adoption", "With AWD")]
            fert_search = fert_grid   if "fertilizer" in resources else [fixed.get("fertilizer_usage", 100.0)]
            water_search = water_grid if "water" in resources       else [fixed.get("water_usage", 600.0)]
            pest_search = pest_grid   if "pesticide" in resources   else [fixed.get("pesticide_usage", 5.0)]
            sal_search  = sal_grid    if "salinity" in resources    else [fixed.get("salinity_exposure", 0.01)]

            best_sim = None
            best_score = -float('inf')

            for awd_val in awd_search:
                for fert_val in fert_search:
                    for water_val in water_search:
                        for pest_val in pest_search:
                            for sal_val in sal_search:
                                sim = run_agricultural_simulation(
                                    awd_adoption=awd_val,
                                    fertilizer_usage=fert_val,
                                    pesticide_usage=pest_val,
                                    water_usage=water_val,
                                    salinity_exposure=sal_val
                                )
                                sc = self._score_sim(sim["predictions"], target_methane)
                                if sc > best_score:
                                    best_score = sc
                                    best_sim = sim

            optimized_resources_label = " + ".join(r.title() for r in resources) if resources else "All Inputs"
            return {
                "optimization_target": f"Optimal {optimized_resources_label} (Methane ceiling: {target_methane} kg/ha)",
                "best_score": best_score,
                "optimized_inputs": best_sim["inputs"] if best_sim else {},
                "expected_outcomes": best_sim["predictions"] if best_sim else {}
            }

        # ── Methane-ceiling optimization (full grid) ───────────────────
        elif "optimize" in task_lower:
            target_methane = kwargs.get("target_methane", 200.0)
            pest_val  = kwargs.get("pesticide_usage", 5.0)
            sal_val   = kwargs.get("salinity_exposure", 0.01)

            fert_grid  = [50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0]
            water_grid = [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0, 1200.0]

            best_sim = None
            best_score = -float('inf')

            for awd_option in ["With AWD", "Without AWD"]:
                for fert_val in fert_grid:
                    for water_val in water_grid:
                        sim = run_agricultural_simulation(
                            awd_adoption=awd_option,
                            fertilizer_usage=fert_val,
                            pesticide_usage=pest_val,
                            water_usage=water_val,
                            salinity_exposure=sal_val
                        )
                        sc = self._score_sim(sim["predictions"], target_methane)
                        if sc > best_score:
                            best_score = sc
                            best_sim = sim

            return {
                "optimization_target": f"Maximize performance with Methane Emissions <= {target_methane}",
                "best_score": best_score,
                "optimized_inputs": best_sim["inputs"] if best_sim else {},
                "expected_outcomes": best_sim["predictions"] if best_sim else {}
            }

        return {"error": f"Task '{task}' not supported by {self.name}."}


class AgentOrchestrator:
    def __init__(self):
        self.clean_agent = DataCleaningAgent()
        self.agg_agent = AggregationAgent()
        self.model_agent = ModelingAgent()

    def process_query(self, query: str, context: dict = None) -> dict:
        """
        Processes standard natural language queries by delegating to the appropriate agents.
        """
        query_lower = query.lower()
        context = context or {}
        
        # 1. Cleaning & Ingestion
        if "clean" in query_lower or "standardize" in query_lower or "upload" in query_lower:
            return {
                "agent": self.clean_agent.name,
                "role": self.clean_agent.role,
                "result": self.clean_agent.execute("clean", **context)
            }
            
        # 2. Simulation and Optimization
        elif "simulate" in query_lower or "predict" in query_lower or "run" in query_lower or "forecast" in query_lower:
            # Parse parameters from query if possible, otherwise use context
            awd_match = re.search(r'(with awd|without awd)', query_lower)
            awd_adoption = awd_match.group(1).title() if awd_match else context.get("awd_adoption", "With AWD")
            
            fert_match = re.search(r'fertilizer\s*[:=]?\s*(\d+)', query_lower)
            fert = float(fert_match.group(1)) if fert_match else context.get("fertilizer_usage", 100.0)
            
            water_match = re.search(r'water\s*[:=]?\s*(\d+)', query_lower)
            water = float(water_match.group(1)) if water_match else context.get("water_usage", 600.0)
            
            pest_match = re.search(r'pesticide\s*[:=]?\s*(\d+)', query_lower)
            pest = float(pest_match.group(1)) if pest_match else context.get("pesticide_usage", 5.0)
            
            sal_match = re.search(r'salinity\s*[:=]?\s*([\d\.]+)', query_lower)
            sal = float(sal_match.group(1)) if sal_match else context.get("salinity_exposure", 0.01)
            
            result = self.model_agent.execute(
                "simulate",
                awd_adoption=awd_adoption,
                fertilizer_usage=fert,
                pesticide_usage=pest,
                water_usage=water,
                salinity_exposure=sal
            )
            
            inputs = result["inputs"]
            preds = result["predictions"]
            text_desc = (
                f"Simulated Outcomes:\n"
                f"• AWD Adoption: {inputs['AWD Adoption']}\n"
                f"• Fertilizer: {inputs['Fertilizer Usage']} kg/ha | Water: {inputs['Water Usage']} m³/ha\n"
                f"• Pesticides: {inputs['Pesticide Usage']} kg/ha | Salinity: {inputs['Salinity Exposure'] * 100:.2f}%\n\n"
                f"Predicted Metrics:\n"
                f"🌾 Average Yield: {preds['Avg Yield']:.2f} t/ha\n"
                f"💨 Methane Emissions: {preds['Methane Emissions']:.1f} kg/ha\n"
                f"📈 Profit Margin: {preds['Profit Margin']:.1f}%\n"
                f"💰 Net Income: ${preds['Net Income']:.0f}/ha"
            )
            return {
                "agent": self.model_agent.name,
                "role": self.model_agent.role,
                "result": result,
                "text": text_desc
            }
            
        elif "optimize" in query_lower:
            # ── Detect which resources the user wants to optimize ──────────────────────
            # Keywords map → resource name used by ModelingAgent
            resource_keywords = {
                "water": "water",
                "fertilizer": "fertilizer",
                "pesticide": "pesticide",
                "salinity": "salinity",
                "awd": "awd",
            }
            resources_to_optimize = [
                res for kw, res in resource_keywords.items()
                if kw in query_lower
            ]

            has_methane_target = bool(re.search(r'methane', query_lower))

            # ── Case 1: User mentions specific resources (e.g. "Optimize water inputs") ──
            if resources_to_optimize and not has_methane_target:
                # Parse any fixed inputs and/or a methane ceiling mentioned
                methane_match = re.search(r'methane\s*(?:below|under|<=|less than)?\s*(\d+)', query_lower)
                target_methane = float(methane_match.group(1)) if methane_match else 500.0  # lenient ceiling

                # Fixed inputs = values explicitly stated for non-optimized resources
                fixed_inputs = {
                    "awd_adoption": context.get("awd_adoption", "With AWD"),
                    "fertilizer_usage": context.get("fertilizer_usage", 100.0),
                    "water_usage": context.get("water_usage", 600.0),
                    "pesticide_usage": context.get("pesticide_usage", 5.0),
                    "salinity_exposure": context.get("salinity_exposure", 0.01),
                }
                # Override any fixed value if user stated it explicitly in the query
                if "water" not in resources_to_optimize:
                    wm = re.search(r'water\s*(?:equal|to|=|at|:)?\s*(\d+)', query_lower)
                    if wm:
                        fixed_inputs["water_usage"] = float(wm.group(1))
                if "fertilizer" not in resources_to_optimize:
                    fm = re.search(r'fertilizer\s*(?:equal|to|=|at|:)?\s*(\d+)', query_lower)
                    if fm:
                        fixed_inputs["fertilizer_usage"] = float(fm.group(1))
                if "pesticide" not in resources_to_optimize:
                    pm = re.search(r'pesticide\s*(?:equal|to|=|at|:)?\s*(\d+)', query_lower)
                    if pm:
                        fixed_inputs["pesticide_usage"] = float(pm.group(1))

                result = self.model_agent.execute(
                    "optimize_resource",
                    resources=resources_to_optimize,
                    fixed_inputs=fixed_inputs,
                    target_methane=target_methane
                )

                inputs = result["optimized_inputs"]
                preds = result["expected_outcomes"]
                resources_label = " + ".join(r.title() for r in resources_to_optimize)

                if inputs:
                    text_desc = (
                        f"Optimal {resources_label} Settings Found:\n"
                        f"• Best AWD Practice: {inputs['AWD Adoption']}\n"
                        f"• Optimal Fertilizer: {inputs['Fertilizer Usage']} kg/ha\n"
                        f"• Optimal Water Input: {inputs['Water Usage']} m³/ha\n"
                        f"• Pesticides: {inputs['Pesticide Usage']} kg/ha | Salinity: {inputs['Salinity Exposure'] * 100:.2f}%\n\n"
                        f"Expected Outcomes:\n"
                        f"🌾 Average Yield: {preds['Avg Yield']:.2f} t/ha\n"
                        f"💨 Methane Emissions: {preds['Methane Emissions']:.1f} kg/ha\n"
                        f"📈 Profit Margin: {preds['Profit Margin']:.1f}%\n"
                        f"💰 Net Income: ${preds['Net Income']:.0f}/ha"
                    )
                else:
                    text_desc = f"Could not find an optimal {resources_label} configuration."

                return {
                    "agent": self.model_agent.name,
                    "role": self.model_agent.role,
                    "result": result,
                    "text": text_desc
                }

            # ── Case 2: Methane-ceiling optimization (all inputs optimized) ────────────
            methane_match = re.search(r'methane\s*(?:below|under|<=|less than|equal|to|at)?\s*(\d+)', query_lower)
            if methane_match:
                target_methane = float(methane_match.group(1))
            else:
                target_methane = context.get("target_methane", 200.0)

            pest_val = context.get("pesticide_usage", 5.0)
            sal_val = context.get("salinity_exposure", 0.01)

            result = self.model_agent.execute(
                "optimize",
                target_methane=target_methane,
                pesticide_usage=pest_val,
                salinity_exposure=sal_val
            )

            inputs = result["optimized_inputs"]
            preds = result["expected_outcomes"]

            if inputs:
                text_desc = (
                    f"Optimized Scenario for Methane Target <= {target_methane} kg/ha:\n"
                    f"• Recommended practice: {inputs['AWD Adoption']}\n"
                    f"• Recommended Fertilizer: {inputs['Fertilizer Usage']} kg/ha\n"
                    f"• Recommended Water Input: {inputs['Water Usage']} m³/ha\n"
                    f"• Constraints - Pesticides: {inputs['Pesticide Usage']} kg/ha | Salinity: {inputs['Salinity Exposure'] * 100:.2f}%\n\n"
                    f"Expected Outcomes:\n"
                    f"🌾 Average Yield: {preds['Avg Yield']:.2f} t/ha\n"
                    f"💨 Methane Emissions: {preds['Methane Emissions']:.1f} kg/ha\n"
                    f"📈 Profit Margin: {preds['Profit Margin']:.1f}%\n"
                    f"💰 Net Income: ${preds['Net Income']:.0f}/ha"
                )
            else:
                text_desc = f"Could not find an optimal allocation meeting the target methane of {target_methane} kg/ha."

            return {
                "agent": self.model_agent.name,
                "role": self.model_agent.role,
                "result": result,
                "text": text_desc
            }

            
        # 3. Default to Aggregations and stats
        else:
            # Detect filters from query, preserving any passed in context
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
                text_desc = (
                    f"Calculated historical statistics from {result.get('total_records', 0)} matching records:\n"
                    f"🌾 Average Yield: {result.get('avg_yield', 0.0):.2f} t/ha\n"
                    f"💨 Methane Emissions: {result.get('avg_methane_emissions', 0.0):.1f} kg/ha\n"
                    f"📈 Profit Margin: {result.get('avg_profit_margin', 0.0):.1f}%\n"
                    f"💰 Net Income: ${result.get('avg_net_income', 0.0):.0f}/ha\n"
                    f"💧 Water Applied: {result.get('avg_water_usage', 0.0):.0f} m³/ha"
                )
                if "climate_breakdown" in result:
                    text_desc += "\n\nClimate Breakdown (Average Yield):"
                    for k, v in result["climate_breakdown"].items():
                        text_desc += f"\n• {k}: {v.get('Avg Yield', 0.0):.2f} t/ha"
                if "season_breakdown" in result:
                    text_desc += "\n\nSeason Breakdown (Average Yield):"
                    for k, v in result["season_breakdown"].items():
                        text_desc += f"\n• {k}: {v.get('Avg Yield', 0.0):.2f} t/ha"
                if "scenario_breakdown" in result:
                    text_desc += "\n\nScenario Breakdown (Average Yield):"
                    for k, v in result["scenario_breakdown"].items():
                        text_desc += f"\n• {k}: {v.get('Avg Yield', 0.0):.2f} t/ha"
                        
            return {
                "agent": self.agg_agent.name,
                "role": self.agg_agent.role,
                "result": result,
                "text": text_desc
            }

if __name__ == "__main__":
    # Test orchestrator
    orchestrator = AgentOrchestrator()
    print("Testing Aggregation:")
    print(orchestrator.process_query("Give me a summary of Business As Usual scenario"))
    print("\nTesting Simulation:")
    print(orchestrator.process_query("Simulate with AWD adoption With AWD and fertilizer 120 and water 750"))
    print("\nTesting Optimization:")
    print(orchestrator.process_query("Optimize inputs for methane below 180"))
