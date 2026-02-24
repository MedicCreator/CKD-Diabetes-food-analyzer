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
MEAL_DISTRIBUTION = {
    "Breakfast":0.25,
    "Lunch":0.30,
    "Dinner":0.30,
    "Snacks":0.15
}

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
    nutrients={"sodium":0,"potassium":0,"phosphorus":0,
               "carbs":0,"protein":0,"calories":0,"water":0}
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
# SIDEBAR (CLINICAL INPUTS)
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
# CKD LIMITS BY STAGE
# ======================================================

def get_ckd_limits(stage,dialysis):
    if dialysis:
        return {"sodium":2000,"potassium":3000,"phosphorus":1000}
    if stage<=2:
        return {"sodium":2300,"potassium":3500,"phosphorus":1000}
    if stage==3:
        return {"sodium":2000,"potassium":2500,"phosphorus":900}
    if stage==4:
        return {"sodium":2000,"potassium":2000,"phosphorus":800}
    return {"sodium":2000,"potassium":1500,"phosphorus":700}

limits=get_ckd_limits(stage,dialysis)

# Lab tightening
if serum_k>=6: limits["potassium"]=1500
if serum_phos>=6: limits["phosphorus"]=700

# Diabetes carb limit
if hba1c<6.5: carb_limit=200
elif hba1c<=7.5: carb_limit=180
else: carb_limit=150

limits["carbs"]=carb_limit

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
# CALCULATE TOTALS
# ======================================================

daily={"sodium":0,"potassium":0,"phosphorus":0,
       "carbs":0,"protein":0,"calories":0,"water":0}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        st.write(item["name"])
        scaled=scale(item["base"],item["grams"])
        for k in scaled:
            daily[k]+=scaled[k]

# ======================================================
# SIDE-BY-SIDE DISPLAY
# ======================================================

st.header("Per-Meal Nutrient Comparison")

meal_percent=MEAL_DISTRIBUTION[meal_choice]

for n in ["sodium","potassium","phosphorus","carbs"]:
    daily_limit=limits[n]
    meal_allowance=daily_limit*meal_percent
    value=daily[n]
    percent=(value/meal_allowance)*100 if meal_allowance else 0

    color="🟢" if percent<=40 else "🟡" if percent<=70 else "🔴"

    st.write(
        f"{n.capitalize()}: {round(value,1)} mg | "
        f"Meal Allowance: {round(meal_allowance,1)} mg | "
        f"{round(percent,1)}% {color}"
    )

# ======================================================
# RISK SUMMARY
# ======================================================

ckd=max(daily["sodium"]/limits["sodium"]*100,
        daily["potassium"]/limits["potassium"]*100,
        daily["phosphorus"]/limits["phosphorus"]*100)

dm=daily["carbs"]/limits["carbs"]*100
combined=round((ckd*0.6)+(dm*0.4),1)

def label(p):
    if p<=40:return "Low","🟢"
    elif p<=70:return "Moderate","🟡"
    return "High","🔴"

l1,c1=label(ckd)
l2,c2=label(dm)
l3,c3=label(combined)

st.subheader("Risk Summary")
st.markdown(f"CKD Risk: {c1} {l1} ({round(ckd,1)}%)")
st.markdown(f"Diabetes Risk: {c2} {l2} ({round(dm,1)}%)")
st.markdown(f"Combined Risk: {c3} {l3} ({combined}%)")

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
