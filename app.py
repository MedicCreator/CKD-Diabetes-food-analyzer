import streamlit as st
import requests
from datetime import date
import pandas as pd

# =====================================
# CONFIG
# =====================================

st.set_page_config(page_title="CKD + Diabetes Smart Analyzer", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

IMPORTANT_NUTRIENTS = {
    1093: "sodium",
    1092: "potassium",
    1091: "phosphorus",
    1005: "carbs",
    1079: "fiber",
    2000: "sugar"
}

# =====================================
# USDA API (CACHED)
# =====================================

@st.cache_data(ttl=86400)
def search_food(query):
    r = requests.get(
        f"{BASE_URL}/foods/search",
        params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
        timeout=20
    )
    return r.json().get("foods", [])

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    r = requests.get(
        f"{BASE_URL}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY},
        timeout=20
    )
    return r.json()

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}
    for n in food_data.get("foodNutrients", []):
        nutrient_id = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        value = n.get("amount") or n.get("value")
        if nutrient_id in IMPORTANT_NUTRIENTS:
            nutrients[IMPORTANT_NUTRIENTS[nutrient_id]] = value if value else 0
    return nutrients

def extract_portions(food_data):
    portions = []

    portions.append({
        "description": "100 g",
        "gramWeight": 100
    })

    if food_data.get("servingSize"):
        portions.append({
            "description": f"1 serving ({food_data['servingSize']} {food_data.get('servingSizeUnit','g')})",
            "gramWeight": food_data["servingSize"]
        })

    for p in food_data.get("foodPortions", []):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "description": p["portionDescription"],
                "gramWeight": p["gramWeight"]
            })

    return portions

def scale_nutrients(nutrients, grams):
    factor = grams / 100
    return {k: round((v or 0) * factor, 2) for k, v in nutrients.items()}

# =====================================
# CKD + DIABETES LOGIC
# =====================================

def get_ckd_limits(stage):
    limits = {"sodium": 2300, "potassium": None, "phosphorus": 1000}
    if stage >= 3:
        limits["potassium"] = 2500
    if stage >= 4:
        limits["sodium"] = 2000
    if stage == 5:
        limits["potassium"] = 2000
    return limits

def per_meal_limits(limits, meals=3):
    return {k: v/meals for k,v in limits.items() if v}

def nutrient_percent(value, limit):
    return min((value/limit)*100,150)

def ckd_score(values, limits):
    weights={"potassium":0.4,"phosphorus":0.3,"sodium":0.3}
    score=0
    triggers=[]
    for n in weights:
        if n in limits:
            percent=nutrient_percent(values[n],limits[n])
            score+=percent*weights[n]
            if percent>100:
                triggers.append(n)
    return round(min(score,100),1), triggers

def diabetes_score(carbs,sugar,fiber):
    carb_score=(carbs/60)*100
    sugar_score=(sugar/25)*100
    fiber_bonus=(fiber/10)*20
    score=carb_score*0.5+sugar_score*0.3-fiber_bonus

    triggers=[]
    if carb_score>100:
        triggers.append("carbohydrates")
    if sugar_score>100:
        triggers.append("sugar")

    return round(max(min(score,100),0),1), triggers

def combined_score(ckd,dm):
    return round((ckd*0.6)+(dm*0.4),1)

def risk_label(score):
    if score<=40:
        return "🟢 Low Risk","Within recommended limits for most CKD and diabetes guidelines."
    elif score<=70:
        return "🟡 Moderate Risk","Approaching recommended limits. Portion control advised."
    return "🔴 High Risk","Exceeds recommended limits. Consider smaller portions or alternatives."

# =====================================
# UI
# =====================================

st.title("CKD + Diabetes Smart Food Analyzer")

stage=st.sidebar.selectbox("CKD Stage",[1,2,3,4,5])

if "meal" not in st.session_state:
    st.session_state.meal=[]

if "history" not in st.session_state:
    st.session_state.history=[]

st.header("Meal Builder")

food_query=st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results=search_food(food_query)

if "results" in st.session_state and st.session_state.results:

    selected=st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x:x["description"]
    )

    food_data=get_food_details(selected["fdcId"])
    nutrients=extract_nutrients(food_data)
    portions=extract_portions(food_data)

    portion_choice=st.selectbox(
        "Select Portion Type",
        portions,
        format_func=lambda x:x["description"]
    )

    quantity=st.number_input("How many portions?",min_value=0.1,value=1.0,step=0.1)

    if st.button("Add Food"):
        grams=portion_choice["gramWeight"]*quantity
        scaled=scale_nutrients(nutrients,grams)
        scaled["name"]=selected["description"]
        scaled["portion"]=portion_choice["description"]
        scaled["grams"]=round(grams,1)
        st.session_state.meal.append(scaled)
        st.success("Food Added")

# =====================================
# MEAL DISPLAY
# =====================================

if st.session_state.meal:

    st.subheader("Current Meal")
    for i,item in enumerate(st.session_state.meal):
        col1,col2=st.columns([4,1])
        with col1:
            st.write(f"• {item['name']} ({item['portion']} | {item['grams']} g)")
        with col2:
            if st.button("Remove",key=i):
                st.session_state.meal.pop(i)
                st.rerun()

    total={k:0 for k in IMPORTANT_NUTRIENTS.values()}
    for item in st.session_state.meal:
        for k in total:
            total[k]+=item.get(k,0)

    st.subheader("Meal Totals")
    st.write(f"Carbohydrates: {round(total['carbs'],1)} g")

    limits=get_ckd_limits(stage)
    meal_limits=per_meal_limits(limits)

    for nutrient,value in total.items():
        if nutrient in meal_limits:
            st.write(f"{nutrient.capitalize()}: {round(value,1)} mg")
            st.progress(min(value/meal_limits[nutrient],1.0))

    ckd,ckd_triggers=ckd_score(total,meal_limits)
    dm,dm_triggers=diabetes_score(total["carbs"],total["sugar"],total["fiber"])
    combined=combined_score(ckd,dm)

    st.subheader("Risk Scores")

    label,desc=risk_label(ckd)
    st.metric("CKD Risk",ckd)
    st.write(label)
    st.info(desc)
    if ckd_triggers:
        st.warning(f"Triggered by high: {', '.join(ckd_triggers)}")

    label2,desc2=risk_label(dm)
    st.metric("Diabetes Risk",dm)
    st.write(label2)
    st.info(desc2)
    if dm_triggers:
        st.warning(f"Triggered by high: {', '.join(dm_triggers)}")

    label3,desc3=risk_label(combined)
    st.metric("Combined Risk",combined)
    st.write(label3)
    st.info(desc3)

    if st.button("Save Today's Meal"):
        st.session_state.history.append({
            "date":str(date.today()),
            "combined":combined
        })
        st.success("Saved!")

# =====================================
# DAILY TRACKING
# =====================================

if st.session_state.history:
    st.header("Daily Risk Trend")
    df=pd.DataFrame(st.session_state.history)
    st.line_chart(df.set_index("date"))

# =====================================
# DISCLAIMER
# =====================================

st.markdown("---")
st.markdown("""
⚠️ **Medical Disclaimer**

This tool is for educational purposes only.
It does not provide medical advice.
Always consult your healthcare provider.
""")

st.markdown("""
Data Source: Nutritional data provided by USDA FoodData Central  
(https://fdc.nal.usda.gov/)

Not affiliated with or endorsed by the USDA.
""")
