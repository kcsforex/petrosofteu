# 2026.02.05  8.00
import dash
from dash import dcc, html, Input, Output, State, callback, dash_table, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import requests
import time
import os
from databricks import sql
from fastapi import APIRouter

# --- 1. FASTAPI ROUTER (If you want n8n to trigger the job) ---
router = APIRouter()

@router.post("/trigger")
def trigger_external_job():
    # Logic to trigger Databricks from n8n could go here
    return {"status": "Job trigger available via UI"}

# --- 2. CONFIGURATION ---
DBX_HOST = os.getenv("DBX_HOST")
DBX_HTTP_PATH = os.getenv("DBX_HTTP_PATH")
DBX_TOKEN = os.getenv("DBX_TOKEN")
KEEPALIVE_INTERVAL = int(os.getenv("DBX_KEEPALIVE_INTERVAL", "180"))
DBX_JOB_ID = os.getenv("DBX_JOB_ID")

headers = {"Authorization": f"Bearer {DBX_TOKEN}", "Content-Type": "application/json"}

# --- 3. DASH REGISTRATION & UI ---
dash.register_page(__name__, icon="fa-brain", name="ML Databricks", order=8)

CARD_STYLE = {
    "background": "rgba(255, 255, 255, 0.03)",
    "backdrop-filter": "blur(10px)",
    "border-radius": "15px",
    "border": "1px solid rgba(255, 255, 255, 0.1)",
    "padding": "25px",
    "marginBottom": "20px"
}

layout = dbc.Container([
    html.Div([
        html.H2("NYC Yellow Taxi (GBT Engine)", className="text-light fw-bold mb-0"),
        html.P("Remote Execution on Databricks Cluster", className="text-muted small"),
    ], className="mb-4"),

    dbc.Row([
        # Controls Sidebar
        dbc.Col([
            html.Div([

                html.Label("Max Iteration", className="text-info small"),
                html.Div([
                    dcc.Slider(id="maxIter", min=5, max=25, step=5, value=10, 
                               marks={i: {'label': str(i), 'style': {'color': 'blue', 'marginTop': '5px'}} for i in range(5, 26, 5)})
                ], style={'backgroundColor': 'white', 'padding': '10px 15px 10px 10px', 'borderRadius': '5px', 'marginTop': '5px'}),
                
                html.Label("Max Depth", className="text-info small mt-4"),
                html.Div([
                    dcc.Slider(id="maxDepth", min=2, max=7, step=1, value=3,
                               marks={i: {'label': str(i), 'style': {'color': 'blue', 'marginTop': '5px'}} for i in range(2, 8)})
                ], style={'backgroundColor': 'white', 'padding': '10px 15px 10px 10px', 'borderRadius': '5px', 'marginTop': '5px'}),
                
                dbc.Button([
                    html.I(className="fas fa-play me-2"), "Run Model"
                ], id="run-btn", color="info", className="w-100 mt-5 fw-bold", style={"borderRadius": "10px"})
                
            ], style=CARD_STYLE),

            html.Div(id="gbt-metrics-table", style=CARD_STYLE)
            
        ], width=12, lg=4),

        

        # Results Area
        dbc.Col([
            html.Div([
                dcc.Loading(
                    dcc.Graph(id="gbt-chart", config={'displayModeBar': False}),
                    type="graph", color="#00d1ff"
                )
            ], style=CARD_STYLE),
            
            html.Div(id="gbt-model-table", style=CARD_STYLE)
            
        ], width=12, lg=8)
    ])
], fluid=True)

# --- 4. CALLBACKS ---
@callback(
    [Output("gbt-metrics-table", "children"),
    Output("gbt-chart", "figure"),
    Output("gbt-model-table", "children")],
    [Input("run-btn", "n_clicks")],
    [State("maxIter", "value"),
     State("maxDepth", "value")],
    prevent_initial_call=True
)
def update_chart(n_clicks, maxIter, maxDepth):
    if not n_clicks:
        raise PreventUpdate

    # ----- A. Trigger Databricks job -----
    run_now_url = f"https://{DBX_HOST}/api/2.2/jobs/run-now"
    payload = { "job_id": DBX_JOB_ID, "notebook_params": {"maxIter": str(maxIter), "maxDepth": str(maxDepth)}}

    response = requests.post(run_now_url, headers=headers, json=payload)
    if response.status_code != 200:
        error_fig = px.scatter(title=f"Error: {response.text}")
        return (
            html.Div("Job Trigger Failed", className="text-danger"),
            error_fig,
            no_update,
        )

    run_id = response.json().get("run_id")

    # ----- B. Poll status (Simplified for 8GB RAM responsiveness) -----
    status_url = f"https://{DBX_HOST}/api/2.2/jobs/runs/get?run_id={run_id}"
    for _ in range(20): # Timeout after ~60 seconds
        status_response = requests.get(status_url, headers=headers).json()
        state = status_response.get("state", {}).get("life_cycle_state")
        if state == "TERMINATED":
            break
        time.sleep(3)

    # ----- C. Query Results using Databricks SQL -----
    try:
        connection = sql.connect(server_hostname=DBX_HOST, http_path=DBX_HTTP_PATH, access_token=DBX_TOKEN)
        with connection.cursor() as cursor:
            cursor.execute("SELECT trip_distance, passenger_count, pickup_hour, duration_mins, prediction FROM test_cat.test_db.nyctaxi_model_pred LIMIT 100")
            model_df = cursor.fetchall_arrow().to_pandas()

            cursor.execute("SELECT * FROM test_cat.test_db.nyctaxi_model_metrics LIMIT 100")
            metrics_df = cursor.fetchall_arrow().to_pandas()
        connection.close()
        
    except Exception as e:
        error_fig = px.scatter(title=f"SQL Error: {e}")
        return (
            html.Div(f"Query Error: {e}", className="text-danger"),
            error_fig,
            no_update,
        )

    fig = px.scatter(model_df, x="duration_mins", y="prediction", title=f"RF Results: Iter={maxIter} | Depth={maxDepth}", template="plotly_dark")
    
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',font_color="white", margin=dict(t=50, b=0, l=0, r=0))

    metrics_num_cols = metrics_df.select_dtypes(include="number").columns
    metrics_df[metrics_num_cols] = metrics_df[metrics_num_cols].round(3)
    metrics_table = dbc.Table.from_dataframe(metrics_df[:10], striped=False, hover=True, responsive=True, borderless=True, className="text-light m-0", 
        style={"backgroundColor": "transparent", "--bs-table-bg": "transparent", "--bs-table-accent-bg": "transparent", "color": "white"})


    model_num_cols = model_df.select_dtypes(include="number").columns
    model_df[model_num_cols] = model_df[model_num_cols].round(3)
    model_table = dbc.Table.from_dataframe(model_df[:10], striped=False, hover=True, responsive=True, borderless=True, className="text-light m-0", 
        style={"backgroundColor": "transparent", "--bs-table-bg": "transparent", "--bs-table-accent-bg": "transparent", "color": "white"})

    return metrics_table, fig, model_table
