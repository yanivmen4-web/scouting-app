import io
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Player Database (Transfermarkt open dataset)")

BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/"
DEFAULT_URL = BASE + "players.csv.gz"
DEFAULT_TRANSFERS_URL = BASE + "transfers.csv.gz"

COLUMNS = {
    "name": "Name",
    "position": "Position",
    "sub_position": "Sub Position",
    "current_club_name": "Club",
    "current_club_id": "Club ID",
    "country_of_citizenship": "Nationality",
    "market_value_in_eur": "Market Value (€)",
    "contract_expiration_date": "Contract Expires",
    "agent_name": "Agent",
}

ORDER = [
    "Name", "Transfermarkt", "Age", "Position", "Sub Position", "Club",
    "Last Transfer", "Nationality", "Market Value (€)", "Contract Expires",
    "Agent", "Club Name",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}

st.sidebar.header("Data Source")
data_url = st.sidebar.text_input("Players file URL", value=DEFAULT_URL)
transfers_url = st.sidebar.text_input("Transfers file URL", value=DEFAULT_TRANSFERS_URL)


def download_csv(url):
    res = requests.get(url, headers=HEADERS, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    content = res.content
    compression = "gzip" if content[:2] == b"\x1f\x8b" else None
    return pd.read_csv(io.BytesIO(content), compression=compression), res.headers


@st.cache_data(ttl=3600)
def load_players(url):
    raw, headers = download_csv(url)
    file_modified = headers.get("Last-Modified", "not provided")
    latest_season = raw["last_season"].max() if "last_season" in raw.columns else "unknown"
    if "last_season" in raw.columns:
        raw = raw[raw["last_season"] == raw["last_season"].max()]
    keep = [c for c in COLUMNS if c in raw.columns]
    df = raw[keep].rename(columns=COLUMNS)
    if "Club ID" in df.columns:
        df["Club ID"] = df["Club ID"].astype("Int64")
    else:
        df["Club ID"] = pd.NA
    if "Contract Expires" in df.columns:
        contract = pd.to_datetime(df["Contract Expires"], errors="coerce")
        df["Contract Expires"] = contract.dt.strftime("%Y-%m-%d")
    if "date_of_birth" in raw.columns:
        dob = pd.to_datetime(raw["date_of_birth"], errors="coerce")
        age = (pd.Timestamp.today() - dob).dt.days // 365.25
        df.insert(1, "Age", age.astype("Int64"))
    else:
        df.insert(1, "Age", pd.NA)
    if "player_id" in raw.columns:
        ids = raw["player_id"].astype("Int64")
        df["player_id"] = ids
        df["Transfermarkt"] = "https://www.transfermarkt.com/-/profil/spieler/" + ids.astype(str)
    if "Market Value (€)" in df.columns:
        df = df.sort_values("Market Value (€)", ascending=False, na_position="last")
    return df.reset_index(drop=True), file_modified, str(latest_season)


@st.cache_data(ttl=3600)
def load_latest_transfers(url):
    tr, _ = download_csv(url)
    tr["transfer_date"] = pd.to_datetime(tr["transfer_date"], errors="coerce")
    tr = tr.dropna(subset=["transfer_date"])
    tr = tr[tr["transfer_date"] <= pd.Timestamp.today()]
    tr = tr.sort_values("transfer_date")
    last = tr.groupby("player_id").tail(1)
    out = pd.DataFrame({
        "player_id": last["player_id"].astype("Int64"),
        "Latest Club": last["to_club_name"],
        "Latest Club ID":
