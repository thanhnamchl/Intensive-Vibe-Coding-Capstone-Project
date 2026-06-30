# AI-Agents Agricultural Modeling System

An AI-powered multi-agent system and interactive simulation dashboard designed to analyze the impacts of agricultural practices (like AWD adoption, water management, fertilizer/pesticide usage) on crop yields, methane emissions, net income, and profit margins.

---

## 🏗️ Architecture Overview

The system consists of three main components:
1. **Model Context Protocol (MCP) Server & Predictors (`backend/mcp_server.py`)**: 
   - Dynamically ingests `Simulation_Data.csv`.
   - Trains Random Forest regression models to predict yield, methane emissions, net income, and profit margins.
   - Exposes tools to query, filter, simulate, and clean data.
2. **Multi-Agent System (`backend/agent_adk.py`)**:
   - Implements an Agent Development Kit (ADK) orchestrating:
     - **Agricultural Statistics Analyst (AggregationAgent)**: Groups and aggregates historical trends.
     - **Agricultural Yield & Emission Predictor (ModelingAgent)**: Performs scenario forecasts and inputs optimization.
     - **AgentOrchestrator**: Dynamically routes and resolves natural language queries.
3. **Interactive Dashboard (`frontend/`)**:
   - Built with React, TypeScript, and Vite.
   - Formulates interactive sliders, scenario-based filtration cards, dynamic charts, policy optimizers, and a chat interface to talk directly to the AI agents.

---

## 🚀 Setup & Execution Instructions

Follow these steps to run both the Backend API server and the Frontend Dashboard locally.

### 1. Backend Setup

The backend runs on Python.

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Create a virtual environment (recommended)**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Windows (PowerShell)**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **Windows (CMD)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install backend dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Start the FastAPI Backend server**:
   ```bash
   python main.py
   ```
   *The backend server will start at **`http://localhost:8000`**. The MCP SSE endpoint is exposed under `/mcp`.*

---

### 2. Frontend Setup

The frontend is a React + Vite application.

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install Node dependencies**:
   ```bash
   npm install
   ```

3. **Run the frontend development server**:
   ```bash
   npm run dev
   ```
   *The dashboard will be available at **`http://localhost:5173`**.*

---

## 💡 System Features & Usage

1. **Simulation Slider Tools**: Adjust input parameters (Fertilizer, Pesticides, Water, Salinity, AWD) on the sidebar and click **"Simulate Scenario Outcomes"** to get real-time machine-learning predictions.
2. **Agent Chat**: Ask natural language queries like:
   - *"Optimize inputs for methane below 180"*
   - *"Give me a summary of Business As Usual scenario"*
   - *"Simulate with AWD adoption With AWD and fertilizer 120 and water 750"*
