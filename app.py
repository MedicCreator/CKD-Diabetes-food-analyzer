import streamlit as st
import requests

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
    url = f"{BASE_URL}/foods/search"
    params = {"query": query, "api_key": USDA_API_KEY, "pageSize": 5}
    r = requests.get(url, params=params, timeout=20)
    return r.json().get("foods", [])

@st.cache_data(ttl=86400)
def get_food_details(fdc_id):
    url = f"{BASE_URL}/food/{fdc_id}"
    params = {"api_key": USDA_API_KEY}
    r = requests.get(url, params=params, timeout=20)
    return r.json()

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}
    for n in food_data.get("foodNutrients", []):
        nutrient_id = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        value = n.get("amount") or n.get("value")

        if nutrient_id in IMPORTANT_NUTRIENTS:
            nutrients[IMPORTANT_NUTRIENTS[nutrient_id]] = value if value is not None else 0
    return nutrients

def extract_portions(food_data):
    portions = [{"description": "100 g", "gramWeight": 100}]

    if food_data.get("servingSize"):
        portions.append({
            "description": f"1 serving ({food_data['servingSize']} {food_data.get('servingSizeUnit','g')})",
            "gramWeight": food_data["servingSize"]
        })

    for p in food_data.get("foodPortions", []):
        if p.get("gramWeight"):
            portions.append({
                "description": p.get("portionDescription"),
                "gramWeight": p.get("gramWeight")
            })

    return portions

def scale_nutrients(nutrients, grams):
    factor = grams / 100
    scaled = {}
    for k, v in nutrients.items():
        if v is None:
            v = 0
        scaled[k] = round(v * factor, 2)
    return scaled

# =====================================
# CKD LOGIC
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

def adjust_labs(limits, k, phos):
    if k > 5.5:
        limits["potassium"] = 1500
    elif k > 5.0:
        limits["potassium"] = 2000
    if phos > 4.5:
        limits["phosphorus"] = 800
    return limits

def dialysis_adjust(limits, dialysis):
    if dialysis:
        limits["sodium"] = 2000
        limits["potassium"] = 3000
    return limits

def per_meal_limits(limits, meals=3):
    return {k: v / meals for k, v in limits.items() if v}

def nutrient_percent(value, limit):
    return min((value / limit) * 100, 150)

def ckd_score(values, limits):
    weights = {"potassium": 0.4, "phosphorus": 0.3, "sodium": 0.3}
    score = 0
    for n in weights:
        if n in limits:
            score += nutrient_percent(values[n], limits[n]) * weights[n]
    return round(min(score, 100), 1)

# =====================================
# DIABETES LOGIC
# =====================================

def diabetes_score(carbs, sugar, fiber):
    carb_score = (carbs / 60) * 100
    sugar_score = (sugar / 25) * 100
    fiber_bonus = (fiber / 10) * 20
    score = carb_score * 0.5 + sugar_score * 0.3 - fiber_bonus
    return round(max(min(score, 100), 0), 1)

def combined_score(ckd, dm):
    return round((ckd * 0.6) + (dm * 0.4), 1)

def risk_label(score):
    if score <= 40:
        return "🟢 Low Risk"
    elif score <= 70:
        return "🟡 Moderate Risk"
    return "🔴 High Risk"

# =====================================
# UI
# =====================================

st.title("CKD + Diabetes Smart Food Analyzer")

st.sidebar.header("Patient Settings")
stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
serum_k = st.sidebar.number_input("Serum Potassium", value=4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", value=4.0)
dialysis = st.sidebar.checkbox("On Dialysis")

if "meal" not in st.session_state:
    st.session_state.meal = []

st.header("Meal Builder")

food_query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.search_results = search_food(food_query)

if "search_results" in st.session_state and st.session_state.search_results:

    selected = st.selectbox(
        "Select Food",
        st.session_state.search_results,
        format_func=lambda x: x["description"]
    )

    food_data = get_food_details(selected["fdcId"])
    nutrients = extract_nutrients(food_data)
    portions = extract_portions(food_data)

    portion_choice = st.selectbox(
        "Select Portion",
        portions,
        format_func=lambda x: x["description"]
    )

    quantity = st.number_input("Quantity", value=1.0)

    if st.button("Add Food"):
        grams = portion_choice["gramWeight"] * quantity
        scaled = scale_nutrients(nutrients, grams)
        st.session_state.meal.append(scaled)
        st.success("Food Added")

# Remove items
if st.session_state.meal:
    st.subheader("Current Meal")
    for i, item in enumerate(st.session_state.meal):
        col1, col2 = st.columns([4,1])
        with col1:
            st.write(f"Item {i+1}")
        with col2:
            if st.button("Remove", key=i):
                st.session_state.meal.pop(i)
                st.rerun()

# =====================================
# RISK ANALYSIS
# =====================================

if st.session_state.meal:

    st.subheader("Meal Nutrient Totals")

    total = {k:0 for k in IMPORTANT_NUTRIENTS.values()}
    for item in st.session_state.meal:
        for k in total:
            total[k] += item.get(k, 0)

    limits = get_ckd_limits(stage)
    limits = adjust_labs(limits, serum_k, serum_phos)
    limits = dialysis_adjust(limits, dialysis)
    meal_limits = per_meal_limits(limits)

    for nutrient, value in total.items():
        if nutrient in meal_limits:
            limit = meal_limits[nutrient]
            percent = min(value / limit, 1.5)
            st.write(f"{nutrient.capitalize()}: {round(value,1)} mg")
            st.progress(min(percent, 1.0))

    ckd = ckd_score(total, meal_limits)
    dm = diabetes_score(total["carbs"], total["sugar"], total["fiber"])
    combined = combined_score(ckd, dm)

    st.divider()
    st.subheader("Risk Scores")

    st.metric("CKD Risk", ckd)
    st.write(risk_label(ckd))

    st.metric("Diabetes Risk", dm)
    st.write(risk_label(dm))

    st.metric("Combined Risk", combined)
    st.write(risk_label(combined))

# =====================================
# DISCLAIMER
# =====================================

st.markdown("---")

st.markdown("""
⚠️ **Medical Disclaimer**

This application is intended for educational and informational purposes only.
It does not provide medical advice, diagnosis, or treatment.
Always consult your physician or registered dietitian before making
dietary or medical decisions.
""")

st.markdown("""
**Data Source:** Nutritional data provided by USDA FoodData Central  
(https://fdc.nal.usda.gov/)

This application is not affiliated with, endorsed by, or certified by the USDA.
""")
