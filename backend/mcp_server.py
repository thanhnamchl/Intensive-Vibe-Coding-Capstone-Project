import os
import pandas as pd
from mcp.server.fastmcp import FastMCP
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

# Initialize FastMCP Server
mcp = FastMCP("AI Agents Agricultural Modeling")

# Load and clean master data
CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
    "Simulation_Data.csv"
)

# Global variables for models and data
data = None
models = {}
label_encoders = {}

def init_data_and_models():
    global data, models, label_encoders
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Simulation CSV file not found at {CSV_PATH}")
    
    # Ingest CSV
    data = pd.read_csv(CSV_PATH)
    
    # Basic data cleaning: handle missing values or incorrect types if any
    data['datetime'] = pd.to_datetime(data['datetime'], errors='coerce')
    data['AWD Adoption'] = data['AWD Adoption'].str.strip()
    data['Scenario Group'] = data['Scenario Group'].str.strip()
    data['Season Type'] = data['Season Type'].str.strip()
    data['Climate Type'] = data['Climate Type'].str.strip()
    data['Resource Scenario'] = data['Resource Scenario'].str.strip()
    
    # Train predictors for Yield, Methane Emissions, and Profit Margin
    # Features: AWD Adoption, Fertilizer Usage, Pesticide Usage, Water Usage, Salinity Exposure
    features = ['AWD Adoption', 'Fertilizer Usage', 'Pesticide Usage', 'Water Usage', 'Salinity Exposure']
    
    # Prepare training dataset
    train_df = data[features + ['Avg Yield', 'Methane Emissions', 'Profit Margin', 'Net Income']].dropna()
    
    # Label encode categorical columns
    le_awd = LabelEncoder()
    train_df['AWD_encoded'] = le_awd.fit_transform(train_df['AWD Adoption'])
    label_encoders['AWD Adoption'] = le_awd
    
    X = train_df[['AWD_encoded', 'Fertilizer Usage', 'Pesticide Usage', 'Water Usage', 'Salinity Exposure']]
    
    # Train Random Forest Regressors
    for target in ['Avg Yield', 'Methane Emissions', 'Profit Margin', 'Net Income']:
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, train_df[target])
        models[target] = model
        
    print("Data Ingested and Predictive Models Trained Successfully.")

# Run init
init_data_and_models()

@mcp.tool()
def get_scenarios() -> dict:
    """
    Get all unique scenarios, climate types, season types, and resource scenarios available in the dataset.
    """
    global data
    return {
        "scenario_groups": data["Scenario Group"].dropna().unique().tolist(),
        "season_types": data["Season Type"].dropna().unique().tolist(),
        "climate_types": data["Climate Type"].dropna().unique().tolist(),
        "resource_scenarios": data["Resource Scenario"].dropna().unique().tolist(),
        "awd_options": data["AWD Adoption"].dropna().unique().tolist(),
    }

@mcp.tool()
def get_aggregated_metrics(filters: dict = None) -> dict:
    """
    Get aggregated agricultural metrics (yield, emissions, profit, usage) with optional filters.
    Filters can contain: Scenario Group, Season Type, Climate Type, Resource Scenario, AWD Adoption
    """
    global data
    filtered_data = data.copy()
    
    if filters:
        for col, val in filters.items():
            if col in filtered_data.columns and val:
                filtered_data = filtered_data[filtered_data[col] == val]
                
    if filtered_data.empty:
        return {"status": "empty", "message": "No data matches current filters."}
        
    summary = {
        "total_records": len(filtered_data),
        "avg_yield": float(filtered_data["Avg Yield"].mean()),
        "avg_methane_emissions": float(filtered_data["Methane Emissions"].mean()),
        "avg_profit_margin": float(filtered_data["Profit Margin"].mean()),
        "avg_net_income": float(filtered_data["Net Income"].mean()),
        "avg_water_usage": float(filtered_data["Water Usage"].mean()),
        "avg_fertilizer_usage": float(filtered_data["Fertilizer Usage"].mean()),
        "avg_pesticide_usage": float(filtered_data["Pesticide Usage"].mean()),
        "avg_salinity_exposure": float(filtered_data["Salinity Exposure"].mean()),
    }
    
    # AWD comparison
    awd_comparison = filtered_data.groupby('AWD Adoption')[['Avg Yield', 'Methane Emissions', 'Profit Margin']].mean().to_dict(orient='index')
    summary['awd_comparison'] = awd_comparison
    
    return summary

@mcp.tool()
def run_agricultural_simulation(
    awd_adoption: str,
    fertilizer_usage: float,
    pesticide_usage: float,
    water_usage: float,
    salinity_exposure: float
) -> dict:
    """
    Simulate Yield, Methane Emissions, Net Income, and Profit Margin based on agricultural inputs and AWD adoption practice.
    Inputs:
    - awd_adoption: 'With AWD' or 'Without AWD'
    - fertilizer_usage: Amount of fertilizer used (e.g. 50-200)
    - pesticide_usage: Amount of pesticide used (e.g. 2-10)
    - water_usage: Amount of water applied (e.g. 300-1200)
    - salinity_exposure: Salinity levels (e.g. 0.0 - 0.05)
    """
    global models, label_encoders
    
    try:
        le_awd = label_encoders['AWD Adoption']
        awd_encoded = le_awd.transform([awd_adoption])[0]
    except Exception:
        # Fallback to defaults
        awd_encoded = 0 if awd_adoption == 'Without AWD' else 1
        
    X_input = pd.DataFrame([{
        'AWD_encoded': awd_encoded,
        'Fertilizer Usage': fertilizer_usage,
        'Pesticide Usage': pesticide_usage,
        'Water Usage': water_usage,
        'Salinity Exposure': salinity_exposure
    }])
    
    predictions = {}
    for target, model in models.items():
        pred = model.predict(X_input)[0]
        predictions[target] = float(pred)
        
    return {
        "inputs": {
            "AWD Adoption": awd_adoption,
            "Fertilizer Usage": fertilizer_usage,
            "Pesticide Usage": pesticide_usage,
            "Water Usage": water_usage,
            "Salinity Exposure": salinity_exposure
        },
        "predictions": predictions
    }

@mcp.tool()
def clean_and_standardize_csv(file_content: str) -> dict:
    """
    Upload a custom agricultural simulation output CSV and standardize columns, clean data types, and report quality metrics.
    """
    from io import StringIO
    import csv
    
    if not file_content or not file_content.strip():
        return {"status": "error", "message": "Input content is empty."}
        
    try:
        # Detect delimiter
        dialect = csv.Sniffer().sniff(file_content[:1024])
        df = pd.read_csv(StringIO(file_content), sep=dialect.delimiter)
        
        if df.empty:
            return {"status": "error", "message": "The provided CSV file contains no data."}
            
        original_cols = df.columns.tolist()
        
        # Mapping common variations to standard columns
        mapping = {
            'yield': 'Avg Yield',
            'methane': 'Methane Emissions',
            'profit': 'Profit Margin',
            'net_income': 'Net Income',
            'water': 'Water Usage',
            'fertilizer': 'Fertilizer Usage',
            'pesticide': 'Pesticide Usage',
            'awd': 'AWD Adoption'
        }
        
        renamed = {}
        for col in df.columns:
            col_lower = col.lower()
            for key, val in mapping.items():
                if key in col_lower:
                    df.rename(columns={col: val}, inplace=True)
                    renamed[col] = val
                    break
                    
        # Basic type conversions
        numeric_cols = ['Avg Yield', 'Methane Emissions', 'Profit Margin', 'Net Income', 'Water Usage', 'Fertilizer Usage', 'Pesticide Usage']
        conversions = []
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                conversions.append(col)
                
        # Calculate clean statistics
        missing_counts = df.isnull().sum().to_dict()
        
        return {
            "status": "success",
            "records_processed": len(df),
            "original_columns": original_cols,
            "renamed_columns": renamed,
            "converted_types": conversions,
            "missing_values": missing_counts,
            "preview": df.head(10).to_dict(orient='records')
        }
    except csv.Error:
        return {"status": "error", "message": "Could not detect CSV format/delimiter."}
    except Exception as e:
        return {"status": "error", "message": f"Processing failed: {str(e)}"}

if __name__ == "__main__":
    # If run directly, run stdio server
    mcp.run()
