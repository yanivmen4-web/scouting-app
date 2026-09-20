import io
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")

BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/"

EU = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic",
    "czechia", "denmark", "estonia", "finland", "france", "germany", "greece",
    "hungary", "ireland", "republic of ireland", "italy", "latvia", "lithuania",
    "luxembourg", "malta", "netherlands", "poland", "portugal", "romania",
    "slovakia", "slovenia", "spain", "sweden",
}

COLUMNS = {
    "name": "Name",
    "position": "Position",
    "sub_position": "Sub Position",
    "current_club_name": "Club",
    "current_club_id": "Club ID",
    "country_of_citizenship": "Citizenship",
    "country_of_birth": "Birth Country",
    "city_of_birth": "Birth City",
    "market_value_in_eur": "Market Value (€)",
    "contract_expiration_date": "Contract Expires",
    "agent_name": "Agent",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}

with st.sidebar.expander("Data source"):
    data_url = st.text_input("Players file URL", value=BASE + "players.csv.gz")
    transfers_url = st.text_input("Transfers file URL", value=BASE + "transfers.csv.gz")


def download_csv(url):
    res = requests.get(url, headers=HEADERS, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    content = res.content
    compression = "gzip" if content[:2] == b"\x1f\x8b" else None
    return pd.read_csv(io.BytesIO(content), compression=compression), res.headers


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
        "Latest Club ID": last["to_club_id"].astype("Int64"),
        "Last Transfer": last["transfer_date"].dt.strftime("%Y-%m-%d"),
    })
    return out.reset_index(drop=True)


def club_link(name, club_id):
    if pd.isna(name):
        return None
    if pd.notna(club_id):
        return f"https://www.transfermarkt.com/-/startseite/verein/{int(club_id)}#{name}"
    search = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query="
    return f"{search}{quote(str(name))}#{name}"




@st.cache_data(ttl=3600)


POS_CODES = {
    "Goalkeeper": "GK",
    "Centre-Back": "CB",
    "Right-Back": "RB",
    "Left-Back": "LB",
    "Defensive Midfield": "DMC",
    "Central Midfield": "CM",
    "Attacking Midfield": "AMC",
    "Right Midfield": "RM",
    "Left Midfield": "LM",
    "Right Winger": "RW",
    "Left Winger": "LW",
    "Second Striker": "SS",
    "Centre-Forward": "SC",
}
FOOT_CODES = {"right": "R", "left": "L", "both": "Both"}
COLUMNS["foot"] = "Foot"


@st.cache_data(ttl=3600)
def load_players(url):
    raw, headers = download_csv(url)
    file_modified = headers.get("Last-Modified", "")
    if "last_season" in raw.columns:
        raw = raw[raw["last_season"] == raw["last_season"].max()]
    keep = [c for c in COLUMNS if c in raw.columns]
    df = raw[keep].rename(columns=COLUMNS)
    for col in COLUMNS.values():
        if col not in df.columns:
            df[col] = pd.NA
    df["Club ID"] = pd.to_numeric(df["Club ID"], errors="coerce").astype("Int64")
    df["Market Value (€)"] = pd.to_numeric(df["Market Value (€)"], errors="coerce")
    contract = pd.to_datetime(df["Contract Expires"], errors="coerce")
    df["Contract Expires"] = contract.dt.strftime("%Y-%m-%d")
    if "date_of_birth" in raw.columns:
        dob = pd.to_datetime(raw["date_of_birth"], errors="coerce")
        df["Age"] = ((pd.Timestamp.today() - dob).dt.days // 365.25).astype("Int64")
    else:
        df["Age"] = pd.NA
    cit = df["Citizenship"].fillna("").astype(str).str.strip().str.lower()
    born = df["Birth Country"].fillna("").astype(str).str.strip().str.lower()
    df["EU"] = (cit.isin(EU) | born.isin(EU)).map({True: "YES", False: "NO"})
    df["Israeli"] = ((cit == "israel") | (born == "israel")).map({True: "YES", False: "NO"})
    df["Position"] = df["Sub Position"].map(POS_CODES)
    df["Foot"] = df["Foot"].astype(str).str.strip().str.lower().map(FOOT_CODES)
    if "player_id" in raw.columns:
        df["player_id"] = raw["player_id"].astype("Int64")
        df["Transfermarkt"] = "https://www.transfermarkt.com/-/profil/spieler/" + df["player_id"].astype(str)
    else:
        df["player_id"] = pd.NA
        df["Transfermarkt"] = pd.NA
    df = df.sort_values("Market Value (€)", ascending=False, na_position="last")
    return df.reset_index(drop=True), file_modified


try:
    with st.spinner("Loading players file..."):
        df, file_modified = load_players(data_url)
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

df["Club Name"] = df["Club"]
df["Last Transfer"] = pd.NA
latest_transfer_date = "unknown"

try:
    with st.spinner("Loading transfers file..."):
        latest = load_latest_transfers(transfers_url)
    latest_transfer_date = latest["Last Transfer"].max()
    df = df.drop(columns=["Last Transfer"]).merge(latest, on="player_id", how="left")
    has_latest = df["Latest Club"].notna()
    df["Club Name"] = df["Latest Club"].where(has_latest, df["Club"])
    df["Club ID"] = df["Latest Club ID"].where(has_latest, df["Club ID"])
except Exception as e:
    st.warning(f"Could not load transfers file: {e}")

df["Club"] = [club_link(n, c) for n, c in zip(df["Club Name"], df["Club ID"])]
