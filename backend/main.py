"""
AI-Agent Backplane & API Server
Security hardened: rate limiting, security headers, CORS restriction,
Pydantic field validation, request-size guard, structured error responses.
All configuration is read from environment variables — no secrets in code.
"""
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from agent_adk import AgentOrchestrator
from mcp_server import mcp, get_scenarios, upload_simulation_csv, get_data_status, get_sample_csv

# ── Configuration from environment ───────────────────────────────────────────
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
RATE_LIMIT: str = os.getenv("RATE_LIMIT_PER_MIN", "60") + "/minute"

# Các path KHÔNG bị chặn bởi "chưa có dữ liệu" — phải luôn truy cập được
# để người dùng có thể upload CSV và kiểm tra trạng thái.
_DATA_GATE_EXEMPT_PATHS = {
    "/api/upload",
    "/api/data-status",
    "/api/sample-csv",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Agent Backplane & API Server",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Security headers ──────────────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'"
    )
    return response

# ── Data-gate middleware ──────────────────────────────────────────────────────
# Chặn mọi endpoint /api/* (trừ upload/data-status) cho tới khi có CSV hợp lệ
# đã được nạp vào mcp_server. Buộc frontend phải đưa người dùng qua màn hình
# upload trước khi vào được dashboard.
@app.middleware("http")
async def require_data_loaded(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in _DATA_GATE_EXEMPT_PATHS:
        status = get_data_status()
        if not status.get("data_loaded"):
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "code": "NO_DATA_LOADED",
                    "message": (
                        "Chưa có dữ liệu mô phỏng nào được nạp. "
                        "Vui lòng upload file CSV đúng template qua /api/upload trước."
                    ),
                    "required_columns": status.get("required_columns", []),
                },
            )
    return await call_next(request)

# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"[ERROR] Unhandled exception on {request.url.path}: {exc!r}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    optimization_paths = {
        "/api/optimize",
        "/api/optimize/resource",
    }

    if request.url.path in optimization_paths:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Cannot be optimized"
            },
        )

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
        },
    )
# ── Agent Orchestrator ────────────────────────────────────────────────────────
orchestrator = AgentOrchestrator()

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FilterRequest(BaseModel):
    """Filter for historical aggregation queries."""
    filters: dict = {}

class CompareRequest(BaseModel):
    """
    Structured Compare X by Y request.
    
    Example:
        { "metrics": ["Avg Yield", "Methane Emissions"], "dimension": "Climate Type" }
        { "metrics": ["Profit Margin"], "dimension": "Scenario Group", "filters": {"AWD Adoption": "With AWD"} }
    """
    metrics: list[str] = Field(
        default=[],
        description=(
            "List of column names to compare. Leave empty to use default metrics. "
            "Valid values: Avg Yield, Methane Emissions, Emission Intensity, Profit Margin, "
            "Net Income, Production Cost, Straw Value, Water Usage, Fertilizer Usage, "
            "Pesticide Usage, Salinity Exposure, Max Flood Continuous, Flood Stress, "
            "Drought Stress, Salinity Stress, Biodiversity, Resilient Varieties, "
            "Water Reliability, Labor Intensity."
        ),
    )
    dimension: str = Field(
        description=(
            "DataFrame column to group by. "
            "Valid values: Climate Type, Season Type, Scenario Group, Scenario Name, "
            "AWD Adoption, Resource Scenario."
        ),
    )
    filters: dict = Field(
        default={},
        description="Optional pre-filters, e.g. {'AWD Adoption': 'With AWD'}.",
    )

class SimulationRequest(BaseModel):
    """
    Input parameters for a single-scenario agricultural simulation.
    Ranges are agronomically validated.
    """
    awd_adoption: str = Field(
        description="AWD practice. One of: 'With AWD', 'Without AWD'.",
    )
    fertilizer_usage: float = Field(
        ge=50.0,  le=250.0,
        description="Fertilizer applied (kg/ha). Range: 50–250.",
    )
    pesticide_usage: float = Field(
        ge=0.5,   le=15.0,
        description="Pesticide applied (kg/ha). Range: 0.5–15.",
    )
    water_usage: float = Field(
        ge=100.0, le=1500.0,
        description="Irrigation water applied (m³/ha). Range: 100–1500.",
    )
    salinity_exposure: float = Field(
        ge=0.0,   le=0.1,
        description="Salinity exposure level (ppt, 0–0.1).",
    )

class OptimizationRequest(BaseModel):
    """
    Parameters for full-grid optimization (all AWD × fertilizer × water combinations).
    Pesticide and salinity are held fixed as constraints.
    """
    target_methane: float = Field(
        ge=50.0, le=2000.0,
        description="Maximum allowed Methane Emissions (kg/ha).",
    )
    pesticide_usage: float = Field(
        default=5.0, ge=0.5, le=15.0,
        description="Fixed pesticide level (kg/ha) used as a constraint.",
    )
    salinity_exposure: float = Field(
        default=0.01, ge=0.0, le=0.1,
        description="Fixed salinity exposure (ppt) used as a constraint.",
    )

class ResourceOptimizationRequest(BaseModel):
    """
    Targeted resource optimization: search over only the listed resources,
    hold everything else fixed.
    
    Example:
        { "resources": ["water", "fertilizer"], "target_methane": 300 }
        { "resources": ["awd", "water"], "fixed_inputs": {"fertilizer_usage": 120} }
    """
    resources: list[str] = Field(
        description=(
            "Resources to optimize. Valid values: 'water', 'fertilizer', "
            "'pesticide', 'salinity', 'awd'."
        ),
    )
    fixed_inputs: dict = Field(
        default={},
        description=(
            "Fixed values for non-optimized inputs. Keys: awd_adoption, "
            "fertilizer_usage, water_usage, pesticide_usage, salinity_exposure."
        ),
    )
    target_methane: float = Field(
        default=500.0, ge=50.0, le=2000.0,
        description="Methane ceiling used in scoring (kg/ha). Default: 500 (lenient).",
    )

class QueryRequest(BaseModel):
    """Free-text natural-language query routed through the AgentOrchestrator."""
    query: str = Field(min_length=1, max_length=1000)
    context: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_DIMENSIONS = {
    "Climate Type", "Season Type", "Scenario Group",
    "Scenario Name", "AWD Adoption", "Resource Scenario",
    "Year",
}

_VALID_METRICS = {
    "Avg Yield", "Methane Emissions", "Emission Intensity",
    "Profit Margin", "Net Income", "Production Cost", "Straw Value",
    "Water Usage", "Fertilizer Usage", "Pesticide Usage", "Salinity Exposure",
    "Max Flood Continuous", "Flood Stress", "Drought Stress", "Salinity Stress",
    "Biodiversity", "Resilient Varieties", "Water Reliability", "Labor Intensity",
}

_VALID_RESOURCES = {"water", "fertilizer", "pesticide", "salinity", "awd"}

_VALID_AWD = {"With AWD", "Without AWD"}

def _validate_dimension(dimension: str) -> None:
    if dimension not in _VALID_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid dimension '{dimension}'. Valid options: {sorted(_VALID_DIMENSIONS)}.",
        )

def _validate_metrics(metrics: list[str]) -> None:
    invalid = [m for m in metrics if m not in _VALID_METRICS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown metric(s): {invalid}. Valid options: {sorted(_VALID_METRICS)}.",
        )

def _validate_resources(resources: list[str]) -> None:
    invalid = [r for r in resources if r not in _VALID_RESOURCES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown resource(s): {invalid}. Valid options: {sorted(_VALID_RESOURCES)}.",
        )

def _validate_awd(awd: str) -> None:
    if awd not in _VALID_AWD:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid awd_adoption '{awd}'. Must be one of: {sorted(_VALID_AWD)}.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

# 0a. Data status — dashboard gọi tool này để quyết định có cho vào hay bắt upload
@app.get("/api/data-status")
@limiter.limit(RATE_LIMIT)
def api_get_data_status(request: Request):
    """
    Trả về trạng thái dữ liệu hiện tại: đã có CSV hợp lệ chưa, model đã
    sẵn sàng chưa, và danh sách cột bắt buộc theo template. Frontend nên
    gọi endpoint này ngay khi load app để quyết định hiện dashboard hay
    màn hình upload.
    """
    try:
        return get_data_status()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve data status.")


# 0a-bis. Tải file CSV mẫu đúng template
@app.get("/api/sample-csv")
@limiter.limit(RATE_LIMIT)
def api_download_sample_csv(request: Request):
    """
    Trả về 1 file CSV mẫu đúng template (đủ cột bắt buộc, kèm vài dòng ví dụ)
    để người dùng tải về, điền dữ liệu thật rồi upload lại. Endpoint này
    KHÔNG bị chặn bởi data-gate vì cần dùng được ngay cả khi chưa có dữ liệu.
    """
    try:
        csv_text = get_sample_csv()
    except Exception:
        raise HTTPException(status_code=500, detail="Không tạo được file CSV mẫu.")

    from fastapi.responses import Response
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=star_farm_template.csv"},
    )


# 0b. Upload CSV — bắt buộc phải gọi thành công trước khi dùng các endpoint khác
@app.post("/api/upload")
@limiter.limit(RATE_LIMIT)
async def api_upload_csv(request: Request, file: UploadFile = File(...)):
    """
    Upload file CSV mô phỏng nông nghiệp. File sẽ được validate đúng
    template (đủ cột, đúng kiểu dữ liệu, đủ số dòng) trước khi được nạp
    và dùng để train model. Cho tới khi upload thành công, mọi endpoint
    /api/* khác đều trả về 409.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file .csv")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File vượt quá giới hạn {MAX_UPLOAD_BYTES} bytes.",
        )
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="File rỗng.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        result = upload_simulation_csv(tmp_path)

        if result.get("status") == "success":
            return {"success": True, **result}

        # invalid_template hoặc error → trả về lỗi rõ ràng cho FE hiển thị
        raise HTTPException(
            status_code=422,
            detail={
                "message": result.get("message", "Upload thất bại."),
                "errors": result.get("errors", []),
                "required_columns": result.get("required_columns", []),
            },
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Xử lý file upload thất bại.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# 1. Scenarios listing
@app.get("/api/scenarios")
@limiter.limit(RATE_LIMIT)
def api_get_scenarios(request: Request):
    """
    Return all distinct filter options (scenario groups, season types,
    climate types, AWD options, resource scenarios, scenario names).
    """
    try:
        return get_scenarios()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to retrieve scenarios.")


# 2. Aggregation with filters
@app.post("/api/metrics")
@limiter.limit(RATE_LIMIT)
def api_get_metrics(request: Request, req: FilterRequest):
    """
    Return aggregated statistics for all metrics, optionally pre-filtered.
    
    Returns averages for: Avg Yield, Methane Emissions, Emission Intensity,
    Profit Margin, Net Income, Production Cost, Straw Value, Water Usage,
    Fertilizer Usage, Pesticide Usage, Salinity Exposure, Max Flood Continuous,
    Flood Stress, Drought Stress, Salinity Stress, Biodiversity,
    Resilient Varieties, Water Reliability, Labor Intensity.
    """
    try:
        result = orchestrator.process_query("aggregate", context={"filters": req.filters})
        return result["result"]
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to compute metrics.")


# 3. Compare X by Y (structured)
@app.post("/api/compare")
@limiter.limit(RATE_LIMIT)
def api_compare(request: Request, req: CompareRequest):
    """
    Compare one or more metrics grouped by a dimension.
    
    Example request body:
    ```json
    {
      "metrics": ["Avg Yield", "Methane Emissions", "Water Reliability"],
      "dimension": "Climate Type",
      "filters": {}
    }
    ```
    Leave `metrics` empty to use the default metric set.
    """
    _validate_dimension(req.dimension)
    if req.metrics:
        _validate_metrics(req.metrics)

    try:
        query = f"Compare {' and '.join(req.metrics) if req.metrics else 'all'} by {req.dimension}"
        result = orchestrator.process_query(
            query,
            context={"filters": req.filters},
        )
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Comparison failed.")


# 4. Simulate
@app.post("/api/simulate")
@limiter.limit(RATE_LIMIT)
def api_run_simulation(request: Request, req: SimulationRequest):
    """
    Run a single-scenario simulation with explicit agronomic inputs.
    
    Returns predictions for all output indicators:
    Avg Yield, Methane Emissions, Emission Intensity, Profit Margin,
    Net Income, Production Cost, Straw Value, Water Reliability,
    Biodiversity, Resilient Varieties, Labor Intensity,
    Flood Stress, Drought Stress, Salinity Stress.
    """
    _validate_awd(req.awd_adoption)
    try:
        result = orchestrator.process_query(
            "simulate",
            context={
                "awd_adoption":      req.awd_adoption,
                "fertilizer_usage":  req.fertilizer_usage,
                "pesticide_usage":   req.pesticide_usage,
                "water_usage":       req.water_usage,
                "salinity_exposure": req.salinity_exposure,
            },
        )
        return result["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Simulation failed.")

# 5. Full-grid optimization (methane ceiling)
@app.post("/api/optimize")
@limiter.limit(RATE_LIMIT)
def api_optimize(request: Request, req: OptimizationRequest):
    """
    Grid-search over AWD × fertilizer × water to maximize
    (Avg Yield × 2 + Profit Margin) while keeping Methane Emissions
    below `target_methane`. Pesticide and salinity are held fixed.
    """
    try:
        result = orchestrator.process_query(
            "optimize",
            context={
                "target_methane":    req.target_methane,
                "pesticide_usage":   req.pesticide_usage,
                "salinity_exposure": req.salinity_exposure,
            },
        )
        return result["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Optimization failed.")


# 6. Targeted resource optimization
@app.post("/api/optimize/resource")
@limiter.limit(RATE_LIMIT)
def api_run_resource_optimization(request: Request, req: ResourceOptimizationRequest):
    """
    Optimize only the listed resources; hold everything else fixed.
    
    Example — find the best water + fertilizer combination while keeping
    AWD fixed at 'With AWD' and pesticide at 10 kg/ha:
    ```json
    {
      "resources": ["water", "fertilizer"],
      "fixed_inputs": { "awd_adoption": "With AWD", "pesticide_usage": 10.0 },
      "target_methane": 300
    }
    ```
    """
    _validate_resources(req.resources)
    try:
        result = orchestrator.model_agent.execute(
            "optimize_resource",
            resources=req.resources,
            fixed_inputs=req.fixed_inputs,
            target_methane=req.target_methane,
        )
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Resource optimization failed.")


# 7. Natural-language agent query
@app.post("/api/query")
@limiter.limit(RATE_LIMIT)
def api_process_agent_query(request: Request, req: QueryRequest):
    """
    Route any free-text query through the AgentOrchestrator.
    
    Supports:
    - "Compare yield and water reliability by climate"
    - "Simulate with AWD fertilizer 120 water 750"
    - "Optimize inputs for methane below 200"
    - "Give me a summary of BAU scenario"
    - "Clean and standardize my CSV"
    """
    try:
        return orchestrator.process_query(req.query, context=req.context)
    except Exception:
        raise HTTPException(status_code=500, detail="Agent query failed.")


# ── MCP SSE mount ─────────────────────────────────────────────────────────────
try:
    sse_app = mcp.sse_app()
    app.mount("/mcp", sse_app)
    print("Mounted MCP SSE App on /mcp")
except Exception as e:
    print(f"Could not mount MCP SSE app: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)