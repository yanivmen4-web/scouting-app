import streamlit as st
import pandas as pd

st.title("CMA Scouting Tool")
st.write("Player Filtering System")

data = {
    "Name": ["Player A", "Player B", "Player C"],
    "Age": [22, 25, 28],
    "Position": ["CB", "CM", "ST"],
    "Market Value (€)": [500000, 1200000, 850000]
}

df = pd.DataFrame(data)
st.dataframe(df)
