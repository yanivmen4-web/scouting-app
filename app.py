import time
import io
import json
import re
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

ISRAEL_CLUBS = re.compile(
    r"hapoel|maccabi|beitar|ironi|bnei sakhnin|bnei yehuda|bnei reineh|sektzia|"
    r"ashdod|tel aviv|jerusalem|haifa|beer sheva|be'er sheva|kiryat|tiberias|"
    r"netanya|nazareth|ashkelon|rishon|afula",
    re.IGNORECASE,
)

COLUMNS = {
    "name": "Name", "position": "Position", "sub_position": "Sub Position",
    "current_club_name": "Club", "current_club_id": "Club ID",
    "country_of_citizenship": "Citizenship", "country_of_birth": "Birth Country",
    "market_value_in_eur": "Market Value (€)",
    "contract_expiration_date": "Contract Expires",
    "agent_name": "Agent", "foot": "Foot",
    "_in_cm": " (cm)",
}

POS_CODES = {
    "Goalkeeper": "GK", "Centre-Back": "CB", "Right-Back": "RB", "Left-Back": "LB",
    "Defensive Midfield": "DMC", "Central Midfield": "CM", "Attacking Midfield": "AMC",
    "Right Midfield": "RM", "Left Midfield": "LM", "Right Winger": "RW",
    "Left Winger": "LW", "Second Striker": "SS", "Centre-Forward": "SC",
}
FOOT_CODES = {"right": "R", "left": "L", "both": "Both"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
}

with st.sidebar.expander("Data source"):
    data_url = st.text_input("Players file URL", value=BASE + "players.csv.gz")
    transfers_url = st.text_input("Transfers file URL", value=BASE + "transfers.csv.gz")


def download_csv(url, usecols=None):
    res = requests.get(url, headers=HEADERS, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    content = res.content
    compression = "gzip" if content[:2] == b"\x1f\x8b" else None
    return pd.read_csv(io.BytesIO(content), compression=compression, usecols=usecols), res.headers


@st.cache_data(ttl=604800, show_spinner="Loading season stats...")
def load_season_stats():
    df, _ = download_csv(
        BASE + "appearances.csv.gz",
        usecols=["player_id", "date", "goals", "assists", "minutes_played"],
    )
    df["date"] = pd.to_datetime(
        df["date"].astype(str), errors="coerce", utc=True
    ).dt.tz_localize(None)
    
    today = pd.Timestamp.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    cur_start = pd.Timestamp(start_year, 7, 1)
    cur_end = pd.Timestamp(start_year + 1, 6, 30)
    prev_start = pd.Timestamp(start_year - 1, 7, 1)

    df = df[(df["date"] >= prev_start) & (df["date"] <= cur_end)]

    def _sum_stats(d, label):
        return d.groupby("player_id", as_index=False).agg(
            **{
                f"Minutes {label}": ("minutes_played", "sum"),
                f"Goals {label}": ("goals", "sum"),
                f"Assists {label}": ("assists", "sum"),
            }
        )

    cur = _sum_stats(df[df["date"] >= cur_start], "Current")
    prev = _sum_stats(df[df["date"] < cur_start], "Previous")
    stats = prev.merge(cur, on="player_id", how="outer").fillna(0)
    return stats


SSA = {
    "Angola": [], "Benin": [], "Botswana": [], "Burkina Faso": [], "Burundi": [],
    "Cameroon": [], "Cape Verde": ["cabo verde"], "Central African Republic": [],
    "Chad": [], "Comoros": [], "Congo": ["republic of the congo"],
    "DR Congo": ["congo dr", "democratic republic of the congo"],
    "Cote d'Ivoire": ["ivory coast", "c\u00f4te d'ivoire"], "Djibouti": [],
    "Equatorial Guinea": [], "Eritrea": [], "Eswatini": ["swaziland"], "Ethiopia": [],
    "Gabon": [], "Gambia": ["the gambia"], "Ghana": [], "Guinea": [],
    "Guinea-Biussau": [], "Kenya": [], "Lesotho": [], "Liberia": [], "Madagascar": [],
    "Malawi": [], "Mali": [], "Mauritania": [], "Mauritius": [], "Mozambique": [],
    "Namibia": [], "Niger": [], "Nigeria": [], "Rwanda": [], "Sao Tome and Principe": [],
    "Senegal": [], "Seychelles": [], "Sierra Leone": [], "Somalia": [],
    "South Africa": [], "South Sudan": [], "Sudan": [], "Tanzania": [], "Togo": [],
    "Uganda": [], "Zambia": [], "Zimbabwe": [],
}
SSA_LOOKUP = {}
for _name, _aliases in SSA.items():
    SSA_LOOKUP[_name.lower()] = _name
    for _alias in _aliases:
        SSA_LOOKUP[_alias] = _name


def parse_value(text):
    t = str(text).strip().lower().replace("€", "").replace(",", "")
    mult = 1
    if t.endswith("bn"):
        mult, t = 1e9, t[:-2]
    elif t.endswith("m"):
        mult, t = 1e6, t[:-1]
    elif t.endswith("k"):
        mult, t = 1e3, t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return None


def club_link(name, club_id):
    if pd.isna(name):
        return None
    if pd.notna(club_id):
        return f"https://www.transfermarkt.com/-/startseite/verein/{int(club_id)}#{name}"
    search = "https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query="
    return f"{search}{quote(str(name))}#{name}"


@st.cache_data(ttl=3600)
def load_transfer_info(url):
    tr, _ = download_csv(url)
    tr["transfer_date"] = pd.to_datetime(tr["transfer_date"], errors="coerce")
    tr = tr.dropna(subset=["transfer_date"])
    tr = tr[tr["transfer_date"] <= pd.Timestamp.today()]
    names = tr["from_club_name"].astype(str) + " | " + tr["to_club_name"].astype(str)
    israel_ids = tr.loc[names.str.contains(ISRAEL_CLUBS), "player_id"].unique().tolist()
    last = tr.sort_values("transfer_date").groupby("player_id").tail(1)
    latest = pd.DataFrame({
        "player_id": last["player_id"].astype("Int64"),
        "Latest Club": last["to_club_name"],
        "Latest Club ID": last["to_club_id"].astype("Int64"),
        "Latest Transfer Date": last["transfer_date"],
    })
    return latest.reset_index(drop=True), israel_ids




@st.cache_data(ttl=21600, show_spinner=False)
def load_apify_players(token):
    api = "https://api.apify.com/v2"
    auth = {"Authorization": f"Bearer {token}"}
    actor = "data_xplorer~transfermarkt-api-scraper"
    res = requests.get(
        f"{api}/acts/{actor}/runs",
        params={"status": "SUCCEEDED", "desc": "true", "limit": 200},
        headers=auth,
        timeout=60,
    )
    if res.status_code != 200:
        raise RuntimeError(f"Runs list failed: {res.status_code} {res.text[:200]}")
    runs = res.json()["data"]["items"]
    rows = []
    seen = set()
    for run in runs:
        got = requests.get(
            f"{api}/datasets/{run['defaultDatasetId']}/items",
            params={"fields": "clubName,clubUrl,clubSquad", "clean": "true"},
            headers=auth,
            timeout=120,
        )
        if got.status_code == 402:
            raise RuntimeError("Apify data is locked (402): the monthly limit was exceeded. It resets on the 20th of the month.")
        if got.status_code != 200:
            continue
        data = got.json()
        if not isinstance(data, list):
            continue
        for club in data:
            club_match = re.search(r"/verein/(\d+)", str(club.get("clubUrl", "")))
            club_id = int(club_match.group(1)) if club_match else None
            for p in club.get("clubSquad") or []:
                match = re.search(r"/spieler/(\d+)", str(p.get("playerUrl", "")))
                if not match or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                rows.append({
                    "player_id": int(match.group(1)),
                    "A_Name": p.get("name"),
                    "A_Nat": " | ".join(p.get("nationalities") or []),
                    "A_Age": p.get("age"),
                    "A_Contract": p.get("contract"),
                    "A_Value": p.get("marketValue"),
                    "A_Pos": p.get("specificPosition"),
                    "A_Club": club.get("clubName"),
                    "A_ClubID": club_id,
                    "Scraped": run.get("finishedAt"),
                })
    return pd.DataFrame(rows), len(runs)


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
    df["Position"] = df["Sub Position"].map(POS_CODES)
    df["Foot"] = df["Foot"].astype(str).str.strip().str.lower().map(FOOT_CODES)
    df["player_id"] = raw["player_id"].astype("Int64")
    df = df.sort_values("Market Value (€)", ascending=False, na_position="last")
    return df.reset_index(drop=True), file_modified




try:
    with st.spinner("Loading players file..."):
        base, file_modified = load_players(data_url)
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

df = base.copy()
df["Club Name"] = df["Club"]
israel_ids = []

try:
    with st.spinner("Loading transfers file..."):
        latest, israel_ids = load_transfer_info(transfers_url)
    df = df.merge(latest, on="player_id", how="left")
    contract_col = next((c for c in df.columns if "contract" in c.lower()), None)
    under_contract = (pd.to_datetime(df[contract_col], errors="coerce") > pd.Timestamp.today()) if contract_col else False
    free_transfer = df["Latest Club"].astype(str).str.strip().str.lower().eq("without club")
    has_latest = df["Latest Club"].notna() & ~(free_transfer & under_contract & df["Club"].notna())
    df["Club Name"] = df["Latest Club"].where(has_latest, df["Club"])
    df["Club ID"] = df["Latest Club ID"].where(has_latest, df["Club ID"])
except Exception as e:
    st.warning(f"Could not load transfers file: {e}")
try:
    with st.spinner("Loading season stats..."):
        result = load_season_stats()
    stats = result[0] if isinstance(result, tuple) else result
    stats["player_id"] = stats["player_id"].astype("Int64")
    df = df.merge(stats, on="player_id", how="left")
except Exception as e:
    st.warning(f"Could not load season stats: {e}")
try:
    apify_token = st.secrets["APIFY_TOKEN"]
except Exception:
    apify_token = ""

apify_df = pd.DataFrame()
if apify_token:
    try:
        with st.spinner("Loading live squads from Apify (the first load can take a few minutes)..."):
            apify_df, apify_runs = load_apify_players(apify_token)
    except Exception as e:
        st.warning(f"Could not load Apify data: {e}")
else:
    st.warning("APIFY_TOKEN is missing, showing open data only")

df["Live"] = False
if not apify_df.empty:
    apify_df["player_id"] = apify_df["player_id"].astype("Int64")
    only = apify_df[~apify_df["player_id"].isin(df["player_id"])]
    df = df.merge(apify_df, on="player_id", how="left")
    df = pd.concat([df, only], ignore_index=True)
    scraped_dt = pd.to_datetime(df["Scraped"], errors="coerce", utc=True).dt.tz_localize(None)
    transfer_dt = pd.to_datetime(df.get("Latest Transfer Date"), errors="coerce")
    has_transfer = transfer_dt.notna()
    apify_newer = scraped_dt >= transfer_dt
    live = df["A_Club"].notna() & (~has_transfer | apify_newer)
    df["Live"] = live
    df["Name"] = df["Name"].where(df["Name"].notna(), df["A_Name"])
    df["Club ID"] = pd.to_numeric(df["Club ID"], errors="coerce").astype("Int64")
    a_club_id = pd.to_numeric(df["A_ClubID"], errors="coerce").astype("Int64")
    df["Club ID"] = a_club_id.where(live, df["Club ID"])
    df["Club Name"] = df["A_Club"].where(live, df["Club Name"])
    a_value = pd.to_numeric(df["A_Value"].map(parse_value), errors="coerce")
    df["Market Value (€)"] = a_value.combine_first(df["Market Value (€)"])
    a_contract = pd.to_datetime(df["A_Contract"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    df["Contract Expires"] = a_contract.where(a_contract.notna(), df["Contract Expires"])
    a_age = pd.to_numeric(df["A_Age"], errors="coerce").astype("Int64")
    df["Age"] = df["Age"].astype("Int64").where(df["Age"].notna(), a_age)
    df["Position"] = df["Position"].where(df["Position"].notna(), df["A_Pos"].map(POS_CODES))

for col in ("A_Nat", "Scraped"):
    if col not in df.columns:
        df[col] = pd.NA


def to_list(nat, primary):
    if isinstance(nat, str) and nat:
        return [x.strip() for x in nat.split("|") if x.strip()]
    return [primary] if isinstance(primary, str) and primary else []


nats = [to_list(a, p) for a, p in zip(df["A_Nat"], df["Citizenship"])]
lower = [[x.lower() for x in n] for n in nats]
births = df["Birth Country"].fillna("").astype(str).str.strip().str.lower().tolist()
df["Nationalities"] = [", ".join(n) for n in nats]
df["EU"] = ["YES" if any(x in EU for x in l) or b in EU else "NO" for l, b in zip(lower, births)]
df["Israeli"] = ["YES" if "israel" in l or b == "israel" else "NO" for l, b in zip(lower, births)]
df["African"] = [
    ", ".join(sorted({SSA_LOOKUP[x] for x in l + [b] if x in SSA_LOOKUP}))
    for l, b in zip(lower, births)
]
played = df["player_id"].isin(set(israel_ids)) | df["Club Name"].astype(str).str.contains(ISRAEL_CLUBS)
df["Played in Israel"] = played.map({True: "YES", False: "NO"})
df["In Israel Now"] = df["Club Name"].astype(str).str.contains(ISRAEL_CLUBS).map({True: "YES", False: "NO"})
df["Without Club"] = (df["Club Name"].isna() | df["Club Name"].astype(str).str.contains("without club", case=False, na=False)).map({True: "YES", False: "NO"})
df["Source"] = df["Live"].map({True: "Live (Apify)", False: "Open data"})
df["Transfermarkt"] = "https://www.transfermarkt.com/-/profil/spieler/" + df["player_id"].astype(str)
df["Club"] = [club_link(n, c) for n, c in zip(df["Club Name"], df["Club ID"])]
df = df.sort_values("Market Value (€)", ascending=False, na_position="last").reset_index(drop=True)



live_dates = pd.to_datetime(df["Scraped"], errors="coerce", utc=True).dropna()
if len(live_dates) > 0:
    newest = live_dates.max()
    days = (pd.Timestamp.now(tz="UTC") - newest).days
    note = (
        f"Live squads (Apify): {int(df['Live'].sum())} players, latest scrape "
        f"{newest.strftime('%d %b %Y')} ({days} days ago). Other players show open data "
        f"updated {pd.to_datetime(file_modified, utc=True, errors='coerce').strftime('%d %b %Y')}."
    )
    if days > 7:
        st.warning(note + " Re-run the club batches to refresh.")
    else:
        st.success(note)
else:
    st.warning("No live data loaded, showing the open dataset only. Updated: " + str(file_modified))

st.markdown(
    "<style>[data-testid='stSidebar'][aria-expanded='true'] {min-width: 380px;}</style>",
    unsafe_allow_html=True,
)
with st.expander("Debug: raw data columns"):
    raw_debug, _ = download_csv(data_url)
    st.write("Columns:", raw_debug.columns.tolist())
    codes = sorted(raw_debug["current_club_domestic_competition_id"].dropna().unique().tolist())
    st.write(f"Total competition codes: {len(codes)}")
    st.write(codes)

def ver(name):
    return st.session_state.get("v_" + name, 0)


def wkey(name):
    return f"{name}_{ver(name)}"


def bump(*names):
    for n in names:
        st.session_state["v_" + n] = ver(n) + 1


ALL_FILTERS = (
    "f_name", "f_club", "f_age", "f_", "f_pos", "f_value", "f_foot",
    "f_eu", "f_", "f_played", "f_inisrael", "f_without", "f_ssa", "f_ssa_countries",
)


def filter_header(label, *names):
    left, right = st.sidebar.columns([6, 1], vertical_alignment="center")
    left.write(label)
    right.button(
        ":material/close:", key="x_" + names[0], on_click=bump, args=names,
        type="tertiary", help="Reset this filter",
    )


st.sidebar.header("Filter Players")
st.sidebar.button("Reset all filters", key="x_all", on_click=bump, args=ALL_FILTERS)

filter_header("Search by name", "f_name")
search_name = st.sidebar.text_input(
    "Search by name", key=wkey("f_name"), label_visibility="collapsed"
)
filter_header("Search by club", "f_club")
search_club = st.sidebar.text_input(
    "Search by club", key=wkey("f_club"), label_visibility="collapsed"
)

ages = df["Age"].dropna()
age_range = None
if len(ages) > 0 and ages.min() < ages.max():
    age_min, age_max = int(ages.min()), int(ages.max())
    filter_header("Age Range", "f_age")
    age_cols = st.sidebar.columns(2)
    age_from = age_cols[0].number_input(
        "Min age", min_value=age_min, max_value=age_max, value=age_min,
        step=1, key=wkey("f_age") + "_min",
    )
    age_to = age_cols[1].number_input(
        "Max age", min_value=age_min, max_value=age_max, value=age_max,
        step=1, key=wkey("f_age") + "_max",
    )
age_range = (min(age_from, age_to), max(age_from, age_to))
heights = pd.to_numeric(df["Height (cm)"], errors="coerce") if "Height (cm)" in df.columns else pd.Series(dtype=float)
heights = heights[(heights >= 150) & (heights <= 220)].dropna()
height_range = None
if len(heights) > 0 and heights.min() < heights.max():
    h_min, h_max = int(heights.min()), int(heights.max())
    filter_header("Height (cm)", "f_height")
    h_cols = st.sidebar.columns(2)
    h_from = h_cols[0].number_input(
        "Min height", min_value=h_min, max_value=h_max, value=h_min,
        step=1, key=wkey("f_height") + "_min",
    )
    h_to = h_cols[1].number_input(
        "Max height", min_value=h_min, max_value=h_max, value=h_max,
        step=1, key=wkey("f_height") + "_max",
    )
    if h_from != h_min or h_to != h_max:
        height_range = (min(h_from, h_to), max(h_from, h_to))
filter_header("Position (empty = all)", "f_pos")
selected_positions = st.sidebar.multiselect(
    "Position (empty = all)", list(POS_CODES.values()),
    key=wkey("f_pos"), label_visibility="collapsed",
)

value_cap = int(df["Market Value (€)"].max()) if df["Market Value (€)"].notna().any() else 0
filter_header("Market value (€)", "f_value")
value_from = st.sidebar.number_input(
    "From", min_value=0, max_value=value_cap, value=0, step=100000,
    key=wkey("f_value") + "_from",
)
st.sidebar.caption(f"From: {value_from:,}")
value_to_text = st.sidebar.text_input(
    "To", value="", placeholder="No limit",
    key=wkey("f_value") + "_to",
)
_digits = value_to_text.replace(",", "").strip()
value_to = int(_digits) if _digits.isdigit() else value_cap

filter_header("Foot", "f_foot")
foot_choice = st.sidebar.radio(
    "Foot", ["All", "R", "L"], horizontal=True,
    key=wkey("f_foot"), label_visibility="collapsed",
)
filter_header("EU passport", "f_eu")
eu_choice = st.sidebar.radio(
    "EU passport", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_eu"), label_visibility="collapsed",
)
filter_header("Israeli", "f_israeli")
israeli_choice = st.sidebar.radio(
    "Israeli", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_israeli"), label_visibility="collapsed",
)
filter_header("Played in Israel", "f_played")
played_choice = st.sidebar.radio(
    "Played in Israel", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_played"), label_visibility="collapsed",
)
filter_header("In Israel Now", "f_inisrael")
inisrael_choice = st.sidebar.radio(
    "In Israel Now", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_inisrael"), label_visibility="collapsed",
)
filter_header("Without Club", "f_without")
without_choice = st.sidebar.radio(
    "Without Club", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_without"), label_visibility="collapsed",
)
filter_header("African", "f_ssa")
ssa_choice = st.sidebar.radio(
    "African", ["All", "YES", "NO"], horizontal=True,
    key=wkey("f_ssa"), label_visibility="collapsed",
)
filter_header("African countries (any of)", "f_ssa_countries")
ssa_countries = st.sidebar.multiselect(
    "African countries (any of)", list(SSA.keys()),
    key=wkey("f_ssa_countries"), label_visibility="collapsed",
)
st.sidebar.caption(
    "Israeli = Israeli citizenship or born in Israel. Played in Israel is estimated "
    "from club names. African = a sub-Saharan country by any citizenship or birth country"
)

mask = pd.Series(True, index=df.index)
mask &= ~df["Club Name"].astype(str).str.contains("retired|career break", case=False, na=False)
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
if played_choice != "All":
    mask &= df["Played in Israel"] == played_choice
if inisrael_choice != "All":
    mask &= df["In Israel Now"] == inisrael_choice
if without_choice != "All":
    mask &= df["Without Club"] == without_choice
if ssa_choice == "YES":
    mask &= df["African"] != ""
elif ssa_choice == "NO":
    mask &= df["African"] == ""
if ssa_countries:
    mask &= df["African"].apply(lambda s: any(c in s.split(", ") for c in ssa_countries))
if height_range:
    h_vals = pd.to_numeric(df["Height (cm)"], errors="coerce")
    mask &= h_vals.between(height_range[0], height_range[1])

df = df[mask]




st.write(f"Showing **{len(df)}** players:")

SHOW = [
    "Name", "Transfermarkt", "Age", "Height (cm)", "Position", "Foot", "Club",
    "Nationalities", "Market Value (€)",
    "Minutes Current", "Goals Current", "Assists Current",
    "Minutes Previous", "Goals Previous", "Assists Previous",
    "Contract Expires", "Agent",
    "Scraped", "Latest Transfer Date",
    "Source", "EU", "Israeli", "Played in Israel", "African",
]
display_df = df[[c for c in SHOW if c in df.columns]]

column_config = {
    "Latest Transfer Date": st.column_config.DateColumn("Latest Transfer Date", format="YYYY-MM-DD"),
    "Transfermarkt": st.column_config.LinkColumn("Transfermarkt", display_text="Open"),
    "Club": st.column_config.LinkColumn("Club", display_text=r"#(.*)$"),
    "Minutes Current": st.column_config.NumberColumn("Minutes (current season)", format="localized"),
    "Goals Current": st.column_config.NumberColumn("Goals (current season)"),
    "Assists Current": st.column_config.NumberColumn("Assists (current season)"),
    "Minutes Previous": st.column_config.NumberColumn("Minutes (previous season)", format="localized"),
    "Goals Previous": st.column_config.NumberColumn("Goals (previous season)"),
    "Assists Previous": st.column_config.NumberColumn("Assists (previous season)"),
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



API = "https://api.apify.com/v2"
ACTOR = "data_xplorer~transfermarkt-api-scraper"
AUTH = {"Authorization": f"Bearer {apify_token}"}

ISRAEL_LEAGUES = [
    "Hapoel Be'er Sheva", "Beitar Jerusalem", "Maccabi Tel Aviv", "Hapoel Tel Aviv",
    "Maccabi Haifa", "Hapoel Petah Tikva", "Maccabi Netanya", "Bnei Sakhnin",
    "Ironi Kiryat Shmona", "Hapoel Haifa", "Hapoel Katamon Jerusalem", "Ironi Tiberias",
    "Maccabi Petah Tikva", "Hapoel Ramat Gan Givatayim", "FC Ashdod",
    "Maccabi Bnei Reineh", "Maccabi Kiryat Gat", "Maccabi Akhi Nazareth",
    "Bnei Yehuda Tel Aviv", "FC Kiryat Yam", "Maccabi Jaffa", "Hapoel Rishon LeZion",
    "Hapoel Kfar Shalem", "FC Kafr Qasim", "Ironi Modi'in", "Hapoel Acre",
]

clubs = base.dropna(subset=["Club ID"]).drop_duplicates("Club ID")
club_urls = [f"https://www.transfermarkt.com/-/startseite/verein/{int(i)}" for i in clubs["Club ID"]]
club_batches = [club_urls[i:i + 100] for i in range(0, len(club_urls), 100)]


def run_options():
    opts = {}
    try:
        info = requests.get(f"{API}/acts/{ACTOR}", headers=AUTH, timeout=30).json()["data"]
        defaults = info.get("defaultRunOptions") or {}
        opts = {k: defaults[k] for k in ("build", "timeoutSecs", "memoryMbytes") if k in defaults}
    except Exception:
        pass
    opts["maxTotalChargeUsd"] = 1
    return opts


def run_debug_competition_test():
    st.divider()
    st.write("Testing all target leagues:")

    TARGET_LEAGUES = [
        ("Spain", "LaLiga", "https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1"),
        ("Spain", "LaLiga2", "https://www.transfermarkt.com/laliga2/startseite/wettbewerb/ES2"),
        ("Germany", "Bundesliga", "https://www.transfermarkt.com/bundesliga/startseite/wettbewerb/L1"),
        ("Germany", "2. Bundesliga", "https://www.transfermarkt.com/2-bundesliga/startseite/wettbewerb/L2"),
        ("France", "Ligue 1", "https://www.transfermarkt.com/ligue-1/startseite/wettbewerb/FR1"),
        ("France", "Ligue 2", "https://www.transfermarkt.com/ligue-2/startseite/wettbewerb/FR2"),
        ("Portugal", "Liga Portugal", "https://www.transfermarkt.com/liga-nos/startseite/wettbewerb/PO1"),
        ("Portugal", "Liga Portugal 2", "https://www.transfermarkt.com/liga-portugal-2/startseite/wettbewerb/PO2"),
        ("Netherlands", "Eredivisie", "https://www.transfermarkt.com/eredivisie/startseite/wettbewerb/NL1"),
        ("Netherlands", "Keuken Kampioen Divisie", "https://www.transfermarkt.com/keuken-kampioen-divisie/startseite/wettbewerb/NL2"),
        ("Belgium", "Jupiler Pro League", "https://www.transfermarkt.com/jupiler-pro-league/startseite/wettbewerb/BE1"),
        ("Belgium", "Challenger Pro League", "https://www.transfermarkt.com/challenger-pro-league/startseite/wettbewerb/BE2"),
        ("Turkey", "Super Lig", "https://www.transfermarkt.com/super-lig/startseite/wettbewerb/TR1"),
        ("Turkey", "1.Lig", "https://www.transfermarkt.com/1-lig/startseite/wettbewerb/TR2"),
        ("Greece", "Super League 1", "https://www.transfermarkt.com/super-league-1/startseite/wettbewerb/GR1"),
        ("Greece", "Super League 2", "https://www.transfermarkt.com/super-league-2-north/startseite/wettbewerb/GR22"),
        ("Italy", "Serie A", "https://www.transfermarkt.com/serie-a/startseite/wettbewerb/IT1"),
        ("Italy", "Serie B", "https://www.transfermarkt.com/serie-b/startseite/wettbewerb/IT2"),
        ("Sweden", "Allsvenskan", "https://www.transfermarkt.com/allsvenskan/startseite/wettbewerb/SE1"),
        ("Norway", "Eliteserien", "https://www.transfermarkt.com/eliteserien/startseite/wettbewerb/NO1"),
        ("Denmark", "Superliga", "https://www.transfermarkt.com/superliga/startseite/wettbewerb/DK1"),
        ("Finland", "Veikkausliiga", "https://www.transfermarkt.com/veikkausliiga/startseite/wettbewerb/FI1"),
        ("Morocco", "Botola Pro", "https://www.transfermarkt.com/botola-pro/startseite/wettbewerb/MAR1"),
        ("Egypt", "Egyptian Premier League", "https://www.transfermarkt.com/egyptian-premier-league/startseite/wettbewerb/EGY1"),
        ("Tunisia", "Ligue Professionnelle 1", "https://www.transfermarkt.com/ligue-professionnelle-1/startseite/wettbewerb/TUN1"),
        ("Algeria", "Ligue Professionnelle 1", "https://www.transfermarkt.com/ligue-professionnelle-1/startseite/wettbewerb/ALG1"),
        ("South Africa", "Premiership", "https://www.transfermarkt.com/dstv-premiership/startseite/wettbewerb/SFA1"),
        ("Brazil", "Serie A", "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1"),
        ("Argentina", "Liga Profesional", "https://www.transfermarkt.com/liga-profesional-argentina/startseite/wettbewerb/AR1N"),
        ("Colombia", "Liga Dimayor I", "https://www.transfermarkt.com/liga-dimayor-i/startseite/wettbewerb/COLP"),
        ("Chile", "Primera Division", "https://www.transfermarkt.com/primera-division/startseite/wettbewerb/CLPD"),
        ("Venezuela", "Liga FUTVE", "https://www.transfermarkt.com/liga-futve/startseite/wettbewerb/VEN1"),
        ("Ecuador", "LigaPro Serie A", "https://www.transfermarkt.com/ligapro-serie-a/startseite/wettbewerb/EL1A"),
        ("Bolivia", "Division Profesional", "https://www.transfermarkt.com/division-profesional/startseite/wettbewerb/BOL1"),
        ("Costa Rica", "Primera Division", "https://www.transfermarkt.com/primera-division-clausura/startseite/wettbewerb/CRPD"),
    ]

    if False and st.button("Test all target leagues (debug)"):
        results = []
        club_ids_by_league = {}
        progress = st.progress(0)
        for i, (country, league, url) in enumerate(TARGET_LEAGUES):
            status = None
            for attempt in range(3):
                try:
                    resp = requests.post(
                        f"{API}/acts/{ACTOR}/run-sync-get-dataset-items",
                        json={"scrapeType": "transfersCompetition", "items": [url]},
                        headers=AUTH,
                        timeout=120,
                    )
                except Exception as e:
                    status = f"Error: {e}"
                    break
                if resp.status_code in (200, 201):
                    data = resp.json()
                    clubs = data[0].get("clubs", []) if data else []
                    ids = []
                    for c in clubs:
                        m = re.search(r"/verein/(\d+)", str(c.get("clubUrl", "")))
                        if m:
                            ids.append(int(m.group(1)))
                    club_ids_by_league[(country, league)] = ids
                    status = "OK"
                    break
                elif resp.status_code == 403:
                    status = "HTTP 403"
                    time.sleep(5 * (attempt + 1))
                    continue
                else:
                    status = f"HTTP {resp.status_code}"
                    break
            results.append({
                "Country": country, "League": league, "Status": status,
                "Clubs": len(club_ids_by_league.get((country, league), [])),
            })
            time.sleep(2)
            progress.progress((i + 1) / len(TARGET_LEAGUES))
        all_ids = sorted({cid for ids in club_ids_by_league.values() for cid in ids})
        st.session_state["priority_club_ids"] = all_ids
        st.dataframe(results)
        st.write(f"Total clubs across working leagues: {sum(r['Clubs'] for r in results)}")
        st.write(f"Unique club IDs collected: {len(all_ids)}")


st.subheader("Admin: Apify updates")

with st.expander("Refresh and manual runs"):
    if not apify_token:
        st.error("APIFY_TOKEN is missing from the app secrets")
    else:
        if st.button("Refresh app data now"):
            st.cache_data.clear()
            st.rerun()
        st.caption("Reloads the newest Apify results into the table (also happens automatically every 6 hours).")
        run_debug_competition_test()
        club_text = st.text_area("Clubs to scrape now (one per line)", value="\n".join(ISRAEL_LEAGUES), height=200)
        if st.button("Scrape these clubs now"):
            items = [line.strip() for line in club_text.splitlines() if line.strip()]
            resp = requests.post(
                f"{API}/acts/{ACTOR}/runs",
                json={"scrapeType": "clubs", "items": items},
                headers=AUTH,
                timeout=60,
            )
            if resp.status_code in (200, 201):
                st.success(f"Started ({len(items)} clubs). It takes a few minutes, then press Refresh app data now.")
            else:
                st.error(f"Could not start: {resp.status_code} {resp.text[:300]}")
        st.divider()
        if st.button("Show all Apify runs (debug)"):
            runs_resp = requests.get(
                f"{API}/acts/{ACTOR}/runs",
                params={"limit": 100, "desc": "true"},
                headers=AUTH,
                timeout=60,
            )
            if runs_resp.status_code == 200:
                runs = runs_resp.json()["data"]["items"]
                rows = []
                for run in runs:
                    store_id = run.get("defaultKeyValueStoreId")
                    clubs = []
                    if store_id:
                        input_resp = requests.get(
                            f"{API}/key-value-stores/{store_id}/records/INPUT",
                            headers=AUTH,
                            timeout=30,
                        )
                        if input_resp.status_code == 200:
                            clubs = input_resp.json().get("items", [])
                    rows.append({
                        "Started": run.get("startedAt"),
                        "Finished": run.get("finishedAt"),
                        "Status": run.get("status"),
                        "Clubs count": len(clubs),
                        "Clubs": ", ".join(clubs),
                    })
                st.dataframe(rows)
            else:
                st.error(f"Could not list runs: {runs_resp.status_code} {runs_resp.text[:300]}")
