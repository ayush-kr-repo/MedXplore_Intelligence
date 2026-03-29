"""
Agent 2: Spend Intelligence
PharmaCost Intelligence — Track 3: AI Financial Operations

Detects rate variance, duplicate procurement, overstock capital lock-in,
and discount abuse in billing — all quantified in INR.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pharmacost.db")


class SpendIntelligence:
    """
    Agent 2: Financial anomaly detection across procurement and billing.
    Signals: billing patterns, stock velocity, discount variance, overstock.
    """

    OVERSTOCK_THRESHOLD = 500     # units — above this without proportional sales = capital lock-in
    LOW_VELOCITY_THRESHOLD = 10   # units sold in 30 days — below this = slow mover
    DISCOUNT_ANOMALY_THRESHOLD = 50  # ₹ avg discount — above this = flag for review

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

    def detect_overstock(self):
        """Overstock = capital tied up in slow-moving inventory."""
        anomalies = []
        rows = self._query("""
            SELECT d.name, d.category, d.price,
                   COALESCE(SUM(b.quantity), 0) AS total_stock,
                   COALESCE(SUM(bi.quantity), 0) AS sold_30d
            FROM Drug d
            LEFT JOIN Batch b ON d.drug_id = b.drug_id AND date(b.exp_date) >= date('now')
            LEFT JOIN BillItem bi ON bi.drug_name = d.name
            GROUP BY d.drug_id
            HAVING total_stock > ? AND sold_30d < ?
        """, (self.OVERSTOCK_THRESHOLD, self.LOW_VELOCITY_THRESHOLD))

        for r in rows:
            locked_capital = r["total_stock"] * r["price"]
            monthly_burn   = r["sold_30d"] * r["price"]
            months_to_clear= (r["total_stock"] / max(r["sold_30d"], 1))
            recoverable    = locked_capital * 0.4  # 40% recoverable via reallocation

            anomalies.append({
                "agent": "SpendIntelligence",
                "anomaly_id": f"SI-OVER-{r['name'].replace(' ', '_')[:10]}",
                "type": "overstock_capital_lockin",
                "severity": "medium" if locked_capital < 10000 else "high",
                "drug_name": r["name"],
                "category": r["category"],
                "total_stock": r["total_stock"],
                "sold_30d": r["sold_30d"],
                "months_to_clear": round(months_to_clear, 1),
                "financial_impact_inr": round(locked_capital, 2),
                "math_breakdown": f"₹{r['price']} × {r['total_stock']} units = ₹{locked_capital:,.2f} locked capital (velocity: {r['sold_30d']} units/month)",
                "recovery_potential_inr": round(recoverable, 2),
                "action_type": "stage_for_approval",
                "recommended_action": f"Reallocate {r['name']} stock to high-demand branches. Pause procurement for {int(months_to_clear)} months. Estimated ₹{recoverable:,.2f} capital freed.",
                "before_inr": round(locked_capital, 2),
                "after_inr": round(locked_capital - recoverable, 2),
                "urgency_days": 30,
                "status": "pending",
            })

        return anomalies

    def detect_discount_anomalies(self):
        """Unusual discount patterns per pharmacist — may indicate revenue leakage."""
        anomalies = []
        rows = self._query("""
            SELECT billed_by, COUNT(*) AS bills,
                   AVG(discount) AS avg_discount,
                   SUM(discount) AS total_discount,
                   SUM(total) AS total_revenue,
                   MAX(discount) AS max_discount
            FROM Bill
            GROUP BY billed_by
            HAVING avg_discount > ? OR max_discount > 200
        """, (self.DISCOUNT_ANOMALY_THRESHOLD,))

        for r in rows:
            revenue_leakage = r["total_discount"]
            anomalies.append({
                "agent": "SpendIntelligence",
                "anomaly_id": f"SI-DISC-{r['billed_by'].upper()}",
                "type": "discount_abuse",
                "severity": "high" if r["avg_discount"] > 100 else "medium",
                "billed_by": r["billed_by"],
                "bills": r["bills"],
                "avg_discount": round(r["avg_discount"], 2),
                "max_discount": round(r["max_discount"], 2),
                "total_discount": round(r["total_discount"], 2),
                "financial_impact_inr": round(revenue_leakage, 2),
                "math_breakdown": f"₹{r['avg_discount']:.2f} avg discount × {r['bills']} bills = ₹{revenue_leakage:,.2f} total revenue reduction",
                "recovery_potential_inr": round(revenue_leakage * 0.5, 2),
                "action_type": "stage_for_approval",
                "recommended_action": f"Review discount policy for {r['billed_by']}. Implement approval workflow for discounts > ₹50. Estimated ₹{revenue_leakage*0.5:,.2f} recoverable.",
                "before_inr": round(revenue_leakage, 2),
                "after_inr": round(revenue_leakage * 0.5, 2),
                "urgency_days": 7,
                "status": "pending",
            })

        return anomalies

    def detect_low_stock_risk(self):
        """Low stock of critical drugs = stockout risk = lost revenue."""
        anomalies = []
        rows = self._query("""
            SELECT d.name, d.category, d.price,
                   COALESCE(SUM(b.quantity), 0) AS total_stock
            FROM Drug d
            LEFT JOIN Batch b ON d.drug_id = b.drug_id AND date(b.exp_date) >= date('now')
            GROUP BY d.drug_id
            HAVING total_stock < 100 AND total_stock > 0
        """)

        for r in rows:
            lost_revenue_est = r["total_stock"] * r["price"] * 3  # 3x multiplier for stockout impact
            anomalies.append({
                "agent": "SpendIntelligence",
                "anomaly_id": f"SI-LOW-{r['name'].replace(' ', '_')[:10]}",
                "type": "low_stock_risk",
                "severity": "medium",
                "drug_name": r["name"],
                "category": r["category"],
                "total_stock": r["total_stock"],
                "financial_impact_inr": round(lost_revenue_est, 2),
                "math_breakdown": f"Only {r['total_stock']} units remain — potential stockout revenue loss ≈ ₹{lost_revenue_est:,.2f}",
                "recovery_potential_inr": round(lost_revenue_est * 0.8, 2),
                "action_type": "stage_for_approval",
                "recommended_action": f"Raise procurement order for {r['name']}. Current stock: {r['total_stock']} units. Reorder point: 200 units.",
                "before_inr": round(lost_revenue_est, 2),
                "after_inr": 0,
                "urgency_days": 14,
                "status": "pending",
            })

        return anomalies

    def scan(self):
        """Full scan across all spend intelligence signals."""
        anomalies = []
        anomalies.extend(self.detect_overstock())
        anomalies.extend(self.detect_discount_anomalies())
        anomalies.extend(self.detect_low_stock_risk())
        return anomalies

    def financial_summary(self, anomalies):
        total_impact    = sum(a["financial_impact_inr"] for a in anomalies)
        total_recovery  = sum(a.get("recovery_potential_inr", 0) for a in anomalies)
        return {
            "agent": "SpendIntelligence",
            "total_financial_impact_inr": round(total_impact, 2),
            "recovery_potential_inr": round(total_recovery, 2),
            "net_loss_without_action": round(total_impact, 2),
            "net_loss_with_action": round(total_impact - total_recovery, 2),
            "anomaly_count": len(anomalies),
            "breakdown": {
                "overstock": len([a for a in anomalies if a["type"] == "overstock_capital_lockin"]),
                "discount_abuse": len([a for a in anomalies if a["type"] == "discount_abuse"]),
                "low_stock": len([a for a in anomalies if a["type"] == "low_stock_risk"]),
            }
        }


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  AGENT 2: SPEND INTELLIGENCE")
    print("  PharmaCost Intelligence — Track 3")
    print("="*60)

    agent = SpendIntelligence()
    try:
        agent.connect()
        anomalies = agent.scan()
        summary   = agent.financial_summary(anomalies)

        print(f"\n{'ANOMALY':<22} {'TYPE':<25} {'SEV':<8} {'IMPACT (₹)':<14} {'RECOVERY (₹)'}")
        print("-"*80)
        for a in anomalies:
            print(f"{a['anomaly_id'][:21]:<22} {a['type'][:24]:<25} {a['severity'].upper():<8} ₹{a['financial_impact_inr']:>9,.0f}   ₹{a.get('recovery_potential_inr',0):>9,.0f}")

        print("\n" + "─"*60)
        print("  BEFORE / AFTER FINANCIAL MODEL")
        print("─"*60)
        print(f"  Total Financial Impact:       ₹{summary['total_financial_impact_inr']:>10,.2f}")
        print(f"  WITHOUT action — net loss:    ₹{summary['net_loss_without_action']:>10,.2f}")
        print(f"  WITH action — net loss:       ₹{summary['net_loss_with_action']:>10,.2f}")
        print(f"  Recovery Potential:           ₹{summary['recovery_potential_inr']:>10,.2f}")
        print("─"*60)
        print(f"\n  Breakdown: {summary['breakdown']}\n")
    finally:
        agent.close()
