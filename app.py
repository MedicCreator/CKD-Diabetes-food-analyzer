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
MEAL_TYPES = ["Breakfast","Lunch","Dinner","Snacks"]

# ======================================================
# DATABASE
# ======================================================

conn = sqlite3.connect("renal_app.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS daily_log (
    log_date TEXT, ckd REAL, diabetes REAL, combined REAL)""")
conn.commit()

# ======================================================
# USDA FUNCTIONS
# ======================================================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(f"{BASE_URL}/foods/search",
                         params={"query":query,"api_key":USDA_API_KEY,"pageSize":5},
                         timeout=20)
        return r.json().get("foods",[]) if r.status_code==200 else []
    except:
        return []

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    try:
        r = requests.get(f"{BASE_URL}/food/{fdc_id}",
                         params={"api_key":USDA_API_KEY},timeout=20)
        return r.json() if r.status_code==200 else {}
    except:
        return {}

def extract_nutrients(food):
    nutrients = {"sodium":0,"potassium":0,"phosphorus":0,
                 "carbs":0,"protein":0,"calories":0,
                 "sugar":0,"water":0}
    for n in food.get("foodNutrients",[]):
        if "nutrient" in n:
            num=n["nutrient"].get("number")
            val=n.get("amount") or 0
            if num=="307": nutrients["sodium"]=val
            elif num=="306": nutrients["potassium"]=val
            elif num=="305": nutrients["phosphorus"]=val
            elif num=="205": nutrients["carbs"]=val
            elif num=="203": nutrients["protein"]=val
            elif num=="208": nutrients["calories"]=val
            elif num=="269": nutrients["sugar"]=val
            elif num=="255": nutrients["water"]=val
    return nutrients

def extract_portions(food):
    portions=[{"desc":"100 g","grams":100}]
    if food.get("servingSize"):
        portions.append({
            "desc":f"1 serving ({food['servingSize']} g)",
            "grams":food["servingSize"]
        })
    for p in food.get("foodPortions",[]):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "desc":p["portionDescription"],
                "grams":p["gramWeight"]
            })
    return portions

def scale(nutrients,grams):
    factor=grams/100
    return {k:round(v*factor,2) for k,v in nutrients.items()}

# ======================================================
# SIDEBAR
# ======================================================

st.sidebar.header("Patient Profile")

stage=st.sidebar.selectbox("CKD Stage",[1,2,3,4,5])
dialysis=st.sidebar.checkbox("On Dialysis")
weight=st.sidebar.number_input("Body Weight (kg)",70.0)

serum_k=st.sidebar.number_input("Serum Potassium",4.5)
serum_phos=st.sidebar.number_input("Serum Phosphorus",4.0)
hba1c=st.sidebar.number_input("HbA1c (%)",6.5)
fasting_glucose=st.sidebar.number_input("Fasting Glucose",100)

fluid_limit=st.sidebar.number_input("Daily Fluid Limit (ml)",
                                     1500 if dialysis else 2000)

protein_target=weight*(1.2 if dialysis else 0.8)

# ======================================================
# SESSION STATE
# ======================================================

if "meals" not in st.session_state:
    st.session_state.meals={m:[] for m in MEAL_TYPES}

# ======================================================
# MEAL BUILDER
# ======================================================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice=st.selectbox("Meal Section",MEAL_TYPES)
query=st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results=search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected=st.selectbox("Select Food",
                          st.session_state.results,
                          format_func=lambda x:x["description"])
    food=get_food_details(selected["fdcId"])
    base=extract_nutrients(food)
    portions=extract_portions(food)

    portion_choice=st.selectbox("Select Portion",
                                portions,
                                format_func=lambda x:x["desc"])
    qty=st.number_input("How many portions?",1.0,step=0.5)

    if st.button("Add Food"):
        st.session_state.meals[meal_choice].append({
            "id":str(uuid.uuid4()),
            "name":selected["description"],
            "grams":portion_choice["grams"]*qty,
            "base":base
        })

# ======================================================
# DISPLAY & CALCULATE
# ======================================================

daily={"sodium":0,"potassium":0,"phosphorus":0,
       "carbs":0,"protein":0,"calories":0,"sugar":0,"water":0}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1,col2,col3=st.columns([4,2,1])
        with col1: st.write(item["name"])
        with col2:
            new_g=st.number_input("grams",
                                  value=item["grams"],
                                  key=item["id"])
            item["grams"]=new_g
        with col3:
            if st.button("Remove",key="r"+item["id"]):
                st.session_state.meals[meal]=[
                    i for i in st.session_state.meals[meal]
                    if i["id"]!=item["id"]]
                st.rerun()

        scaled=scale(item["base"],item["grams"])
        for k in scaled:
            daily[k]+=scaled[k]

# ======================================================
# TOTALS
# ======================================================

st.header("Daily Totals")

for k in ["sodium","potassium","phosphorus",
          "carbs","protein","calories"]:
    st.write(f"{k.capitalize()}: {round(daily[k],1)}")

manual_fluid=st.number_input("Additional Fluid Intake (ml)",0.0)
food_water=daily["water"] if daily["water"]>0 else daily["calories"]*0
total_fluid=food_water+manual_fluid

st.write(f"Total Fluid: {round(total_fluid,1)} ml (Limit {fluid_limit})")

# ======================================================
# LIMITS
# ======================================================

limits={
    "sodium":2000 if stage>=4 else 2300,
    "potassium":1500 if serum_k>=6 else 1800,
    "phosphorus":700 if serum_phos>=6 else 800,
    "carbs":180
}

def risk_label(p):
    if p<=40: return "Low","🟢"
    elif p<=70: return "Moderate","🟡"
    return "High","🔴"

# ======================================================
# CKD RISK
# ======================================================

st.subheader("CKD Risk Analysis")

ckd_components={}
for n in ["sodium","potassium","phosphorus"]:
    percent=daily[n]/limits[n]*100
    ckd_components[n]=percent

ckd=max(ckd_components.values())
label_ckd,color_ckd=risk_label(ckd)

st.markdown(f"### {color_ckd} CKD Risk: {label_ckd} ({round(ckd,1)}%)")

for n,p in sorted(ckd_components.items(),
                  key=lambda x:x[1],reverse=True):
    st.write(f"{n.capitalize()}: {round(p,1)}% of limit")

# ======================================================
# DIABETES RISK
# ======================================================

st.subheader("Diabetes Risk Analysis")

dm=daily["carbs"]/limits["carbs"]*100
label_dm,color_dm=risk_label(dm)

st.markdown(f"### {color_dm} Diabetes Risk: {label_dm} ({round(dm,1)}%)")
st.write(f"Carbohydrates: {round(dm,1)}% of limit")

if hba1c>=7: st.warning("Elevated HbA1c increases risk")
if fasting_glucose>=130: st.warning("Elevated fasting glucose increases risk")

# ======================================================
# COMBINED
# ======================================================

combined=round((ckd*0.6)+(dm*0.4),1)
label_c,color_c=risk_label(combined)

st.subheader("Combined Risk")
st.markdown(f"### {color_c} {label_c} ({combined}%)")

# ======================================================
# PROTEIN
# ======================================================

st.subheader("Protein Target")
st.write("Target:",round(protein_target,1),"g")

if daily["protein"]<protein_target*0.8:
    st.warning("Protein too low")
elif daily["protein"]>protein_target*1.3:
    st.warning("Protein too high")
else:
    st.success("Protein adequate")

# ======================================================
# SAVE & WEEKLY
# ======================================================

if st.button("Save Today"):
    c.execute("INSERT INTO daily_log VALUES (?,?,?,?)",
              (str(date.today()),ckd,dm,combined))
    conn.commit()
    st.success("Saved")

df=pd.read_sql("SELECT * FROM daily_log ORDER BY log_date DESC LIMIT 7",conn)
st.subheader("Weekly Trend")
st.dataframe(df)

# ======================================================
# DISCLAIMER
# ======================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
Educational tool only. Not medical advice.
Consult your healthcare provider before dietary changes.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by USDA.
""")
