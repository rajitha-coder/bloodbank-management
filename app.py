"""Blood Bank Management System - Flask + SQLite."""
import os, re, sqlite3
from datetime import date
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
# Choose the DBMS with environment variables (default: SQLite).
#   DB_TYPE=mysql DB_HOST=localhost DB_USER=root DB_PASSWORD=... DB_NAME=bloodbank
DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()
SQLITE_FILE = os.path.join(BASE, "bloodbank.db")
MYSQL = dict(host=os.environ.get("DB_HOST", "localhost"),
             port=int(os.environ.get("DB_PORT", "3306")),
             user=os.environ.get("DB_USER", "root"),
             password=os.environ.get("DB_PASSWORD", ""),
             database=os.environ.get("DB_NAME", "bloodbank"))
GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
LOW_STOCK = 5
IS_MYSQL = DB_TYPE == "mysql"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")


# ---------- database layer (SQLite or MySQL) ----------
def connect():
    if IS_MYSQL:
        import pymysql
        return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4", **MYSQL)
    conn = sqlite3.connect(SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def adapt(sql):
    """Write SQL once with ? placeholders; convert for MySQL."""
    if IS_MYSQL:
        return sql.replace("?", "%s").replace("INSERT OR IGNORE", "INSERT IGNORE")
    return sql

def db():
    if "db" not in g:
        g.db = connect()
    return g.db

@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()

def execute(conn, sql, args=()):
    cur = conn.cursor()
    cur.execute(adapt(sql), tuple(args))
    return cur

def q(sql, args=(), one=False):
    rows = execute(db(), sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    cur = execute(db(), sql, args)
    db().commit()
    return cur

def init_db():
    conn = connect()
    schema = "schema_mysql.sql" if IS_MYSQL else "schema.sql"
    script = open(os.path.join(BASE, schema)).read()
    if IS_MYSQL:
        for stmt in filter(None, (x.strip() for x in script.split(";"))):
            execute(conn, stmt)
    else:
        conn.executescript(script)
    def one(sql, a=()):
        return execute(conn, sql, a).fetchone()
    if not one("SELECT 1 FROM users WHERE role='admin'"):
        execute(conn, "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')",
                ("Administrator", "admin@bloodbank.com", generate_password_hash("admin123")))
        for bg in GROUPS:
            execute(conn, "INSERT OR IGNORE INTO inventory(blood_group,units) VALUES(?,0)", (bg,))
        sample = [("Rahul Sharma", "rahul@example.com", "O+", "9876543212", "Hubli", 28, "Male"),
                  ("Priya Verma", "priya@example.com", "AB+", "9876543213", "Belagavi", 25, "Female"),
                  ("Arjun Rao", "arjun@example.com", "A+", "9876543214", "Bengaluru", 31, "Male")]
        for n, e, bg, ph, c, a, gd in sample:
            cur = execute(conn,
                "INSERT INTO users(name,email,password_hash,role,blood_group,phone,city,age,gender)"
                " VALUES(?,?,?,'donor',?,?,?,?,?)",
                (n, e, generate_password_hash("donor123"), bg, ph, c, a, gd))
            execute(conn, "INSERT INTO donations(donor_id,blood_group,units,donated_on) VALUES(?,?,?,?)",
                    (cur.lastrowid, bg, 2, str(date.today())))
            execute(conn, "UPDATE inventory SET units=units+2 WHERE blood_group=?", (bg,))
    conn.commit()
    conn.close()


# ---------- auth ----------
def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "uid" not in session:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco

def notify(user_id, msg):
    run("INSERT INTO notifications(user_id,message,created_on) VALUES(?,?,?)",
        (user_id, msg, str(date.today())))

def clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())

@app.errorhandler(403)
def forbidden(_):
    return render_template("message.html", title="Access denied",
                           text="You do not have permission to open this page."), 403


# ---------- public pages ----------
@app.route("/")
def home():
    stock = q("SELECT * FROM inventory ORDER BY blood_group")
    return render_template("home.html", stock=stock, low=LOW_STOCK)

@app.route("/emergency")
def emergency():
    bg = request.args.get("bg", "")
    stock = q("SELECT * FROM inventory WHERE blood_group=?", (bg,), one=True) if bg in GROUPS else None
    donors = q("SELECT name,phone,city FROM users WHERE role='donor' AND status='active' AND blood_group=?",
               (bg,)) if stock else []
    return render_template("emergency.html", groups=GROUPS, bg=bg, stock=stock, donors=donors)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = {k: clean(request.form.get(k)) for k in
             ("name", "email", "password", "role", "blood_group", "phone", "city", "age", "gender")}
        f["email"] = f["email"].lower()
        errors = []
        if not f["name"]: errors.append("Name is required.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]): errors.append("Enter a valid email address.")
        if len(f["password"]) < 6: errors.append("Password must be at least 6 characters.")
        if f["role"] not in ("donor", "patient"): errors.append("Choose Donor or Patient.")
        if f["blood_group"] not in GROUPS: errors.append("Choose a valid blood group.")
        if not re.match(r"^\d{10}$", f["phone"]): errors.append("Phone must be 10 digits.")
        if f["role"] == "donor":
            if not f["age"].isdigit() or not 18 <= int(f["age"]) <= 65:
                errors.append("Donors must be between 18 and 65 years old.")
        if q("SELECT 1 FROM users WHERE email=?", (f["email"],), one=True):
            errors.append("That email is already registered.")
        if errors:
            for e in errors: flash(e, "error")
            return render_template("register.html", groups=GROUPS, f=f)
        run("INSERT INTO users(name,email,password_hash,role,blood_group,phone,city,age,gender)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (f["name"], f["email"], generate_password_hash(f["password"]), f["role"],
             f["blood_group"], f["phone"], f["city"], int(f["age"]) if f["age"].isdigit() else None, f["gender"]))
        flash("Account created. Log in to continue.", "ok")
        return redirect(url_for("login"))
    return render_template("register.html", groups=GROUPS, f={})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE email=?", (clean(request.form.get("email")).lower(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            if u["status"] != "active":
                flash("This account is disabled.", "error")
            else:
                session.clear()
                session.update(uid=u["id"], role=u["role"], name=u["name"])
                return redirect(url_for("dashboard"))
        else:
            flash("Email or password is incorrect.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required()
def dashboard():
    return redirect(url_for({"admin": "admin_dashboard", "donor": "donor_dashboard",
                             "patient": "patient_dashboard"}[session["role"]]))


# ---------- admin ----------
@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    stats = {
        "donors": q("SELECT COUNT(*) c FROM users WHERE role='donor'", one=True)["c"],
        "patients": q("SELECT COUNT(*) c FROM users WHERE role='patient'", one=True)["c"],
        "requests": q("SELECT COUNT(*) c FROM requests", one=True)["c"],
        "pending": q("SELECT COUNT(*) c FROM requests WHERE status='pending'", one=True)["c"],
        "units": int(q("SELECT COALESCE(SUM(units),0) c FROM inventory", one=True)["c"]),
    }
    dist = q("SELECT blood_group, COUNT(*) c FROM users WHERE role='donor' GROUP BY blood_group ORDER BY blood_group")
    stock = q("SELECT * FROM inventory ORDER BY blood_group")
    return render_template("admin_dashboard.html", s=stats, dist=dist, stock=stock, low=LOW_STOCK)

@app.route("/admin/donors")
@login_required("admin")
def admin_donors():
    bg = request.args.get("bg", "")
    city = clean(request.args.get("city"))
    sql, args = "SELECT * FROM users WHERE role='donor'", []
    if bg in GROUPS: sql += " AND blood_group=?"; args.append(bg)
    if city: sql += " AND city LIKE ?"; args.append(f"%{city}%")
    return render_template("admin_donors.html", donors=q(sql + " ORDER BY name", args),
                           groups=GROUPS, bg=bg, city=city)

@app.post("/admin/donors/<int:uid>/delete")
@login_required("admin")
def delete_donor(uid):
    run("DELETE FROM users WHERE id=? AND role='donor'", (uid,))
    flash("Donor deleted.", "ok")
    return redirect(url_for("admin_donors"))

@app.post("/admin/donors/<int:uid>/toggle")
@login_required("admin")
def toggle_donor(uid):
    run("UPDATE users SET status=CASE status WHEN 'active' THEN 'disabled' ELSE 'active' END "
        "WHERE id=? AND role='donor'", (uid,))
    return redirect(url_for("admin_donors"))

@app.route("/admin/requests")
@login_required("admin")
def admin_requests():
    return render_template("admin_requests.html",
                           reqs=q("SELECT * FROM requests ORDER BY id DESC"))

@app.post("/admin/requests/<int:rid>/<action>")
@login_required("admin")
def request_action(rid, action):
    r = q("SELECT * FROM requests WHERE id=?", (rid,), one=True)
    if not r or action not in ("approve", "reject", "delete"):
        abort(404)
    if action == "delete":
        run("DELETE FROM requests WHERE id=?", (rid,))
        flash("Request deleted.", "ok")
    elif r["status"] != "pending":
        flash("Only pending requests can be changed.", "error")
    elif action == "approve":
        stock = q("SELECT units FROM inventory WHERE blood_group=?", (r["blood_group"],), one=True)
        if not stock or stock["units"] < r["units"]:
            flash(f"Not enough {r['blood_group']} stock ({stock['units'] if stock else 0} units available).", "error")
        else:
            run("UPDATE inventory SET units=units-? WHERE blood_group=?", (r["units"], r["blood_group"]))
            run("UPDATE requests SET status='approved' WHERE id=?", (rid,))
            notify(r["user_id"], f"Your request for {r['units']} unit(s) of {r['blood_group']} was approved.")
            flash("Request approved and stock updated.", "ok")
    else:
        run("UPDATE requests SET status='rejected' WHERE id=?", (rid,))
        notify(r["user_id"], f"Your request for {r['blood_group']} was rejected.")
        flash("Request rejected.", "ok")
    return redirect(url_for("admin_requests"))

@app.route("/admin/inventory", methods=["GET", "POST"])
@login_required("admin")
def admin_inventory():
    if request.method == "POST":
        bg, units = request.form.get("blood_group"), request.form.get("units", "")
        if bg in GROUPS and units.isdigit():
            run("UPDATE inventory SET units=? WHERE blood_group=?", (int(units), bg))
            flash(f"{bg} stock set to {units}.", "ok")
        else:
            flash("Enter a valid blood group and unit count.", "error")
        return redirect(url_for("admin_inventory"))
    return render_template("admin_inventory.html", stock=q("SELECT * FROM inventory ORDER BY blood_group"),
                           low=LOW_STOCK)

@app.route("/admin/reports")
@login_required("admin")
def admin_reports():
    return render_template(
        "admin_reports.html",
        donations=q("SELECT d.*, u.name FROM donations d JOIN users u ON u.id=d.donor_id ORDER BY d.id DESC"),
        stock=q("SELECT * FROM inventory ORDER BY blood_group"),
        issued=q("SELECT blood_group, SUM(units) s FROM requests WHERE status='approved' GROUP BY blood_group"))


# ---------- donor ----------
@app.route("/donor")
@login_required("donor")
def donor_dashboard():
    uid = session["uid"]
    don = q("SELECT * FROM donations WHERE donor_id=? ORDER BY id DESC", (uid,))
    total = sum(d["units"] for d in don)
    return render_template("donor_dashboard.html", don=don, total=total,
                           notes=q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)),
                           me=q("SELECT * FROM users WHERE id=?", (uid,), one=True))

@app.route("/donor/profile", methods=["GET", "POST"])
@login_required("donor")
def donor_profile():
    uid = session["uid"]
    if request.method == "POST":
        phone, city = clean(request.form.get("phone")), clean(request.form.get("city"))
        if not re.match(r"^\d{10}$", phone):
            flash("Phone must be 10 digits.", "error")
        else:
            run("UPDATE users SET phone=?, city=? WHERE id=?", (phone, city, uid))
            flash("Profile updated.", "ok")
    return render_template("donor_profile.html", me=q("SELECT * FROM users WHERE id=?", (uid,), one=True))

@app.route("/donor/donate", methods=["GET", "POST"])
@login_required("donor")
def donate():
    uid = session["uid"]
    me = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    last = q("SELECT MAX(donated_on) d FROM donations WHERE donor_id=?", (uid,), one=True)["d"]
    days = (date.today() - date.fromisoformat(last)).days if last else None
    eligible = days is None or days >= 90
    if request.method == "POST":
        if not eligible:
            flash(f"You can donate again in {90 - days} day(s).", "error")
        else:
            run("INSERT INTO donations(donor_id,blood_group,units,donated_on) VALUES(?,?,?,?)",
                (uid, me["blood_group"], 1, str(date.today())))
            run("UPDATE inventory SET units=units+1 WHERE blood_group=?", (me["blood_group"],))
            notify(uid, "Thank you! Your donation was recorded.")
            flash("Donation recorded. Thank you.", "ok")
            return redirect(url_for("donor_dashboard"))
    return render_template("donate.html", me=me, eligible=eligible, days=days, last=last)

@app.route("/donor/notifications")
@login_required("donor", "patient")
def notifications():
    return render_template("notifications.html",
                           notes=q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (session["uid"],)))


# ---------- patient ----------
@app.route("/patient")
@login_required("patient")
def patient_dashboard():
    return render_template("patient_dashboard.html",
                           reqs=q("SELECT * FROM requests WHERE user_id=? ORDER BY id DESC", (session["uid"],)))

@app.route("/patient/request", methods=["GET", "POST"])
@login_required("patient")
def request_blood():
    f = {}
    if request.method == "POST":
        f = {k: clean(request.form.get(k)) for k in ("patient", "blood_group", "units", "hospital", "city", "phone")}
        errors = []
        if not f["patient"]: errors.append("Patient name is required.")
        if f["blood_group"] not in GROUPS: errors.append("Choose a blood group.")
        if not f["units"].isdigit() or not 1 <= int(f["units"]) <= 10: errors.append("Units must be 1 to 10.")
        if not f["hospital"]: errors.append("Hospital is required.")
        if not re.match(r"^\d{10}$", f["phone"]): errors.append("Phone must be 10 digits.")
        for e in errors: flash(e, "error")
        if not errors:
            run("INSERT INTO requests(user_id,patient,blood_group,units,hospital,city,phone,requested_on)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (session["uid"], f["patient"], f["blood_group"], int(f["units"]), f["hospital"],
                 f["city"], f["phone"], str(date.today())))
            flash("Request submitted. We will update you here.", "ok")
            return redirect(url_for("patient_dashboard"))
    return render_template("request_blood.html", groups=GROUPS, f=f)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
