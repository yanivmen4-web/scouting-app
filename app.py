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

st.markdown(
    "<style>[data-testid='stSidebar'][aria-expanded='true'] {min-width: 380px;}</style>",
    unsafe_allow_html=True,
)

st.sidebar.header("Filter Players")

search_name = st.sidebar.text_input("Search by name")
search_club = st.sidebar.text_input("Search by club")

ages = df["Age"].dropna()
age_range = None
if len(ages) > 0 and ages.min() < ages.max():
    age_min, age_max = int(ages.min()), int(ages.max())
    age_range = st.sidebar.slider("Age Range", age_min, age_max, (age_min, age_max))

selected_positions = st.sidebar.multiselect(
    "Position (empty = all)", list(POS_CODES.values())
)

value_cap = int(df["Market Value (€)"].max()) if df["Market Value (€)"].notna().any() else 0
st.sidebar.write("Market value (€)")
value_from = st.sidebar.number_input("From", min_value=0, max_value=value_cap, value=0, step=100000)
st.sidebar.caption(f"From: {value_from:,}")
value_to = st.sidebar.number_input("To", min_value=0, max_value=value_cap, value=value_cap, step=100000)
st.sidebar.caption(f"To: {value_to:,}")

foot_choice = st.sidebar.radio("Foot", ["All", "R", "L"], horizontal=True)
eu_choice = st.sidebar.radio("EU passport", ["All", "YES", "NO"], horizontal=True)
israeli_choice = st.sidebar.radio("Israeli", ["All", "YES", "NO"], horizontal=True)
st.sidebar.caption(
    "EU and Israeli are based on primary citizenship and birth country. "
    "Additional passports are not included."
)

mask = pd.Series(True, index=df.index)
if search_name:
    mask &= df["Name"].astype(str).str.contains(search_name, case=False, na=False, regex=False)
if search_club:
    mask &= df["Club Name"].astype(str).str.contains(search_club, case=False, na=False, regex=False)
if age_range:
    mask &= df["Age"].between(age_range[0], age_range[1]).fillna(False).astype(bool)
if selected_positions:
    mask &= df["Position"].isin(selected_positions)
if foot_choice != "All":
    mask &= df["Foot"].isin([foot_choice, "Both"])
if value_from > 0 or value_to < value_cap:
    mask &= df["Market Value (€)"].between(value_from, value_to).fillna(False)
if eu_choice != "All":
    mask &= df["EU"] == eu_choice
if israeli_choice != "All":
    mask &= df["Israeli"] == israeli_choice

df = df[mask]



st.write(f"Showing **{len(df)}** players:")

SHOW = [
    "Name", "Transfermarkt", "Age", "Position", "Foot", "Club",
    "Last Transfer", "Citizenship", "EU", "Israeli",
    "Market Value (€)", "Contract Expires", "Agent",
]
display_df = df[[c for c in SHOW if c in df.columns]]

column_config = {
    "Transfermarkt": st.column_config.LinkColumn("Transfermarkt", display_text="Open"),
    "Club": st.column_config.LinkColumn("Club", display_text=r"#(.*)$"),
}

try:
    money_config = dict(column_config)
    money_config["Market Value (€)"] = st.column_config.NumberColumn(
        "Market Value (€)", format="localized"
    )
    st.dataframe(display_df, hide_index=True, width="stretch", column_config=money_config)
except Exception:
    st.dataframe(display_df, hide_index=True, width="stretch", column_config=column_config)


def make_export(frame):
    try:
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False, sheet_name="Players")
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return buffer.getvalue(), "players.xlsx", mime
    except ImportError:
        data = frame.to_csv(index=False).encode("utf-8-sig")
        return data, "players.csv", "text/csv"


st.subheader("Export")

export_df = display_df.copy()
export_df["Club"] = df["Club Name"]
name_hash = pd.util.hash_pandas_object(export_df["Name"].astype(str), index=False).sum()
signature = (len(export_df), int(name_hash))

if st.button("Prepare Excel file"):
    with st.spinner("Preparing file..."):
        st.session_state["export"] = (signature, make_export(export_df))

saved = st.session_state.get("export")
if saved and saved[0] == signature:
    file_bytes, file_name, file_mime = saved[1]
    label = f"Download {file_name} ({len(export_df)} players)"
    try:
        st.download_button(label, data=file_bytes, file_name=file_name, mime=file_mime, on_click="ignore")
    except TypeError:
        st.download_button(label, data=file_bytes, file_name=file_name, mime=file_mime)
elif saved:
    st.caption("The filters changed since the file was prepared. Press Prepare Excel file again.")




import json

with st.expander("Apify input generator (clubs)"):
    orig, _ = load_players(data_url)
    clubs = orig.dropna(subset=["Club ID"]).drop_duplicates("Club ID")
    urls = [
        f"https://www.transfermarkt.com/-/startseite/verein/{int(i)}"
        for i in clubs["Club ID"]
    ]
    batches = [urls[i:i + 100] for i in range(0, len(urls), 100)]
    st.write(f"{len(urls)} clubs in {len(batches)} batches of up to 100")
    for n, batch in enumerate(batches, start=1):
        st.write(f"Batch {n} ({len(batch)} clubs)")
        st.code(json.dumps({"scrapeType": "clubs", "items": batch}, indent=2), language="json")
