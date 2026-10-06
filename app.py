from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import pandas as pd
import plotly
import plotly.express as px
import json
import re
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = "transactiq_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

DATABASE = os.path.join(
    BASE_DIR,
    "database.db"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# DATABASE
# =========================================================

def get_db_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL
        )
    """)

    conn.commit()

    conn.close()


# =========================================================
# COLUMN NORMALIZATION
# =========================================================

def normalize_column_name(column):

    column = str(column).strip().lower()

    column = column.replace("_", " ")

    column = column.replace("-", " ")

    column = re.sub(
        r"\s+",
        " ",
        column
    )

    return column.strip()


# =========================================================
# FIND COLUMN
# =========================================================

def find_column(columns, possible_names):

    normalized_columns = {
        normalize_column_name(col): col
        for col in columns
    }

    for name in possible_names:

        normalized_name = normalize_column_name(
            name
        )

        if normalized_name in normalized_columns:

            return normalized_columns[
                normalized_name
            ]

    return None


# =========================================================
# AUTOMATIC COLUMN DETECTION
# =========================================================

def detect_transaction_columns(df):

    columns = list(df.columns)

    mapping = {}

    # DATE
    mapping["date"] = find_column(
        columns,
        [
            "date",
            "transaction date",
            "txn date",
            "value date",
            "posting date",
            "posted date"
        ]
    )

    # TIME
    mapping["time"] = find_column(
        columns,
        [
            "time",
            "transaction time",
            "txn time"
        ]
    )

    # TRANSACTION DETAILS
    mapping["transaction_details"] = find_column(
        columns,
        [
            "transaction details",
            "transaction detail",
            "description",
            "transaction description",
            "narration",
            "remarks",
            "remark",
            "details",
            "particulars",
            "merchant",
            "merchant name"
        ]
    )

    # TRANSACTION ID
    mapping["transaction_id"] = find_column(
        columns,
        [
            "transaction id",
            "txn id",
            "reference number",
            "reference no",
            "ref no",
            "utr",
            "utr number"
        ]
    )

    # TYPE
    mapping["type"] = find_column(
        columns,
        [
            "type",
            "transaction type",
            "txn type",
            "credit debit",
            "debit credit",
            "transaction mode"
        ]
    )

    # AMOUNT
    mapping["amount"] = find_column(
        columns,
        [
            "amount",
            "transaction amount",
            "txn amount",
            "value"
        ]
    )

    # DEBIT
    mapping["debit"] = find_column(
        columns,
        [
            "debit",
            "debit amount",
            "withdrawal",
            "withdrawal amount",
            "withdrawn",
            "paid",
            "payment",
            "expense"
        ]
    )

    # CREDIT
    mapping["credit"] = find_column(
        columns,
        [
            "credit",
            "credit amount",
            "deposit",
            "deposit amount",
            "received",
            "income"
        ]
    )

    return mapping


# =========================================================
# AMOUNT CLEANING
# =========================================================

def clean_amount(value):

    if pd.isna(value):

        return None

    value = str(value).strip()

    if value == "":

        return None

    # Convert (500) into -500
    if value.startswith("(") and value.endswith(")"):

        value = "-" + value[1:-1]

    # Remove commas
    value = value.replace(",", "")

    # Remove currency symbols
    value = value.replace("₹", "")
    value = value.replace("$", "")
    value = value.replace("€", "")
    value = value.replace("£", "")

    # Remove Rs / Rs.
    value = value.replace("Rs.", "")
    value = value.replace("Rs", "")

    value = value.strip()

    try:

        return float(value)

    except:

        return None


# =========================================================
# TRANSACTION TYPE STANDARDIZATION
# =========================================================

def standardize_type(value):

    if pd.isna(value):

        return None

    value = str(value).strip().lower()

    paid_values = [

        "debit",
        "withdrawal",
        "withdraw",
        "withdrawn",
        "paid",
        "payment",
        "expense",
        "spent",
        "sent",
        "dr",
        "d"
    ]

    received_values = [

        "credit",
        "deposit",
        "received",
        "income",
        "refund",
        "cr",
        "c"
    ]

    if value in paid_values:

        return "paid"

    if value in received_values:

        return "received"

    return value


# =========================================================
# AUTOMATIC TRANSACTION CATEGORIZATION
# =========================================================

CATEGORY_KEYWORDS = {

    "Food": [

        "swiggy",
        "zomato",
        "uber eats",
        "restaurant",
        "cafe",
        "coffee",
        "bakery",
        "food",
        "pizza",
        "dominos",
        "mcdonald",
        "kfc",
        "subway",
        "biryani"
    ],

    "Shopping": [

        "amazon",
        "flipkart",
        "myntra",
        "ajio",
        "meesho",
        "shopping",
        "walmart",
        "reliance trends",
        "dmart",
        "mall"
    ],

    "Travel": [

        "uber",
        "ola",
        "rapido",
        "taxi",
        "cab",
        "fuel",
        "petrol",
        "diesel",
        "shell",
        "hpcl",
        "bpcl",
        "indianoil",
        "irctc",
        "flight",
        "airline",
        "bus",
        "metro",
        "travel"
    ],

    "Bills": [

        "electricity",
        "electric bill",
        "water bill",
        "gas bill",
        "broadband",
        "internet bill",
        "bill payment",
        "airtel bill",
        "jio bill",
        "rent",
        "maintenance"
    ],

    "Recharge": [

        "recharge",
        "mobile recharge",
        "jio recharge",
        "airtel recharge",
        "vi recharge",
        "vodafone",
        "bsnl"
    ],

    "Entertainment": [

        "netflix",
        "spotify",
        "hotstar",
        "prime video",
        "youtube premium",
        "movie",
        "cinema",
        "pvr",
        "inox",
        "gaming",
        "steam"
    ],

    "Health": [

        "apollo",
        "pharmacy",
        "medical",
        "hospital",
        "doctor",
        "medicine",
        "medplus",
        "netmeds",
        "1mg",
        "health"
    ],

    "Education": [

        "college",
        "university",
        "school",
        "course",
        "udemy",
        "coursera",
        "exam",
        "education",
        "books",
        "bookstore"
    ]
}


def categorize_transaction(details):

    if pd.isna(details):

        return "Others"

    text = str(details).strip().lower()

    if text == "":

        return "Others"

    # Entertainment first
    for keyword in CATEGORY_KEYWORDS["Entertainment"]:

        if keyword in text:

            return "Entertainment"

    # Bills before Recharge
    for keyword in CATEGORY_KEYWORDS["Bills"]:

        if keyword in text:

            return "Bills"

    # Travel before Food
    for keyword in CATEGORY_KEYWORDS["Travel"]:

        if keyword in text:

            return "Travel"

    # Remaining categories
    for category, keywords in CATEGORY_KEYWORDS.items():

        if category in [
            "Entertainment",
            "Bills",
            "Travel"
        ]:

            continue

        for keyword in keywords:

            if keyword in text:

                return category

    return "Others"


# =========================================================
# STANDARDIZE TRANSACTIONS
# =========================================================

def standardize_transactions(df):

    mapping = detect_transaction_columns(df)

    print("\nDetected column mapping:")
    print(mapping)

    result = pd.DataFrame()

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    if mapping["date"]:

        result["date"] = pd.to_datetime(
            df[mapping["date"]],
            errors="coerce",
            dayfirst=True
        )

    else:

        result["date"] = pd.NaT

    # -----------------------------------------------------
    # TIME
    # -----------------------------------------------------

    if mapping["time"]:

        result["time"] = (
            df[mapping["time"]]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        result["time"] = ""

    # -----------------------------------------------------
    # TRANSACTION DETAILS
    # -----------------------------------------------------

    if mapping["transaction_details"]:

        result["transaction_details"] = (

            df[mapping["transaction_details"]]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        result["transaction_details"] = ""

    # -----------------------------------------------------
    # TRANSACTION ID
    # -----------------------------------------------------

    if mapping["transaction_id"]:

        result["transaction_id"] = (

            df[mapping["transaction_id"]]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        result["transaction_id"] = ""

    # -----------------------------------------------------
    # AMOUNT + TYPE
    # -----------------------------------------------------

    # CASE 1:
    # Separate debit and credit columns

    if mapping["debit"] or mapping["credit"]:

        debit_values = pd.Series(
            0,
            index=df.index,
            dtype="float64"
        )

        credit_values = pd.Series(
            0,
            index=df.index,
            dtype="float64"
        )

        if mapping["debit"]:

            debit_values = (

                df[mapping["debit"]]
                .apply(clean_amount)
                .fillna(0)
            )

        if mapping["credit"]:

            credit_values = (

                df[mapping["credit"]]
                .apply(clean_amount)
                .fillna(0)
            )

        result["amount"] = (

            debit_values.abs()
            +
            credit_values.abs()
        )

        result["type"] = "received"

        result.loc[
            debit_values.abs() > 0,
            "type"
        ] = "paid"

        result.loc[
            (debit_values.abs() == 0)
            &
            (credit_values.abs() > 0),
            "type"
        ] = "received"

    # CASE 2:
    # Single amount column

    elif mapping["amount"]:

        raw_amount = (

            df[mapping["amount"]]
            .apply(clean_amount)
        )

        result["amount"] = raw_amount.abs()

        if mapping["type"]:

            result["type"] = (

                df[mapping["type"]]
                .apply(standardize_type)
            )

        else:

            result["type"] = raw_amount.apply(

                lambda x:

                "paid"

                if pd.notna(x) and x < 0

                else "received"
            )

    # CASE 3:
    # No amount column found

    else:

        result["amount"] = 0

        result["type"] = "unknown"

    # -----------------------------------------------------
    # CLEAN TYPE
    # -----------------------------------------------------

    result["type"] = (

        result["type"]
        .fillna("unknown")
    )

    # -----------------------------------------------------
    # REMOVE INVALID AMOUNTS
    # -----------------------------------------------------

    result = result[
        result["amount"].notna()
    ]

    result = result[
        result["amount"] > 0
    ]

    # -----------------------------------------------------
    # AUTOMATIC CATEGORY
    # -----------------------------------------------------

    result["category"] = (

        result["transaction_details"]
        .apply(categorize_transaction)
    )

    # -----------------------------------------------------
    # DAY
    # -----------------------------------------------------

    result["day"] = (

        result["date"]
        .dt.day_name()
    )

    # -----------------------------------------------------
    # FINAL COLUMN ORDER
    # -----------------------------------------------------

    result = result[
        [
            "date",
            "time",
            "transaction_details",
            "transaction_id",
            "type",
            "amount",
            "category",
            "day"
        ]
    ]

    return result, mapping


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# WELCOME
# =========================================================

@app.route("/welcome")
def welcome():

    return render_template(
        "welcome.html"
    )


# =========================================================
# SIGNUP
# =========================================================

@app.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():

    if request.method == "POST":

        name = request.form["name"].strip()

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form["password"]

        if not name or not email or not password:

            flash(
                "Please fill all fields."
            )

            return redirect(
                url_for("signup")
            )

        hashed_password = generate_password_hash(
            password
        )

        conn = get_db_connection()

        try:

            conn.execute(
                """
                INSERT INTO users
                (name, email, password)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    email,
                    hashed_password
                )
            )

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            flash(
                "Email already registered."
            )

            return redirect(
                url_for("signup")
            )

        conn.close()

        flash(
            "Account created successfully."
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "signup.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            session["user_name"] = user["name"]

            return redirect(
                url_for("upload")
            )

        flash(
            "Invalid email or password."
        )

    return render_template(
        "login.html"
    )


# =========================================================
# UPLOAD
# =========================================================

@app.route(
    "/upload",
    methods=["GET", "POST"]
)
def upload():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        file = request.files.get("file")

        # -------------------------------------------------
        # CHECK FILE
        # -------------------------------------------------

        if not file or file.filename == "":

            flash(
                "Please select a CSV file."
            )

            return redirect(
                url_for("upload")
            )

        if not file.filename.lower().endswith(".csv"):

            flash(
                "Please upload a CSV file."
            )

            return redirect(
                url_for("upload")
            )

        user_id = session["user_id"]

        original_path = os.path.join(
            UPLOAD_FOLDER,
            f"user_{user_id}_transactions.csv"
        )

        cleaned_path = os.path.join(
            UPLOAD_FOLDER,
            f"user_{user_id}_cleaned.csv"
        )

        try:

            # -------------------------------------------------
            # SAVE ORIGINAL FILE
            # -------------------------------------------------

            file.save(
                original_path
            )

            # -------------------------------------------------
            # READ CSV
            # -------------------------------------------------

            df = pd.read_csv(
                original_path
            )

            print("\n====================================")
            print("ORIGINAL CSV")
            print("====================================")

            print(df.head())

            # -------------------------------------------------
            # CLEANING SUMMARY
            # -------------------------------------------------

            original_rows = len(df)

            # Number of rows containing at least one null
            null_rows = int(
                df.isnull()
                .any(axis=1)
                .sum()
            )

            # Number of exact duplicate rows
            duplicate_rows = int(
                df.duplicated()
                .sum()
            )

            # Remove duplicate rows
            df = df.drop_duplicates().copy()

            # -------------------------------------------------
            # STANDARDIZE TRANSACTIONS
            # -------------------------------------------------

            cleaned_df, mapping = (
                standardize_transactions(df)
            )

            cleaned_rows = len(
                cleaned_df
            )

            # -------------------------------------------------
            # SAVE CLEANED CSV
            # -------------------------------------------------

            cleaned_df.to_csv(
                cleaned_path,
                index=False
            )

            # -------------------------------------------------
            # SAVE CLEANING SUMMARY
            # -------------------------------------------------

            session["cleaning_summary"] = {

                "original_rows": original_rows,

                "duplicate_rows": duplicate_rows,

                "null_rows": null_rows,

                "cleaned_rows": cleaned_rows
            }

            # -------------------------------------------------
            # PRINT CLEANING SUMMARY
            # -------------------------------------------------

            print("\n====================================")
            print("CSV CLEANING SUMMARY")
            print("====================================")

            print(
                "Original rows:",
                original_rows
            )

            print(
                "Duplicate rows:",
                duplicate_rows
            )

            print(
                "Rows with null values:",
                null_rows
            )

            print(
                "Cleaned rows:",
                cleaned_rows
            )

            # -------------------------------------------------
            # PRINT CLEANED CSV
            # -------------------------------------------------

            print("\n====================================")
            print("CLEANED CSV")
            print("====================================")

            print(
                cleaned_df.head()
            )

            # -------------------------------------------------
            # CATEGORY COUNTS
            # -------------------------------------------------

            print("\n====================================")
            print("CATEGORY COUNTS")
            print("====================================")

            print(
                cleaned_df[
                    "category"
                ].value_counts()
            )

            # -------------------------------------------------
            # TRANSACTION TYPE COUNTS
            # -------------------------------------------------

            print("\n====================================")
            print("TRANSACTION TYPE COUNTS")
            print("====================================")

            print(
                cleaned_df[
                    "type"
                ].value_counts()
            )

            # -------------------------------------------------
            # FINAL COLUMNS
            # -------------------------------------------------

            print("\n====================================")
            print("FINAL COLUMNS")
            print("====================================")

            print(
                list(
                    cleaned_df.columns
                )
            )

            print("====================================")

            flash(
                "CSV uploaded, standardized and categorized successfully!"
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as e:

            print(
                "UPLOAD ERROR:",
                e
            )

            flash(
                f"Could not process the CSV: {str(e)}"
            )

            return redirect(
                url_for("upload")
            )

    return render_template(
        "upload.html"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    cleaned_path = os.path.join(
        UPLOAD_FOLDER,
        f"user_{user_id}_cleaned.csv"
    )

    # -----------------------------------------------------
    # CHECK CLEANED FILE
    # -----------------------------------------------------

    if not os.path.exists(
        cleaned_path
    ):

        return redirect(
            url_for("upload")
        )

    # -----------------------------------------------------
    # READ CLEANED CSV
    # -----------------------------------------------------

    df = pd.read_csv(
        cleaned_path
    )

    if df.empty:

        flash(
            "No transaction data available."
        )

        return redirect(
            url_for("upload")
        )

    # -----------------------------------------------------
    # CONVERT DATE
    # -----------------------------------------------------

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    # -----------------------------------------------------
    # CONVERT AMOUNT
    # -----------------------------------------------------

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    ).fillna(0)

    # -----------------------------------------------------
    # FILTER
    # -----------------------------------------------------

    selected_day = request.args.get(
        "day",
        "All"
    )

    if selected_day != "All":

        filtered_df = df[
            df["day"] == selected_day
        ].copy()

    else:

        filtered_df = df.copy()

    # -----------------------------------------------------
    # KPI
    # -----------------------------------------------------

    total_spent = filtered_df.loc[
        filtered_df["type"] == "paid",
        "amount"
    ].sum()

    total_received = filtered_df.loc[
        filtered_df["type"] == "received",
        "amount"
    ].sum()

    transactions = len(
        filtered_df
    )

    balance = (
        total_received
        -
        total_spent
    )

    # -----------------------------------------------------
    # SPENDING TREND
    # -----------------------------------------------------

    spending_df = filtered_df[
        filtered_df["type"] == "paid"
    ].copy()

    if not spending_df.empty:

        trend_df = (

            spending_df
            .groupby("date")["amount"]
            .sum()
            .reset_index()
        )

        fig_trend = px.line(
            trend_df,
            x="date",
            y="amount",
            markers=True
        )

    else:

        fig_trend = px.line()

    fig_trend.update_layout(

        margin=dict(
            l=20,
            r=20,
            t=20,
            b=20
        ),

        xaxis_title="",

        yaxis_title="Amount"
    )

    trend_chart = json.dumps(
        fig_trend,
        cls=plotly.utils.PlotlyJSONEncoder
    )

    # -----------------------------------------------------
    # SPENDING BY DAY
    # -----------------------------------------------------

    if not spending_df.empty:

        day_order = [

            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday"
        ]

        day_df = (

            spending_df
            .groupby("day")["amount"]
            .sum()
            .reindex(day_order)
            .fillna(0)
            .reset_index()
        )

        fig_day = px.bar(
            day_df,
            x="day",
            y="amount"
        )

    else:

        fig_day = px.bar()

    fig_day.update_layout(

        margin=dict(
            l=20,
            r=20,
            t=20,
            b=20
        ),

        xaxis_title="",

        yaxis_title="Amount"
    )

    day_chart = json.dumps(
        fig_day,
        cls=plotly.utils.PlotlyJSONEncoder
    )

    # -----------------------------------------------------
    # PIE CHART
    # -----------------------------------------------------
    # Keeping transaction details for now.
    # We can change this to category later.

    if not spending_df.empty:

        detail_df = (

            spending_df
            .groupby(
                "transaction_details"
            )["amount"]
            .sum()
            .reset_index()
            .sort_values(
                "amount",
                ascending=False
            )
            .head(10)
        )

        fig_pie = px.pie(

            detail_df,

            names="transaction_details",

            values="amount"
        )

    else:

        fig_pie = px.pie()

    fig_pie.update_layout(

        margin=dict(
            l=20,
            r=20,
            t=20,
            b=20
        )
    )

    pie_chart = json.dumps(
        fig_pie,
        cls=plotly.utils.PlotlyJSONEncoder
    )

    # -----------------------------------------------------
    # SMART INSIGHTS
    # -----------------------------------------------------

    insights = []

    if total_spent > 0:

        insights.append(
            f"You spent ₹{total_spent:,.2f}."
        )

    if total_received > 0:

        insights.append(
            f"You received ₹{total_received:,.2f}."
        )

    if total_received > total_spent:

        insights.append(
            "Your received amount is higher than your spending."
        )

    elif total_spent > total_received:

        insights.append(
            "Your spending is higher than your received amount."
        )

    if not spending_df.empty:

        highest_transaction = spending_df.loc[
            spending_df["amount"].idxmax()
        ]

        insights.append(

            f"Your highest transaction was "
            f"₹{highest_transaction['amount']:,.2f} "
            f"for "
            f"{highest_transaction['transaction_details']}."
        )

    # -----------------------------------------------------
    # MONEY FLOW
    # -----------------------------------------------------

    money_flow = {

        "spent": total_spent,

        "received": total_received
    }

    # -----------------------------------------------------
    # AVAILABLE DAYS
    # -----------------------------------------------------

    available_days = [

        "All",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    ]

    # -----------------------------------------------------
    # CLEANING SUMMARY
    # -----------------------------------------------------
    # IMPORTANT:
    # Use session.get() instead of session.pop()
    # so the summary remains visible after refresh/filter.

    cleaning_summary = session.get(
        "cleaning_summary",
        None
    )

    # -----------------------------------------------------
    # RENDER DASHBOARD
    # -----------------------------------------------------

    return render_template(

        "dashboard.html",

        user_name=session.get(
            "user_name"
        ),

        total_spent=total_spent,

        total_received=total_received,

        transactions=transactions,

        balance=balance,

        trend_chart=trend_chart,

        day_chart=day_chart,

        pie_chart=pie_chart,

        insights=insights,

        money_flow=money_flow,

        available_days=available_days,

        selected_day=selected_day,

        cleaning_summary=cleaning_summary
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("index")
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )