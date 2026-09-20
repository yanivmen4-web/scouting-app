import io

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Player Database (Transfermarkt open dataset)")

DEFAULT_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"

COLUMNS = {
    "name": "Name",
    "position": "Position",
    "sub_position": "Sub Position",
    "current_club_name": "Club",
    "country_of_citizenship": "Nationality",
    "market_value_in_eur": "Market Value (€)",
    "contract_expiration_date": "Contract Expires",
    "agent_name": "Agent",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}

st.sidebar.header("Data Source")
data_url = st.sidebar.text_input("Players file URL", value=DEFAULT_URL)


@st.cache_data(ttl=3600)
def load_players(url):
    res = requests.get(url, headers=HEADERS, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    file_modified = res.headers.get("Last-Modified", "not provided")
    content = res.content
    compression = "gzip" if content[:2] == b"\x1f\x8b" else None
    raw = pd.read_csv(io.BytesIO(content), compression=compression)
    latest_season = raw["last_season"].max() if "last_season" in raw.columns else "unknown"
    if "last_season" in raw.columns:
        raw = raw[raw["last_season"] == raw["last_season"].max()]
    keep = [c for c in COLUMNS if c in raw.columns]
    df = raw[keep].rename(columns=COLUMNS)
    if "date_of_birth" in raw.columns:
        dob = pd.to_datetime(raw["date_of_birth"], errors="coerce")
        age = (pd.Timestamp.today() - dob).dt.days // 365.25
        df.insert(1, "Age", age.astype("Int64"))
    else:
        df.insert(1, "Age", pd.NA)
    if "player_id" in raw.columns:
        ids = raw["player_id"].astype("Int64").astype(str)
        df["Transfermarkt"] = "https://www.transfermarkt.com/-/profil/spieler/" + ids
    if "Market Value (€)" in df.columns:
        df = df.sort_values("Market Value (€)", ascending=False, na_position="last")
    return df.reset_index(drop=True), file_modified, str(latest_season)


try:
    df, file_modified, latest_season = load_players(data_url)
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

st.caption(f"File last modified: {file_modified} | Latest season in file: {latest_season}")

st.sidebar.header("Filter Players")

search_name = st.sidebar.text_input("Search by name")
if search_name:
    df = df[df["Name"].str.contains(search_name, case=False, na=False)]

if "Club" in df.columns:
    search_club = st.sidebar.text_input("Search by club")
    if search_club:
        df = df[df["Club"].str.contains(search_club, case=False, na=False)]

if df["Age"].notna().any():
    min_age = int(df["Age"].min())
    max_age = int(df["Age"].max())
    if min_age < max_age:
        selected_age = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))
        df = df[df["Age"].between(selected_age[0], selected_age[1])]

if "Position" in df.columns and df["Position"].notna().any():
    positions = df["Position"].dropna().unique().tolist()
    selected_positions = st.sidebar.multiselect("Position", positions, default=positions)
    df = df[df["Position"].isin(selected_positions)]

if "Market Value (€)" in df.columns:
    min_value = st.sidebar.number_input("Min market value (€)", min_value=0, value=0, step=100000)
    if min_value > 0:
        df = df[df["Market Value (€)"] >= min_value]

st.write(f"Showing **{len(df)}** players:")

column_config = {}
if "Transfermarkt" in df.columns:
    column_config["Transfermarkt"] = st.column_config.LinkColumn("Transfermarkt", display_text="Open")

st.dataframe(df, hide_index=True, use_container_width=True, column_config=column_config)
