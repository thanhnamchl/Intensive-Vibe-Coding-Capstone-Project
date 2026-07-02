import os
import io
import csv
import pandas as pd
from mcp.server.fastmcp import FastMCP
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import numpy as np
import itertools

# ── FastMCP Server ────────────────────────────────────────────────────────────
mcp = FastMCP("AI Agents Agricultural Modeling")

# CSV path này hiện KHÔNG còn được dùng để auto-load — chỉ giữ lại làm hằng số
# tham khảo. Muốn khôi phục auto-load cho dev cục bộ, tự thêm điều kiện env
# (ví dụ os.getenv("AUTO_LOAD_DEFAULT_CSV") == "true") rồi gọi load_simulation_csv().
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Simulation_Data.csv",
)

# ── Global state ──────────────────────────────────────────────────────────────
data            = None   # None nghĩa là CHƯA có dữ liệu hợp lệ nào được upload
models          = {}
label_encoders  = {}

# ── All numeric columns that can be predicted / aggregated ───────────────────
INPUT_FEATURES = [
    "AWD Adoption",
    "Fertilizer Usage",
    "Pesticide Usage",
    "Water Usage",
    "Salinity Exposure",
]

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

CATEGORICAL_COLS = [
    "AWD Adoption",
    "Scenario Group",
    "Season Type",
    "Climate Type",
    "Resource Scenario",
    "Scenario Name",
]

# ── Cột bắt buộc theo đúng template hiện tại (hợp nhất tất cả các nhóm trên) ──
REQUIRED_COLUMNS = sorted(set(
    CATEGORICAL_COLS + INPUT_FEATURES + PREDICTION_TARGETS + AGG_NUMERIC_COLS
))

# Thứ tự cột "dễ đọc" hơn dùng riêng cho file CSV mẫu tải về (categorical trước,
# rồi input, rồi target...). Tập hợp cột giống hệt REQUIRED_COLUMNS, chỉ khác thứ tự.
SAMPLE_COLUMN_ORDER = list(dict.fromkeys(
    CATEGORICAL_COLS + INPUT_FEATURES + PREDICTION_TARGETS + AGG_NUMERIC_COLS
))

# Số dòng tối thiểu để train RandomForest cho từng target (đồng bộ với logic cũ)
MIN_ROWS_PER_TARGET = 10


def _agg_key(col: str) -> str:
    normalized = col.lower().replace(" ", "_")
    if normalized.startswith("avg_"):
        return normalized
    return f"avg_{normalized}"


# ── Validate schema CSV upload lên có đúng template không ────────────────────

def validate_csv_schema(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Kiểm tra file CSV được upload có đúng cấu trúc (template) mà hệ thống
    yêu cầu hay không. Trả về (is_valid, danh_sach_loi).
    """
    errors: list[str] = []

    # 1. Kiểm tra thiếu cột
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Thiếu {len(missing)} cột bắt buộc: {missing}")

    # 2. Kiểm tra các cột số phải là dạng số (không lẫn text/rác)
    numeric_cols = [c for c in REQUIRED_COLUMNS if c not in CATEGORICAL_COLS]
    for col in numeric_cols:
        if col not in df.columns:
            continue
        coerced = pd.to_numeric(df[col], errors="coerce")
        bad_mask = coerced.isna() & df[col].notna()
        if bad_mask.any():
            errors.append(
                f"Cột '{col}' có {int(bad_mask.sum())} giá trị không phải số"
            )

    # 3. Kiểm tra cột categorical không được rỗng toàn bộ
    for col in CATEGORICAL_COLS:
        if col in df.columns and df[col].dropna().astype(str).str.strip().eq("").all():
            errors.append(f"Cột '{col}' không có giá trị hợp lệ nào")

    # 4. Kiểm tra AWD Adoption chỉ có đúng 2 giá trị mong đợi (nếu cột tồn tại)
    if "AWD Adoption" in df.columns:
        vals = set(df["AWD Adoption"].dropna().astype(str).str.strip().unique())
        allowed = {"With AWD", "Without AWD"}
        unexpected = vals - allowed
        if unexpected and vals:
            errors.append(
                f"Cột 'AWD Adoption' có giá trị lạ ngoài {allowed}: {unexpected}"
            )

    # 5. Kiểm tra đủ số dòng tối thiểu để train model
    if len(df) < MIN_ROWS_PER_TARGET:
        errors.append(
            f"File cần tối thiểu {MIN_ROWS_PER_TARGET} dòng dữ liệu, hiện có {len(df)}"
        )

    return (len(errors) == 0, errors)


# ── Load + train từ một DataFrame đã validate ─────────────────────────────────

def _load_and_train(df: pd.DataFrame) -> dict:
    global data, models, label_encoders

    df = df.copy()

    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    new_label_encoders = {}
    le_awd = LabelEncoder()
    df["AWD_encoded"] = le_awd.fit_transform(df["AWD Adoption"])
    new_label_encoders["AWD Adoption"] = le_awd

    X_all = df[
        ["AWD_encoded", "Fertilizer Usage", "Pesticide Usage",
         "Water Usage", "Salinity Exposure"]
    ]

    new_models = {}
    trained, skipped = [], []
    for target in PREDICTION_TARGETS:
        if target not in df.columns:
            skipped.append(target)
            continue

        mask = df[target].notna()
        X_train = X_all[mask]
        y_train = df.loc[mask, target]

        if len(y_train) < MIN_ROWS_PER_TARGET:
            skipped.append(target)
            continue

        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)
        new_models[target] = model
        trained.append(target)

    if not new_models:
        return {
            "status": "error",
            "message": "Không train được model nào — dữ liệu không đủ ở các cột target.",
            "skipped": skipped,
        }

    # Chỉ commit vào global state khi mọi thứ ổn — tránh để hệ thống ở trạng thái dở dang
    data = df
    models = new_models
    label_encoders = new_label_encoders

    return {
        "status": "success",
        "rows_loaded": len(df),
        "trained_models": trained,
        "skipped_models": skipped,
    }


def load_simulation_csv(csv_path: str) -> dict:
    if not csv_path or not os.path.exists(csv_path):
        return {"status": "error", "message": f"Không tìm thấy file tại: {csv_path}"}

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return {"status": "error", "message": f"Không đọc được CSV: {e}"}

    is_valid, errors = validate_csv_schema(df)
    if not is_valid:
        return {
            "status": "invalid_template",
            "message": "CSV không đúng định dạng template yêu cầu.",
            "errors": errors,
            "required_columns": REQUIRED_COLUMNS,
        }

    return _load_and_train(df)


def _require_data():
    """Gọi ở đầu mỗi tool cần dữ liệu. Raise lỗi rõ ràng nếu chưa upload CSV."""
    if data is None:
        raise ValueError(
            "Chưa có dữ liệu mô phỏng nào được nạp. "
            "Vui lòng gọi tool 'upload_simulation_csv' với file CSV đúng template trước."
        )


# Server luôn khởi động với data = None. KHÔNG auto-load bất kỳ file nào có sẵn
# trên đĩa (kể cả DEFAULT_CSV_PATH) — người dùng bắt buộc phải upload qua
# upload_simulation_csv() / POST /api/upload trước khi dùng được các tool khác.
print("[mcp_server] Chưa có dữ liệu. Chờ người dùng upload_simulation_csv().")


# ── Sinh file CSV mẫu để người dùng tải về, điền dữ liệu thật rồi upload lại ──

def build_sample_csv_text(n_rows: int = 12) -> str:
    """
    Sinh 1 chuỗi CSV đúng template (đủ REQUIRED_COLUMNS) kèm vài dòng ví dụ
    với giá trị hợp lý trong khoảng agronomically-valid, để người dùng có
    điểm khởi đầu rõ ràng thay vì phải tự đoán tên cột / định dạng.
    """
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_rows):
        awd = "With AWD" if i % 2 == 0 else "Without AWD"
        row = {
            "AWD Adoption":        awd,
            "Scenario Group":      "BAU" if i % 2 == 0 else "OMRH",
            "Season Type":         "Winter-Spring" if i % 3 != 0 else "Summer-Autumn",
            "Climate Type":        "Historical" if i % 2 == 0 else "RCP4.5",
            "Resource Scenario":   "High Resource" if i % 2 == 0 else "Low Resource",
            "Scenario Name":       f"Scenario_{i + 1}",
            "Fertilizer Usage":    round(float(rng.uniform(80, 200)), 1),
            "Pesticide Usage":     round(float(rng.uniform(2, 10)), 2),
            "Water Usage":         round(float(rng.uniform(400, 900)), 1),
            "Salinity Exposure":   round(float(rng.uniform(0.005, 0.03)), 4),
            "Avg Yield":           round(float(rng.uniform(4, 7)), 2),
            "Methane Emissions":   round(float(rng.uniform(150, 400)), 1),
            "Emission Intensity":  round(float(rng.uniform(20, 60)), 2),
            "Profit Margin":       round(float(rng.uniform(10, 35)), 1),
            "Net Income":          round(float(rng.uniform(800, 2500)), 0),
            "Production Cost":     round(float(rng.uniform(500, 1200)), 0),
            "Straw Value":         round(float(rng.uniform(50, 200)), 0),
            "Max Flood Continuous": round(float(rng.uniform(0, 10)), 1),
            "Flood Stress":        round(float(rng.uniform(0, 1)), 3),
            "Drought Stress":      round(float(rng.uniform(0, 1)), 3),
            "Salinity Stress":     round(float(rng.uniform(0, 1)), 3),
            "Biodiversity":        round(float(rng.uniform(0.3, 0.9)), 3),
            "Resilient Varieties": round(float(rng.uniform(20, 90)), 1),
            "Water Reliability":   round(float(rng.uniform(50, 95)), 1),
            "Labor Intensity":     round(float(rng.uniform(20, 80)), 1),
        }
        rows.append(row)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SAMPLE_COLUMN_ORDER)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in SAMPLE_COLUMN_ORDER})
    return output.getvalue()


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_sample_csv() -> str:
    """
    Trả về nội dung 1 file CSV mẫu đúng template (đủ cột bắt buộc, kèm vài
    dòng dữ liệu ví dụ) để người dùng tải về, điền dữ liệu thật rồi upload
    lại qua upload_simulation_csv() / POST /api/upload.
    """
    return build_sample_csv_text()


@mcp.tool()
def upload_simulation_csv(csv_path: str) -> dict:
    """
    Upload và validate một file CSV mô phỏng nông nghiệp.
    PHẢI gọi tool này (và nhận status="success") trước khi dùng
    get_scenarios, get_aggregated_metrics, hoặc run_agricultural_simulation.

    File CSV phải chứa đầy đủ các cột trong REQUIRED_COLUMNS (xem get_data_status
    để lấy danh sách cụ thể), đúng kiểu dữ liệu, và tối thiểu 10 dòng.
    """
    return load_simulation_csv(csv_path)


@mcp.tool()
def get_data_status() -> dict:
    """
    Kiểm tra trạng thái dữ liệu hiện tại: đã có CSV hợp lệ được nạp chưa,
    model đã sẵn sàng chưa, và danh sách cột bắt buộc theo template.
    Dashboard nên gọi tool này trước khi cho phép người dùng vào trang chính.
    """
    return {
        "data_loaded": data is not None,
        "rows_loaded": len(data) if data is not None else 0,
        "models_ready": len(models) > 0,
        "trained_targets": list(models.keys()),
        "required_columns": REQUIRED_COLUMNS,
        "categorical_columns": CATEGORICAL_COLS,
    }


@mcp.tool()
def get_scenarios() -> dict:
    """
    Return all distinct categorical filter values available in the dataset:
    scenario groups, season types, climate types, resource scenarios,
    AWD options, and scenario names.
    """
    _require_data()
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
    Return aggregated means for all agricultural indicators, with optional
    pre-filtering.

    Supported filter keys:
        Scenario Group, Season Type, Climate Type, Resource Scenario,
        AWD Adoption, Scenario Name
    """
    _require_data()
    filtered = data.copy()

    if filters:
        for col, val in filters.items():
            if col in filtered.columns and val:
                filtered = filtered[filtered[col] == val]

    if filtered.empty:
        return {"status": "empty", "message": "No data matches the current filters."}

    summary: dict = {"total_records": len(filtered)}

    for col in AGG_NUMERIC_COLS:
        if col in filtered.columns:
            summary[_agg_key(col)] = float(filtered[col].mean())

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
    _require_data()

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

    first_model = next(iter(models.values()))
    feature_order = list(first_model.feature_names_in_)
    X = pd.DataFrame(raw)[feature_order]

    results = {}
    for target, model in models.items():
        results[target] = model.predict(X).astype(float)

    return pd.DataFrame(results).to_dict(orient="records")


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