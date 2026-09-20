import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Live Transfermarkt Squad Search")

st.sidebar.header("Search Settings")
base_url = st.sidebar.text_input("API Base URL", value="https://transfermarkt-api.fly.dev")
club_id = st.sidebar.text_input("Transfermarkt Club ID", value="500")


@st.cache_data(ttl=3600)
def fetch_club_players(api_url, c_id):
    url = f"{api_url.rstrip('/')}/clubs/{c_id}/players"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    rows = []
    for p in res.json().get("players", []):
        rows.append({
            "Name": p.get("name"),
            "Position": p.get("position"),
            "Age": p.get("age"),
            "Market Value (€)": p.get("marketValue"),
        })
    return pd.DataFrame(rows)


try:
    df = fetch_club_players(base_url, club_id)
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

if df.empty:
    st.warning("No players found for this Club ID.")
    st.stop()

df["Age"] = pd.to_numeric(df["Age"], errors="coerce")
df["Market Value (€)"] = pd.to_numeric(df["Market Value (€)"], errors="coerce")

st.sidebar.header("Filter Players")

if df["Age"].notna().any():
    min_age = int(df["Age"].min())
    max_age = int(df["Age"].max())
    if min_age < max_age:
        selected_age = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))
        df = df[df["Age"].between(selected_age[0], selected_age[1])]

if df["Position"].notna().any():
    positions = df["Position"].dropna().unique().tolist()
    selected_positions = st.sidebar.multiselect("Position", positions, default=positions)
    df = df[df["Position"].isin(selected_positions)]

st.write(f"Showing **{len(df)}** players:")
st.dataframe(df, hide_index=True)
