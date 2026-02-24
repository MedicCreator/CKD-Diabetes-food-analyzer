# ==============================================
# RENAL + DIABETES CLINICAL PLATFORM (PRO)
# ==============================================

import streamlit as st
import requests
import sqlite3
import pandas as pd
import uuid
import bcrypt
from datetime import date, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# ==============================================
# CONFIG
# ==============================================

st.set_page_config(page_title="Renal + Diabetes Clinical Platform", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

MEALS = ["Breakfast","Lunch","Dinner","Snacks"]

# ==============================================
# DATABASE
# ==============================================

conn = sqlite3.connect("renal_system.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password BLOB
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

# ==============================================
# AUTH SYSTEM
# ==============================================

if "user" not in st.session_state:
    st.session_state.user = None

def register(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    try:
        c.execute("INSERT INTO users VALUES (?,?)", (username, hashed))
        conn.commit()
        return True
    except:
        return False

def login(username, password):
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if result and bcrypt.checkpw(password.encode(), result[0]):
        return True
    return False

if not st.session_state.user:
    st.title("🔐 Login / Register")

    mode = st.radio("Select Mode", ["Login","Register"])
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
                st.success("Logged in successfully.")
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# ==============================================
# PATIENT PROFILE
# ==============================================

st.sidebar.title(f"👤 {st.session_state.user}")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
weight = st.sidebar.number_input("Body Weight (kg)", 70.0)
hba1c = st.sidebar.number_input("HbA1c (%)", 6.5)
fluid_limit = st.sidebar.number_input("Daily Fluid Limit (ml)", 2000.0)

protein_target = weight * 0.8

# ==============================================
# DAILY DATA ENTRY (Simplified)
# ==============================================

st.title("Renal + Diabetes Clinical Dashboard")

sodium = st.number_input("Total Sodium (mg)", 0.0)
potassium = st.number_input("Total Potassium (mg)", 0.0)
phosphorus = st.number_input("Total Phosphorus (mg)", 0.0)
carbs = st.number_input("Total Carbs (g)", 0.0)
protein = st.number_input("Total Protein (g)", 0.0)
water = st.number_input("Total Water Intake (ml)", 0.0)

# ==============================================
# LIMITS
# ==============================================

limits = {
    1: {"sodium":2300,"potassium":3500,"phosphorus":1000},
    2: {"sodium":2300,"potassium":3500,"phosphorus":1000},
    3: {"sodium":2000,"potassium":2500,"phosphorus":900},
    4: {"sodium":2000,"potassium":2000,"phosphorus":800},
    5: {"sodium":2000,"potassium":1500,"phosphorus":700},
}[stage]

limits["carbs"] = 180

# ==============================================
# RISK CALCULATION
# ==============================================

def risk_label(p):
    if p <= 40: return "Low","🟢"
    elif p <= 70: return "Moderate","🟡"
    return "High","🔴"

ckd_score = max(
    sodium/limits["sodium"]*100 if limits["sodium"] else 0,
    potassium/limits["potassium"]*100 if limits["potassium"] else 0,
    phosphorus/limits["phosphorus"]*100 if limits["phosphorus"] else 0
)

dm_score = carbs/limits["carbs"]*100 if limits["carbs"] else 0
combined = round((ckd_score*0.6)+(dm_score*0.4),1)

# ==============================================
# SAVE LOG
# ==============================================

today = str(date.today())

c.execute("""
INSERT OR REPLACE INTO logs
VALUES (?,?,?,?,?,?,?,?,?,?,?)
""", (
    st.session_state.user,
    today,
    sodium,potassium,phosphorus,
    carbs,protein,water,
    ckd_score,dm_score,combined
))
conn.commit()

# ==============================================
# DISPLAY RISKS
# ==============================================

st.header("Risk Summary")

for label,value in [
    ("CKD Risk",ckd_score),
    ("Diabetes Risk",dm_score),
    ("Combined Risk",combined)
]:
    l,i = risk_label(value)
    st.write(f"{label}: {i} {l} ({round(value,1)}%)")

# ==============================================
# WEEKLY DASHBOARD
# ==============================================

st.header("📊 Weekly Dashboard")

week = str(date.today()-timedelta(days=7))

df = pd.read_sql_query(
    "SELECT * FROM logs WHERE username=? AND log_date>=?",
    conn,
    params=(st.session_state.user, week)
)

if not df.empty:
    st.line_chart(df.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])

# ==============================================
# MONTHLY DASHBOARD
# ==============================================

st.header("📅 Monthly Dashboard")

month = str(date.today()-timedelta(days=30))

df_month = pd.read_sql_query(
    "SELECT * FROM logs WHERE username=? AND log_date>=?",
    conn,
    params=(st.session_state.user, month)
)

if not df_month.empty:
    st.line_chart(df_month.set_index("log_date")[["ckd_risk","diabetes_risk","combined_risk"]])

# ==============================================
# PDF EXPORT
# ==============================================

def generate_pdf():
    filename = f"{st.session_state.user}_report.pdf"
    doc = SimpleDocTemplate(filename)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Renal + Diabetes Clinical Report", styles["Title"]))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(f"Date: {today}", styles["Normal"]))
    elements.append(Paragraph(f"CKD Risk: {round(ckd_score,1)}%", styles["Normal"]))
    elements.append(Paragraph(f"Diabetes Risk: {round(dm_score,1)}%", styles["Normal"]))
    elements.append(Paragraph(f"Combined Risk: {round(combined,1)}%", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("Nutrient Totals:", styles["Heading2"]))
    elements.append(Paragraph(f"Sodium: {sodium}", styles["Normal"]))
    elements.append(Paragraph(f"Potassium: {potassium}", styles["Normal"]))
    elements.append(Paragraph(f"Phosphorus: {phosphorus}", styles["Normal"]))
    elements.append(Paragraph(f"Carbs: {carbs}", styles["Normal"]))
    elements.append(Paragraph(f"Protein: {protein}", styles["Normal"]))

    doc.build(elements)
    return filename

if st.button("📄 Export PDF Report"):
    pdf_file = generate_pdf()
    with open(pdf_file, "rb") as f:
        st.download_button("Download Report", f, file_name=pdf_file)

# ==============================================
# LOGOUT
# ==============================================

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()

# ==============================================
# DISCLAIMER
# ==============================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
Educational tool only. Not medical advice.
Consult your physician before making clinical decisions.

Nutritional data reference: USDA FoodData Central.
Not affiliated with USDA.
""")
