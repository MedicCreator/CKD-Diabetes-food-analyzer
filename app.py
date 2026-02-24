import streamlit as st
import requests
import uuid
import sqlite3
from datetime import date
import pandas as pd

# ======================================================
# CONFIG
# ======================================================

st.set_page_config(page_title="Renal + Diabetes Clinical Planner", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner", "Snacks"]

# ======================================================
# DATABASE (Weekly Dashboard)
# ======================================================

conn = sqlite3.connect("renal_app.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT,
    ckd REAL,
    diabetes REAL,
    combined REAL
)
""")
conn.commit()

# ======================================================
# USDA
# ======================================================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
            timeout=20
        )
        return r.json().get("foods", []) if r.status_code == 200 else []
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
        return r.json() if r.status_code == 200 else {}
    except:
        return {}

def extract_nutrients(food):
    nutrients = {
        "sodium":0,"potassium":0,"phosphorus":0,
        "carbs":0,"protein":0,"calories":0,"sugar":0
    }

    for n in food.get("foodNutrients", []):
        if "nutrient" in n:
            num = n["nutrient"].get("number")
            val = n.get("amount") or 0
            if num == "307": nutrients["sodium"]=val
            elif num == "306": nutrients["potassium"]=val
            elif num == "305": nutrients["phosphorus"]=val
            elif num == "205": nutrients["carbs"]=val
            elif num == "203": nutrients["protein"]=val
            elif num == "208": nutrients["calories"]=val
            elif num == "269": nutrients["sugar"]=val
    return nutrients

def scale(nutrients, grams):
    factor = grams/100
    return {k: round(v*factor,2) for k,v in nutrients.items()}

# ======================================================
# SIDEBAR (Clinical)
# ======================================================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage",[1,2,3,4,5])
dialysis = st.sidebar.checkbox("On Dialysis")
dialysis_day = st.sidebar.checkbox("Dialysis Day Today")
weight = st.sidebar.number_input("Body Weight (kg)",70.0)

serum_k = st.sidebar.number_input("Serum Potassium",4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus",4.0)
hba1c = st.sidebar.number_input("HbA1c (%)",6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose",100)

fluid_limit = 1500 if dialysis else 2000

protein_target = weight*(1.2 if dialysis else 0.8)

# ======================================================
# SESSION STATE
# ======================================================

if "meals" not in st.session_state:
    st.session_state.meals = {m:[] for m in MEAL_TYPES}

# ======================================================
# MEAL BUILDER
# ======================================================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice = st.selectbox("Meal Section",MEAL_TYPES)
query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected = st.selectbox("Select Food",st.session_state.results,
                            format_func=lambda x: x["description"])
    food = get_food_details(selected["fdcId"])
    base = extract_nutrients(food)

    grams = st.number_input("Quantity (grams)",100.0)

    if st.button("Add Food"):
        st.session_state.meals[meal_choice].append({
            "id":str(uuid.uuid4()),
            "name":selected["description"],
            "grams":grams,
            "base":base,
            "fluid":grams*0.7  # approximate 70% water content
        })

# ======================================================
# DISPLAY MEALS
# ======================================================

daily_totals = {"sodium":0,"potassium":0,"phosphorus":0,
                "carbs":0,"protein":0,"calories":0,"sugar":0,
                "fluid":0}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1,col2,col3 = st.columns([4,2,1])
        with col1:
            st.write(item["name"])
        with col2:
            new_g = st.number_input("g",value=item["grams"],key=item["id"])
            item["grams"]=new_g
        with col3:
            if st.button("Remove",key="r"+item["id"]):
                st.session_state.meals[meal]=[
                    i for i in st.session_state.meals[meal] if i["id"]!=item["id"]
                ]
                st.rerun()

        scaled = scale(item["base"],item["grams"])
        for k in scaled:
            daily_totals[k]+=scaled[k]
        daily_totals["fluid"]+=item["fluid"]

# ======================================================
# LIMITS
# ======================================================

limits={
    "sodium":2000 if stage>=4 else 2300,
    "potassium":1500 if serum_k>=6 else 1800,
    "phosphorus":700 if serum_phos>=6 else 800,
    "carbs":180
}

# ======================================================
# DAILY TOTAL DISPLAY
# ======================================================

st.header("Daily Totals")

for k in ["sodium","potassium","phosphorus","carbs","protein","calories"]:
    st.write(f"{k.capitalize()}: {round(daily_totals[k],1)}")

st.write(f"Fluid: {round(daily_totals['fluid'],1)} ml (Limit {fluid_limit})")

# ======================================================
# PER-MEAL RISK
# ======================================================

def risk(percent):
    if percent<=40: return "Low"
    elif percent<=70: return "Moderate"
    return "High"

ckd_percent=max(
    daily_totals["sodium"]/limits["sodium"]*100,
    daily_totals["potassium"]/limits["potassium"]*100,
    daily_totals["phosphorus"]/limits["phosphorus"]*100
)

dm_percent=daily_totals["carbs"]/limits["carbs"]*100

combined=round((ckd_percent*0.6)+(dm_percent*0.4),1)

st.subheader("CKD Risk")
st.write(risk(ckd_percent),round(ckd_percent,1),"%")

st.subheader("Diabetes Risk")
st.write(risk(dm_percent),round(dm_percent,1),"%")

st.subheader("Combined Risk")
st.write(risk(combined),combined,"%")

# ======================================================
# PROTEIN ADEQUACY
# ======================================================

st.subheader("Protein Target")
st.write("Target:",round(protein_target,1),"g")

if daily_totals["protein"]<protein_target*0.8:
    st.warning("Protein too low")
elif daily_totals["protein"]>protein_target*1.3:
    st.warning("Protein too high")
else:
    st.success("Protein adequate")

# ======================================================
# WEEKLY DASHBOARD
# ======================================================

if st.button("Save Today"):
    c.execute("INSERT INTO daily_log VALUES (?,?,?,?)",
              (str(date.today()),ckd_percent,dm_percent,combined))
    conn.commit()
    st.success("Saved")

st.subheader("Weekly Trend")

df=pd.read_sql("SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7",conn)
st.dataframe(df)

# ======================================================
# DISCLAIMER
# ======================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer

Educational tool only. Not medical advice.
Consult your nephrologist or endocrinologist before dietary changes.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by USDA.
""")
