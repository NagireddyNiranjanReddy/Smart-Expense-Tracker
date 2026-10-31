# Smart Expense Tracker

A Flask + SQLite personal expense tracker with monthly dashboard, category chart,
search/filter, monthly budgets and 80% budget alerts, transaction deletion, and CSV export.

## Requirements
- Python 3.10+
- pip

## Setup (Windows PowerShell)
```powershell
cd smart_expense_tracker
py -m venv venv
.env\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FLASK_DEBUG="1"
$env:FLASK_SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```
Open http://127.0.0.1:5000

## Setup (macOS/Linux)
```bash
cd smart_expense_tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_DEBUG=1
export FLASK_SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

The SQLite database (`database.db`) is created automatically. Keep it private and
back it up regularly. This starter app is intended for local/personal use; before
public deployment, add authentication, CSRF protection, HTTPS, and production
secret management. The category chart loads Chart.js from a CDN.
