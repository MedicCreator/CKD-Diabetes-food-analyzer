# =====================================================
# RENAL + DIABETES CLINICAL PLATFORM – OPEN VERSION
# =====================================================

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta

st.set_page_config(page_title="Renal + Diabetes Clinical Platform", layout="wide")

# =====================================================
# DATABASE (Single Shared Clinical Log)
# =====================================================

conn = sqlite3.connect("renal_open_platform.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    log_date TEXT PRIMARY KEY,
    sodium REAL,
    potassium REAL,
    phosphorus REAL,
    carbs REAL,
    protein REAL,
    water REAL,
    ckd_risk REAL,
    diabetes_risk REAL,
    combined_risk REAL
)
""")
conn.commit()

# =====================================================
# PATIENT PROFILE
# =====================================================

st.sidebar.title("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
weight = st.sidebar.number_input("Body Weight (kg)", 70.0)
hba1c = st.sidebar.number_input("HbA1c (%)", 6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", 100)
fluid_limit = st.sidebar.number_input("Daily Fluid Limit (ml)", 2000.0)

protein_target = weight * 0.8

# =====================================================
# DAILY ENTRY
# =====================================================

st.title("Renal + Diabetes Daily Clinical Entry")

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
VALUES (?,?,?,?,?,?,?,?,?,?)
""", (
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
# DISPLAY RISK ANALYSIS
# =====================================================

st.header("Risk Analysis")

label_ckd, icon_ckd = risk_label(ckd_score)
label_dm, icon_dm = risk_label(dm_score)
label_comb, icon_comb = risk_label(combined_score)

st.subheader(f"CKD Risk: {icon_ckd} {label_ckd} ({round(ckd_score,1)}%)")
for k,v in sorted(ckd_factors.items(), key=lambda x:x[1], reverse=True):
    st.write(f"• {k}: {round(v,1)}% of daily limit")

st.subheader(f"Diabetes Risk: {icon_dm} {label_dm} ({round(dm_score,1)}%)")
st.write(f"• Carbohydrates: {round(dm_score,1)}% of daily limit")

st.subheader(f"Combined Risk: {icon_comb} {label_comb} ({combined_score}%)")

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
    "SELECT * FROM logs WHERE log_date>=?",
    conn,
    params=(week_ago,)
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
    "SELECT * FROM logs WHERE log_date>=?",
    conn,
    params=(month_ago,)
)

if not df_month.empty:
    st.line_chart(df_month.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])
else:
    st.info("No monthly data yet.")

# =====================================================
# CSV EXPORT
# =====================================================

if st.button("📥 Download Full Clinical Log (CSV)"):
    report_df = pd.read_sql_query("SELECT * FROM logs", conn)
    st.download_button(
        "Download CSV",
        report_df.to_csv(index=False),
        file_name="renal_diabetes_clinical_log.csv"
    )

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
