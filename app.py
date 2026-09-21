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


def download_csv(url):
    res = requests.get(url, headers=HEADERS, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"Server returned status {res.status_code}")
    content = res.content
    compression = "gzip" if content[:2] == b"\x1f\x8b" else None
    return pd.read_csv(io.BytesIO(content), compression=compression), res.headers




SSA = {
    "Angola": [], "Benin": [], "Botswana": [], "Burkina Faso": [], "Burundi": [],
    "Cameroon": [], "Cape Verde": ["cabo verde"], "Central African Republic": [],
    "Chad": [], "Comoros": [], "Congo": ["republic of the congo"],
    "DR Congo": ["congo dr", "democratic republic of the congo"],
    "Cote d'Ivoire": ["ivory coast", "c\u00f4te d'ivoire"], "Djibouti": [],
    "Equatorial Guinea": [], "Eritrea": [], "Eswatini": ["swaziland"], "Ethiopia": [],
    "Gabon": [], "Gambia": ["the gambia"], "Ghana": [], "Guinea": [],
    "Guinea-Bissau": [], "Kenya": [], "Lesotho": [], "Liberia": [], "Madagascar": [],
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
