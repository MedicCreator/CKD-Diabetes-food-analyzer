import streamlit as st
import requests
import uuid

# ==============================
# CONFIG
# ==============================

st.set_page_config(page_title="Renal + Diabetes Clinical Planner", layout="wide")

USDA_API_KEY = st.secrets["USDA_API_KEY"]
BASE_URL = "https://api.nal.usda.gov/fdc/v1"

IMPORTANT_NUTRIENTS = {
    1093: "sodium",
    1092: "potassium",
    1091: "phosphorus",
    1005: "carbs",
    1003: "protein",
    1008: "calories",
    2000: "sugar"
}

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner", "Snacks"]

# ==============================
# USDA API
# ==============================

@st.cache_data(ttl=86400)
def search_food(query):
    try:
        r = requests.get(
            f"{BASE_URL}/foods/search",
            params={"query": query, "api_key": USDA_API_KEY, "pageSize": 5},
            timeout=20
        )
        if r.status_code != 200:
            return []
        return r.json().get("foods", [])
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
        if r.status_code != 200 or not r.text.strip():
            return {}
        return r.json()
    except:
        return {}

# ==============================
# Nutrient Extraction
# ==============================

def extract_nutrients(food_data):
    nutrients = {v: 0 for v in IMPORTANT_NUTRIENTS.values()}

    for n in food_data.get("foodNutrients", []):
        nutrient_id = None
        value = None

        if "nutrient" in n:
            nutrient_id = n["nutrient"].get("id")
            nutrient_number = n["nutrient"].get("number")
            value = n.get("amount")

            if nutrient_number == "307":
                nutrients["sodium"] = value or 0
            elif nutrient_number == "306":
                nutrients["potassium"] = value or 0
            elif nutrient_number == "305":
                nutrients["phosphorus"] = value or 0
            elif nutrient_number == "205":
                nutrients["carbs"] = value or 0
            elif nutrient_number == "203":
                nutrients["protein"] = value or 0
            elif nutrient_number == "208":
                nutrients["calories"] = value or 0
            elif nutrient_number == "269":
                nutrients["sugar"] = value or 0

        if not nutrient_id:
            nutrient_id = n.get("nutrientId")
            value = n.get("value")

        if nutrient_id in IMPORTANT_NUTRIENTS and value is not None:
            nutrients[IMPORTANT_NUTRIENTS[nutrient_id]] = value

    return nutrients

def extract_portions(food_data):
    portions = [{"description": "100 g", "gramWeight": 100}]

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

# ==============================
# Clinical Logic
# ==============================

def adjusted_limits(stage, serum_k, serum_phos):
    limits = {
        "sodium": 2000 if stage >= 4 else 2300,
        "potassium": 2500,
        "phosphorus": 1000,
        "carbs": 180
    }

    if serum_k >= 6:
        limits["potassium"] = 1500
    elif serum_k >= 5.5:
        limits["potassium"] = 1800

    if serum_phos >= 6:
        limits["phosphorus"] = 700
    elif serum_phos >= 5:
        limits["phosphorus"] = 800

    return limits

def percent_and_excess(value, limit):
    percent = (value / limit) * 100 if limit else 0
    excess = max(value - limit, 0)
    return round(percent,1), round(excess,1)

def risk_label(score):
    if score <= 40:
        return "Low", "🟢"
    elif score <= 70:
        return "Moderate", "🟡"
    return "High", "🔴"

def categorize(percent):
    if percent > 100:
        return "Exceeded", "🔴"
    elif percent >= 70:
        return "High", "🟡"
    elif percent >= 40:
        return "Moderate", "🟡"
    else:
        return "Low", "🟢"

# ==============================
# Sidebar
# ==============================

st.sidebar.header("Patient Profile")

stage = st.sidebar.selectbox("CKD Stage", [1,2,3,4,5])
serum_k = st.sidebar.number_input("Serum Potassium", value=4.5)
serum_phos = st.sidebar.number_input("Serum Phosphorus", value=4.0)
hba1c = st.sidebar.number_input("HbA1c (%)", value=6.5)
fasting_glucose = st.sidebar.number_input("Fasting Glucose", value=100)

# ==============================
# Session State
# ==============================

if "meals" not in st.session_state:
    st.session_state.meals = {meal: [] for meal in MEAL_TYPES}

# ==============================
# UI
# ==============================

st.title("Renal + Diabetes Clinical Daily Planner")

meal_choice = st.selectbox("Select Meal Section", MEAL_TYPES)

query = st.text_input("Search Food")

if st.button("Search"):
    st.session_state.results = search_food(query)

if "results" in st.session_state and st.session_state.results:

    selected = st.selectbox(
        "Select Food",
        st.session_state.results,
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

    quantity = st.number_input("How many portions?", value=1.0, step=0.1)

    if st.button("Add Food"):
        grams = portion_choice["gramWeight"] * quantity
        scaled = scale_nutrients(nutrients, grams)
        scaled["id"] = str(uuid.uuid4())
        scaled["name"] = selected["description"]
        scaled["portion"] = portion_choice["description"]
        st.session_state.meals[meal_choice].append(scaled)

# ==============================
# Display Meals
# ==============================

daily_total = {k:0 for k in IMPORTANT_NUTRIENTS.values()}

for meal in MEAL_TYPES:
    st.subheader(meal)
    for item in st.session_state.meals[meal]:
        col1, col2 = st.columns([4,1])
        with col1:
            st.write(f"- {item['name']} ({item['portion']})")
        with col2:
            if st.button("Remove", key=item["id"]):
                st.session_state.meals[meal] = [
                    i for i in st.session_state.meals[meal]
                    if i["id"] != item["id"]
                ]
                st.rerun()

        for k in daily_total:
            daily_total[k] += item.get(k,0)

# ==============================
# Daily Totals
# ==============================

st.header("Daily Total")

limits = adjusted_limits(stage, serum_k, serum_phos)

nutrient_percents = {}

for nutrient in ["sodium","potassium","phosphorus","carbs"]:
    value = daily_total[nutrient]
    limit = limits[nutrient]
    percent, excess = percent_and_excess(value, limit)
    nutrient_percents[nutrient] = percent

    st.write(
        f"{nutrient.capitalize()}: {round(value,1)} "
        f"(Limit: {limit} | {percent}% | +{excess} over)"
    )

# ==============================
# CKD Risk (All Contributors)
# ==============================

st.subheader("CKD Risk Analysis")

ckd_components = {
    "Sodium": nutrient_percents["sodium"],
    "Potassium": nutrient_percents["potassium"],
    "Phosphorus": nutrient_percents["phosphorus"]
}

max_ckd = max(ckd_components.values())
ckd_label, ckd_icon = risk_label(max_ckd)

st.metric("CKD Risk Score", round(max_ckd,1))
st.markdown(f"### {ckd_icon} {ckd_label} Risk")

st.markdown("#### Contributors:")

for nutrient, percent in sorted(ckd_components.items(), key=lambda x: x[1], reverse=True):
    category, icon = categorize(percent)
    st.write(f"{icon} {nutrient}: {percent}% ({category})")

# ==============================
# Diabetes Risk
# ==============================

st.subheader("Diabetes Risk Analysis")

dm_percent = nutrient_percents["carbs"]
dm_label, dm_icon = risk_label(dm_percent)

st.metric("Diabetes Risk Score", round(dm_percent,1))
st.markdown(f"### {dm_icon} {dm_label} Risk")

category, icon = categorize(dm_percent)
st.write(f"{icon} Carbohydrates: {dm_percent}% ({category})")

if hba1c >= 7:
    st.warning("Elevated HbA1c increases long-term glycemic risk.")

if fasting_glucose >= 130:
    st.warning("Elevated fasting glucose increases short-term glycemic risk.")

# ==============================
# Combined Risk
# ==============================

combined_score = round((max_ckd * 0.6) + (dm_percent * 0.4), 1)
combined_label, combined_icon = risk_label(combined_score)

st.subheader("Combined Risk")
st.metric("Combined Score", combined_score)
st.markdown(f"### {combined_icon} {combined_label} Risk")

# ==============================
# Disclaimer
# ==============================

st.markdown("---")
st.markdown("""
### Medical & Data Disclaimer

This application is for educational purposes only.
It does not provide medical advice, diagnosis, or treatment.

Risk scores are generalized estimates based on dietary guidance
and user-entered laboratory values.

Always consult your physician before making dietary decisions.

Nutritional data provided by USDA FoodData Central.
Not affiliated with or endorsed by the USDA.
""")
