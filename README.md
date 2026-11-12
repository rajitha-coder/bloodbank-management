# Blood Bank Management System

Flask + SQLite web app (donors, patients, admin, blood stock, requests, reports).

## Run
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000 (database is created on first run).

## Connect to MySQL (DBMS)
1. Install MySQL Server and run: `mysql -u root -p < create_mysql_db.sql`
2. Set environment variables, then start the app (tables are created automatically):

Windows (PowerShell):
    $env:DB_TYPE="mysql"; $env:DB_USER="root"; $env:DB_PASSWORD="yourpassword"; $env:DB_NAME="bloodbank"
    python app.py
Linux / macOS:
    DB_TYPE=mysql DB_USER=root DB_PASSWORD=yourpassword DB_NAME=bloodbank python app.py

Without DB_TYPE the app uses SQLite (bloodbank.db).

## Demo logins
| Role  | Email                | Password |
|-------|----------------------|----------|
| Admin | admin@bloodbank.com  | admin123 |
| Donor | rahul@example.com    | donor123 |
Register a new Patient from the Register page.

## Features
- Role-based login (admin / donor / patient), hashed passwords
- Donor registration with validation (age 18-65, 10-digit phone, unique email)
- Donation recording with 90-day eligibility rule; stock updates automatically
- Blood requests: approve checks stock first, then deducts units; notifications sent
- Admin: dashboard, donor search/filter/disable/delete, inventory editor, printable reports
- Public emergency search by blood group (stock + active donors)

## Structure
app.py (routes + logic) · schema.sql (tables) · templates/ · static/style.css
Tables: users, inventory, donations, requests, notifications
