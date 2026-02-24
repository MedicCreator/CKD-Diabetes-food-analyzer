# ==========================================================
# RENAL + DIABETES CLINICAL PLATFORM – ADVANCED VERSION
# ==========================================================

import streamlit as st
import requests
import sqlite3
import pandas as pd
import uuid
from datetime import date, timedelta

st.set_page_config(page_title="Renal + Diabetes Clinical Platform", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

MEALS = ["Breakfast", "Lunch", "Dinner", "Snacks"]
MEAL_SPLIT = {"Breakfast":0.25,"Lunch":0.30,"Dinner":0.30,"Snacks":0.15}

# ==========================================================
# DATABASE
# ==========================================================

conn = sqlite3.connect("renal_multi_patient.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    patient TEXT,
    log_date TEXT,
    sodium REAL,
    potassium REAL,
    phosphorus REAL,
    carbs REAL,
    protein REAL,
    water REAL,
    calories REAL,
    ckd_risk REAL,
    dm_risk REAL,
    combined_risk REAL,
    PRIMARY KEY (patient, log_date)
)
""")
conn.commit()

# ==========================================================
# USDA FUNCTIONS
# ==========================================================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 10},
            timeout=20
        )
        if r.status_code == 200:
            return r.json().get("foods", [])
        return []
    except:
        return []

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    try:
        r = requests.get(
            f"{BASE_URL}/food/{fdc_id}",
            params={"api_key": USDA_API_KEY},
            timeout=20
        )
        if r.status_code == 200:
            return r.json()
        return {}
    except:
        return {}

def extract_nutrients(food):
    nutrients = {"sodium":0,"potassium":0,"phosphorus":0,
                 "carbs":0,"protein":0,"calories":0,"water":0}

    for n in food.get("foodNutrients", []):
        if "nutrient" in n:
            number = n["nutrient"].get("number")
            val = float(n.get("amount") or 0)

            if number == "307": nutrients["sodium"]=val
            elif number == "306": nutrients["potassium"]=val
            elif number == "305": nutrients["phosphorus"]=val
            elif number == "205": nutrients["carbs"]=val
            elif number == "203": nutrients["protein"]=val
            elif number == "208": nutrients["calories"]=val
            elif number == "255": nutrients["water"]=val

    return nutrients

def extract_portions(food):
    portions=[{"desc":"100 g","grams":100}]
    if food.get("servingSize"):
        portions.append({
            "desc":f"1 serving ({food['servingSize']} g)",
            "grams":float(food["servingSize"])
        })
    for p in food.get("foodPortions",[]):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "desc":p["portionDescription"],
                "grams":float(p["gramWeight"])
            })
    return portions

def scale(base, grams):
    factor=grams/100
    return {k:round(v*factor,2) for k,v in base.items()}

# ==========================================================
# SIDEBAR – PATIENT PROFILE
# ==========================================================

st.sidebar.header("Patient Profile")

patient = st.sidebar.text_input("Patient Name","Patient A")
stage = st.sidebar.selectbox("CKD Stage",[1,2,3,4,5])
dialysis = st.sidebar.checkbox("On Dialysis")
weight = st.sidebar.number_input("Body Weight (kg)",70.0)
hba1c = st.sidebar.number_input("HbA1c (%)",6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose",100)

protein_target = weight * (1.2 if dialysis else 0.8)

limits = {
    1:{"sodium":2300,"potassium":3500,"phosphorus":1000},
    2:{"sodium":2300,"potassium":3500,"phosphorus":1000},
    3:{"sodium":2000,"potassium":2500,"phosphorus":900},
    4:{"sodium":2000,"potassium":2000,"phosphorus":800},
    5:{"sodium":2000,"potassium":1500,"phosphorus":700},
}[stage]

limits["carbs"] = 180 - (10 if hba1c>7 else 0)

# ==========================================================
# SESSION STATE
# ==========================================================

if "meals" not in st.session_state:
    st.session_state.meals = {m: [] for m in MEALS}

# ==========================================================
# MEAL BUILDER
# ==========================================================

st.title("Renal + Diabetes Clinical Platform")

meal_choice = st.selectbox("Meal Section",MEALS)
query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x:x["description"]
    )

    food = get_food_details(selected["fdcId"])
    base = extract_nutrients(food)
    portions = extract_portions(food)

    portion = st.selectbox("Select Portion",portions,
                           format_func=lambda x:x["desc"])

    qty = st.number_input("How many portions?",1.0,step=0.5)

    if st.button("Add Food"):
        grams = portion["grams"] * qty
        st.session_state.meals[meal_choice].append({
            "id":str(uuid.uuid4()),
            "name":selected["description"],
            "grams":grams,
            "base":base
        })
        st.rerun()

# ==========================================================
# CALCULATE TOTALS
# ==========================================================

daily = {"sodium":0,"potassium":0,"phosphorus":0,
         "carbs":0,"protein":0,"calories":0,"water":0}

meal_totals = {m:{"sodium":0,"potassium":0,"phosphorus":0,
                  "carbs":0,"protein":0,"calories":0,"water":0}
               for m in MEALS}

for meal in MEALS:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:

        col1,col2,col3=st.columns([4,2,1])
        with col1: st.write(item["name"])
        with col2:
            item["grams"]=st.number_input("grams",item["grams"],key=item["id"])
        with col3:
            if st.button("Remove",key="r"+item["id"]):
                st.session_state.meals[meal]=[
                    i for i in st.session_state.meals[meal]
                    if i["id"]!=item["id"]
                ]
                st.rerun()

        scaled = scale(item["base"],item["grams"])

        for k in daily:
            daily[k]+=scaled[k]
            meal_totals[meal][k]+=scaled[k]

# ==========================================================
# RISK ENGINE
# ==========================================================

def risk_label(p):
    if p<=40: return "Low","🟢"
    elif p<=70: return "Moderate","🟡"
    return "High","🔴"

ckd_components={
    "Sodium":(daily["sodium"]/limits["sodium"])*100,
    "Potassium":(daily["potassium"]/limits["potassium"])*100,
    "Phosphorus":(daily["phosphorus"]/limits["phosphorus"])*100
}

ckd_score=max(ckd_components.values())
dm_score=(daily["carbs"]/limits["carbs"])*100
dm_score*=1.1 if hba1c>7 else 1
combined=round((ckd_score*0.6)+(dm_score*0.4),1)

st.header("Risk Dashboard")

l1,i1=risk_label(ckd_score)
st.subheader(f"CKD Risk: {i1} {l1} ({round(ckd_score,1)}%)")
for k,v in sorted(ckd_components.items(),key=lambda x:x[1],reverse=True):
    st.write(f"{k}: {round(v,1)}% of limit")

l2,i2=risk_label(dm_score)
st.subheader(f"Diabetes Risk: {i2} {l2} ({round(dm_score,1)}%)")
st.write(f"Carbohydrates: {round(dm_score,1)}% of limit")

l3,i3=risk_label(combined)
st.subheader(f"Combined Risk: {i3} {l3} ({combined}%)")

# ==========================================================
# PER-MEAL BREAKDOWN
# ==========================================================

st.header("Per-Meal Risk Breakdown")

for meal in MEALS:
    meal_ckd = max(
        (meal_totals[meal]["sodium"]/limits["sodium"])*100,
        (meal_totals[meal]["potassium"]/limits["potassium"])*100,
        (meal_totals[meal]["phosphorus"]/limits["phosphorus"])*100
    )
    label,icon=risk_label(meal_ckd)
    st.write(f"{meal}: {icon} {label} ({round(meal_ckd,1)}%)")

# ==========================================================
# SAVE LOG
# ==========================================================

today=str(date.today())

c.execute("""
INSERT OR REPLACE INTO logs
VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
""",(
    patient,today,
    daily["sodium"],daily["potassium"],daily["phosphorus"],
    daily["carbs"],daily["protein"],daily["water"],
    daily["calories"],ckd_score,dm_score,combined
))
conn.commit()

# ==========================================================
# WEEKLY & MONTHLY DASHBOARD
# ==========================================================

st.header("Weekly Trend")
week=str(date.today()-timedelta(days=7))
df_week=pd.read_sql_query(
    "SELECT * FROM logs WHERE patient=? AND log_date>=?",
    conn,params=(patient,week)
)
if not df_week.empty:
    st.line_chart(df_week.set_index("log_date")[["ckd_risk","dm_risk","combined_risk"]])

st.header("Monthly Trend")
month=str(date.today()-timedelta(days=30))
df_month=pd.read_sql_query(
    "SELECT * FROM logs WHERE patient=? AND log_date>=?",
    conn,params=(patient,month)
)
if not df_month.empty:
    st.line_chart(df_month.set_index("log_date")[["ckd_risk","dm_risk","combined_risk"]])

# ==========================================================
# PDF REPORT (HTML DOWNLOAD)
# ==========================================================

if st.button("Download Patient Summary Report"):
    report=f"""
    Renal + Diabetes Clinical Report
    Patient: {patient}
    Date: {today}

    Sodium: {daily['sodium']}
    Potassium: {daily['potassium']}
    Phosphorus: {daily['phosphorus']}
    Carbs: {daily['carbs']}
    Protein: {daily['protein']}
    Calories: {daily['calories']}

    CKD Risk: {round(ckd_score,1)}%
    Diabetes Risk: {round(dm_score,1)}%
    Combined Risk: {combined}%
    """

    st.download_button(
        "Download Report",
        report,
        file_name="renal_clinical_report.txt"
    )

# ==========================================================
# DISCLAIMER
# ==========================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
Educational tool only. Not medical advice.
Consult your physician before dietary changes.
Data from USDA FoodData Central.
""")
