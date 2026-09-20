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
    cit = df["Citizenship"].fillna("").astype(str).str.strip().str.lower().isin(EU)
    born = df["Birth Country"].fillna("").astype(str).str.strip().str.lower().isin(EU)
    df["EU"] = "-"
    df.loc[cit & ~born, "EU"] = "Citizenship"
    df.loc[~cit & born, "EU"] = "Birth"
    df.loc[cit & born, "EU"] = "Both"
    place = df["Birth City"].fillna("").astype(str) + ", " + df["Birth Country"].fillna("").astype(str)
    df["Place of Birth"] = place.str.strip(", ").replace("", pd.NA)
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

try:
    updated = pd.to_datetime(file_modified, utc=True)
    days = (pd.Timestamp.now(tz="UTC") - updated).days
    note = (
        f"Data last updated: {updated.strftime('%d %b %Y')} ({days} days ago). "
        f"Latest transfer in the data: {latest_transfer_date}."
    )
    if days > 7:
        st.warning(note + " Changes after these dates are not included. Verify with the Transfermarkt link.")
    else:
        st.success(note)
except Exception:
    st.info(f"Data last updated: {file_modified or 'unknown'}")




st.sidebar.header("Filter Players")

search_name = st.sidebar.text_input("Search by name")
search_club = st.sidebar.text_input("Search by club")

ages = df["Age"].dropna()
age_range = None
if len(ages) > 0 and ages.min() < ages.max():
    age_min, age_max = int(ages.min()), int(ages.max())
    age_range = st.sidebar.slider("Age Range", age_min, age_max, (age_min, age_max))

positions = sorted(df["Position"].dropna().unique().tolist())
selected_positions = st.sidebar.multiselect("Position", positions, default=positions)

value_cap = int(df["Market Value (€)"].max()) if df["Market Value (€)"].notna().any() else 0
st.sidebar.write("Market value (€)")
col_from, col_to = st.sidebar.columns(2)
value_from = col_from.number_input("From", min_value=0, max_value=value_cap, value=0, step=100000)
value_to = col_to.number_input("To", min_value=0, max_value=value_cap, value=value_cap, step=100000)

eu_choice = st.sidebar.radio(
    "EU passport",
    [
        "All players",
        "EU citizenship or EU birth country",
        "EU citizenship only",
        "Born in EU only",
    ],
)

mask = pd.Series(True, index=df.index)
if search_name:
    mask &= df["Name"].astype(str).str.contains(search_name, case=False, na=False, regex=False)
if search_club:
    mask &= df["Club Name"].astype(str).str.contains(search_club, case=False, na=False, regex=False)
if age_range:
    mask &= df["Age"].between(age_range[0], age_range[1]).fillna(False).astype(bool)
if len(selected_positions) < len(positions):
    mask &= df["Position"].isin(selected_positions)
if value_from > 0 or value_to < value_cap:
    mask &= df["Market Value (€)"].between(value_from, value_to).fillna(False)
if eu_choice == "EU citizenship or EU birth country":
    mask &= df["EU"] != "-"
elif eu_choice == "EU citizenship only":
    mask &= df["EU"].isin(["Citizenship", "Both"])
elif eu_choice == "Born in EU only":
    mask &= df["EU"].isin(["Birth", "Both"])

df = df[mask]
