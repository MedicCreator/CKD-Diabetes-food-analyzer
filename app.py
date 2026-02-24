# =====================================================
# RENAL + DIABETES CLINICAL PLATFORM – FINAL ADMIN VERSION
# =====================================================

import streamlit as st
import sqlite3
import pandas as pd
import hashlib
from datetime import date, timedelta

st.set_page_config(page_title="Renal + Diabetes Clinical Platform", layout="wide")

# =====================================================
# DATABASE
# =====================================================

conn = sqlite3.connect("renal_platform.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    log_date TEXT,
    sodium REAL,
    potassium REAL,
    phosphorus REAL,
    carbs REAL,
    protein REAL,
    water REAL,
    ckd_risk REAL,
    diabetes_risk REAL,
    combined_risk REAL,
    PRIMARY KEY (username, log_date)
)
""")
conn.commit()

# =====================================================
# AUTH SYSTEM (HASHLIB SAFE)
# =====================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register(username, password):
    try:
        c.execute("INSERT INTO users VALUES (?,?)",
                  (username, hash_password(password)))
        conn.commit()
        return True
    except:
        return False

def login(username, password):
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if result and result[0] == hash_password(password):
        return True
    return False

if "user" not in st.session_state:
    st.session_state.user = None

# =====================================================
# LOGIN SCREEN
# =====================================================

if not st.session_state.user:

    st.title("🔐 Renal + Diabetes Clinical Platform")

    mode = st.radio("Select Mode", ["Login", "Register"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button(mode):
        if mode == "Register":
            if register(username, password):
                st.success("Account created. Please login.")
            else:
                st.error("Username already exists.")
        else:
            if login(username, password):
                st.session_state.user = username
                st.success("Login successful.")
                st.rerun()
            else:
                st.error("Invalid credentials.")

    st.stop()

# =====================================================
# MAIN APP
# =====================================================

st.sidebar.title(f"👤 {st.session_state.user}")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
weight = st.sidebar.number_input("Body Weight (kg)", 70.0)
hba1c = st.sidebar.number_input("HbA1c (%)", 6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", 100)
fluid_limit = st.sidebar.number_input("Daily Fluid Limit (ml)", 2000.0)

protein_target = weight * 0.8

st.title("Renal + Diabetes Daily Entry")

sodium = st.number_input("Total Sodium (mg)", 0.0)
potassium = st.number_input("Total Potassium (mg)", 0.0)
phosphorus = st.number_input("Total Phosphorus (mg)", 0.0)
carbs = st.number_input("Total Carbohydrates (g)", 0.0)
protein = st.number_input("Total Protein (g)", 0.0)
water = st.number_input("Total Water Intake (ml)", 0.0)

# =====================================================
# LIMITS BY CKD STAGE
# =====================================================

limits = {
    1: {"sodium":2300,"potassium":3500,"phosphorus":1000},
    2: {"sodium":2300,"potassium":3500,"phosphorus":1000},
    3: {"sodium":2000,"potassium":2500,"phosphorus":900},
    4: {"sodium":2000,"potassium":2000,"phosphorus":800},
    5: {"sodium":2000,"potassium":1500,"phosphorus":700},
}[stage]

limits["carbs"] = 180

# =====================================================
# RISK CALCULATION
# =====================================================

def risk_label(p):
    if p <= 40:
        return "Low", "🟢"
    elif p <= 70:
        return "Moderate", "🟡"
    else:
        return "High", "🔴"

ckd_factors = {
    "Sodium": (sodium/limits["sodium"])*100 if limits["sodium"] else 0,
    "Potassium": (potassium/limits["potassium"])*100 if limits["potassium"] else 0,
    "Phosphorus": (phosphorus/limits["phosphorus"])*100 if limits["phosphorus"] else 0
}

ckd_score = max(ckd_factors.values())
dm_score = (carbs/limits["carbs"])*100 if limits["carbs"] else 0
combined_score = round((ckd_score*0.6)+(dm_score*0.4),1)

# =====================================================
# SAVE DAILY LOG
# =====================================================

today = str(date.today())

c.execute("""
INSERT OR REPLACE INTO logs
VALUES (?,?,?,?,?,?,?,?,?,?,?)
""", (
    st.session_state.user,
    today,
    sodium,
    potassium,
    phosphorus,
    carbs,
    protein,
    water,
    ckd_score,
    dm_score,
    combined_score
))
conn.commit()

# =====================================================
# DISPLAY RISK SUMMARY
# =====================================================

st.header("Risk Analysis")

label_ckd, icon_ckd = risk_label(ckd_score)
label_dm, icon_dm = risk_label(dm_score)
label_comb, icon_comb = risk_label(combined_score)

st.write(f"CKD Risk: {icon_ckd} {label_ckd} ({round(ckd_score,1)}%)")
for k,v in sorted(ckd_factors.items(), key=lambda x:x[1], reverse=True):
    st.write(f"   • {k}: {round(v,1)}% of daily limit")

st.write(f"Diabetes Risk: {icon_dm} {label_dm} ({round(dm_score,1)}%)")
st.write(f"   • Carbohydrates: {round(dm_score,1)}% of daily limit")

st.write(f"Combined Risk: {icon_comb} {label_comb} ({combined_score}%)")

# =====================================================
# PROTEIN & FLUID
# =====================================================

st.header("Protein & Fluid Summary")

protein_percent = (protein/protein_target)*100 if protein_target else 0

st.write(f"Protein Target: {round(protein_target,1)} g")
st.write(f"Protein Consumed: {protein} g ({round(protein_percent,1)}%)")
st.write(f"Fluid Intake: {water} ml / {fluid_limit} ml")

# =====================================================
# WEEKLY DASHBOARD
# =====================================================

st.header("📊 Weekly Dashboard")

week_ago = str(date.today() - timedelta(days=7))

df_week = pd.read_sql_query(
    "SELECT * FROM logs WHERE username=? AND log_date>=?",
    conn,
    params=(st.session_state.user, week_ago)
)

if not df_week.empty:
    st.line_chart(df_week.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])
else:
    st.info("No weekly data yet.")

# =====================================================
# MONTHLY DASHBOARD
# =====================================================

st.header("📅 Monthly Dashboard")

month_ago = str(date.today() - timedelta(days=30))

df_month = pd.read_sql_query(
    "SELECT * FROM logs WHERE username=? AND log_date>=?",
    conn,
    params=(st.session_state.user, month_ago)
)

if not df_month.empty:
    st.line_chart(df_month.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])
else:
    st.info("No monthly data yet.")

# =====================================================
# CSV EXPORT
# =====================================================

if st.button("📥 Download My Clinical Report (CSV)"):
    report_df = pd.read_sql_query(
        "SELECT * FROM logs WHERE username=?",
        conn,
        params=(st.session_state.user,)
    )
    st.download_button(
        "Download CSV",
        report_df.to_csv(index=False),
        file_name=f"{st.session_state.user}_clinical_report.csv"
    )

# =====================================================
# ADMIN PANEL
# =====================================================

if st.session_state.user == "admin":

    st.header("🔎 Admin Dashboard")

    users_df = pd.read_sql_query("SELECT username FROM users", conn)
    st.subheader("Registered Users")
    st.dataframe(users_df)

    logs_df = pd.read_sql_query("SELECT * FROM logs", conn)
    st.subheader("All Logs")
    st.dataframe(logs_df)

    if st.button("⚠ Delete All Logs (Admin Only)"):
        c.execute("DELETE FROM logs")
        conn.commit()
        st.warning("All logs deleted.")

# =====================================================
# LOGOUT
# =====================================================

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()

# =====================================================
# DISCLAIMER
# =====================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
This application is for educational purposes only.
It does not provide medical advice, diagnosis, or treatment.
Always consult your physician before making clinical decisions.
""")
