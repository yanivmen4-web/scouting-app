  import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Live Transfermarkt Squad Search")

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

st.sidebar.header("Search Settings")
club_id = st.sidebar.text_input("Transfermarkt Club ID", value="500")

@st.cache_data
def fetch_club_players(c_id):
    url = f"https://api.transfermarkt-api.visiting.fans/clubs/{c_id}/players"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            players = []
            for p in data.get("players", []):
                players.append({
                    "Name": p.get("name"),
                    "Position": p.get("position"),
                    "Age": p.get("age"),
                    "Market Value (€)": p.get("marketValue")
                })
            return pd.DataFrame(players)
    except:
        pass
    return pd.DataFrame()

df = fetch_club_players(club_id)

if not df.empty:
    st.sidebar.header("Filter Players")
    
    if "Age" in df.columns and df["Age"].notna().any():
        min_age = int(df["Age"].min())
        max_age = int(df["Age"].max())
        selected_age = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))
        df = df[(df["Age"] >= selected_age[0]) & (df["Age"] <= selected_age[1])]
    
    if "Position" in df.columns and df["Position"].notna().any():
        positions = df["Position"].dropna().unique().tolist()
        selected_positions = st.sidebar.multiselect("Position", positions, default=positions)
        df = df[df["Position"].isin(selected_positions)]

    st.write(f"Showing **{len(df)}** players:")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No player data found for this Club ID or live connection pending.")
