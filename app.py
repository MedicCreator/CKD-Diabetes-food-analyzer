import streamlit as st
import requests
import uuid

# =====================================================
# CONFIG
# =====================================================

st.set_page_config(page_title="Renal + Diabetes Clinical Planner", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

MEALS = ["Breakfast", "Lunch", "Dinner", "Snacks"]

# =====================================================
# USDA FUNCTIONS
# =====================================================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
            timeout=20,
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
            timeout=20,
        )
        if r.status_code == 200:
            return r.json()
        return {}
    except:
        return {}

def extract_nutrients(food):
    nutrients = {
        "sodium": 0,
        "potassium": 0,
        "phosphorus": 0,
        "carbs": 0,
        "protein": 0,
        "calories": 0,
        "water": 0,
    }

    for n in food.get("foodNutrients", []):
        if "nutrient" in n:
            number = n["nutrient"].get("number")
            val = n.get("amount") or 0

            if number == "307":
                nutrients["sodium"] = val
            elif number == "306":
                nutrients["potassium"] = val
            elif number == "305":
                nutrients["phosphorus"] = val
            elif number == "205":
                nutrients["carbs"] = val
            elif number == "203":
                nutrients["protein"] = val
            elif number == "208":
                nutrients["calories"] = val
            elif number == "255":   # WATER
                nutrients["water"] = val

    return nutrients

def extract_portions(food):
    portions = [{"desc": "100 g", "grams": 100}]

    if food.get("servingSize"):
        portions.append({
            "desc": f"1 serving ({food['servingSize']} g)",
            "grams": food["servingSize"]
        })

    for p in food.get("foodPortions", []):
        if p.get("gramWeight") and p.get("portionDescription"):
            portions.append({
                "desc": p["portionDescription"],
                "grams": p["gramWeight"]
            })

    return portions

def scale(nutrients, grams):
    factor = grams / 100
    return {k: round(v * factor, 2) for k, v in nutrients.items()}

# =====================================================
# SIDEBAR - PATIENT PROFILE
# =====================================================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
dialysis = st.sidebar.checkbox("On Dialysis")
weight = st.sidebar.number_input("Body Weight (kg)", 70.0)

serum_k = st.sidebar.number_input("Serum Potassium", 4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", 4.0)

hba1c = st.sidebar.number_input("HbA1c (%)", 6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", 100)

fluid_limit = st.sidebar.number_input("Daily Fluid Limit (ml)", 2000.0)

# =====================================================
# LIMITS LOGIC
# =====================================================

def get_ckd_limits(stage, dialysis):
    if dialysis:
        return {"sodium":2000, "potassium":3000, "phosphorus":1000}
    if stage <= 2:
        return {"sodium":2300, "potassium":3500, "phosphorus":1000}
    if stage == 3:
        return {"sodium":2000, "potassium":2500, "phosphorus":900}
    if stage == 4:
        return {"sodium":2000, "potassium":2000, "phosphorus":800}
    return {"sodium":2000, "potassium":1500, "phosphorus":700}

limits = get_ckd_limits(stage, dialysis)

# Lab tightening
if serum_k >= 6:
    limits["potassium"] = 1500
if serum_phos >= 6:
    limits["phosphorus"] = 700

# Carb limit based on HbA1c
if hba1c < 6.5:
    carb_limit = 200
elif hba1c <= 7.5:
    carb_limit = 180
else:
    carb_limit = 150

limits["carbs"] = carb_limit

protein_target = weight * (1.2 if dialysis else 0.8)

# =====================================================
# SESSION STATE
# =====================================================

if "meals" not in st.session_state:
    st.session_state.meals = {m: [] for m in MEALS}

# =====================================================
# MEAL BUILDER
# =====================================================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice = st.selectbox("Meal Section", MEALS)
query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:
    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
        format_func=lambda x: x["description"]
    )

    food = get_food_details(selected["fdcId"])
    base = extract_nutrients(food)
    portions = extract_portions(food)

    portion_choice = st.selectbox(
        "Select Portion",
        portions,
        format_func=lambda x: x["desc"]
    )

    qty = st.number_input("How many portions?", 1.0, step=0.5)

    if st.button("Add Food"):
        st.session_state.meals[meal_choice].append({
            "id": str(uuid.uuid4()),
            "name": selected["description"],
            "grams": portion_choice["grams"] * qty,
            "base": base
        })

# =====================================================
# DISPLAY + REMOVE + EDIT
# =====================================================

daily = {"sodium":0,"potassium":0,"phosphorus":0,
         "carbs":0,"protein":0,"calories":0,"water":0}

for meal in MEALS:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1, col2, col3 = st.columns([4,2,1])

        with col1:
            st.write(item["name"])

        with col2:
            new_g = st.number_input("grams", value=item["grams"], key=item["id"])
            item["grams"] = new_g

        with col3:
            if st.button("Remove", key="r"+item["id"]):
                st.session_state.meals[meal] = [
                    i for i in st.session_state.meals[meal]
                    if i["id"] != item["id"]
                ]
                st.rerun()

        scaled = scale(item["base"], item["grams"])
        for k in scaled:
            daily[k] += scaled[k]

# =====================================================
# TOTALS
# =====================================================

st.header("Daily Totals")

for k in ["sodium","potassium","phosphorus","carbs","protein","calories"]:
    st.write(f"{k.capitalize()}: {round(daily[k],1)}")

manual_fluid = st.number_input("Additional Fluid Intake (ml)", 0.0)
total_fluid = daily["water"] + manual_fluid

st.write(f"Water from Food: {round(daily['water'],1)} ml")
st.write(f"Total Fluid: {round(total_fluid,1)} ml (Limit {fluid_limit})")

# =====================================================
# RISK CALCULATION
# =====================================================

def risk_label(p):
    if p <= 40:
        return "Low","🟢"
    elif p <= 70:
        return "Moderate","🟡"
    return "High","🔴"

# CKD
ckd_contrib = {}
for n in ["sodium","potassium","phosphorus"]:
    percent = (daily[n] / limits[n]) * 100
    ckd_contrib[n] = percent

ckd_score = max(ckd_contrib.values())
label_ckd, icon_ckd = risk_label(ckd_score)

st.subheader("CKD Risk")
st.markdown(f"{icon_ckd} **{label_ckd}** ({round(ckd_score,1)}%)")

for n,p in sorted(ckd_contrib.items(), key=lambda x:x[1], reverse=True):
    st.write(f"{n.capitalize()}: {round(p,1)}% of daily limit")

# Diabetes
dm_percent = (daily["carbs"] / limits["carbs"]) * 100
label_dm, icon_dm = risk_label(dm_percent)

st.subheader("Diabetes Risk")
st.markdown(f"{icon_dm} **{label_dm}** ({round(dm_percent,1)}%)")
st.write(f"Carbohydrates: {round(dm_percent,1)}% of daily limit")

if hba1c >= 7:
    st.warning("Elevated HbA1c increases long-term glycemic risk.")
if fasting_glucose >= 130:
    st.warning("Elevated fasting glucose increases short-term glycemic risk.")

# Combined
combined = round((ckd_score * 0.6) + (dm_percent * 0.4),1)
label_c, icon_c = risk_label(combined)

st.subheader("Combined Risk")
st.markdown(f"{icon_c} **{label_c}** ({combined}%)")

# =====================================================
# PROTEIN
# =====================================================

st.subheader("Protein Target")
st.write(f"Target: {round(protein_target,1)} g")

if daily["protein"] < protein_target*0.8:
    st.warning("Protein intake below recommended target.")
elif daily["protein"] > protein_target*1.3:
    st.warning("Protein intake above recommended target.")
else:
    st.success("Protein intake within target range.")

# =====================================================
# DISCLAIMER
# =====================================================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer
This application is for educational purposes only.
It does not provide medical advice, diagnosis, or treatment.
Always consult your physician before making dietary decisions.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by USDA.
""")
