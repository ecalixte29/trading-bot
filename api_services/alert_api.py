from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from datetime import datetime

app = FastAPI(
    title="Options Trading Bot Alert API",
    description="API for receiving and managing alerts from the trading bot.",
    version="0.1.0"
)

class AlertMessage(BaseModel):
    message: str
    level: str = "INFO" # e.g., INFO, WARNING, ERROR, CRITICAL
    timestamp: datetime = None

# In a real application, you might store alerts in a database or send them to a notification service.
# For now, we'll just keep them in memory and print to console.
alert_log = []

@app.post("/alert", status_code=201)
async def receive_alert(alert: AlertMessage):
    """
    Receives an alert from the trading bot.
    - **message**: The content of the alert.
    - **level**: Severity of the alert (INFO, WARNING, ERROR, CRITICAL).
    """
    if alert.timestamp is None:
        alert.timestamp = datetime.now()
    
    log_entry = f"[{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{alert.level.upper()}] {alert.message}"
    print(f"ALERT RECEIVED: {log_entry}")
    alert_log.append({
        "timestamp": alert.timestamp,
        "level": alert.level.upper(),
        "message": alert.message
    })
    # Keep a rolling log of the last N alerts, for example
    # global alert_log
    # alert_log = alert_log[-100:] 
    return {"status": "Alert received", "log_entry": log_entry}

@app.get("/alerts")
async def get_alerts(limit: int = 20):
    """
    Retrieves the latest alerts.
    - **limit**: Maximum number of alerts to return.
    """
    return {"alerts": alert_log[-limit:]}

@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "API is healthy"}

if __name__ == "__main__":
    print("Starting Alert API server...")
    print("Access it at http://127.0.0.1:8001")
    print("POST to http://127.0.0.1:8001/alert with JSON like: {\"message\": \"Test alert\", \"level\": \"INFO\"}")
    print("GET from http://127.0.0.1:8001/alerts to see logged alerts")
    print("GET from http://127.0.0.1:8001/health for health check")
    # Note: Running directly with uvicorn.run is great for development.
    # For production, you might use Gunicorn or another ASGI server manager.
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info") 