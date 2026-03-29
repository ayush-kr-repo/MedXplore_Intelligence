# 💊 PharmaCost Intelligence
### AI-Powered Drug Expiry & Financial Operations Agent
**Track 3 — AI for Financial Operations & Cost Intelligence**

> Built on top of DrugWatch (DBMS Project) · B.Tech CSE · KIIT University

---

## 👥 Team

| Name | Roll No |
|------|---------|
| Ayush Kumar | 24155916 |
| Anubhab Das | 24155906 |
| Abhijoy Debnath | 24155928 |
| Aditya Sengupta | 24155302 |

---

## 🎯 Problem Statement (Track 3)

Pharmacies and hospital formularies lose **₹2,000–8,000 crore annually** to drug expiry write-offs, overstock capital lock-in, and procurement inefficiency — primarily because detection is manual and reaction is always late. This system replaces passive reporting with **autonomous financial agents** that detect breaches from operational signals, quantify rupee impact, and take corrective action before losses land.

---

## ⚡ The Agentic Architecture

```
Enterprise Data Sources
    InventoryDB  →  Agent 1: Expiry Watchdog    (Detect → Classify → Quantify write-off risk)
    BillingDB    →  Agent 2: Spend Intelligence  (Rate variance, overstock, discount anomalies)
    AuditLogs    →  Agent 3: Compliance Sentinel (SLA breaches, penalty exposure, audit gaps)
                              ↓
                      Orchestrator (Claude claude-sonnet-4-20250514)
                 Root-cause synthesis · Before/After ₹ model
                 Action ranking · ROI calculation · Penalty math
                              ↓
              Enterprise Approval Workflow
           ┌──────────────┬──────────────┐
      Auto-Execute   Stage for Approval  Escalate
   (Flag expired)   (Procurement)    (Regulatory)
                              ↓
              Downstream Workflow Triggers (NEW)
         Email · Slack · ERP Webhook · Regulatory Alert
```

---

## 📊 Before / After Financial Model (Demo Data)

| Metric | Before Agent | After Agent | Δ Saved |
|--------|-------------|------------|---------|
| Confirmed Expiry Loss | ₹14,960 | ₹14,960 | — (already lost) |
| At-Risk Expiring Stock | ₹20,400 | ₹8,160 | **₹12,240** |
| Overstock Capital Lock-in | ₹37,200 | ₹22,320 | **₹14,880** |
| Regulatory Penalty Exposure | ₹15,570 | ₹0 | **₹15,570** |
| Discount Revenue Leakage | — | — | Ongoing |
| **Total Recovery Potential** | — | — | **₹42,690+** |

> All numbers calculated deterministically: `quantity × unit_price × recovery_factor`. No magic numbers.

---

## 🤖 3 Agents — What Each One Does

### Agent 1: Expiry Watchdog (`agents/expiry_watchdog.py`)
- **Signal**: `vw_ExpiredBatches`, `vw_ExpiringBatches`
- **Detects**: Confirmed losses (expired), at-risk stock (<30d), warning stock (<90d)
- **Quantifies**: `quantity × price` per batch → exact INR impact
- **Action**: Auto-flags expired batches · Stages critical for approval · Alerts warning

### Agent 2: Spend Intelligence (`agents/spend_intelligence.py`)
- **Signal**: `Bill`, `BillItem`, `Batch`, `Drug`
- **Detects**: Overstock capital lock-in, slow-moving inventory, discount abuse, stockout risk
- **Quantifies**: Capital locked = `stock × price`; Revenue leakage = `avg_discount × bill_count`
- **Action**: Stages procurement reallocation · Flags discount anomalies for admin review

### Agent 3: Compliance Sentinel + Orchestrator (`agents/orchestrator.py`)
- **Signal**: `AuditLog`, `AgentActions`, `sla_penalty_signals`, `audit_gap_batches`
- **Detects**: Batches with no audit trail, expired stock not yet flagged, SLA breach
- **Quantifies**: Regulatory penalty = `quantity × price × 15% penalty_rate` (CDSCO standard)
- **Orchestrates**: Runs all 3 agents → synthesises → Before/After model → routes to approval

---

## 🔁 The Full Loop

```
1. DETECT    → Agent reads operational DB signals (not reports, raw signals)
2. DIAGNOSE  → Root cause attributed per anomaly (e.g. "slow procurement cycle")
3. RECOMMEND → Specific action with rupee math shown ("flag B003 → recover ₹7,200")
4. EXECUTE   → auto_execute / stage_for_approval / escalate
5. LOG       → Every action written to AuditLog via SQL triggers (full paper trail)
6. NOTIFY    → Downstream triggers fired: Email + Slack + ERP webhook + Regulatory alert ← NEW
```

All 6 steps are live in the system — not mocked.

---

## 📬 Downstream Workflow Triggers (NEW)

Every agent action automatically fires multi-channel notifications logged to the `Notifications` table:

| Channel | Trigger Condition | Recipient |
|---------|------------------|-----------|
| **Email** | Every action execution | admin@pharmacost.in |
| **Slack** | Critical / High severity only | #pharmacy-alerts |
| **ERP Webhook** | Stage/Approve + impact > ₹5,000 | procurement-module |
| **Regulatory** | SLA breach / penalty exposure | compliance@pharmacost.in |

View all fired notifications at `/notifications` — full channel, recipient, body, timestamp log.

---

## 🚀 Quick Start

```bash
# 1. Install
pip install flask reportlab

# 2. Set Anthropic API key (required for /agent FinAgent page)
# Windows PowerShell:
$env:ANTHROPIC_API_KEY="sk-ant-api03-your-key-here"

# Linux/Mac:
export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# 3. Run
python app.py
# Open http://127.0.0.1:5000
# Login: admin / admin123
```

---

## 🌐 Web Interface Pages

| URL | What It Shows |
|-----|--------------|
| `/dashboard` | Financial risk banner + live stats |
| `/agent` | **FinAgent AI** — full Track 3 interface, Claude-powered |
| `/alerts` | All expiry alerts with ₹ loss estimates |
| `/inventory` | Batch-level stock with expiry status |
| `/billing` | Atomic transaction billing |
| `/reports` | Revenue, expiry distribution, supplier breakdown |
| `/audit` | Full SQL trigger audit log + agent action history |
| `/notifications` | **Downstream workflow triggers** — Email, Slack, ERP, Regulatory ← NEW |

---

## 🗄️ Database Design

### Tables (11)
`Drug`, `Batch`, `Supplier`, `MedicineCatalog`, `Patient`, `Bill`, `BillItem`, `Users`, `AuditLog`, `AgentActions`, **`Notifications`** ← new for downstream triggers

### Views (4)
`vw_Inventory`, `vw_ExpiredBatches`, `vw_ExpiringBatches`, `vw_BillSummary`

### Triggers (4)
Auto-log every INSERT/UPDATE/DELETE on Batch and Bill → AuditLog

### Constraints
`CHECK(quantity >= 0)`, `CHECK(role IN ('admin','pharmacist'))`, `FOREIGN KEY ON DELETE CASCADE`, `NOT NULL` on critical fields

---

## 📁 Project Structure

```
pharmacost/
├── app.py                    ← Flask app + all routes + AI agent + notification engine
├── README.md
├── agents/
│   ├── expiry_watchdog.py    ← Agent 1: Expiry loss detection
│   ├── spend_intelligence.py ← Agent 2: Overstock, discount, low stock
│   └── orchestrator.py       ← Agent 3 + Master orchestrator
└── templates/
    ├── base.html             ← Sidebar layout
    ├── login.html
    ├── dashboard.html        ← Financial risk banner
    ├── agent.html            ← FinAgent AI (Track 3 core)
    ├── notifications.html    ← Downstream workflow triggers ← NEW
    ├── inventory.html
    ├── alerts.html
    ├── billing.html
    ├── bills.html
    ├── bill_detail.html
    ├── drugs.html
    ├── patients.html
    ├── patient_detail.html
    ├── suppliers.html
    ├── reports.html
    └── audit.html
```

---

## 🔐 Login Credentials

| Role | Username | Password | Access |
|------|----------|----------|--------|
| Admin | `admin` | `admin123` | Full — agent execution, approval, audit, notifications |
| Pharmacist | `pharma1` | `pharma123` | Inventory, billing, alerts |

---

## 📚 DBMS Concepts Demonstrated

✅ ER Modeling · ✅ Normalization (3NF) · ✅ SQL DDL/DML · ✅ Views · ✅ Triggers
✅ Foreign Keys · ✅ Transactions (atomic billing) · ✅ Role-based Access Control
✅ **Agentic AI Layer** · ✅ **Before/After Financial Modelling** · ✅ **Enterprise Approval Workflow**
✅ **SLA & Penalty Quantification** · ✅ **Downstream Workflow Triggers** · ✅ **Multi-channel Notifications**

---

## 📄 License

Submitted for hackathon — Track 3: AI for Financial Operations & Cost Intelligence.
Built on DBMS university project (KIIT University). For educational/competition purposes.
