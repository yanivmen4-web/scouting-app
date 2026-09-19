import streamlit as st
import pandas as pd

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Player Filtering System")

data = {
    "Name": ["Player A", "Player B", "Player C", "Player D", "Player E"],
    "Age": [20, 23, 26, 29, 31],
    "Position": ["CB", "CM", "ST", "CB", "RW"],
    "Market Value (€)": [300000, 750000, 1200000, 500000, 2000000]
}

df = pd.DataFrame(data)

st.sidebar.header("Filter Players")

min_age, max_age = int(df["Age"].min()), int(df["Age"].max())
selected_age = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))

positions = df["Position"].unique().tolist()
selected_positions = st.sidebar.multiselect("Position", positions, default=positions)

filtered_df = df[
    (df["Age"] >= selected_age[0]) & 
    (df["Age"] <= selected_age[1]) & 
    (df["Position"].isin(selected_positions))
]

st.write(f"Showing **{len(filtered_df)}** players:")
st.dataframe(filtered_df, use_container_width=True)
