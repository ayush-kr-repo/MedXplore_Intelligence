"""
PharmaCost Intelligence — AI Financial Operations Agent
Track 3: AI for Financial Operations & Cost Intelligence

Works on ANY dataset:
  - Drop medicine_dataset.csv → auto-imports on first run
  - Or use the web UI to add drugs/batches manually
  - Or use /admin/import to bulk-import via CSV upload
  - Seed data is demo-only; real data takes over automatically

Run: python app.py
     Then open http://127.0.0.1:5000
"""

import sqlite3, os, csv, io, json, urllib.request
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, g, jsonify, send_file)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pharmacost_agent_2024")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "pharmacost.db")
CSV_PATH = os.path.join(BASE_DIR, "medicine_dataset.csv")

# ══════════════════════════════════════════════════════════════
#  SCHEMA — works on empty DB or any pre-existing data
# ══════════════════════════════════════════════════════════════
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS MedicineCatalog (
    med_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    therapeutic_class TEXT, chemical_class TEXT, habit_forming TEXT,
    action_class TEXT, uses TEXT, side_effects TEXT, substitutes TEXT
);
CREATE TABLE IF NOT EXISTS Drug (
    drug_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'General',
    manufacturer TEXT NOT NULL DEFAULT 'Unknown', price REAL NOT NULL DEFAULT 0.0,
    med_id INTEGER, FOREIGN KEY (med_id) REFERENCES MedicineCatalog(med_id)
);
CREATE TABLE IF NOT EXISTS Supplier (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, contact TEXT, address TEXT
);
CREATE TABLE IF NOT EXISTS Batch (
    batch_id TEXT PRIMARY KEY, drug_id INTEGER NOT NULL,
    supplier_id INTEGER, mfg_date TEXT NOT NULL DEFAULT (date('now','-1 year')),
    exp_date TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0),
    location TEXT DEFAULT 'Main Store',
    FOREIGN KEY (drug_id) REFERENCES Drug(drug_id) ON DELETE CASCADE,
    FOREIGN KEY (supplier_id) REFERENCES Supplier(supplier_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK(role IN ('admin','pharmacist')),
    password TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Patient (
    patient_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    phone TEXT, email TEXT, address TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS Bill (
    bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL UNIQUE, patient_id TEXT,
    billed_by TEXT NOT NULL, bill_date TEXT DEFAULT (datetime('now')),
    subtotal REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0,
    gst_pct REAL NOT NULL DEFAULT 0, gst_amount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0, payment_method TEXT DEFAULT 'Cash', notes TEXT,
    FOREIGN KEY (patient_id) REFERENCES Patient(patient_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS BillItem (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL, batch_id TEXT NOT NULL,
    drug_name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL, amount REAL NOT NULL,
    FOREIGN KEY (bill_id) REFERENCES Bill(bill_id) ON DELETE CASCADE,
    FOREIGN KEY (batch_id) REFERENCES Batch(batch_id)
);
CREATE TABLE IF NOT EXISTS AuditLog (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL, table_name TEXT NOT NULL,
    record_id TEXT NOT NULL, details TEXT,
    done_by TEXT DEFAULT 'system',
    timestamp TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS AgentActions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id TEXT NOT NULL UNIQUE, anomaly_title TEXT,
    action_type TEXT NOT NULL, severity TEXT,
    impact_inr REAL DEFAULT 0, status TEXT DEFAULT 'pending',
    affected_items TEXT, executed_by TEXT, executed_at TEXT, notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS Notifications (
    notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    triggered_by TEXT DEFAULT 'system',
    anomaly_id TEXT,
    impact_inr REAL DEFAULT 0,
    status TEXT DEFAULT 'sent',
    sent_at TEXT DEFAULT (datetime('now'))
);

-- TRIGGERS: auto-audit every change
CREATE TRIGGER IF NOT EXISTS trg_batch_insert AFTER INSERT ON Batch BEGIN
    INSERT INTO AuditLog(action,table_name,record_id,details)
    VALUES('INSERT','Batch',NEW.batch_id,'DrugID:'||NEW.drug_id||' Qty:'||NEW.quantity||' Exp:'||NEW.exp_date);
END;
CREATE TRIGGER IF NOT EXISTS trg_batch_delete AFTER DELETE ON Batch BEGIN
    INSERT INTO AuditLog(action,table_name,record_id,details)
    VALUES('DELETE','Batch',OLD.batch_id,'DrugID:'||OLD.drug_id||' WasQty:'||OLD.quantity);
END;
CREATE TRIGGER IF NOT EXISTS trg_batch_qty_update AFTER UPDATE OF quantity ON Batch BEGIN
    INSERT INTO AuditLog(action,table_name,record_id,details)
    VALUES('UPDATE','Batch',NEW.batch_id,'Qty:'||OLD.quantity||'->'||NEW.quantity);
END;
CREATE TRIGGER IF NOT EXISTS trg_bill_insert AFTER INSERT ON Bill BEGIN
    INSERT INTO AuditLog(action,table_name,record_id,details)
    VALUES('INSERT','Bill',NEW.bill_number,'Total:Rs.'||NEW.total||' By:'||NEW.billed_by);
END;

-- VIEWS: financial status computed live
CREATE VIEW IF NOT EXISTS vw_Inventory AS
SELECT b.batch_id, d.drug_id, d.name AS drug_name, d.category,
       d.manufacturer, d.price, COALESCE(s.name,'Unknown') AS supplier,
       b.mfg_date, b.exp_date, b.quantity, b.location,
       CAST(julianday(b.exp_date)-julianday('now') AS INTEGER) AS days_left,
       CASE WHEN date(b.exp_date)<date('now') THEN 'expired'
            WHEN date(b.exp_date)<=date('now','+30 days') THEN 'critical'
            WHEN date(b.exp_date)<=date('now','+90 days') THEN 'warning'
            ELSE 'good' END AS status
FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
LEFT JOIN Supplier s ON b.supplier_id=s.supplier_id;

CREATE VIEW IF NOT EXISTS vw_ExpiredBatches AS
SELECT b.batch_id, d.name AS drug_name, d.category, b.exp_date,
       b.quantity, b.location, COALESCE(s.name,'Unknown') AS supplier, d.price,
       CAST(julianday('now')-julianday(b.exp_date) AS INTEGER) AS days_overdue
FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
LEFT JOIN Supplier s ON b.supplier_id=s.supplier_id
WHERE date(b.exp_date)<date('now');

CREATE VIEW IF NOT EXISTS vw_ExpiringBatches AS
SELECT b.batch_id, d.name AS drug_name, d.category, b.exp_date,
       b.quantity, b.location, COALESCE(s.name,'Unknown') AS supplier, d.price,
       CAST(julianday(b.exp_date)-julianday('now') AS INTEGER) AS days_left
FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
LEFT JOIN Supplier s ON b.supplier_id=s.supplier_id
WHERE date(b.exp_date)>=date('now') AND date(b.exp_date)<=date('now','+90 days');

CREATE VIEW IF NOT EXISTS vw_BillSummary AS
SELECT b.bill_id, b.bill_number, b.bill_date, b.total, b.subtotal,
       b.discount, b.gst_pct, b.gst_amount, b.payment_method, b.billed_by,
       b.notes, b.patient_id,
       COALESCE(p.name,'Walk-in') AS patient_name,
       COALESCE(p.phone,'') AS patient_phone,
       COUNT(bi.item_id) AS item_count
FROM Bill b
LEFT JOIN Patient p ON b.patient_id=p.patient_id
LEFT JOIN BillItem bi ON b.bill_id=bi.bill_id
GROUP BY b.bill_id;
"""

# Minimal seed — only users. All other data entered via UI or CSV import.
SEED_SQL = """
INSERT OR IGNORE INTO Users(username,role,password) VALUES
('admin','admin','admin123'),
('pharma1','pharmacist','pharma123');
"""

# Demo data — only inserted if DB is completely empty (no drugs at all)
DEMO_SQL = """
INSERT OR IGNORE INTO Supplier(supplier_id,name,contact,address) VALUES
(1,'MedSupply Co.','9800001111','Kolkata, WB'),
(2,'PharmaDist','9800002222','Mumbai, MH'),
(3,'HealthBridge','9800003333','Delhi, DL');

INSERT OR IGNORE INTO Drug(drug_id,name,category,manufacturer,price) VALUES
(1,'Amoxicillin','Antibiotic','Sun Pharma',45.00),
(2,'Paracetamol','Analgesic','Cipla',12.00),
(3,'Metformin','Antidiabetic','Dr. Reddys',38.00),
(4,'Atorvastatin','Statin','Pfizer',95.00),
(5,'Omeprazole','Antacid','Zydus',28.00),
(6,'Cetirizine','Antihistamine','Abbott',22.00);

INSERT OR IGNORE INTO Batch(batch_id,drug_id,supplier_id,mfg_date,exp_date,quantity,location) VALUES
('B001',1,1,'2023-06-01','2025-06-01',500,'Rack A1'),
('B002',1,2,'2024-01-15','2026-01-15',300,'Rack A2'),
('B003',2,1,'2023-11-01','2025-03-20',1200,'Rack B1'),
('B004',3,3,'2022-05-10','2025-02-05',80,'Rack C2'),
('B005',4,2,'2024-03-01','2026-03-01',450,'Rack D1'),
('B006',5,1,'2023-08-20','2025-04-10',220,'Rack E1'),
('B007',6,3,'2024-02-14','2027-02-14',600,'Rack F3'),
('B008',2,2,'2024-05-01','2026-05-01',900,'Rack B2'),
('B009',3,3,'2023-09-15','2025-02-28',40,'Rack C1');

INSERT OR IGNORE INTO Patient(patient_id,name,phone,email,address) VALUES
('CUST-000001','Rajesh Kumar','9876543210','rajesh@email.com','Bhubaneswar'),
('CUST-000002','Priya Sharma','9812345678','priya@email.com','Cuttack'),
('CUST-000003','Anand Das','9898989898','anand@email.com','Puri');

INSERT OR IGNORE INTO Bill(bill_id,bill_number,patient_id,billed_by,bill_date,subtotal,discount,gst_pct,gst_amount,total,payment_method) VALUES
(1,'BILL-20250101-0001','CUST-000001','admin','2025-01-15 10:30:00',540.00,50.00,5,24.50,514.50,'Cash'),
(2,'BILL-20250102-0001','CUST-000002','pharma1','2025-01-22 14:00:00',285.00,0.00,5,14.25,299.25,'UPI'),
(3,'BILL-20250201-0001','CUST-000003','admin','2025-02-05 11:15:00',760.00,100.00,5,33.00,693.00,'Card'),
(4,'BILL-20250210-0001','CUST-000001','pharma1','2025-02-10 09:45:00',190.00,0.00,5,9.50,199.50,'Cash'),
(5,'BILL-20250301-0001','CUST-000002','admin','2025-03-01 16:20:00',475.00,25.00,5,22.50,472.50,'UPI'),
(6,'BILL-20250315-0001','CUST-000003','pharma1','2025-03-15 13:00:00',380.00,0.00,5,19.00,399.00,'Cash');

INSERT OR IGNORE INTO BillItem(bill_id,batch_id,drug_name,quantity,unit_price,amount) VALUES
(1,'B002','Amoxicillin',8,45.00,360.00),
(1,'B007','Cetirizine',8,22.00,176.00),
(2,'B008','Paracetamol',15,12.00,180.00),
(2,'B007','Cetirizine',5,22.00,110.00),
(3,'B005','Atorvastatin',6,95.00,570.00),
(3,'B008','Paracetamol',10,12.00,120.00),
(3,'B006','Omeprazole',2,28.00,56.00),
(4,'B008','Paracetamol',10,12.00,120.00),
(4,'B006','Omeprazole',2,28.00,56.00),
(5,'B002','Amoxicillin',5,45.00,225.00),
(5,'B005','Atorvastatin',2,95.00,190.00),
(6,'B005','Atorvastatin',4,95.00,380.00);
"""

# ── DB helpers ──
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()

    # Only insert demo data if absolutely no drugs exist
    drug_count = conn.execute("SELECT COUNT(*) FROM Drug").fetchone()[0]
    if drug_count == 0:
        print("[PharmaCost] Fresh database — loading demo data...")
        conn.executescript(DEMO_SQL)
        conn.commit()

    # Auto-import medicine catalog CSV if present
    cat_count = conn.execute("SELECT COUNT(*) FROM MedicineCatalog").fetchone()[0]
    if cat_count == 0 and os.path.exists(CSV_PATH):
        print("[PharmaCost] Importing medicine catalog (this takes ~30s)...")
        _import_catalog(conn)

    conn.close()
    print("[PharmaCost] Ready.")

def _import_catalog(conn):
    """Import any CSV with columns: id, name, Therapeutic Class, etc."""
    batch = []
    with open(CSV_PATH, encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                med_id = int(row.get('id', 0) or 0)
                if med_id == 0:
                    continue
                uses   = ', '.join(filter(None, [row.get(f'use{i}','') for i in range(5)]))
                sfx    = ', '.join(filter(None, [row.get(f'sideEffect{i}','') for i in range(42)]))
                subs   = ', '.join(filter(None, [row.get(f'substitute{i}','') for i in range(5)]))
                batch.append((med_id, row.get('name','').strip().title(),
                    row.get('Therapeutic Class','').strip(),
                    row.get('Chemical Class','').strip(),
                    row.get('Habit Forming','').strip(),
                    row.get('Action Class','').strip(),
                    uses, sfx, subs))
                if len(batch) >= 5000:
                    conn.executemany("INSERT OR IGNORE INTO MedicineCatalog VALUES(?,?,?,?,?,?,?,?,?)", batch)
                    conn.commit(); batch = []
            except Exception:
                continue
    if batch:
        conn.executemany("INSERT OR IGNORE INTO MedicineCatalog VALUES(?,?,?,?,?,?,?,?,?)", batch)
        conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM MedicineCatalog").fetchone()[0]
    print(f"[PharmaCost] Catalog loaded: {total:,} medicines.")

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv  = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def mutate(sql, args=()):
    db = get_db(); cur = db.execute(sql, args); db.commit(); return cur

def get_stats():
    rows = query("SELECT status, COUNT(*) as cnt FROM vw_Inventory GROUP BY status")
    stats = {"expired":0,"critical":0,"warning":0,"good":0}
    for r in rows: stats[r["status"]] = r["cnt"]
    stats["total"]      = sum(stats.values())
    stats["total_qty"]  = query("SELECT COALESCE(SUM(quantity),0) as s FROM Batch",one=True)["s"]
    stats["drugs"]      = query("SELECT COUNT(*) as c FROM Drug",one=True)["c"]
    stats["suppliers"]  = query("SELECT COUNT(*) as c FROM Supplier",one=True)["c"]
    stats["patients"]   = query("SELECT COUNT(*) as c FROM Patient",one=True)["c"]
    stats["bills"]      = query("SELECT COUNT(*) as c FROM Bill",one=True)["c"]
    stats["revenue"]    = query("SELECT COALESCE(SUM(total),0) as s FROM Bill",one=True)["s"]
    expired_rows        = query("SELECT quantity, price FROM vw_ExpiredBatches")
    stats["expired_loss"]   = sum(r["quantity"] * r["price"] for r in expired_rows)
    expiring_rows       = query("SELECT quantity, price FROM vw_ExpiringBatches")
    stats["expiring_risk"]  = sum(r["quantity"] * r["price"] for r in expiring_rows)
    stats["pending_actions"]= query("SELECT COUNT(*) as c FROM AgentActions WHERE status='pending'",one=True)["c"]
    stats["notifications"]  = query("SELECT COUNT(*) as c FROM Notifications",one=True)["c"]
    return stats

def next_patient_id():
    row = query("SELECT patient_id FROM Patient ORDER BY patient_id DESC LIMIT 1", one=True)
    if not row: return "CUST-000001"
    try: return f"CUST-{int(row['patient_id'].split('-')[1])+1:06d}"
    except: return f"CUST-{datetime.now().strftime('%H%M%S')}"

def next_bill_number():
    today = datetime.now().strftime("%Y%m%d")
    row   = query("SELECT COUNT(*) as c FROM Bill WHERE bill_number LIKE ?", (f"BILL-{today}-%",), one=True)
    return f"BILL-{today}-{row['c']+1:04d}"

def login_required(f):
    from functools import wraps
    @wraps(f)
    def d(*a, **kw):
        if "user" not in session: return redirect(url_for("login"))
        return f(*a, **kw)
    return d

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def d(*a, **kw):
        if "user" not in session: return redirect(url_for("login"))
        if session["user"]["role"] != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return d

@app.context_processor
def inject_globals():
    stats = None
    try:
        if "user" in session:
            stats = get_stats()
    except Exception:
        pass
    return {"now": datetime.now(), "stats": stats}

# ══════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════
@app.route("/", methods=["GET","POST"])
def login():
    if "user" in session: return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        user = query("SELECT * FROM Users WHERE username=? AND password=?", (u,p), one=True)
        if user:
            session["user"] = dict(user)
            flash(f"Welcome back, {u}!", "success")
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════
@app.route("/dashboard")
@login_required
def dashboard():
    stats       = get_stats()
    alerts      = query("SELECT * FROM vw_Inventory WHERE status IN ('expired','critical','warning') ORDER BY days_left ASC LIMIT 8")
    recent_audit= query("SELECT * FROM AuditLog ORDER BY timestamp DESC LIMIT 6")
    recent_bills= query("SELECT * FROM vw_BillSummary ORDER BY bill_date DESC LIMIT 5")
    return render_template("dashboard.html", stats=stats, alerts=alerts,
                           recent_audit=recent_audit, recent_bills=recent_bills,
                           role=session["user"]["role"])

# ══════════════════════════════════════════════════════════════
#  INVENTORY
# ══════════════════════════════════════════════════════════════
@app.route("/inventory")
@login_required
def inventory():
    sq     = request.args.get("q","").strip()
    status = request.args.get("status","")
    sql    = "SELECT * FROM vw_Inventory WHERE 1=1"; args=[]
    if sq:     sql += " AND (drug_name LIKE ? OR batch_id LIKE ? OR category LIKE ?)"; args += [f"%{sq}%"]*3
    if status: sql += " AND status=?"; args.append(status)
    sql += " ORDER BY days_left ASC"
    return render_template("inventory.html", rows=query(sql,args),
                           search=sq, status_filter=status,
                           suppliers=query("SELECT * FROM Supplier ORDER BY name"),
                           drugs=query("SELECT * FROM Drug ORDER BY name"))

@app.route("/inventory/update_qty", methods=["POST"])
@login_required
def update_qty():
    mutate("UPDATE Batch SET quantity=? WHERE batch_id=?",
           (max(0, int(request.form["quantity"])), request.form["batch_id"]))
    flash("Stock updated.", "success")
    return redirect(url_for("inventory"))

# ══════════════════════════════════════════════════════════════
#  ALERTS
# ══════════════════════════════════════════════════════════════
@app.route("/alerts")
@login_required
def alerts():
    return render_template("alerts.html",
        expired  =query("SELECT * FROM vw_ExpiredBatches ORDER BY days_overdue DESC"),
        critical =query("SELECT * FROM vw_Inventory WHERE status='critical' ORDER BY days_left ASC"),
        warning  =query("SELECT * FROM vw_Inventory WHERE status='warning' ORDER BY days_left ASC"),
        low_stock=query("SELECT * FROM vw_Inventory WHERE quantity<100 AND status!='expired' ORDER BY quantity ASC"))

# ══════════════════════════════════════════════════════════════
#  DRUGS
# ══════════════════════════════════════════════════════════════
@app.route("/drugs")
@login_required
def drugs():
    return render_template("drugs.html",
        drugs=query("""SELECT d.drug_id,d.name,d.category,d.manufacturer,d.price,
               COUNT(b.batch_id) AS batches, COALESCE(SUM(b.quantity),0) AS total_qty
        FROM Drug d LEFT JOIN Batch b ON d.drug_id=b.drug_id
        GROUP BY d.drug_id ORDER BY d.name"""),
        suppliers=query("SELECT * FROM Supplier ORDER BY name"))

@app.route("/drugs/add", methods=["POST"])
@login_required
def add_drug():
    name = request.form["name"].strip()
    if not name: flash("Name required.", "danger"); return redirect(url_for("drugs"))
    mutate("INSERT INTO Drug(name,category,manufacturer,price) VALUES(?,?,?,?)",
           (name, request.form.get("category","General"),
            request.form.get("manufacturer","Unknown"),
            float(request.form.get("price",0) or 0)))
    flash(f"'{name}' added.", "success")
    return redirect(url_for("drugs"))

@app.route("/drugs/add_batch", methods=["POST"])
@login_required
def add_batch():
    try:
        mutate("""INSERT INTO Batch(batch_id,drug_id,supplier_id,mfg_date,exp_date,quantity,location)
                  VALUES(?,?,?,?,?,?,?)""",
               (request.form["batch_id"].strip(), request.form["drug_id"],
                request.form.get("supplier_id") or None,
                request.form["mfg_date"], request.form["exp_date"],
                int(request.form["quantity"]), request.form.get("location","Main Store")))
        flash("Batch added.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("inventory"))

@app.route("/drugs/delete/<int:drug_id>")
@admin_required
def delete_drug(drug_id):
    mutate("DELETE FROM Drug WHERE drug_id=?", (drug_id,))
    flash("Drug removed.", "info"); return redirect(url_for("drugs"))

# ══════════════════════════════════════════════════════════════
#  BULK CSV IMPORT — organizers can upload their own data
# ══════════════════════════════════════════════════════════════
@app.route("/admin/import", methods=["GET","POST"])
@admin_required
def bulk_import():
    """
    Upload a CSV to bulk-import drugs and batches.
    Expected columns (flexible — missing columns get defaults):
      drug_name, category, manufacturer, price,
      batch_id, mfg_date, exp_date, quantity, location, supplier_name
    """
    if request.method == "GET":
        return render_template("import.html")

    f = request.files.get("csvfile")
    if not f or not f.filename.endswith(".csv"):
        flash("Please upload a .csv file.", "danger")
        return redirect(url_for("bulk_import"))

    content = f.stream.read().decode("utf-8", errors="ignore")
    reader  = csv.DictReader(io.StringIO(content))
    imported = 0; errors = 0

    for row in reader:
        try:
            drug_name    = (row.get("drug_name") or row.get("name") or "").strip()
            if not drug_name: continue
            category     = (row.get("category") or "General").strip()
            manufacturer = (row.get("manufacturer") or "Unknown").strip()
            price        = float(row.get("price",0) or 0)

            # Upsert drug
            existing = query("SELECT drug_id FROM Drug WHERE name=? AND manufacturer=?",
                             (drug_name, manufacturer), one=True)
            if existing:
                drug_id = existing["drug_id"]
            else:
                cur = mutate("INSERT INTO Drug(name,category,manufacturer,price) VALUES(?,?,?,?)",
                             (drug_name, category, manufacturer, price))
                drug_id = cur.lastrowid

            # Supplier
            sup_name = (row.get("supplier_name") or row.get("supplier") or "").strip()
            sup_id   = None
            if sup_name:
                sup = query("SELECT supplier_id FROM Supplier WHERE name=?", (sup_name,), one=True)
                if sup:
                    sup_id = sup["supplier_id"]
                else:
                    cur2 = mutate("INSERT INTO Supplier(name) VALUES(?)", (sup_name,))
                    sup_id = cur2.lastrowid

            # Batch
            batch_id = (row.get("batch_id") or f"B-{drug_id}-{imported+1:04d}").strip()
            exp_date = (row.get("exp_date") or row.get("expiry_date") or "").strip()
            mfg_date = (row.get("mfg_date") or row.get("manufacture_date") or
                        datetime.now().strftime("%Y-%m-%d"))
            quantity = int(float(row.get("quantity",0) or 0))
            location = (row.get("location") or "Main Store").strip()

            if not exp_date: continue

            mutate("""INSERT OR REPLACE INTO Batch
                      (batch_id,drug_id,supplier_id,mfg_date,exp_date,quantity,location)
                      VALUES(?,?,?,?,?,?,?)""",
                   (batch_id, drug_id, sup_id, mfg_date, exp_date, quantity, location))
            imported += 1
        except Exception as e:
            errors += 1
            continue

    flash(f"Imported {imported} batches successfully. {errors} rows skipped.", "success")
    return redirect(url_for("inventory"))

# ══════════════════════════════════════════════════════════════
#  PATIENTS
# ══════════════════════════════════════════════════════════════
@app.route("/patients")
@login_required
def patients():
    sq  = request.args.get("q","").strip()
    sql = """SELECT p.*, COUNT(b.bill_id) AS total_bills, COALESCE(SUM(b.total),0) AS total_spent
             FROM Patient p LEFT JOIN Bill b ON p.patient_id=b.patient_id WHERE 1=1"""
    args = []
    if sq:
        sql += " AND (p.name LIKE ? OR p.phone LIKE ? OR p.patient_id LIKE ?)"
        args += [f"%{sq}%"]*3
    sql += " GROUP BY p.patient_id ORDER BY p.created_at DESC"
    return render_template("patients.html", patients=query(sql,args), search=sq)

@app.route("/patients/add", methods=["POST"])
@login_required
def add_patient():
    name = request.form["name"].strip()
    if not name: flash("Name required.", "danger"); return redirect(url_for("patients"))
    pid = next_patient_id()
    mutate("INSERT INTO Patient(patient_id,name,phone,email,address) VALUES(?,?,?,?,?)",
           (pid, name, request.form.get("phone",""), request.form.get("email",""),
            request.form.get("address","")))
    flash(f"Patient {pid} added.", "success")
    return redirect(url_for("patients"))

@app.route("/patients/<patient_id>")
@login_required
def patient_detail(patient_id):
    patient = query("SELECT * FROM Patient WHERE patient_id=?", (patient_id,), one=True)
    if not patient: flash("Not found.", "danger"); return redirect(url_for("patients"))
    bills = query("""SELECT b.*, COUNT(bi.item_id) AS item_count
                     FROM Bill b LEFT JOIN BillItem bi ON b.bill_id=bi.bill_id
                     WHERE b.patient_id=? GROUP BY b.bill_id ORDER BY b.bill_date DESC""",
                  (patient_id,))
    return render_template("patient_detail.html", patient=patient, bills=bills,
                           total_spent=sum(b["total"] for b in bills))

@app.route("/patients/delete/<patient_id>")
@admin_required
def delete_patient(patient_id):
    mutate("DELETE FROM Patient WHERE patient_id=?", (patient_id,))
    flash("Patient removed. Bills preserved.", "info")
    return redirect(url_for("patients"))

@app.route("/api/patients/search")
@login_required
def api_search_patients():
    q = request.args.get("q","").strip()
    return jsonify([dict(r) for r in query(
        "SELECT patient_id,name,phone FROM Patient WHERE name LIKE ? OR phone LIKE ? LIMIT 8",
        (f"%{q}%", f"%{q}%"))])

@app.route("/api/drugs/search")
@login_required
def api_search_drugs():
    q = request.args.get("q","").strip()
    return jsonify([dict(r) for r in query("""
        SELECT b.batch_id, d.name AS drug_name, d.price, b.quantity, b.exp_date
        FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
        WHERE (d.name LIKE ? OR d.category LIKE ?) AND b.quantity>0
          AND date(b.exp_date)>=date('now')
        ORDER BY b.exp_date ASC LIMIT 10""", (f"%{q}%", f"%{q}%"))])

# ══════════════════════════════════════════════════════════════
#  BILLING
# ══════════════════════════════════════════════════════════════
@app.route("/billing")
@login_required
def billing():
    return render_template("billing.html",
                           patients=query("SELECT * FROM Patient ORDER BY name"))

@app.route("/billing/create", methods=["POST"])
@login_required
def create_bill():
    patient_id = request.form.get("patient_id") or None
    items      = json.loads(request.form.get("items","[]"))
    discount   = float(request.form.get("discount",0) or 0)
    gst_pct    = float(request.form.get("gst_pct",0) or 0)
    payment    = request.form.get("payment_method","Cash")
    notes      = request.form.get("notes","")
    billed_by  = session["user"]["username"]
    if not items: flash("Cart empty.", "danger"); return redirect(url_for("billing"))
    subtotal   = sum(i["quantity"]*i["unit_price"] for i in items)
    gst_amount = round((subtotal-discount)*gst_pct/100, 2)
    total      = round(subtotal - discount + gst_amount, 2)
    bill_number = next_bill_number()
    db = get_db()
    try:
        cur = db.execute("""INSERT INTO Bill(bill_number,patient_id,billed_by,subtotal,
                            discount,gst_pct,gst_amount,total,payment_method,notes)
                            VALUES(?,?,?,?,?,?,?,?,?,?)""",
                         (bill_number,patient_id,billed_by,subtotal,discount,
                          gst_pct,gst_amount,total,payment,notes))
        bill_id = cur.lastrowid
        for item in items:
            db.execute("""INSERT INTO BillItem(bill_id,batch_id,drug_name,quantity,unit_price,amount)
                          VALUES(?,?,?,?,?,?)""",
                       (bill_id,item["batch_id"],item["drug_name"],item["quantity"],
                        item["unit_price"],round(item["quantity"]*item["unit_price"],2)))
            db.execute("UPDATE Batch SET quantity=quantity-? WHERE batch_id=?",
                       (item["quantity"],item["batch_id"]))
        db.commit()
        flash(f"Bill {bill_number} created!", "success")
        return redirect(url_for("bill_detail", bill_id=bill_id))
    except Exception as e:
        db.rollback(); flash(f"Error: {e}", "danger")
        return redirect(url_for("billing"))

@app.route("/bills")
@login_required
def bills():
    sq      = request.args.get("q","").strip()
    from_dt = request.args.get("from","")
    to_dt   = request.args.get("to","")
    sql     = "SELECT * FROM vw_BillSummary WHERE 1=1"; args=[]
    if sq:      sql += " AND (bill_number LIKE ? OR patient_name LIKE ?)"; args += [f"%{sq}%"]*2
    if from_dt: sql += " AND date(bill_date)>=?"; args.append(from_dt)
    if to_dt:   sql += " AND date(bill_date)<=?"; args.append(to_dt)
    sql += " ORDER BY bill_date DESC"
    return render_template("bills.html", bills=query(sql,args),
                           search=sq, from_dt=from_dt, to_dt=to_dt)

@app.route("/bills/<int:bill_id>")
@login_required
def bill_detail(bill_id):
    bill  = query("SELECT * FROM vw_BillSummary WHERE bill_id=?", (bill_id,), one=True)
    if not bill: flash("Not found.","danger"); return redirect(url_for("bills"))
    items = query("SELECT * FROM BillItem WHERE bill_id=?", (bill_id,))
    return render_template("bill_detail.html", bill=bill, items=items)

@app.route("/suppliers")
@login_required
def suppliers():
    return render_template("suppliers.html",
        suppliers=query("""SELECT s.*, COUNT(b.batch_id) AS batch_count,
                            COALESCE(SUM(b.quantity*d.price),0) AS total_value
                          FROM Supplier s
                          LEFT JOIN Batch b ON s.supplier_id=b.supplier_id
                          LEFT JOIN Drug d ON b.drug_id=d.drug_id
                          GROUP BY s.supplier_id ORDER BY total_value DESC"""))

@app.route("/suppliers/add", methods=["POST"])
@login_required
def add_supplier():
    mutate("INSERT INTO Supplier(name,contact,address) VALUES(?,?,?)",
           (request.form["name"], request.form.get("contact",""), request.form.get("address","")))
    flash("Supplier added.", "success"); return redirect(url_for("suppliers"))

@app.route("/reports")
@login_required
def reports():
    stats = get_stats()
    return render_template("reports.html", stats=stats,
        status_dist=query("SELECT status,COUNT(*) as cnt,SUM(quantity) as qty FROM vw_Inventory GROUP BY status"),
        cat_dist   =query("SELECT d.category,COUNT(b.batch_id) as batches,COALESCE(SUM(b.quantity),0) as total_qty,COALESCE(SUM(b.quantity*d.price),0) as value FROM Drug d LEFT JOIN Batch b ON d.drug_id=b.drug_id GROUP BY d.category ORDER BY value DESC"),
        sup_dist   =query("SELECT s.name,COUNT(b.batch_id) as batches,COALESCE(SUM(b.quantity),0) as total_qty FROM Supplier s LEFT JOIN Batch b ON s.supplier_id=b.supplier_id GROUP BY s.supplier_id ORDER BY total_qty DESC"),
        pay_dist   =query("SELECT payment_method,COUNT(*) as cnt,SUM(total) as revenue FROM Bill GROUP BY payment_method ORDER BY revenue DESC"))

@app.route("/audit")
@admin_required
def audit():
    return render_template("audit.html",
                           logs=query("SELECT * FROM AuditLog ORDER BY timestamp DESC LIMIT 300"))

# ══════════════════════════════════════════════════════════════
#  AI FINANCIAL AGENT — TRACK 3 CORE
# ══════════════════════════════════════════════════════════════
@app.route("/agent")
@login_required
def agent():
    stats   = get_stats()
    pending = query("SELECT * FROM AgentActions WHERE status='pending' ORDER BY impact_inr DESC")
    history = query("SELECT * FROM AgentActions WHERE status!='pending' ORDER BY executed_at DESC LIMIT 30")
    return render_template("agent.html", stats=stats, pending=pending, history=history)

@app.route("/api/agent/analyze", methods=["POST"])
@login_required
def agent_analyze():
    def rows_to_list(rows, fields):
        return [{f: r[f] for f in fields if f in r.keys()} for r in rows]

    # Pull all signals from the live database — works on ANY dataset
    expired       = query("SELECT * FROM vw_ExpiredBatches ORDER BY quantity*price DESC")
    expiring      = query("SELECT * FROM vw_ExpiringBatches ORDER BY days_left ASC")
    low_stock     = query("SELECT * FROM vw_Inventory WHERE quantity<100 AND status!='expired' ORDER BY quantity ASC")
    bills_pay     = query("SELECT payment_method,COUNT(*) as cnt,SUM(total) as revenue,AVG(discount) as avg_discount,SUM(discount) as total_discount FROM Bill GROUP BY payment_method")
    rev_trend     = query("SELECT date(bill_date) as day,SUM(total) as revenue,COUNT(*) as bill_count FROM Bill WHERE bill_date>=date('now','-30 days') GROUP BY day ORDER BY day")
    top_drugs     = query("SELECT bi.drug_name,SUM(bi.quantity) as units_sold,SUM(bi.amount) as revenue FROM BillItem bi GROUP BY bi.drug_name ORDER BY revenue DESC LIMIT 10")
    supplier_risk = query("""SELECT s.name as supplier,COUNT(b.batch_id) as batches,
               SUM(CASE WHEN date(b.exp_date)<date('now') THEN 1 ELSE 0 END) as expired_batches,
               COALESCE(SUM(b.quantity*d.price),0) as total_value
               FROM Supplier s JOIN Batch b ON s.supplier_id=b.supplier_id
               JOIN Drug d ON b.drug_id=d.drug_id GROUP BY s.supplier_id ORDER BY total_value DESC""")
    discount_data = query("SELECT billed_by,COUNT(*) as bills,AVG(discount) as avg_discount,SUM(discount) as total_discount,SUM(total) as total_revenue FROM Bill GROUP BY billed_by")
    slow_movers   = query("""SELECT d.name,d.category,COALESCE(SUM(b.quantity),0) as stock,
               COALESCE(SUM(bi.quantity),0) as sold_30d, d.price
               FROM Drug d LEFT JOIN Batch b ON d.drug_id=b.drug_id AND date(b.exp_date)>=date('now')
               LEFT JOIN BillItem bi ON bi.drug_name=d.name
               GROUP BY d.drug_id HAVING stock>200 AND sold_30d<10""")
    stats = get_stats()

    # SLA / penalty signals — Agent 3 data
    sla_breaches = query("""
        SELECT b.batch_id, d.name as drug_name, b.exp_date, b.quantity, d.price,
               CAST(julianday('now')-julianday(b.exp_date) AS INTEGER) as days_overdue,
               CASE WHEN CAST(julianday('now')-julianday(b.exp_date) AS INTEGER)>90 THEN 'critical'
                    WHEN CAST(julianday('now')-julianday(b.exp_date) AS INTEGER)>30 THEN 'high'
                    ELSE 'medium' END as sla_severity,
               ROUND(b.quantity * d.price * 0.15, 2) as penalty_exposure_inr
        FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
        WHERE date(b.exp_date) < date('now') ORDER BY days_overdue DESC""")
    audit_gaps = query("""
        SELECT b.batch_id, d.name as drug_name, b.exp_date, b.quantity, d.price
        FROM Batch b JOIN Drug d ON b.drug_id=d.drug_id
        WHERE date(b.exp_date) < date('now')
          AND b.batch_id NOT IN (
            SELECT record_id FROM AuditLog
            WHERE action IN ('AGENT_FLAG','AGENT_EXECUTE') AND table_name='Batch')""")
    total_penalty = sum(r["penalty_exposure_inr"] for r in sla_breaches)

    context = {
        "pharmacy_overview": {
            "total_batches": stats["total"], "total_stock_units": stats["total_qty"],
            "total_revenue_inr": round(stats["revenue"],2), "total_bills": stats["bills"],
            "expired_batches": stats["expired"], "critical_batches": stats["critical"],
            "warning_batches": stats["warning"],
            "confirmed_expired_loss_inr": round(stats["expired_loss"],2),
            "at_risk_expiring_value_inr": round(stats["expiring_risk"],2),
            "total_regulatory_penalty_exposure_inr": round(total_penalty, 2),
        },
        "expired_stock":            rows_to_list(expired,   ["batch_id","drug_name","category","exp_date","quantity","days_overdue","supplier","price"]),
        "expiring_within_90_days":  rows_to_list(expiring,  ["batch_id","drug_name","category","exp_date","quantity","days_left","supplier","price"]),
        "low_stock_alerts":         rows_to_list(low_stock,  ["batch_id","drug_name","category","quantity","status","days_left","price"]),
        "revenue_last_30_days":     rows_to_list(rev_trend,  ["day","revenue","bill_count"]),
        "billing_by_payment":       rows_to_list(bills_pay,  ["payment_method","cnt","revenue","avg_discount","total_discount"]),
        "top_selling_drugs":        rows_to_list(top_drugs,  ["drug_name","units_sold","revenue"]),
        "supplier_risk_analysis":   rows_to_list(supplier_risk, ["supplier","batches","expired_batches","total_value"]),
        "discount_by_user":         rows_to_list(discount_data, ["billed_by","bills","avg_discount","total_discount","total_revenue"]),
        "slow_moving_stock":        rows_to_list(slow_movers,   ["name","category","stock","sold_30d","price"]),
        "sla_penalty_signals":      rows_to_list(sla_breaches,  ["batch_id","drug_name","exp_date","quantity","price","days_overdue","sla_severity","penalty_exposure_inr"]),
        "audit_gap_batches":        rows_to_list(audit_gaps,    ["batch_id","drug_name","exp_date","quantity","price"]),
    }

    system_prompt = """You are PharmaCost FinAgent — an AI financial operations agent for a pharmacy.
Analyse all signals and return ONLY valid JSON. No markdown, no commentary outside JSON.

IMPORTANT: Always include at least one anomaly of type "sla_breach" or "penalty_exposure" with:
- penalty math shown: e.g. "80 units × ₹38/unit × 15% penalty_rate = ₹456 regulatory exposure"
- urgency_days based on days_overdue of expired batches
- recommended_action that references specific regulatory action (CDSCO, state drug authority)

Return exactly:
{
  "risk_score": <0-100>,
  "summary": "<2-3 sentence executive briefing with real numbers>",
  "agent_verdict": "<one decisive action sentence>",
  "total_confirmed_loss_inr": <number>,
  "total_at_risk_inr": <number>,
  "cost_savings_potential_inr": <number>,
  "financial_model": {
    "current_monthly_revenue_est": <number>,
    "projected_loss_next_30_days": <number>,
    "recovery_potential_inr": <number>,
    "inventory_efficiency_pct": <0-100>,
    "waste_ratio_pct": <0-100>
  },
  "anomalies": [
    {
      "id": "ANO-001",
      "type": "expiry_loss|stock_waste|billing_anomaly|procurement_risk|slow_mover|discount_abuse|supplier_risk|sla_breach|penalty_exposure",
      "severity": "critical|high|medium|low",
      "title": "<short title>",
      "description": "<specific with real numbers from data>",
      "financial_impact_inr": <number>,
      "math_breakdown": "<e.g. 1200 units x Rs12/unit = Rs14400>",
      "affected_items": ["<real batch IDs or drug names>"],
      "root_cause": "<why>",
      "recommended_action": "<specific action>",
      "action_type": "auto_execute|stage_for_approval|alert_only",
      "before_scenario": "<without intervention, with numbers>",
      "after_scenario": "<with intervention, with numbers>",
      "savings_if_actioned_inr": <number>,
      "urgency_days": <integer>
    }
  ],
  "resource_optimization": [
    { "area": "<area>", "current_state": "<now>", "recommendation": "<action>", "estimated_savings_inr": <number> }
  ],
  "variance_analysis": {
    "revenue_variance": "<analysis>",
    "stock_variance": "<analysis>",
    "discount_variance": "<analysis>"
  }
}
Use REAL batch IDs, drug names, quantities and prices from the data. Sort anomalies critical first."""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514", "max_tokens": 4000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": json.dumps(context, default=str)}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            raw  = data["content"][0]["text"].strip()
            if raw.startswith("```"): raw = raw.split("\n",1)[1].rsplit("```",1)[0].strip()
            return jsonify({"ok": True, "result": json.loads(raw)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/agent/action", methods=["POST"])
@login_required
def agent_action():
    d = request.get_json()
    anomaly_id  = d.get("anomaly_id","")
    title       = d.get("title","")
    action_type = d.get("action_type","")
    severity    = d.get("severity","")
    impact      = d.get("impact_inr", 0)
    items       = d.get("affected_items", [])
    by          = session["user"]["username"]
    mutate("""INSERT OR REPLACE INTO AgentActions
              (anomaly_id,anomaly_title,action_type,severity,impact_inr,
               status,affected_items,executed_by,executed_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",
           (anomaly_id,title,action_type,severity,impact,"executed",
            json.dumps(items),by,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    mutate("INSERT INTO AuditLog(action,table_name,record_id,details,done_by) VALUES(?,?,?,?,?)",
           ("AGENT_EXECUTE","AgentActions",anomaly_id,f"Executed:{title}|₹{impact}",by))
    for bid in items:
        if query("SELECT 1 FROM Batch WHERE batch_id=?", (bid,), one=True):
            mutate("INSERT INTO AuditLog(action,table_name,record_id,details,done_by) VALUES(?,?,?,?,?)",
                   ("AGENT_FLAG","Batch",bid,f"Flagged by FinAgent|{anomaly_id}",by))

    # ── Downstream workflow triggers ──────────────────────────────
    _fire_notifications(anomaly_id, title, severity, impact, action_type, by)
    return jsonify({"ok": True})

@app.route("/api/agent/stage", methods=["POST"])
@login_required
def agent_stage():
    d = request.get_json()
    anomaly_id  = d.get("anomaly_id","")
    title       = d.get("title","")
    action_type = d.get("action_type","")
    severity    = d.get("severity","")
    impact      = d.get("impact_inr", 0)
    items       = d.get("affected_items", [])
    by          = session["user"]["username"]
    mutate("""INSERT OR REPLACE INTO AgentActions
              (anomaly_id,anomaly_title,action_type,severity,impact_inr,
               status,affected_items,executed_by,notes)
              VALUES(?,?,?,?,?,?,?,?,?)""",
           (anomaly_id,title,action_type,severity,impact,"pending",
            json.dumps(items),by,"Awaiting admin approval"))
    mutate("INSERT INTO AuditLog(action,table_name,record_id,details,done_by) VALUES(?,?,?,?,?)",
           ("AGENT_STAGE","AgentActions",anomaly_id,f"Staged:{title}|₹{impact}",by))
    _fire_notifications(anomaly_id, title, severity, impact, "stage_for_approval", by)
    return jsonify({"ok": True, "message": "Staged for approval"})

@app.route("/api/agent/approve/<int:action_id>", methods=["POST"])
@admin_required
def approve_action(action_id):
    by = session["user"]["username"]
    row = query("SELECT * FROM AgentActions WHERE action_id=?", (action_id,), one=True)
    mutate("UPDATE AgentActions SET status='approved',executed_by=?,executed_at=? WHERE action_id=?",
           (by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action_id))
    mutate("INSERT INTO AuditLog(action,table_name,record_id,details,done_by) VALUES(?,?,?,?,?)",
           ("AGENT_APPROVED","AgentActions",str(action_id),"Admin approved",by))
    if row:
        _fire_notifications(row["anomaly_id"], row["anomaly_title"], row["severity"],
                            row["impact_inr"], "approved", by)
    return jsonify({"ok": True})

@app.route("/api/agent/reject/<int:action_id>", methods=["POST"])
@admin_required
def reject_action(action_id):
    by = session["user"]["username"]
    mutate("UPDATE AgentActions SET status='rejected',executed_by=?,executed_at=? WHERE action_id=?",
           (by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action_id))
    return jsonify({"ok": True})

@app.route("/notifications")
@login_required
def notifications():
    notifs = query("SELECT * FROM Notifications ORDER BY sent_at DESC LIMIT 100")
    return render_template("notifications.html", notifs=notifs)

@app.route("/api/notifications")
@login_required
def api_notifications():
    notifs = query("SELECT * FROM Notifications ORDER BY sent_at DESC LIMIT 50")
    return jsonify([dict(n) for n in notifs])

# ── Downstream notification / webhook helper ──────────────────
def _fire_notifications(anomaly_id, title, severity, impact, action_type, triggered_by):
    """
    Simulates firing downstream workflow triggers:
      - Email to pharmacy admin
      - Slack webhook (simulated)
      - ERP procurement alert (simulated)
    All logged to Notifications table as proof of downstream integration.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notifications_to_fire = []

    # 1. Email notification
    notifications_to_fire.append((
        "email",
        "admin@pharmacost.in",
        f"[PharmaCost FinAgent] {severity.upper()} Alert: {title}",
        f"Anomaly {anomaly_id} triggered action '{action_type}'.\n"
        f"Financial Impact: ₹{impact:,.2f}\n"
        f"Actioned by: {triggered_by} at {ts}\n"
        f"Please review the approval queue at /agent",
        triggered_by, anomaly_id, impact
    ))

    # 2. Slack webhook (simulated)
    if severity in ("critical", "high"):
        notifications_to_fire.append((
            "slack",
            "#pharmacy-alerts",
            f"FinAgent ALERT: {title}",
            f":rotating_light: *{severity.upper()}* | {title}\n"
            f"Impact: ₹{impact:,.2f} | Action: {action_type}\n"
            f"Triggered by {triggered_by}",
            triggered_by, anomaly_id, impact
        ))

    # 3. ERP procurement trigger for stock-related actions
    if action_type in ("stage_for_approval", "approved") and impact > 5000:
        notifications_to_fire.append((
            "erp_webhook",
            "procurement-module",
            f"Procurement Reallocation Request: {title}",
            f"FinAgent has flagged a procurement action.\n"
            f"Anomaly: {anomaly_id} | Impact: ₹{impact:,.2f}\n"
            f"ERP workflow initiated for review and PO generation.",
            triggered_by, anomaly_id, impact
        ))

    # 4. Regulatory escalation for SLA/penalty issues
    if "sla" in anomaly_id.lower() or "penalty" in (title or "").lower() or severity == "critical":
        notifications_to_fire.append((
            "regulatory",
            "compliance@pharmacost.in",
            f"[COMPLIANCE] Regulatory Exposure Detected: {title}",
            f"Batch(es) with SLA breach identified.\n"
            f"Penalty Exposure: ₹{impact:,.2f}\n"
            f"CDSCO reporting may be required. Escalated by FinAgent at {ts}.",
            triggered_by, anomaly_id, impact
        ))

    for (channel, recipient, subject, body, tby, aid, imp) in notifications_to_fire:
        try:
            mutate("""INSERT INTO Notifications
                      (channel,recipient,subject,body,triggered_by,anomaly_id,impact_inr,status,sent_at)
                      VALUES(?,?,?,?,?,?,?,'sent',?)""",
                   (channel, recipient, subject, body, tby, aid, imp, ts))
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
#  PDF RECEIPT
# ══════════════════════════════════════════════════════════════
@app.route("/bills/<int:bill_id>/pdf")
@login_required
def download_pdf(bill_id):
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        flash("reportlab not installed. Run: pip install reportlab", "danger")
        return redirect(url_for("bill_detail", bill_id=bill_id))

    bill      = query("SELECT * FROM vw_BillSummary WHERE bill_id=?", (bill_id,), one=True)
    full_bill = query("SELECT * FROM Bill WHERE bill_id=?", (bill_id,), one=True)
    items     = query("SELECT * FROM BillItem WHERE bill_id=?", (bill_id,))
    if not bill: flash("Not found.", "danger"); return redirect(url_for("bills"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
                            rightMargin=12*mm, leftMargin=12*mm,
                            topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    dark  = colors.HexColor("#0d1117"); muted = colors.HexColor("#8b949e")
    green = colors.HexColor("#00e576"); white = colors.white
    cyan  = colors.HexColor("#00e5ff")

    def ps(name, **kw): return ParagraphStyle(name, parent=styles["Normal"], **kw)
    elems = []

    hdr = Table([[
        Paragraph("<font color='white'><b>PharmaCost Intelligence</b></font><br/>"
                  "<font color='#8b949e' size='7'>AI Financial Operations</font>",
                  ps("h", fontSize=12, textColor=white, leading=15)),
        Paragraph(f"<font color='#00e5ff'><b>{bill['bill_number']}</b></font><br/>"
                  f"<font color='#8b949e' size='7'>{bill['bill_date'][:10]}</font>",
                  ps("hr", fontSize=9, textColor=white, alignment=TA_RIGHT, leading=13))
    ]], colWidths=[75*mm, 45*mm])
    hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),dark),
                              ("PADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    elems.extend([hdr, Spacer(1, 4*mm)])

    tdata = [["Medicine","Qty","Rate","Amount"]]
    for item in items:
        tdata.append([item["drug_name"], str(item["quantity"]),
                      f"Rs.{item['unit_price']:.2f}", f"Rs.{item['amount']:.2f}"])
    itbl = Table(tdata, colWidths=[62*mm, 13*mm, 27*mm, 25*mm])
    itbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),dark),("TEXTCOLOR",(0,0),(-1,0),white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),
        ("ALIGN",(1,0),(-1,-1),"RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#0a0e14"),colors.HexColor("#161b22")]),
        ("TEXTCOLOR",(0,1),(-1,-1),colors.HexColor("#e6edf3")),
        ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#21262d")),("PADDING",(0,0),(-1,-1),5),
    ]))
    elems.extend([itbl, Spacer(1, 3*mm)])

    tots = [["Subtotal", f"Rs. {full_bill['subtotal']:.2f}"]]
    if full_bill["discount"]   > 0: tots.append(["Discount",      f"- Rs. {full_bill['discount']:.2f}"])
    if full_bill["gst_amount"] > 0: tots.append([f"GST ({full_bill['gst_pct']}%)", f"Rs. {full_bill['gst_amount']:.2f}"])
    tots.append(["TOTAL", f"Rs. {full_bill['total']:.2f}"])
    ttbl = Table(tots, colWidths=[100*mm, 27*mm])
    ttbl.setStyle(TableStyle([
        ("ALIGN",(1,0),(1,-1),"RIGHT"),("FONTSIZE",(0,0),(-1,-1),8),
        ("TEXTCOLOR",(0,0),(-1,-2),muted),("PADDING",(0,0),(-1,-1),4),
        ("BACKGROUND",(0,-1),(-1,-1),dark),("TEXTCOLOR",(0,-1),(-1,-1),green),
        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,-1),(-1,-1),11),
    ]))
    elems.extend([ttbl, Spacer(1, 5*mm),
                  HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#21262d")),
                  Spacer(1, 3*mm),
                  Paragraph("Thank you for choosing PharmaCost Pharmacy.",
                             ps("ft", fontSize=8, textColor=muted, alignment=TA_CENTER))])
    doc.build(elems)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"{bill['bill_number']}.pdf",
                     mimetype="application/pdf")

if __name__ == "__main__":
    init_db()
    print("="*55)
    print("  PharmaCost Intelligence → http://127.0.0.1:5000")
    print("  Admin     : admin   / admin123")
    print("  Pharmacist: pharma1 / pharma123")
    print("  FinAgent  : /agent")
    print("  CSV Import: /admin/import")
    print("="*55)
    app.run(debug=True, host="0.0.0.0", port=5000)
