"""
AI-Agent Backplane & API Server
Security hardened: rate limiting, security headers, CORS restriction,
Pydantic field validation, request-size guard, structured error responses.
All configuration is read from environment variables — no secrets in code.
"""
import os
from dotenv import load_dotenv

# Load .env file if present (safe: no-op when file is missing)
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from agent_adk import AgentOrchestrator
from mcp_server import mcp, get_scenarios

# ── Configuration from environment ───────────────────────────────────────────
# Comma-separated list of allowed CORS origins.
# Default: Vite dev + preview ports. Override in .env for production.
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Maximum accepted upload body size in bytes (default 10 MB).
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

# Rate limit: requests per minute per IP (default 60).
RATE_LIMIT: str = os.getenv("RATE_LIMIT_PER_MIN", "60") + "/minute"

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Agent Backplane & API Server",
    # Disable automatic OpenAPI schema exposure in production-like settings
    # (can be re-enabled by setting ENABLE_DOCS=true)
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
    redoc_url=None,
)

# Register slowapi's rate-limit-exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS (restricted to known origins) ───────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,       # no cookies / credentials needed
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Security-headers middleware ───────────────────────────────────────────────
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

# ── Global unhandled-exception handler (never leak stack traces) ──────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Log the real error server-side only
    print(f"[ERROR] Unhandled exception on {request.url.path}: {exc!r}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )

# ── Agent Orchestrator ────────────────────────────────────────────────────────
orchestrator = AgentOrchestrator()

# ── Pydantic schemas with field-level validation ──────────────────────────────
class FilterRequest(BaseModel):
    filters: dict = {}

class SimulationRequest(BaseModel):
    awd_adoption: str
    fertilizer_usage: float = Field(ge=50.0, le=250.0)
    pesticide_usage: float  = Field(ge=0.5,  le=15.0)
    water_usage: float      = Field(ge=100.0, le=1500.0)
    salinity_exposure: float = Field(ge=0.0,  le=0.1)

class OptimizationRequest(BaseModel):
    target_methane: float   = Field(ge=50.0, le=2000.0)
    pesticide_usage: float  = Field(default=5.0, ge=0.5, le=15.0)
    salinity_exposure: float = Field(default=0.01, ge=0.0, le=0.1)

class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    context: dict = {}

class UploadRequest(BaseModel):
    file_content: str = Field(min_length=1)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _check_upload_size(content: str) -> None:
    """Reject payloads exceeding the configured size limit."""
    if len(content.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

# ── Endpoints ─────────────────────────────────────────────────────────────────

# 1. Scenarios listing
@app.get("/api/scenarios")
@limiter.limit(RATE_LIMIT)
def api_get_scenarios(request: Request):
    try:
        return get_scenarios()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve scenarios.")

# 2. Aggregations with filters
@app.post("/api/metrics")
@limiter.limit(RATE_LIMIT)
def api_get_metrics(request: Request, req: FilterRequest):
    try:
        result = orchestrator.process_query("aggregate", context={"filters": req.filters})
        return result["result"]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to compute metrics.")

# 3. Simulate inputs
@app.post("/api/simulate")
@limiter.limit(RATE_LIMIT)
def api_run_simulation(request: Request, req: SimulationRequest):
    try:
        result = orchestrator.process_query("simulate", context={
            "awd_adoption": req.awd_adoption,
            "fertilizer_usage": req.fertilizer_usage,
            "pesticide_usage": req.pesticide_usage,
            "water_usage": req.water_usage,
            "salinity_exposure": req.salinity_exposure,
        })
        return result["result"]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Simulation failed.")

# 4. Optimize inputs
@app.post("/api/optimize")
@limiter.limit(RATE_LIMIT)
def api_run_optimization(request: Request, req: OptimizationRequest):
    try:
        result = orchestrator.process_query("optimize", context={
            "target_methane": req.target_methane,
            "pesticide_usage": req.pesticide_usage,
            "salinity_exposure": req.salinity_exposure,
        })
        return result["result"]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Optimization failed.")

# 5. Natural-language agent query
@app.post("/api/query")
@limiter.limit(RATE_LIMIT)
def api_process_agent_query(request: Request, req: QueryRequest):
    try:
        return orchestrator.process_query(req.query, context=req.context)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Agent query failed.")

# 6. Raw CSV ingestion & cleaning (string body)
@app.post("/api/upload")
@limiter.limit("20/minute")   # stricter limit for upload endpoint
def api_upload_csv(request: Request, req: UploadRequest):
    _check_upload_size(req.file_content)
    try:
        result = orchestrator.process_query("clean", context={"file_content": req.file_content})
        return result["result"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="CSV processing failed.")

# 6b. Raw CSV ingestion via multipart file upload
@app.post("/api/upload_file")
@limiter.limit("20/minute")
async def api_upload_csv_file(request: Request, file: UploadFile = File(...)):
    # Validate MIME type
    allowed_types = {"text/csv", "application/csv", "text/plain"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Please upload a CSV file.",
        )
    try:
        content_bytes = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read uploaded file.")

    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    try:
        file_content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text.")

    try:
        result = orchestrator.process_query("clean", context={"file_content": file_content})
        return result["result"]
    except Exception:
        raise HTTPException(status_code=500, detail="CSV processing failed.")

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
