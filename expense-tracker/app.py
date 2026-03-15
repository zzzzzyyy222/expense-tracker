from flask import Flask, render_template, request, redirect, jsonify, send_file
import sqlite3
from datetime import datetime
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def setup_budget_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budget (
            id INTEGER PRIMARY KEY,
            monthly_limit REAL NOT NULL
        )
    """)

    conn.execute("""
        INSERT OR IGNORE INTO budget (id, monthly_limit)
        VALUES (1, 10000)
    """)

    conn.commit()
    conn.close()


setup_budget_table()


@app.route("/")
def index():

    conn = get_db()

    filter_type = request.args.get("filter", "this_month")

    now = datetime.now()

    current_month = now.strftime("%Y-%m")

    if now.month == 1:
        last_month = f"{now.year - 1}-12"
    else:
        last_month = f"{now.year}-{str(now.month - 1).zfill(2)}"

    if filter_type == "last_month":

        condition = "WHERE date LIKE ?"
        params = [last_month + "%"]
        filter_label = "Last Month"

    elif filter_type == "six_months":

        condition = "WHERE date >= date('now','-6 months')"
        params = []
        filter_label = "Past 6 Months"

    elif filter_type == "last_year":

        condition = "WHERE date LIKE ?"
        params = [str(now.year - 1) + "%"]
        filter_label = "Last Year"

    else:

        condition = "WHERE date LIKE ?"
        params = [current_month + "%"]
        filter_label = "This Month"

    expenses = conn.execute(f"""
        SELECT * FROM expenses
        {condition}
        ORDER BY date DESC, id DESC
    """, params).fetchall()

    total_row = conn.execute(
        "SELECT SUM(amount) AS total FROM expenses"
    ).fetchone()

    total = total_row["total"] if total_row["total"] else 0

    monthly_row = conn.execute(
        "SELECT SUM(amount) AS total FROM expenses WHERE date LIKE ?",
        (current_month + "%",)
    ).fetchone()

    monthly_total = monthly_row["total"] if monthly_row["total"] else 0

    budget_row = conn.execute(
        "SELECT monthly_limit FROM budget WHERE id = 1"
    ).fetchone()

    budget = budget_row["monthly_limit"] if budget_row else 10000

    top_category_row = conn.execute(f"""
        SELECT category, SUM(amount) AS total
        FROM expenses
        {condition}
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """, params).fetchone()

    top_category = top_category_row["category"] if top_category_row else "No Data"

    budget_percent = 0

    if budget > 0:
        budget_percent = min((monthly_total / budget) * 100, 100)

    over_budget = monthly_total > budget

    conn.close()

    return render_template(
        "index.html",
        expenses=expenses,
        total=round(total, 2),
        monthly_total=round(monthly_total, 2),
        budget=round(budget, 2),
        budget_percent=round(budget_percent, 2),
        over_budget=over_budget,
        top_category=top_category,
        filter_type=filter_type,
        filter_label=filter_label
    )


@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


@app.route("/add", methods=["POST"])
def add_expense():

    amount = request.form["amount"]
    category = request.form["category"]
    note = request.form["note"]
    date = request.form["date"]

    conn = get_db()

    conn.execute(
        "INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
        (amount, category, note, date)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/delete/<int:id>")
def delete(id):

    conn = get_db()

    conn.execute(
        "DELETE FROM expenses WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    conn = get_db()

    if request.method == "POST":

        amount = request.form["amount"]
        category = request.form["category"]
        note = request.form["note"]
        date = request.form["date"]

        conn.execute("""
            UPDATE expenses
            SET amount = ?, category = ?, note = ?, date = ?
            WHERE id = ?
        """, (amount, category, note, date, id))

        conn.commit()
        conn.close()

        return redirect("/")

    expense = conn.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (id,)
    ).fetchone()

    conn.close()

    return render_template("edit.html", expense=expense)


@app.route("/set-budget", methods=["POST"])
def set_budget():

    limit = request.form["limit"]

    conn = get_db()

    conn.execute(
        "UPDATE budget SET monthly_limit = ? WHERE id = 1",
        (limit,)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/chart-data")
def chart_data():

    conn = get_db()

    filter_type = request.args.get("filter", "this_month")

    now = datetime.now()

    current_month = now.strftime("%Y-%m")

    if now.month == 1:
        last_month = f"{now.year - 1}-12"
    else:
        last_month = f"{now.year}-{str(now.month - 1).zfill(2)}"

    if filter_type == "last_month":

        condition = "WHERE date LIKE ?"
        params = [last_month + "%"]

    elif filter_type == "six_months":

        condition = "WHERE date >= date('now','-6 months')"
        params = []

    elif filter_type == "last_year":

        condition = "WHERE date LIKE ?"
        params = [str(now.year - 1) + "%"]

    else:

        condition = "WHERE date LIKE ?"
        params = [current_month + "%"]

    category_data = conn.execute(f"""
        SELECT category, SUM(amount) AS total
        FROM expenses
        {condition}
        GROUP BY category
        ORDER BY total DESC
    """, params).fetchall()

    line_data = conn.execute(f"""
        SELECT date AS day, SUM(amount) AS total
        FROM expenses
        {condition}
        GROUP BY date
        ORDER BY date
    """, params).fetchall()

    conn.close()

    categories = [row["category"] for row in category_data]
    totals = [row["total"] for row in category_data]

    line_labels = [row["day"] for row in line_data]
    line_totals = [row["total"] for row in line_data]

    return jsonify({
        "categories": categories,
        "totals": totals,
        "line_labels": line_labels,
        "line_totals": line_totals
    })


@app.route("/report")
def report():

    conn = get_db()

    data = conn.execute(
        "SELECT date, category, note, amount FROM expenses ORDER BY date DESC"
    ).fetchall()

    conn.close()

    buffer = BytesIO()

    pdf = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()

    elements = []

    title = Paragraph("Expense Report", styles["Title"])

    elements.append(title)
    elements.append(Spacer(1, 12))

    table_data = [["Date", "Category", "Note", "Amount (RM)"]]

    total_amount = 0

    for row in data:

        amount = float(row["amount"])

        total_amount += amount

        table_data.append([
            row["date"],
            row["category"],
            row["note"] if row["note"] else "-",
            f"{amount:.2f}"
        ])

    table_data.append(["", "", "Total", f"{total_amount:.2f}"])

    table = Table(table_data, repeatRows=1)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT")
    ]))

    elements.append(table)

    pdf.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="expense_report.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)