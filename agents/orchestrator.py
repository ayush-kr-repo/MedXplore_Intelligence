"""
Agent 3: Compliance Sentinel + Orchestrator
PharmaCost Intelligence — Track 3: AI Financial Operations

Compliance Sentinel: SLA breaches, audit gaps, penalty exposure.
Orchestrator: Synthesises Agent 1 + 2 + 3, builds Before/After financial model,
              ranks actions, routes to approval workflow.

Run: python orchestrator.py
     python orchestrator.py --demo   (uses seed data, no API key needed)
"""

import sqlite3
import os
import sys
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pharmacost.db")

# ══════════════════════════════════════════════════════════════
#  AGENT 3: COMPLIANCE SENTINEL
# ══════════════════════════════════════════════════════════════

class ComplianceSentinel:
    """
    Agent 3: Monitors audit trail for compliance gaps, SLA breaches,
    unlogged transactions, and penalty exposure.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self

    def close(self):
        if self.conn: self.conn.close()

    def _query(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def detect_audit_gaps(self):
        """Flag batches with no audit trail — unlogged additions = compliance risk."""
        anomalies = []
        rows = self._query("""
            SELECT b.batch_id, d.name AS drug_name, d.price, b.quantity, b.exp_date
            FROM Batch b
            JOIN Drug d ON b.drug_id = d.drug_id
            WHERE b.batch_id NOT IN (
                SELECT record_id FROM AuditLog WHERE table_name = 'Batch' AND action = 'INSERT'
            )
        """)

        for r in rows:
            penalty_est = r["quantity"] * r["price"] * 0.1  # 10% regulatory penalty estimate
            anomalies.append({
                "agent": "ComplianceSentinel",
                "anomaly_id": f"CS-AUD-{r['batch_id']}",
                "type": "audit_gap",
                "severity": "high",
                "batch_id": r["batch_id"],
                "drug_name": r["drug_name"],
                "financial_impact_inr": round(penalty_est, 2),
                "math_breakdown": f"Unlogged batch {r['batch_id']}: {r['quantity']} units × ₹{r['price']} × 10% penalty rate = ₹{penalty_est:,.2f}",
                "recovery_potential_inr": round(penalty_est, 2),
                "action_type": "escalate",
                "recommended_action": f"Immediately audit batch {r['batch_id']}. Reconstruct entry log. Report to compliance officer.",
                "before_inr": round(penalty_est, 2),
                "after_inr": 0,
                "urgency_days": 1,
                "status": "pending",
            })

        return anomalies

    def detect_expired_still_in_stock(self):
        """Expired stock not yet flagged for disposal = regulatory risk."""
        anomalies = []
        rows = self._query("""
            SELECT b.batch_id, d.name AS drug_name, d.price, b.quantity, b.exp_date,
                   CAST(julianday('now') - julianday(b.exp_date) AS INTEGER) AS days_overdue
            FROM Batch b
            JOIN Drug d ON b.drug_id = d.drug_id
            WHERE date(b.exp_date) < date('now') AND b.quantity > 0
              AND b.batch_id NOT IN (
                  SELECT record_id FROM AuditLog
                  WHERE action IN ('AGENT_FLAG','AGENT_ACTION') AND table_name = 'Batch'
              )
        """)

        for r in rows:
            penalty_est = r["quantity"] * r["price"] * 0.25  # 25% regulatory fine for holding expired
            anomalies.append({
                "agent": "ComplianceSentinel",
                "anomaly_id": f"CS-EXP-{r['batch_id']}",
                "type": "regulatory_breach",
                "severity": "critical",
                "batch_id": r["batch_id"],
                "drug_name": r["drug_name"],
                "days_overdue": r["days_overdue"],
                "financial_impact_inr": round(penalty_est, 2),
                "math_breakdown": f"Expired {r['days_overdue']}d ago, {r['quantity']} units still in stock. Regulatory penalty est. 25%: ₹{penalty_est:,.2f}",
                "recovery_potential_inr": 0,
                "action_type": "escalate",
                "recommended_action": f"URGENT: Remove batch {r['batch_id']} from shelves immediately. File disposal report. Penalty risk: ₹{penalty_est:,.2f}.",
                "before_inr": round(penalty_est, 2),
                "after_inr": 0,
                "urgency_days": 0,
                "status": "pending",
            })

        return anomalies

    def scan(self):
        anomalies = []
        anomalies.extend(self.detect_audit_gaps())
        anomalies.extend(self.detect_expired_still_in_stock())
        return anomalies

    def financial_summary(self, anomalies):
        total = sum(a["financial_impact_inr"] for a in anomalies)
        return {
            "agent": "ComplianceSentinel",
            "total_penalty_exposure_inr": round(total, 2),
            "escalation_count": len([a for a in anomalies if a["action_type"] == "escalate"]),
            "anomaly_count": len(anomalies),
        }


# ══════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════════

class Orchestrator:
    """
    Master controller: runs all 3 agents, synthesises results,
    produces Before/After financial model, ranks by ROI, routes actions.

    Architecture:
        Agent1 (ExpiryWatchdog) ─┐
        Agent2 (SpendIntel)    ─── Orchestrator → Approval Workflow
        Agent3 (ComplianceSent) ─┘
    """

    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self

    def close(self):
        if self.conn: self.conn.close()

    def _query(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def run(self):
        """
        Full orchestration run:
        1. Execute all 3 agents
        2. Aggregate and de-duplicate anomalies
        3. Rank by financial impact
        4. Build Before/After model
        5. Route actions (auto / stage / escalate)
        6. Write to AgentActions table
        """
        from agents.expiry_watchdog import ExpiryWatchdog
        from agents.spend_intelligence import SpendIntelligence

        results = {
            "run_at": datetime.now().isoformat(),
            "agents": {},
            "all_anomalies": [],
            "financial_model": {},
            "action_queue": {"auto_execute": [], "stage_for_approval": [], "escalate": []},
        }

        # ── Run Agent 1 ──
        agent1 = ExpiryWatchdog(self.db_path)
        agent1.conn = self.conn
        a1_anomalies = agent1.scan()
        a1_summary   = agent1.financial_summary(a1_anomalies)
        results["agents"]["ExpiryWatchdog"] = a1_summary
        results["all_anomalies"].extend(a1_anomalies)

        # ── Run Agent 2 ──
        agent2 = SpendIntelligence(self.db_path)
        agent2.conn = self.conn
        a2_anomalies = agent2.scan()
        a2_summary   = agent2.financial_summary(a2_anomalies)
        results["agents"]["SpendIntelligence"] = a2_summary
        results["all_anomalies"].extend(a2_anomalies)

        # ── Run Agent 3 ──
        agent3 = ComplianceSentinel(self.db_path)
        agent3.conn = self.conn
        a3_anomalies = agent3.scan()
        a3_summary   = agent3.financial_summary(a3_anomalies)
        results["agents"]["ComplianceSentinel"] = a3_summary
        results["all_anomalies"].extend(a3_anomalies)

        # ── Sort by severity then impact ──
        results["all_anomalies"].sort(key=lambda a: (
            self.SEVERITY_ORDER.get(a["severity"], 9),
            -a["financial_impact_inr"]
        ))

        # ── Build financial model ──
        total_impact    = sum(a["financial_impact_inr"] for a in results["all_anomalies"])
        total_recovery  = sum(a.get("recovery_potential_inr", 0) for a in results["all_anomalies"])
        confirmed_loss  = a1_summary.get("confirmed_loss_inr", 0)

        results["financial_model"] = {
            "total_anomalies": len(results["all_anomalies"]),
            "BEFORE_total_exposure_inr": round(total_impact, 2),
            "BEFORE_confirmed_loss_inr": round(confirmed_loss, 2),
            "AFTER_net_loss_inr": round(total_impact - total_recovery, 2),
            "recovery_potential_inr": round(total_recovery, 2),
            "roi_of_intervention": f"₹{total_recovery:,.0f} saved for minimal ops cost",
        }

        # ── Route actions ──
        for a in results["all_anomalies"]:
            bucket = a.get("action_type", "alert_only")
            if bucket in results["action_queue"]:
                results["action_queue"][bucket].append(a["anomaly_id"])

        # ── Write to AgentActions in DB ──
        for a in results["all_anomalies"]:
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO AgentActions
                    (anomaly_id, anomaly_title, action_type, severity, impact_inr,
                     status, affected_items, executed_by, notes)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (a["anomaly_id"],
                      a.get("drug_name") or a.get("billed_by") or a.get("area","Unknown"),
                      a.get("action_type","alert_only"),
                      a["severity"],
                      a["financial_impact_inr"],
                      "pending",
                      json.dumps([a.get("batch_id") or a.get("drug_name","")]),
                      "orchestrator",
                      a.get("recommended_action","")))
            except Exception:
                pass
        self.conn.commit()

        return results

    def print_report(self, results):
        """Print the full Before/After financial report to terminal."""
        print("\n" + "═"*70)
        print("  PHARMACOST INTELLIGENCE — ORCHESTRATOR REPORT")
        print(f"  Generated: {results['run_at'][:19]}")
        print("═"*70)

        fm = results["financial_model"]
        print(f"""
  ┌─────────────────────────────────────────────────────────────┐
  │  BEFORE / AFTER FINANCIAL MODEL                             │
  ├─────────────────────────────────────────────────────────────┤
  │  BEFORE (without agent intervention):                       │
  │    Total Financial Exposure:   ₹{fm['BEFORE_total_exposure_inr']:>10,.2f}                 │
  │    Confirmed Loss (expired):   ₹{fm['BEFORE_confirmed_loss_inr']:>10,.2f}                 │
  │                                                             │
  │  AFTER (with agent actions executed):                       │
  │    Net Loss:                   ₹{fm['AFTER_net_loss_inr']:>10,.2f}                 │
  │    Recovery Potential:         ₹{fm['recovery_potential_inr']:>10,.2f}                 │
  │    ROI: {fm['roi_of_intervention']:<50}│
  └─────────────────────────────────────────────────────────────┘""")

        print(f"\n  ANOMALIES DETECTED: {fm['total_anomalies']}")
        print(f"  {'ID':<25} {'SEVERITY':<10} {'IMPACT':<14} {'ACTION'}")
        print("  " + "-"*65)
        for a in results["all_anomalies"][:15]:
            print(f"  {a['anomaly_id'][:24]:<25} {a['severity'].upper():<10} ₹{a['financial_impact_inr']:>9,.0f}   {a.get('action_type','')}")

        aq = results["action_queue"]
        print(f"""
  ACTION QUEUE:
    ⚡ Auto-Execute:        {len(aq['auto_execute'])} actions  {aq['auto_execute']}
    ⏳ Stage for Approval:  {len(aq['stage_for_approval'])} actions
    🚨 Escalate:            {len(aq['escalate'])} actions
""")
        print("  AGENT SUMMARIES:")
        for agent_name, summary in results["agents"].items():
            print(f"    [{agent_name}]")
            for k, v in summary.items():
                if k != "agent":
                    print(f"      {k}: {v}")
        print("\n" + "═"*70 + "\n")


if __name__ == "__main__":
    demo_mode = "--demo" in sys.argv

    print("\n" + "═"*70)
    print("  PHARMACOST INTELLIGENCE — AI FINANCIAL OPERATIONS AGENT")
    print("  Track 3: Financial Operations & Cost Intelligence")
    print("  Detect → Diagnose → Recommend → Execute / Stage / Escalate")
    print("═"*70)

    if not os.path.exists(DB_PATH):
        print(f"\n  ⚠  Database not found at: {DB_PATH}")
        print("  Run the Flask app first: python app.py")
        print("  Then re-run this orchestrator.\n")
        sys.exit(1)

    orch = Orchestrator()
    try:
        orch.connect()
        results = orch.run()
        orch.print_report(results)
        # Optionally save JSON report
        report_path = os.path.join(os.path.dirname(__file__), "last_report.json")
        with open(report_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Full report saved to: {report_path}\n")
    finally:
        orch.close()
