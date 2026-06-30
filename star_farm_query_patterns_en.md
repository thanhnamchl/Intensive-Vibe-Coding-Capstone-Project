# Sample Queries for STAR-FARM `AgentOrchestrator`

A list of query patterns that `process_query()` can recognize and handle, based on the regex patterns in `agents.py`.

## 1. Compare X by Y

- Compare yield by climate
- Compare yield and profit by scenario
- Compare methane and water reliability by season
- Compare all metrics by AWD
- Compare biodiversity and labor by resource in BAU

General syntax: `compare <metric(s)> by <dimension> [in <filter>]`

## 2. Average by Year

- average yield in 2026
- average water in 2025

General syntax: `average <metric> in <year>`

## 3. Highest / Lowest Scenario

- highest yield
- lowest methane
- best scenario for profit margin
- worst water reliability

General syntax: `<highest|lowest|best|worst|max|min> <metric>`

## 4. Threshold Filtering

- scenarios with yield greater than 5
- scenarios with methane below 200
- scenario with profit margin above 20

General syntax: `scenarios with <metric> <above|below|greater than|less than> <value>`

## 5. Simulation

- Simulate with AWD adoption With AWD and fertilizer 120 and water 750
- Predict yield with pesticide 10 and salinity 0.02
- Run simulation with water 600
- Forecast with fertilizer:150

Trigger keywords: `simulate`, `predict`, `run`, `forecast`
Optional parameters: `fertilizer`, `water`, `pesticide`, `salinity`, `with/without awd`

## 6. Optimization

**Optimize specific resources:**
- Optimize water and fertilizer
- Optimize pesticide for methane below 180

**Optimize all inputs under a methane ceiling:**
- Optimize inputs for methane below 180
- Optimize for methane equal to 150

Trigger keyword: `optimize` (combined with resource names: `water`, `fertilizer`, `pesticide`, `salinity`, `awd`)

## 7. Default: Aggregation / Summary

- Give me a summary of Business As Usual scenario
- Show stats for Wet season

Applied when a query doesn't match any of the patterns above. Any climate/season/scenario/AWD/resource names mentioned in the query are automatically applied as filters.

---

### Notes
- Patterns rely on regex, so they require the right structural keywords (`compare`, `by`, `highest/lowest/best/worst`, `simulate/predict/run/forecast`, `optimize`) to route correctly.
- Metric/dimension names are mapped via `METRIC_MAP` and `DIMENSION_MAP`, supporting several synonyms (e.g. "yield" → "Avg Yield", "methane"/"emission" → "Methane Emissions").
