import csv
import io
import math
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "database.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

CATEGORIES = [
    "Food", "Travel", "Shopping", "Bills", "Entertainment",
    "Health", "Education", "Salary", "Freelance", "Other"
]
EXPENSE_CATEGORIES = [c for c in CATEGORIES if c not in ("Salary", "Freelance")]


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db_connection()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                month TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                UNIQUE(category, month)
            );
        """)
        conn.commit()


def money(value):
    return f"₹{value:,.2f}"


app.jinja_env.filters["money"] = money


def month_value(raw):
    try:
        datetime.strptime(raw, "%Y-%m")
        return raw
    except (ValueError, TypeError):
        return date.today().strftime("%Y-%m")


@app.route("/")
def index():
    selected_month = month_value(request.args.get("month", date.today().strftime("%Y-%m")))
    search = request.args.get("q", "").strip()[:80]
    category = request.args.get("category", "").strip()
    tx_type = request.args.get("type", "").strip()

    conditions, params = ["substr(date, 1, 7) = ?"], [selected_month]
    if search:
        conditions.append("(title LIKE ? OR category LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if category in CATEGORIES:
        conditions.append("category = ?")
        params.append(category)
    if tx_type in ("income", "expense"):
        conditions.append("type = ?")
        params.append(tx_type)

    where = " AND ".join(conditions)
    with closing(get_db_connection()) as conn:
        transactions = conn.execute(
            f"SELECT * FROM transactions WHERE {where} ORDER BY date DESC, id DESC",
            params
        ).fetchall()

        totals = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type='income' THEN amount END), 0) AS income,
                COALESCE(SUM(CASE WHEN type='expense' THEN amount END), 0) AS expenses
            FROM transactions WHERE substr(date, 1, 7)=?
        """, (selected_month,)).fetchone()

        category_rows = conn.execute("""
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE substr(date, 1, 7)=? AND type='expense'
            GROUP BY category ORDER BY total DESC
        """, (selected_month,)).fetchall()

        budget_rows = conn.execute("""
            SELECT b.category, b.amount AS budget,
                   COALESCE(SUM(t.amount), 0) AS spent
            FROM budgets b
            LEFT JOIN transactions t
              ON t.category=b.category AND t.type='expense'
             AND substr(t.date,1,7)=b.month
            WHERE b.month=?
            GROUP BY b.category, b.amount
            ORDER BY b.category
        """, (selected_month,)).fetchall()

    income = totals["income"]
    expenses = totals["expenses"]
    budget_alerts = [
        {"category": row["category"], "budget": row["budget"],
         "spent": row["spent"], "percent": min(100, row["spent"] / row["budget"] * 100)}
        for row in budget_rows if row["spent"] >= row["budget"] * 0.8
    ]
    return render_template(
        "index.html", transactions=transactions, income=income,
        expenses=expenses, balance=income-expenses, categories=CATEGORIES,
        category_rows=category_rows, budget_rows=budget_rows,
        budget_alerts=budget_alerts, selected_month=selected_month,
        search=search, selected_category=category, selected_type=tx_type
    )


@app.route("/add", methods=["GET", "POST"])
def add_transaction():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        amount_text = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        tx_type = request.form.get("type", "").strip().lower()
        raw_date = request.form.get("date", "").strip()

        try:
            amount = float(amount_text)
        except (TypeError, ValueError):
            amount = 0.0

        try:
            parsed_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            parsed_date = None

        errors = []
        if not title or len(title) > 120:
            errors.append("Enter a description (maximum 120 characters).")
        if not math.isfinite(amount) or amount <= 0:
            errors.append("Enter an amount greater than zero.")
        if tx_type not in ("income", "expense"):
            errors.append("Choose income or expense.")
        if category not in CATEGORIES:
            errors.append("Choose a valid category.")
        if parsed_date is None:
            errors.append("Choose a valid date.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("add_transaction.html", categories=CATEGORIES,
                                   today=date.today().isoformat()), 400

        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO transactions(title, amount, category, type, date) VALUES(?,?,?,?,?)",
                (title, amount, category, tx_type, parsed_date.isoformat())
            )
            conn.commit()
        flash("Transaction saved.", "success")
        return redirect(url_for("index"))

    return render_template("add_transaction.html", categories=CATEGORIES,
                           today=date.today().isoformat())


@app.post("/delete/<int:transaction_id>")
def delete_transaction(transaction_id):
    with closing(get_db_connection()) as conn:
        cur = conn.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
        conn.commit()
    flash("Transaction deleted." if cur.rowcount else "Transaction not found.",
          "success" if cur.rowcount else "error")
    return redirect(url_for("index"))


@app.route("/budgets", methods=["GET", "POST"])
def budgets():
    selected_month = month_value(request.values.get("month", date.today().strftime("%Y-%m")))
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        amount_text = request.form.get("amount", "").strip()
        try:
            amount = float(amount_text)
        except (TypeError, ValueError):
            amount = 0
        if category not in EXPENSE_CATEGORIES or not math.isfinite(amount) or amount <= 0:
            flash("Choose a valid expense category and a budget greater than zero.", "error")
        else:
            with closing(get_db_connection()) as conn:
                conn.execute("""
                    INSERT INTO budgets(category, month, amount) VALUES(?,?,?)
                    ON CONFLICT(category, month) DO UPDATE SET amount=excluded.amount
                """, (category, selected_month, amount))
                conn.commit()
            flash("Budget saved.", "success")
        return redirect(url_for("budgets", month=selected_month))

    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT b.category, b.amount AS budget,
                   COALESCE(SUM(t.amount),0) AS spent
            FROM budgets b LEFT JOIN transactions t
              ON t.category=b.category AND t.type='expense'
             AND substr(t.date,1,7)=b.month
            WHERE b.month=? GROUP BY b.category,b.amount ORDER BY b.category
        """, (selected_month,)).fetchall()
    return render_template("budgets.html", rows=rows, categories=EXPENSE_CATEGORIES,
                           selected_month=selected_month)


@app.get("/export")
def export_csv():
    selected_month = month_value(request.args.get("month", date.today().strftime("%Y-%m")))
    with closing(get_db_connection()) as conn:
        rows = conn.execute("""
            SELECT date, title, type, category, amount FROM transactions
            WHERE substr(date,1,7)=? ORDER BY date DESC, id DESC
        """, (selected_month,)).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Description", "Type", "Category", "Amount (INR)"])
    for row in rows:
        writer.writerow([row["date"], row["title"], row["type"], row["category"], row["amount"]])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=expenses-{selected_month}.csv"})


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
