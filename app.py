
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import hashlib
from datetime import datetime
import os
# USER AUTHENTICATION SETTINGS

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "username" not in st.session_state:
    st.session_state.username = None

if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0
    # USER DATABASE

USERS_FILE = "users.csv"

def load_users():
    if os.path.exists(USERS_FILE):
        return pd.read_csv(USERS_FILE)
    return pd.DataFrame(
        columns=["username", "password", "pin"]
    )
# AUDIT LOG FUNCTION

def record_audit(action, details):

    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_log.csv")

    new_record = pd.DataFrame([{
        "Date and Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "User": st.session_state.get("username", "Admin"),
        "Action": action,
        "Details": details
    }])

    if os.path.exists(log_file):
        new_record.to_csv(log_file, mode="a", header=False, index=False)
    else:
        new_record.to_csv(log_file, index=False)

# DATABASE CONNECTION
conn = sqlite3.connect("finbot.db", check_same_thread=False)
# DATABASE BACKUP
import shutil

if os.path.exists("finbot.db"):
    shutil.copy("finbot.db", "finbot_backup.db")

conn.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    type TEXT,
    description TEXT,
    amount REAL
)
""")
columns = [row[1] for row in conn.execute(
    "PRAGMA table_info(transactions)"
).fetchall()]

if "username" not in columns:
    conn.execute("ALTER TABLE transactions ADD COLUMN username TEXT")
    conn.commit()
# ADD USER IDENTIFIER TO EXISTING TRANSACTIONS

columns = [
    row[1] for row in conn.execute(
        "PRAGMA table_info(transactions)"
    ).fetchall()
]

if "username" not in columns:
    conn.execute(
        "ALTER TABLE transactions ADD COLUMN username TEXT"
    )
    conn.commit()

conn.execute("""
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    date TEXT,
    amount REAL
)
""")


# ADD CUSTOMER PAYMENT TRACKING
debt_columns = [
    row[1] for row in conn.execute("PRAGMA table_info(debts)").fetchall()
]

if "paid_amount" not in debt_columns:
    conn.execute(
        "ALTER TABLE debts ADD COLUMN paid_amount REAL DEFAULT 0"
    )

conn.commit()


# LOAD SAVED DATA
if "transactions" not in st.session_state:
    saved_transactions = conn.execute(
        "SELECT date, type, description, amount FROM transactions"
    ).fetchall()

    st.session_state.transactions = [
        {
            "Date": row[0],
            "Type": row[1],
            "Description": row[2],
            "Amount": row[3]
        }
        for row in saved_transactions
    ]

if "debts" not in st.session_state:
    saved_debts = conn.execute(
        "SELECT customer, date, amount FROM debts"
    ).fetchall()

    st.session_state.debts = [
        {
            "Customer": row[0],
            "Date": row[1],
            "Amount Owed": row[2]
        }
        for row in saved_debts
    ]

transactions = conn.execute(
    """SELECT date, type, description, amount
    FROM transactions
    WHERE username = ?
    ORDER BY date DESC""",
    (st.session_state.username,)
).fetchall()

debts = st.session_state.debts

df = pd.DataFrame(
    transactions,
    columns=["Date", "Type", "Description", "Amount"]
)

# FINANCIAL CALCULATIONS
if not df.empty:
    sales = df[df["Type"] == "Sale"]["Amount"].sum()
    expenses = df[df["Type"] == "Expense"]["Amount"].sum()
else:
    sales = 0
    expenses = 0

profit = sales - expenses
profit_margin = (profit / sales * 100) if sales > 0 else 0

cash_in = df[df["Type"].isin(["Sale", "Customer Payment"])]["Amount"].sum() if not df.empty else 0
cash_out = df[df["Type"].isin(["Expense", "Supplier Payment"])]["Amount"].sum() if not df.empty else 0
cash_balance = cash_in - cash_out

# SIDEBAR NAVIGATION
st.sidebar.title("💰 FinBot Zimbabwe")
st.sidebar.write("SME Financial Management Assistant")

menu = st.sidebar.radio("Navigation", ["Dashboard", "Record Transactions", "Sales & Expenses", "Cash Flow", "Customer Debts", "Ask FinBot AI", "Reports", "Audit Log"])

# USER REGISTRATION AND LOGIN

import hashlib
import hmac
import secrets

conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    pin_hash TEXT NOT NULL,
    created_at TEXT
)
""")
conn.commit()


def hash_credential(value, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        value.encode(),
        salt,
        200000
    ).hex()


def make_hash(value):
    salt = secrets.token_bytes(16)
    hashed = hash_credential(value, salt)
    return salt.hex() + ":" + hashed


def verify_hash(value, stored):
    try:
        salt_hex, saved_hash = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        calculated = hash_credential(value, salt)
        return hmac.compare_digest(calculated, saved_hash)
    except (ValueError, TypeError):
        return False


if not st.session_state.authenticated:

    st.title("FinBot Zimbabwe")
    st.subheader("SME Account Access")

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with register_tab:
        st.subheader("Register Your Business")

        business_name = st.text_input("Business Name")
        new_username = st.text_input("Choose Username")
        new_password = st.text_input("Choose Password", type="password")
        new_pin = st.text_input("Choose 6-digit PIN", type="password")

        if st.button("Create Account"):
            if not business_name or not new_username or not new_password or not new_pin:
                st.error("Please complete all fields.")
            elif len(new_pin) != 6 or not new_pin.isdigit():
                st.error("PIN must contain exactly 6 digits.")
            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")
            else:
                try:
                    conn.execute(
                        """INSERT INTO users
                        (username, business_name, password_hash, pin_hash, created_at)
                        VALUES (?, ?, ?, ?, ?)""",
                        (
                            new_username.strip().lower(),
                            business_name.strip(),
                            make_hash(new_password),
                            make_hash(new_pin),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                    )
                    conn.commit()
                    st.success("Account created. Please log in.")
                except sqlite3.IntegrityError:
                    st.error("That username is already registered.")

    with login_tab:
        st.subheader("Login to FinBot")

        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")
        login_pin = st.text_input("6-digit PIN", type="password", key="login_pin")

        if st.button("Login"):
            if st.session_state.login_attempts >= 5:
                st.error("Too many attempts. Please restart the app and try again.")
            else:
                user = conn.execute(
                    """SELECT username, password_hash, pin_hash
                    FROM users WHERE username = ?""",
                    (login_username.strip().lower(),)
                ).fetchone()

                if (
                    user
                    and verify_hash(login_password, user[1])
                    and verify_hash(login_pin, user[2])
                ):
                    st.session_state.authenticated = True
                    st.session_state.username = user[0]
                    st.session_state.login_attempts = 0
                    st.rerun()
                else:
                    st.session_state.login_attempts += 1
                    st.error("Incorrect username, password or PIN.")

    st.stop()


# DASHBOARD
st.title("💰 FinBot Zimbabwe")
st.caption("Your SME Financial Management and Decision Support Assistant")

if menu == "Dashboard":

    st.header("Business Dashboard")

    # KEY FINANCIAL INDICATORS
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Sales", f"${sales:,.2f}")
    col2.metric("Total Expenses", f"${expenses:,.2f}")
    col3.metric("Net Profit", f"${profit:,.2f}")
    col4.metric("Profit Margin", f"{profit_margin:.2f}%")

    st.divider()

    # SALES VS EXPENSES CHART
    st.subheader("1. Sales vs Expenses")

    summary = pd.DataFrame({
        "Category": ["Sales", "Expenses"],
        "Amount": [sales, expenses]
    })

    st.bar_chart(summary.set_index("Category"))

    # MONTHLY SALES TREND
    st.subheader("2. Monthly Sales Trend")

    records = conn.execute(
        """SELECT date, amount FROM transactions
        WHERE type = 'Sale'"""
    ).fetchall()

    if records:

        monthly_data = pd.DataFrame(
            records, columns=["Date", "Sales"]
        )

        monthly_data["Date"] = pd.to_datetime(
            monthly_data["Date"]
        )

        monthly_data["Month"] = (
            monthly_data["Date"].dt.to_period("M").astype(str)
        )

        monthly_sales = monthly_data.groupby(
            "Month"
        )["Sales"].sum()

        st.line_chart(monthly_sales)

    else:
        st.info("Record sales to view your monthly sales trend.")

    # EXPENSE BREAKDOWN
    st.subheader("3. Expense Breakdown")

    expense_records = conn.execute(
        """SELECT description, amount FROM transactions
        WHERE type = 'Expense'"""
    ).fetchall()

    if expense_records:

        expense_data = pd.DataFrame(
            expense_records,
            columns=["Description", "Amount"]
        )

        expense_summary = expense_data.groupby(
            "Description"
        )["Amount"].sum()

        st.bar_chart(expense_summary)

    else:
        st.info("Record expenses to view your expense breakdown.")

    st.divider()

    # RECENT TRANSACTIONS
    st.subheader("Recent Transactions")

    if not df.empty:
        st.dataframe(
            df.tail(10),
            use_container_width=True
        )
    else:
        st.info("No transactions recorded yet.")

    # FINANCIAL INSIGHT
    st.subheader("FinBot Financial Insight")

    if sales == 0 and expenses == 0:
        st.write(
            "Record your business transactions to receive financial insights."
        )

    elif profit > 0:
        st.success(
            f"Your business is making a profit of ${profit:,.2f}."
        )

    elif profit < 0:
        st.warning(
            f"Your business is making a loss of ${abs(profit):,.2f}. Review your expenses."
        )

    else:
        st.info("Your business is currently breaking even.")

elif menu == "Record Transactions":

    st.header("Record Business Transactions")

    with st.form("transaction_form"):

        transaction_date = st.date_input(
            "Transaction Date", date.today()
        )

        transaction_type = st.selectbox(
            "Transaction Type",
            ["Sale", "Expense", "Customer Payment", "Supplier Payment"]
        )

        description = st.text_input("Description")

        amount = st.number_input(
            "Amount (USD)",
            min_value=0.01,
            step=1.00
        )

        submitted = st.form_submit_button("Save Transaction")

        if submitted:

            if not description.strip():
                st.error("Please enter a transaction description.")

            else:
                conn.execute(
                    """INSERT INTO transactions
                    (date, type, description, amount, username)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        str(transaction_date),
                        transaction_type,
                        description,
                        amount,
                        st.session_state.username
                    )
                )

                conn.commit()

                record_audit(
                    "Transaction Recorded",
                    "A new transaction was successfully saved."
                )

                st.success("Transaction recorded successfully!")
                st.rerun()

# SALES AND EXPENSES
elif menu == "Sales & Expenses":

    st.header("Sales and Expenses Analysis")

    col1, col2 = st.columns(2)

    col1.metric("Total Sales", f"${sales:,.2f}")
    col2.metric("Total Expenses", f"${expenses:,.2f}")

    st.metric("Net Profit / Loss", f"${profit:,.2f}")

    if not df.empty:

        st.subheader("Sales and Expenses Breakdown")

        chart_data = pd.DataFrame({
            "Category": ["Sales", "Expenses"],
            "Amount": [sales, expenses]
        })

        st.bar_chart(chart_data.set_index("Category"))

        st.subheader("Transaction Details")

        st.dataframe(
            df[df["Type"].isin(["Sale", "Expense"])],
            use_container_width=True
        )

    else:
        st.info("No sales or expense records available yet.")

    st.subheader("Profitability Assessment")

    if sales > 0:
        st.write(f"Your business profit margin is {profit_margin:.2f}%.")
    else:
        st.write("Record sales to calculate your profit margin.")

# CASH FLOW
elif menu == "Cash Flow":

    st.header("Business Cash Flow Management")

    # LOAD TRANSACTIONS DIRECTLY FROM DATABASE

    cash_records = conn.execute(
        """SELECT date, type, description, amount
        FROM transactions
        WHERE username = ?
        AND type IN (
            'Sale', 'Expense', 'Customer Payment', 'Supplier Payment'
        )""",
        (st.session_state.username,)
    ).fetchall()

    cash_df = pd.DataFrame(
        cash_records,
        columns=["Date", "Type", "Description", "Amount"]
    )

    # CALCULATE CASH INFLOWS AND OUTFLOWS
    cash_in = cash_df[
        cash_df["Type"].isin(["Sale", "Customer Payment"])
    ]["Amount"].sum()

    cash_out = cash_df[
        cash_df["Type"].isin(["Expense", "Supplier Payment"])
    ]["Amount"].sum()

    cash_balance = cash_in - cash_out

    # DISPLAY CASH FLOW SUMMARY
    col1, col2, col3 = st.columns(3)

    col1.metric("Cash Inflows", f"${cash_in:,.2f}")
    col2.metric("Cash Outflows", f"${cash_out:,.2f}")
    col3.metric("Net Cash Flow", f"${cash_balance:,.2f}")

    if cash_balance > 0:
        st.success("Your recorded cash inflows exceed your outflows.")
    elif cash_balance < 0:
        st.warning("Your recorded cash outflows exceed your inflows.")
    else:
        st.info("Your net cash flow is currently zero.")

    st.subheader("Cash Flow Transactions")

    if not cash_df.empty:
        st.dataframe(cash_df, use_container_width=True)
    else:
        st.info("No cash flow records available.")


# CUSTOMER DEBTS
elif menu == "Customer Debts":

    st.header("Customer Debt Management")

    st.subheader("Record a New Customer Debt")

    with st.form("debt_form"):

        customer = st.text_input("Customer Name")

        debt_amount = st.number_input(
            "Amount Owed (USD)",
            min_value=0.01,
            step=1.00
        )

        debt_date = st.date_input(
            "Date Debt Was Incurred",
            date.today()
        )

        submitted = st.form_submit_button("Add Customer Debt")

        if submitted:

            if not customer.strip():
                st.error("Please enter the customer name.")

            else:
                conn.execute(
                    """INSERT INTO debts
                    (customer, date, amount, paid_amount)
                    VALUES (?, ?, ?, ?)""",
                    (customer, str(debt_date), debt_amount, 0)
                )

                conn.commit()

                st.success("Customer debt saved successfully!")
                st.rerun()

    st.divider()

    st.subheader("Outstanding Customer Debts")

    debt_records = conn.execute(
        """SELECT id, customer, date, amount, paid_amount
        FROM debts ORDER BY date DESC"""
    ).fetchall()

    if debt_records:

        debt_data = []

        for record in debt_records:

            outstanding = record[3] - record[4]

            debt_data.append({
                "Customer": record[1],
                "Date": record[2],
                "Original Debt": record[3],
                "Amount Paid": record[4],
                "Outstanding Balance": outstanding
            })

        debt_df = pd.DataFrame(debt_data)

        total_debt = debt_df["Original Debt"].sum()
        total_paid = debt_df["Amount Paid"].sum()
        total_outstanding = debt_df["Outstanding Balance"].sum()

        col1, col2, col3 = st.columns(3)

        col1.metric("Total Customer Debt", f"${total_debt:,.2f}")
        col2.metric("Payments Received", f"${total_paid:,.2f}")
        col3.metric("Outstanding Balance", f"${total_outstanding:,.2f}")

        st.dataframe(debt_df, use_container_width=True)

        st.divider()

        st.subheader("Record Customer Payment")

        unpaid_debts = [
            record for record in debt_records
            if record[3] - record[4] > 0
        ]

        if unpaid_debts:

            selected_debt = st.selectbox(
                "Select Customer",
                unpaid_debts,
                format_func=lambda r: (
                    f"{r[1]} - Outstanding: ${r[3] - r[4]:,.2f}"
                )
            )

            outstanding = selected_debt[3] - selected_debt[4]

            st.write(f"Outstanding balance: ${outstanding:,.2f}")

            with st.form("payment_form"):

                payment_amount = st.number_input(
                    "Payment Received (USD)",
                    min_value=0.01,
                    max_value=float(outstanding),
                    value=0.01,
                    step=1.00
                )

                payment_submitted = st.form_submit_button(
                    "Record Payment"
                )

                if payment_submitted:

                    conn.execute(
                        """UPDATE debts
                        SET paid_amount = paid_amount + ?
                        WHERE id = ?""",
                        (payment_amount, selected_debt[0])
                    )

                    conn.commit()

                    st.success("Customer payment recorded successfully!")
                    st.rerun()

        else:
            st.success("All customer debts have been fully paid.")

    else:
        st.info("No customer debts have been recorded.")


# ASK FINBOT AI
elif menu == "Ask FinBot AI":

    st.header("Ask FinBot AI")
    st.write("Ask questions about your business finances.")

    # GET LATEST TRANSACTION DATA
    records = conn.execute(
        "SELECT type, amount FROM transactions"
    ).fetchall()

    sales = sum(
        amount for transaction_type, amount in records
        if transaction_type == "Sale"
    )

    expenses = sum(
        amount for transaction_type, amount in records
        if transaction_type == "Expense"
    )

    profit = sales - expenses

    profit_margin = (
        (profit / sales) * 100 if sales > 0 else 0
    )

    cash_in = sum(
        amount for transaction_type, amount in records
        if transaction_type in ["Sale", "Customer Payment"]
    )

    cash_out = sum(
        amount for transaction_type, amount in records
        if transaction_type in ["Expense", "Supplier Payment"]
    )

    cash_balance = cash_in - cash_out

    # GET OUTSTANDING CUSTOMER DEBTS
    debt_records = conn.execute(
        "SELECT amount, paid_amount FROM debts"
    ).fetchall()

    total_debts = sum(
        amount - paid
        for amount, paid in debt_records
    )

    st.divider()

    question = st.text_input(
        "Enter your financial question",
        placeholder="e.g. How much profit is my business making?"
    )

    if st.button("Ask FinBot"):

        if not question.strip():
            st.warning("Please enter a question.")

        else:
            q = question.lower()

            if "sales" in q or "revenue" in q:
                st.info(
                    f"Your recorded total sales are ${sales:,.2f}."
                )

            elif "expense" in q or "cost" in q:
                st.info(
                    f"Your recorded total expenses are ${expenses:,.2f}."
                )

            elif "profit" in q or "loss" in q:
                st.info(
                    f"Your net profit or loss is ${profit:,.2f}. "
                    f"Your profit margin is {profit_margin:.2f}%."
                )

            elif "cash flow" in q or "cash" in q:
                st.info(
                    f"Your cash inflows are ${cash_in:,.2f}, "
                    f"your cash outflows are ${cash_out:,.2f}, "
                    f"and your net cash flow is ${cash_balance:,.2f}."
                )

            elif "debt" in q or "owe" in q:
                st.info(
                    f"Your outstanding customer debts total "
                    f"${total_debts:,.2f}."
                )

            elif "healthy" in q or "performance" in q:
                st.info(
                    f"Your business has recorded sales of ${sales:,.2f}, "
                    f"expenses of ${expenses:,.2f}, "
                    f"net profit of ${profit:,.2f}, "
                    f"and net cash flow of ${cash_balance:,.2f}."
                )

            else:
                st.info(
                    "I can help you understand sales, expenses, "
                    "profitability, cash flow and customer debts. "
                    "Please ask a question about one of these areas."
                )

    st.caption(
        "FinBot Zimbabwe | Financial insights based on recorded business data."
    )

# REPORTS
elif menu == "Reports":

    st.header("Business Financial Reports")

    # LOAD TRANSACTION DATA
    records = conn.execute(
        """SELECT date, type, description, amount
        FROM transactions ORDER BY date DESC"""
    ).fetchall()

    report_df = pd.DataFrame(
        records,
        columns=["Date", "Type", "Description", "Amount"]
    )

    st.subheader("Transaction Report")

    if not report_df.empty:

        st.dataframe(report_df, use_container_width=True)

        csv = report_df.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download Transaction Report",
            data=csv,
            file_name="finbot_transaction_report.csv",
            mime="text/csv"
        )

        # FINANCIAL SUMMARY
        sales = report_df[
            report_df["Type"] == "Sale"
        ]["Amount"].sum()

        expenses = report_df[
            report_df["Type"] == "Expense"
        ]["Amount"].sum()

        profit = sales - expenses

        profit_margin = (
            (profit / sales) * 100 if sales > 0 else 0
        )

        st.divider()

        st.subheader("Financial Summary")

        col1, col2 = st.columns(2)

        col1.metric("Total Sales", f"${sales:,.2f}")
        col2.metric("Total Expenses", f"${expenses:,.2f}")

        col3, col4 = st.columns(2)

        col3.metric("Net Profit", f"${profit:,.2f}")
        col4.metric("Profit Margin", f"{profit_margin:.2f}%")

    else:
        st.info("No transaction records available.")

    # CUSTOMER DEBT REPORT
    st.divider()

    st.subheader("Customer Debt Report")

    debt_records = conn.execute(
        """SELECT customer, date, amount, paid_amount
        FROM debts ORDER BY date DESC"""
    ).fetchall()

    debt_report = pd.DataFrame(
        debt_records,
        columns=["Customer", "Date", "Original Debt", "Amount Paid"]
    )

    if not debt_report.empty:

        debt_report["Outstanding Balance"] = (
            debt_report["Original Debt"] - debt_report["Amount Paid"]
        )

        st.dataframe(debt_report, use_container_width=True)

        debt_csv = debt_report.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download Customer Debt Report",
            data=debt_csv,
            file_name="finbot_customer_debt_report.csv",
            mime="text/csv"
        )

    else:
        st.info("No customer debt records available.")

st.sidebar.divider()
st.sidebar.caption("FinBot Zimbabwe | Academic Prototype")
# AUDIT LOG PAGE
# FINBOT AUDIT LOG PAGE

if menu == "Audit Log":

    st.header("System Audit Log")
    st.write("Monitor activities performed on FinBot Zimbabwe.")

    if os.path.exists("audit_log.csv"):

        audit_data = pd.read_csv("audit_log.csv")

        st.subheader("Activity History")

        st.dataframe(
            audit_data,
            use_container_width=True
        )

        st.download_button(
            "Download Audit Log",
            audit_data.to_csv(index=False),
            "FinBot_Audit_Log.csv",
            "text/csv"
        )

    else:

        st.info("No audit records available yet.")