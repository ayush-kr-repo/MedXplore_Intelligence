"""
Agent 1: Expiry Watchdog
PharmaCost Intelligence — Track 3: AI Financial Operations

Detects → Classifies → Quantifies write-off risk from expired and near-expiry stock.
Works standalone (no API key needed) or with Claude for deeper diagnosis.
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pharmacost.db")


class ExpiryWatchdog:
    """
    Agent 1: Monitors inventory for expiry-related financial breaches.
    Operational signals → Financial impact → Action recommendation.
    """

    SEVERITY_RULES = {
        "expired":  {"label": "CRITICAL", "action": "auto_execute",        "recovery_pct": 0.0},
        "critical": {"label": "HIGH",     "action": "stage_for_approval",  "recovery_pct": 0.6},
        "warning":  {"label": "MEDIUM",   "action": "alert_only",          "recovery_pct": 0.85},
    }

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self

    def close(self):
        if self.conn:
            self.conn.close()

    def _query(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def scan(self):
        """
        Full scan: detect all expiry anomalies, classify by severity,
        quantify financial impact (INR), recommend action.
        Returns list of anomaly dicts.
        """
        anomalies = []

        # ── Expired batches (confirmed loss) ──
        expired = self._query("""
            SELECT b.batch_id, d.name AS drug_name, d.category, d.price,
                   b.exp_date, b.quantity, b.location, s.name AS supplier,
                   CAST(julianday('now') - julianday(b.exp_date) AS INTEGER) AS days_overdue
            FROM Batch b
            JOIN Drug d ON b.drug_id = d.drug_id
            LEFT JOIN Supplier s ON b.supplier_id = s.supplier_id
            WHERE date(b.exp_date) < date('now')
            ORDER BY b.quantity * d.price DESC
        """)

        for row in expired:
            loss = row["quantity"] * row["price"]
            recovery = 0.0  # expired = total loss
            anomalies.append({
                "agent": "ExpiryWatchdog",
                "anomaly_id": f"EW-EXP-{row['batch_id']}",
                "type": "expiry_loss",
                "severity": "critical",
                "batch_id": row["batch_id"],
                "drug_name": row["drug_name"],
                "category": row["category"],
                "exp_date": row["exp_date"],
                "days_overdue": row["days_overdue"],
                "quantity": row["quantity"],
                "unit_price": row["price"],
                "supplier": row["supplier"],
                "financial_impact_inr": round(loss, 2),
                "math_breakdown": f"{row['quantity']} units × ₹{row['price']}/unit = ₹{loss:,.2f}",
                "recovery_potential_inr": recovery,
                "action_type": "auto_execute",
                "recommended_action": f"Immediately flag batch {row['batch_id']} for supplier return or disposal. Log write-off of ₹{loss:,.2f}.",
                "before_inr": round(loss, 2),
                "after_inr": 0,
                "urgency_days": 0,
                "status": "pending",
            })

        # ── Critical batches (expiring < 30 days) ──
        critical = self._query("""
            SELECT b.batch_id, d.name AS drug_name, d.category, d.price,
                   b.exp_date, b.quantity, b.location, s.name AS supplier,
                   CAST(julianday(b.exp_date) - julianday('now') AS INTEGER) AS days_left
            FROM Batch b
            JOIN Drug d ON b.drug_id = d.drug_id
            LEFT JOIN Supplier s ON b.supplier_id = s.supplier_id
            WHERE date(b.exp_date) >= date('now')
              AND date(b.exp_date) <= date('now', '+30 days')
            ORDER BY b.quantity * d.price DESC
        """)

        for row in critical:
            at_risk = row["quantity"] * row["price"]
            recovery = at_risk * 0.6  # 60% recoverable via urgent dispensing
            anomalies.append({
                "agent": "ExpiryWatchdog",
                "anomaly_id": f"EW-CRIT-{row['batch_id']}",
                "type": "expiry_loss",
                "severity": "high",
                "batch_id": row["batch_id"],
                "drug_name": row["drug_name"],
                "category": row["category"],
                "exp_date": row["exp_date"],
                "days_left": row["days_left"],
                "quantity": row["quantity"],
                "unit_price": row["price"],
                "supplier": row["supplier"],
                "financial_impact_inr": round(at_risk, 2),
                "math_breakdown": f"{row['quantity']} units × ₹{row['price']}/unit = ₹{at_risk:,.2f} at risk",
                "recovery_potential_inr": round(recovery, 2),
                "action_type": "stage_for_approval",
                "recommended_action": f"Prioritise dispensing of batch {row['batch_id']} ({row['days_left']} days left). Contact supplier for return. Estimated ₹{recovery:,.2f} recoverable.",
                "before_inr": round(at_risk, 2),
                "after_inr": round(at_risk - recovery, 2),
                "urgency_days": row["days_left"],
                "status": "pending",
            })

        # ── Warning batches (expiring 30–90 days) ──
        warning = self._query("""
            SELECT b.batch_id, d.name AS drug_name, d.category, d.price,
                   b.exp_date, b.quantity, s.name AS supplier,
                   CAST(julianday(b.exp_date) - julianday('now') AS INTEGER) AS days_left
            FROM Batch b
            JOIN Drug d ON b.drug_id = d.drug_id
            LEFT JOIN Supplier s ON b.supplier_id = s.supplier_id
            WHERE date(b.exp_date) > date('now', '+30 days')
              AND date(b.exp_date) <= date('now', '+90 days')
            ORDER BY b.quantity * d.price DESC
        """)

        for row in warning:
            at_risk = row["quantity"] * row["price"]
            recovery = at_risk * 0.85  # 85% recoverable with sufficient lead time
            anomalies.append({
                "agent": "ExpiryWatchdog",
                "anomaly_id": f"EW-WARN-{row['batch_id']}",
                "type": "expiry_loss",
                "severity": "medium",
                "batch_id": row["batch_id"],
                "drug_name": row["drug_name"],
                "category": row["category"],
                "exp_date": row["exp_date"],
                "days_left": row["days_left"],
                "quantity": row["quantity"],
                "unit_price": row["price"],
                "supplier": row["supplier"],
                "financial_impact_inr": round(at_risk * 0.15, 2),  # 15% unrecoverable risk
                "math_breakdown": f"{row['quantity']} units × ₹{row['price']}/unit = ₹{at_risk:,.2f} total; ₹{at_risk*0.15:,.2f} unrecoverable if no action",
                "recovery_potential_inr": round(recovery, 2),
                "action_type": "alert_only",
                "recommended_action": f"Schedule for accelerated dispensing within next 60 days. {row['days_left']} days window available.",
                "before_inr": round(at_risk * 0.15, 2),
                "after_inr": 0,
                "urgency_days": row["days_left"] - 30,
                "status": "pending",
            })

        return anomalies

    def financial_summary(self, anomalies):
        """Compute Before/After financial model from scan results."""
        confirmed_loss   = sum(a["financial_impact_inr"] for a in anomalies if a["severity"] == "critical")
        at_risk          = sum(a["financial_impact_inr"] for a in anomalies if a["severity"] == "high")
        recovery_possible= sum(a.get("recovery_potential_inr", 0) for a in anomalies)
        return {
            "agent": "ExpiryWatchdog",
            "confirmed_loss_inr": round(confirmed_loss, 2),
            "at_risk_inr": round(at_risk, 2),
            "total_exposure_inr": round(confirmed_loss + at_risk, 2),
            "recovery_potential_inr": round(recovery_possible, 2),
            "net_loss_without_action": round(confirmed_loss + at_risk, 2),
            "net_loss_with_action": round(confirmed_loss + at_risk - recovery_possible, 2),
            "anomaly_count": len(anomalies),
        }

    def log_action(self, batch_id, action_type, executed_by="agent"):
        """Write action to AuditLog — closes the detect→execute loop."""
        self.conn.execute("""
            INSERT INTO AuditLog(action, table_name, record_id, details, done_by)
            VALUES (?, ?, ?, ?, ?)
        """, ("AGENT_ACTION", "Batch", batch_id,
              f"ExpiryWatchdog: {action_type}", executed_by))
        self.conn.commit()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  AGENT 1: EXPIRY WATCHDOG")
    print("  PharmaCost Intelligence — Track 3")
    print("="*60)

    agent = ExpiryWatchdog()
    try:
        agent.connect()
        anomalies = agent.scan()
        summary   = agent.financial_summary(anomalies)

        print(f"\n{'ANOMALY':<15} {'DRUG':<18} {'SEVERITY':<10} {'IMPACT (₹)':<14} {'ACTION'}")
        print("-"*75)
        for a in anomalies:
            print(f"{a['anomaly_id'][:14]:<15} {a['drug_name'][:17]:<18} {a['severity'].upper():<10} ₹{a['financial_impact_inr']:>10,.0f}   {a['action_type']}")

        print("\n" + "─"*60)
        print("  BEFORE / AFTER FINANCIAL MODEL")
        print("─"*60)
        print(f"  Confirmed Loss (expired):     ₹{summary['confirmed_loss_inr']:>10,.2f}")
        print(f"  At-Risk Value (expiring):     ₹{summary['at_risk_inr']:>10,.2f}")
        print(f"  Total Exposure:               ₹{summary['total_exposure_inr']:>10,.2f}")
        print(f"  ─────────────────────────────────────────")
        print(f"  WITHOUT action — net loss:    ₹{summary['net_loss_without_action']:>10,.2f}")
        print(f"  WITH action — net loss:       ₹{summary['net_loss_with_action']:>10,.2f}")
        print(f"  Recovery Potential:           ₹{summary['recovery_potential_inr']:>10,.2f}")
        print("─"*60)
        print(f"\n  {len(anomalies)} anomalies detected. Run orchestrator.py for full report.\n")
    finally:
        agent.close()
