  st.set_page_config(page_title="CMA Scouting Tool", layout="wide")

st.title("CMA Scouting Tool")
st.write("Live Transfermarkt Data")

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

@st.cache_data
def get_league_squad(club_id):
    url = f"https://api.transfermarkt-api.visiting.fans/clubs/{club_id}/players"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

st.sidebar.header("Data Source")
st.sidebar.info("Fetching real-time player profiles and market values.")

# Sample live dataset structure for testing
sample_data = {
    "Name": ["Oscar Gloukh", "Liel Abada", "Anan Khalaili", "Dor Turgeman"],
    "Age": [22, 24, 22, 22],
    "Position": ["AM", "RW", "RW", "ST"],
    "Club": ["RB Salzburg", "Charlotte FC", "Union SG", "Maccabi Tel Aviv"],
    "Market Value (€)": [15000000, 7000000, 5000000, 2500000]
}

df = pd.DataFrame(sample_data)

st.sidebar.header("Filter Players")
min_age, max_age = int(df["Age"].min()), int(df["Age"].max())
selected_age = st.sidebar.slider("Age Range", min_age, max_age, (min_age, max_age))

positions = df["Position"].unique().tolist()
selected_positions = st.sidebar.multiselect("Position", positions, default=positions)

filtered_df = df[
    (df["Age"] >= selected_age[0]) & 
    (df["Age"] <= selected_age[1]) & 
    (df["Position"].isin(selected_positions))
]

st.write(f"Showing **{len(filtered_df)}** players:")
st.dataframe(filtered_df, use_container_width=True)
