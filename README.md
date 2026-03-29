# PharmaCost Intelligence

AI-powered pharmacy inventory, billing, expiry, and financial operations system.

## Overview

PharmaCost Intelligence is a Flask-based pharmacy management platform that combines inventory control, billing, expiry monitoring, audit logging, and AI-style financial anomaly detection.

It is designed to help pharmacies and hospital formularies reduce loss from:
- Expired stock.
- Overstock capital lock-in.
- Discount leakage.
- Compliance and audit gaps.

## Features

- Inventory management with batch-level stock tracking.
- Billing system with bill details and patient records.
- Expiry alerts and stock-risk monitoring.
- Audit logging with database triggers.
- Agent-based financial intelligence modules.
- CSV bulk import support.
- Role-based access for admin and pharmacist users.
- Reports and dashboard views for operational insight.

## Tech Stack

- Python
- Flask
- SQLite
- HTML / Jinja2
- ReportLab

## Project Structure

- `app.py` — Main Flask application.
- `expiry_watchdog.py` — Expiry risk detection agent.
- `spend_intelligence.py` — Financial anomaly detection agent.
- `orchestrator.py` — Runs and combines agent outputs.
- `templates/` — HTML templates for UI pages.
- `requirements.txt` — Python dependencies.
- `run.sh` / `run.bat` — Start scripts.

## Key Modules

### Expiry Watchdog
Detects expired and near-expiry batches and estimates financial loss.

### Spend Intelligence
Detects overstock, discount anomalies, and low-stock risk.

### Orchestrator
Combines all agents and produces a financial before/after model.

## Screens Available

- Dashboard
- Inventory
- Drugs
- Suppliers
- Patients
- Billing
- Alerts
- Reports
- Audit Log
- Notifications
- FinAgent AI

## Installation

```bash
pip install -r requirements.txt
```

## Run the Project

```bash
python app.py
```

Then open:

```bash
http://127.0.0.1:5000
```

## Default Login

- Admin: `admin`
- Password: `admin123`

- Pharmacist: `pharma1`
- Password: `pharma123`

## Why This Project Stands Out

This project is not just a CRUD system. It combines:
- Live database operations.
- Financial impact calculations.
- Automated risk detection.
- Auditability.
- Action-oriented workflow design.

## Future Improvements

- Add charts and visual analytics to the dashboard.
- Improve role permissions and authentication security.
- Add API endpoints for integration.
- Deploy on cloud hosting.
- Add unit tests and CI/CD.

## License

For educational and portfolio use.
