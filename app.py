# SDG Progress Monitor (India + Peers) — Overview + Drilldown + Definitions + Data tabs
# Data sources: World Bank WDI (subset via data/sdg_catalogue.csv) OR UN SDG (ALL sub-indicators)
# Python 3.8+; deps: streamlit, requests, pandas, plotly

from __future__ import annotations
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import plotly.express as px

# ------------------------------------------------------------
# Page meta
# ------------------------------------------------------------
st.set_page_config(
    page_title="SDG Progress Monitor",
    page_icon="🎯",
    layout="wide",
)

# ------------------------------------------------------------
# Constants & dictionaries
# ------------------------------------------------------------
DEFAULT_COUNTRY = "IND"  # India
BASELINE_YEAR = 2015
TARGET_YEAR = 2030

COUNTRY_LABELS: Dict[str, str] = {
    "IND": "India", "CHN": "China", "USA": "United States", "BGD": "Bangladesh",
    "PAK": "Pakistan", "LKA": "Sri Lanka", "NPL": "Nepal", "BRA": "Brazil",
    "RUS": "Russia", "ZAF": "South Africa", "IDN": "Indonesia", "MEX": "Mexico",
    "TUR": "Türkiye", "GBR": "United Kingdom", "DEU": "Germany", "FRA": "France",
    "JPN": "Japan", "VNM": "Vietnam",
}
PEER_PRESETS: Dict[str, List[str]] = {
    "SAARC": ["BGD", "PAK", "LKA", "NPL"],
    "BRICS": ["BRA", "RUS", "CHN", "ZAF"],
    "G20 sample": ["USA", "CHN", "JPN", "DEU", "GBR", "FRA"],
}

SDG_NAMES = {
    1: "No Poverty", 2: "Zero Hunger", 3: "Good Health & Well-Being", 4: "Quality Education",
    5: "Gender Equality", 6: "Clean Water & Sanitation", 7: "Affordable & Clean Energy",
    8: "Decent Work & Economic Growth", 9: "Industry, Innovation & Infrastructure",
    10: "Reduced Inequalities", 11: "Sustainable Cities & Communities",
    12: "Responsible Consumption & Production", 13: "Climate Action",
    14: "Life Below Water", 15: "Life On Land", 16: "Peace, Justice & Strong Institutions",
    17: "Partnerships for the Goals",
}

def sdg_icon_url(goal: int, language: str = "en", high_contrast: bool = False) -> str:
    """
    SDG icons via Open SDG translations CDN (informational use).
    https://open-sdg.github.io/sdg-translations/
    """
    base = "https://open-sdg.github.io/sdg-translations/assets/img"
    return f"{base}/{'high-contrast/' if high_contrast else ''}goals/{language}/{goal}.png"

# ------------------------------------------------------------
# Data-driven SDG catalogue for WDI subset
# ------------------------------------------------------------
CATALOG_PATH = Path("data/sdg_catalogue.csv")

def _fallback_catalogue() -> pd.DataFrame:
    """Small built-in seed so the app still runs if CSV not present."""
    data = [
        [1, "No Poverty", "1.1", "Poverty headcount (<$3.00, 2021 PPP) (% pop)", "SI.POV.DDAY", "%", "down", 0],
        [2, "Zero Hunger", "2.1", "Undernourishment (% pop)", "SN.ITK.DEFC.ZS", "%", "down", ""],
        [3, "Good Health & Well-Being", "3.1", "Maternal mortality (per 100k)", "SH.STA.MMRT", "", "down", 70],
        [3, "Good Health & Well-Being", "3.2", "Infant mortality (per 1,000)", "SP.DYN.IMRT.IN", "", "down", ""],
        [4, "Quality Education", "4.1", "Primary net enrollment (%)", "SE.PRM.NENR", "%", "up", 100],
        [6, "Clean Water & Sanitation", "6.1", "Basic drinking water (% pop)", "SH.H2O.BASW.ZS", "%", "up", 100],
        [6, "Clean Water & Sanitation", "6.2", "Basic sanitation (% pop)", "SH.STA.BASS.ZS", "%", "up", 100],
        [7, "Affordable & Clean Energy", "7.1", "Access to electricity (% pop)", "EG.ELC.ACCS.ZS", "%", "up", 100],
        [7, "Affordable & Clean Energy", "7.2", "Renewable energy (% of TFEC)", "EG.FEC.RNEW.ZS", "%", "up", ""],
        [8, "Decent Work & Economic Growth", "8.5", "Unemployment (% labor force)", "SL.UEM.TOTL.ZS", "%", "down", ""],
        [9, "Industry, Innovation & Infrastructure", "9.2", "Manufacturing VA (% of GDP)", "NV.IND.MANF.ZS", "%", "up", ""],
        [9, "Industry, Innovation & Infrastructure", "9.c", "Mobile subs (per 100 people)", "IT.CEL.SETS.P2", "", "up", ""],
    ]
    df = pd.DataFrame(data, columns=["goal","goal_name","target","series_label","wb_code","unit","better","target2030"])
    df["goal"] = df["goal"].astype(int)
    df["target2030"] = pd.to_numeric(df["target2030"], errors="coerce")
    return df

@st.cache_data(show_spinner=False, ttl=None)
def load_sdg_catalogue() -> pd.DataFrame:
    if CATALOG_PATH.exists():
        df = pd.read_csv(CATALOG_PATH, dtype=str).fillna("")
        df["goal"] = df["goal"].astype(int)
        df["target2030"] = pd.to_numeric(df["target2030"], errors="coerce")
        return df
    return _fallback_catalogue()

def indicators_for_goal(df_catalog: pd.DataFrame, goal_label: str) -> List[Dict[str, object]]:
    try:
        goal_no = int(goal_label.split()[1])
    except Exception:
        goal_no = 1
    rows = df_catalog[df_catalog["goal"] == goal_no].sort_values(["target", "series_label"])
    out: List[Dict[str, object]] = []
    for _, r in rows.iterrows():
        out.append({
            "code": r["wb_code"],                      # may be blank if not in WDI
            "name": r["series_label"],
            "better": r["better"] or "up",
            "target2030": None if pd.isna(r["target2030"]) else r["target2030"],
            "unit": r["unit"],
            "target": r["target"],
        })
    return out

# ------------------------------------------------------------
# World Bank API helpers (cached + retry)
# ------------------------------------------------------------
WB_BASE = "https://api.worldbank.org/v2"

def _safe_get(url: str, params: dict, retries: int = 3, backoff: float = 0.6):
    last_exc = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            time.sleep(backoff * (2 ** i))
    raise last_exc

@st.cache_data(show_spinner=False, ttl=3600)
def wb_fetch(indicator: str, iso3_list: List[str]) -> pd.DataFrame:
    """Fetch indicator for a ; separated list of countries."""
    countries = ";".join(iso3_list)
    url = f"{WB_BASE}/country/{countries}/indicator/{indicator}"
    params = {"format": "json", "per_page": 20000}
    rows: List[Dict[str, object]] = []
    page = 1
    while True:
        params["page"] = page
        data = _safe_get(url, params).json()
        if not isinstance(data, list) or len(data) < 2:
            break
        meta, obs = data[0], data[1]
        for d in obs:
            rows.append({
                "country": d.get("country", {}).get("value"),
                "iso3": d.get("countryiso3code"),
                "date": pd.to_numeric(d.get("date"), errors="coerce"),
                "value": pd.to_numeric(d.get("value"), errors="coerce"),
                "indicator": indicator,
            })
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    df = pd.DataFrame(rows).dropna(subset=["date"])
    if not df.empty:
        df["country"] = df["iso3"].map(COUNTRY_LABELS).fillna(df["country"])
        df = df.sort_values(["iso3", "date"])
    return df

def latest_value(df: pd.DataFrame, iso3: str) -> Tuple[Optional[int], Optional[float]]:
    sub = df[df["iso3"] == iso3].dropna(subset=["value"]).sort_values("date")
    if sub.empty:
        return None, None
    row = sub.iloc[-1]
    return int(row["date"]), float(row["value"])

def value_at_or_after(df: pd.DataFrame, iso3: str, year: int) -> Tuple[Optional[int], Optional[float]]:
    sub = df[(df["iso3"] == iso3) & (df["date"] >= year)].dropna(subset=["value"]).sort_values("date")
    if sub.empty:
        return None, None
    row = sub.iloc[0]
    return int(row["date"]), float(row["value"])

def progress_status(baseline: float, latest: float, latest_year: int,
                    target: Optional[float], better: str) -> Tuple[str, Optional[float]]:
    """Return (status label, progress ratio 0..1+ or None). Heuristic pace vs. target."""
    if latest_year is None or latest_year <= BASELINE_YEAR:
        return ("insufficient data", None)
    if target is None or target == "":
        return ("trend only", None)

    years_done = max(1, latest_year - BASELINE_YEAR)
    years_total = max(1, TARGET_YEAR - BASELINE_YEAR)

    if better == "up":
        req_rate = (target - baseline) / years_total
        act_rate = (latest - baseline) / years_done
        progress = (latest - baseline) / (target - baseline) if (target - baseline) else None
    else:
        req_rate = (baseline - target) / years_total
        act_rate = (baseline - latest) / years_done
        progress = (baseline - latest) / (baseline - target) if (baseline - target) else None

    if progress is None or any(map(lambda x: x is None or (isinstance(x, float) and math.isnan(x)), [req_rate, act_rate])):
        return ("trend only", None)

    pace = act_rate / req_rate if req_rate not in (0, None) else 0.0
    if pace >= 1.0:
        return ("🟢 on track", progress)
    if pace >= 0.5:
        return ("🟠 needs acceleration", progress)
    return ("🔴 off track", progress)

def fmt(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{x:,.2f}"

def _get_qp_val(qp, key: str) -> Optional[str]:
    if key not in qp:
        return None
    v = qp[key]
    return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)

# ------------------------------------------------------------
# WDI metadata helpers (for Definitions tab)
# ------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=86400)
def wb_indicator_meta(code: str) -> dict:
    """Fetch WDI indicator metadata: name, unit, definition (sourceNote), source."""
    if not code:
        return {}
    try:
        r = requests.get(f"{WB_BASE}/indicator/{code}", params={"format": "json"}, timeout=20)
        r.raise_for_status()
        js = r.json()
        meta = (js[1][0] if isinstance(js, list) and len(js) > 1 and js[1] else {}) or {}
        return {
            "id": meta.get("id") or code,
            "name": meta.get("name") or meta.get("value") or code,
            "unit": meta.get("unit") or "",
            "sourceNote": meta.get("sourceNote") or "",
            "sourceOrganization": meta.get("sourceOrganization") or "",
            "source": (meta.get("source") or {}).get("value", ""),
        }
    except Exception:
        return {}

def _short(text: str, n: int = 320) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"

# ------------------------------------------------------------
# UN SDG API helpers (Goals/Targets/Indicators/Series + timeseries)
# ------------------------------------------------------------
UN_API = "https://unstats.un.org/SDGAPI/v1/sdg"
UN_SDMX_BASE = "https://data.un.org/ws/rest/data/IAEG-SDGs,DF_SDG_GLH"

# Minimal M49 mapping for common peers; live fallback available
M49_LOCAL = {
    "IND": 356, "BGD": 50, "PAK": 586, "LKA": 144, "NPL": 524,
    "CHN": 156, "USA": 840, "BRA": 76, "RUS": 643, "ZAF": 710,
    "IDN": 360, "MEX": 484, "TUR": 792, "GBR": 826, "DEU": 276,
    "FRA": 250, "JPN": 392, "VNM": 704,
}

@st.cache_data(show_spinner=False, ttl=86400)
def iso3_to_m49(iso3: str) -> Optional[int]:
    """Map ISO3 to UN M49. Try local dict, then fall back to restcountries (ccn3)."""
    iso3 = (iso3 or "").upper()
    if iso3 in M49_LOCAL:
        return M49_LOCAL[iso3]
    try:
        r = requests.get(f"https://restcountries.com/v3.1/alpha/{iso3}", timeout=20)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, list) and js and "ccn3" in js[0] and js[0]["ccn3"]:
            m = int(js[0]["ccn3"])
            M49_LOCAL[iso3] = m
            return m
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=86400)
def un_goals() -> List[dict]:
    r = requests.get(f"{UN_API}/Goal/List", timeout=30)
    r.raise_for_status()
    return sorted(r.json(), key=lambda x: int(x["code"]))

@st.cache_data(show_spinner=False, ttl=86400)
def un_targets(goal_code: str) -> List[dict]:
    r = requests.get(f"{UN_API}/Target/List", params={"goal": goal_code}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return sorted(rows, key=lambda x: x["code"])

@st.cache_data(show_spinner=False, ttl=86400)
def un_indicators(target_code: str) -> List[dict]:
    r = requests.get(f"{UN_API}/Indicator/List", params={"target": target_code}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return sorted(rows, key=lambda x: x["code"])

@st.cache_data(show_spinner=False, ttl=86400)
def un_series(indicator_code: str) -> List[dict]:
    r = requests.get(f"{UN_API}/Series/List", params={"indicator": indicator_code}, timeout=30)
    r.raise_for_status()
    rows = r.json()
    return sorted(rows, key=lambda x: x.get("code",""))

def _un_series_data_via_series_api(series_code: str, area_m49: int, yr1: int, yr2: int) -> pd.DataFrame:
    """Use simple Series/Data endpoint when available."""
    try:
        p = {"seriesCode": series_code, "area": area_m49, "timePeriod": f"{yr1}-{yr2}"}
        r = requests.get(f"{UN_API}/Series/Data", params=p, timeout=30)
        r.raise_for_status()
        js = r.json()
        items = js if isinstance(js, list) else js.get("data", [])
        recs = []
        for it in items:
            t = it.get("timePeriod")
            v = it.get("value")
            if t is None or v in (None, ""):
                continue
            recs.append({"date": int(t), "value": float(v)})
        return pd.DataFrame(recs)
    except Exception:
        return pd.DataFrame()

def _score_series_key(series_dims: List[dict], key: str) -> int:
    """Heuristic: prefer totals/national/both sexes slices."""
    idx = list(map(int, key.split(":"))) if key else []
    score = 0
    total_tokens = ("T", "TOTAL", "TOTL", "ALL", "BTSX", "ALLAREA", "ALLAGE")
    for pos, dim in enumerate(series_dims or []):
        if pos >= len(idx): break
        valmeta = dim["values"][idx[pos]]
        valid = str(valmeta.get("id", "")).upper()
        valname = str(valmeta.get("name", "")).upper()
        if any(tok in valid for tok in total_tokens) or any(tok in valname for tok in total_tokens):
            score += 2
        did = dim.get("id","").upper()
        if did == "REPORTING_TYPE" and valid in ("G","NAT","NATIONAL"):
            score += 3
    return score

def _un_series_data_via_sdmx(series_code: str, area_m49: int, yr1: int, yr2: int) -> pd.DataFrame:
    """
    SDMX fallback: query DF_SDG_GLH by SERIES + REF_AREA + annual freq.
    Pick the 'best' disaggregation (totals) using a simple score.
    """
    try:
        key = f"{series_code}.{area_m49}.A"
        params = {"time": f"{yr1}:{yr2}", "contentType": "json"}
        url = f"{UN_SDMX_BASE}/{key}"
        r = requests.get(url, params=params, timeout=40)
        r.raise_for_status()
        js = r.json()

        ds = js.get("dataSets", [{}])[0]
        sers = ds.get("series", {})
        if not sers:
            return pd.DataFrame()

        series_dims = js["structure"]["dimensions"].get("series", [])
        obs_dims = js["structure"]["dimensions"].get("observation", [])
        # find time dimension index
        time_pos = None
        for i, d in enumerate(obs_dims):
            if d["id"].upper().startswith("TIME"):
                time_pos = i
                break
        if time_pos is None:
            return pd.DataFrame()
        time_values = obs_dims[time_pos]["values"]

        # choose best series key
        best_key, best_score = None, -1
        for k, ser in sers.items():
            score = _score_series_key(series_dims, k)
            if score > best_score and ser.get("observations"):
                best_key, best_score = k, score
        if best_key is None:
            return pd.DataFrame()
        observations = sers[best_key].get("observations", {})
        recs = []
        for k, val in observations.items():
            idx = list(map(int, k.split(":")))
            t_idx = idx[time_pos]
            year = int(time_values[t_idx]["id"])
            v = val[0]
            if v is None:
                continue
            recs.append({"date": year, "value": float(v)})
        return pd.DataFrame(recs)
    except Exception:
        return pd.DataFrame()

def un_fetch_series_timeseries(series_code: str, iso3_list: List[str], yr1: int, yr2: int) -> pd.DataFrame:
    """Return tidy df: country, iso3, date, value (one UN Series code at a time)."""
    frames = []
    for iso in iso3_list:
        a = iso3_to_m49(iso)
        if not a:
            continue
        df = _un_series_data_via_series_api(series_code, a, yr1, yr2)
        if df.empty:
            df = _un_series_data_via_sdmx(series_code, a, yr1, yr2)
        if not df.empty:
            df["iso3"] = iso
            df["country"] = COUNTRY_LABELS.get(iso, iso)
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ------------------------------------------------------------
# UI helpers — ALWAYS show all 17 goals in the selector
# ------------------------------------------------------------
def goal_labels_all_17() -> List[str]:
    return [f"SDG {i} · {SDG_NAMES[i]}" for i in range(1, 18)]

# ------------------------------------------------------------
# Sidebar — form-based controls (best-practice: fewer reruns)
# ------------------------------------------------------------
def init_defaults(catalog: pd.DataFrame):
    if "controls" not in st.session_state:
        goal_labels = goal_labels_all_17()
        st.session_state.controls = {
            "goal": goal_labels[0] if goal_labels else "SDG 1 · No Poverty",
            "preset": "SAARC",
            "manual_peers": ["BGD", "PAK", "LKA", "NPL"],
            "yr1": 2000,
            "yr2": datetime.now().year,
            "log_y": False,
            "smooth3": False,
            "theme": "Light",
            "show_table": False,
            "search": "",
            "data_src": "World Bank (WDI subset)",
        }
        # hydrate from URL
        qp = st.query_params
        if qp:
            goal = _get_qp_val(qp, "goal")
            peers = _get_qp_val(qp, "peers")
            yr1 = _get_qp_val(qp, "yr1")
            yr2 = _get_qp_val(qp, "yr2")
            theme = _get_qp_val(qp, "theme")
            if goal:
                st.session_state.controls["goal"] = goal
            if yr1:
                try: st.session_state.controls["yr1"] = max(1990, min(datetime.now().year, int(yr1)))
                except Exception: pass
            if yr2:
                try: st.session_state.controls["yr2"] = max(1990, min(datetime.now().year, int(yr2)))
                except Exception: pass
            if theme and theme.lower() in ("light", "dark"):
                st.session_state.controls["theme"] = "Dark" if theme.lower()=="dark" else "Light"
            if peers:
                iso_list = [p.strip() for p in peers.split(",") if p.strip()]
                st.session_state.controls["manual_peers"] = [p for p in iso_list if p != DEFAULT_COUNTRY]

def controls_form(catalog: pd.DataFrame) -> dict:
    init_defaults(catalog)
    c = st.session_state.controls
    goal_labels = goal_labels_all_17()

    with st.sidebar:
        st.header("Controls")
        with st.form("sdg_controls", clear_on_submit=False):
            src = st.radio("Data source", ["World Bank (WDI subset)", "UN SDG (ALL)"],
                           index=0 if c["data_src"].startswith("World Bank") else 1)
            goal = st.selectbox("Goal", goal_labels,
                                index=goal_labels.index(c["goal"]) if c["goal"] in goal_labels else 0)
            preset = st.selectbox("Peer preset", list(PEER_PRESETS.keys()),
                                  index=list(PEER_PRESETS.keys()).index(c["preset"]))
            all_peers = sorted(set(sum(PEER_PRESETS.values(), [])) | set(["USA","CHN","BRA","ZAF","IDN","VNM"]))
            manual_peers = st.multiselect("Peers (ISO-3, India is always included)", options=all_peers,
                                          default=c["manual_peers"])
            yr1, yr2 = st.slider("Year range", min_value=1990, max_value=datetime.now().year,
                                 value=(c["yr1"], c["yr2"]), step=1)
            log_y = st.toggle("Log scale (y-axis)", value=c["log_y"])
            smooth3 = st.toggle("3-year smoothing overlay", value=c["smooth3"])
            theme = st.selectbox("Chart theme", ["Light", "Dark"], index=0 if c["theme"]=="Light" else 1)
            show_table = st.toggle("Show data table in Drilldown", value=c["show_table"])
            search = st.text_input("Search indicators (WDI Drilldown)", value=c["search"])
            apply_btn = st.form_submit_button("Apply")

        co1, co2 = st.columns(2)
        with co1:
            if st.button("Reset"):
                st.session_state.controls = {
                    "goal": goal_labels[0],
                    "preset": "SAARC",
                    "manual_peers": ["BGD", "PAK", "LKA", "NPL"],
                    "yr1": 2000, "yr2": datetime.now().year,
                    "log_y": False, "smooth3": False, "theme": "Light",
                    "show_table": False, "search": "", "data_src": "World Bank (WDI subset)",
                }
                st.rerun()
        with co2:
            if st.button("Permalink"):
                peers_iso = list(dict.fromkeys(PEER_PRESETS[c["preset"]] + c["manual_peers"]))  # dedupe keep order
                params = {
                    "goal": c["goal"], "peers": ",".join(peers_iso),
                    "yr1": c["yr1"], "yr2": c["yr2"], "theme": c["theme"].lower(),
                }
                st.query_params = params
                st.toast("URL updated with your selection. Copy it from the address bar.", icon="🔗")

    if apply_btn:
        st.session_state.controls = {
            "goal": goal, "preset": preset, "manual_peers": manual_peers,
            "yr1": yr1, "yr2": yr2, "log_y": log_y, "smooth3": smooth3,
            "theme": theme, "show_table": show_table, "search": search,
            "data_src": src,
        }
        c = st.session_state.controls
    return c

# ------------------------------------------------------------
# Main layout: Overview • Drilldown • Definitions • Data/Sources
# ------------------------------------------------------------
CATALOG = load_sdg_catalogue()
controls = controls_form(CATALOG)
goal = controls["goal"]
preset = controls["preset"]
manual_peers = controls["manual_peers"]
yr1, yr2 = controls["yr1"], controls["yr2"]
log_y, smooth3 = controls["log_y"], controls["smooth3"]
template = "plotly_dark" if controls["theme"] == "Dark" else "plotly"
show_table = controls["show_table"]
search_q = (controls["search"] or "").strip().lower()
data_src = controls.get("data_src", "World Bank (WDI subset)")

tab_overview, tab_drill, tab_defs, tab_data = st.tabs(["Overview", "Drilldown", "Definitions", "Data & Sources"])

# ------------------------------------------------------------
# Overview (WDI-based, goal-level summary)
# ------------------------------------------------------------
with tab_overview:
    # Hero with SDG icon (spaced)
    try:
        sdg_no = int(goal.split()[1])
    except Exception:
        sdg_no = 1
    c1, c2 = st.columns([1, 5], gap="large")
    with c1:
        st.image(sdg_icon_url(sdg_no), width=128)
    with c2:
        st.markdown(f"<h1 style='margin:0'>{goal}</h1>", unsafe_allow_html=True)
        st.caption(f"Baseline: {BASELINE_YEAR} · Target year: {TARGET_YEAR} · India + peers")

    # Build country list
    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))
    ind_cfgs = indicators_for_goal(CATALOG, goal)

    # Fetch data for all indicators with a WDI code
    with st.spinner("Fetching World Bank data…"):
        df_map: Dict[str, pd.DataFrame] = {}
        for cfg in ind_cfgs:
            code = (cfg.get("code") or "").strip()
            if not code:
                continue
            df_map[code] = wb_fetch(code, countries)

    # India quick status table
    st.markdown("### 🇮🇳 India — Quick status")
    header = st.columns([2.8, 1.2, 1.2, 1.6, 1.8])
    header[0].markdown("**Indicator**")
    header[1].markdown(f"**Baseline {BASELINE_YEAR}**")
    header[2].markdown("**Latest**")
    header[3].markdown("**Δ since baseline**")
    header[4].markdown("**2030 check**")

    any_row = False
    for cfg in ind_cfgs:
        code = (cfg.get("code") or "").strip()
        df_i = df_map.get(code, pd.DataFrame())
        if df_i.empty:
            continue
        b_y, b_v = value_at_or_after(df_i, DEFAULT_COUNTRY, BASELINE_YEAR)
        l_y, l_v = latest_value(df_i, DEFAULT_COUNTRY)
        dv = (l_v - b_v) if (b_v is not None and l_v is not None) else None
        status, prog = ("—", None)
        if b_v is not None and l_v is not None:
            status, prog = progress_status(b_v, l_v, l_y, cfg.get("target2030"), cfg["better"])

        c0, c1, c2, c3, c4 = st.columns([2.8, 1.2, 1.2, 1.6, 1.8])
        c0.markdown(f"**{cfg['name']}**  \n`{code}`")
        c1.write(fmt(b_v))
        c2.write(f"{fmt(l_v)}{' (' + str(l_y) + ')' if l_y else ''}")
        c3.write(fmt(dv) if dv is not None else "—")
        if prog is None:
            c4.write(status)
        else:
            c4.write(status)
            c4.progress(min(max(prog, 0.0), 1.0))
        any_row = True

    if not any_row:
        st.info("No World Bank/WDI series found for this goal in the current catalog. "
                "Add or map more indicators in `data/sdg_catalogue.csv`.")

    # Peer snapshot mini-charts (latest values)
    st.markdown("### Peer snapshot (latest available)")
    for cfg in ind_cfgs:
        code = (cfg.get("code") or "").strip()
        df_i = df_map.get(code, pd.DataFrame())
        if df_i.empty:
            continue
        latest_vals = (
            df_i.dropna(subset=["value"])
               .sort_values(["country", "date"])
               .groupby("country", as_index=False).tail(1)
               .sort_values("value", ascending=(cfg["better"] == "down"))
        )
        if latest_vals.empty:
            continue
        st.markdown(f"**{cfg['name']}**  ·  `{code}`")
        fig = px.bar(latest_vals, x="country", y="value", template=template)
        if log_y:
            fig.update_yaxes(type="log")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=0), height=300)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# Drilldown (WDI subset OR UN SDG ALL)
# ------------------------------------------------------------
with tab_drill:
    st.subheader("Drilldown by indicator")
    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))

    if data_src == "World Bank (WDI subset)":
        # WDI path (catalog-driven)
        ind_all = indicators_for_goal(CATALOG, goal)
        ind_cfgs = [c for c in ind_all if search_q in str(c.get("name","")).lower()] if search_q else ind_all
        if not ind_cfgs:
            st.info("No indicators match your search for this goal.")
            st.stop()

        options = [f"{c['name']} [{(c.get('code') or '—')}]" for c in ind_cfgs]
        ind_label = st.selectbox("Indicator (WDI)", options, index=0)
        code = ind_label.split("[")[-1].strip("]").strip()

        if code in ("—", ""):
            st.info("This series has no WDI code in the catalog. Switch to **UN SDG (ALL)** to browse the full list.")
            st.stop()

        df = wb_fetch(code, countries)
        df = df[(df["date"] >= yr1) & (df["date"] <= yr2)]
        if df.empty:
            st.info("No data available for this selection.")
            st.stop()

        fig = px.line(df, x="date", y="value", color="country",
                      labels={"date":"Year", "value": ind_label}, template=template, markers=True)
        if smooth3:
            smoothed = (
                df.sort_values(["country","date"])
                  .groupby("country", as_index=False)
                  .apply(lambda g: g.assign(value_smooth=g["value"].rolling(window=3, min_periods=1).mean()))
                  .reset_index(drop=True)
            )
            fig2 = px.line(smoothed, x="date", y="value_smooth", color="country", template=template)
            for tr in fig2.data:
                tr.update(line=dict(dash="dash"))
                fig.add_trace(tr)
        if log_y: fig.update_yaxes(type="log")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=0), height=460)
        st.plotly_chart(fig, use_container_width=True)

        # KPIs for India
        l_y, l_v = latest_value(df, DEFAULT_COUNTRY)
        b_y, b_v = value_at_or_after(df, DEFAULT_COUNTRY, BASELINE_YEAR)
        dv = (l_v - b_v) if (b_v is not None and l_v is not None) else None
        k1, k2, k3 = st.columns(3)
        k1.metric("India latest", f"{fmt(l_v)}", f"Year {l_y if l_y else '—'}")
        k2.metric("Baseline", f"{fmt(b_v)}", f"Year {BASELINE_YEAR}")
        k3.metric("Δ since baseline", f"{fmt(dv)}" if dv is not None else "—")

        if show_table:
            with st.expander("See data"):
                st.dataframe(df.sort_values(["country","date"]).reset_index(drop=True),
                             use_container_width=True, height=360)

    else:
        # UN SDG ALL path (Goal → Target → Indicator → Series)
        st.markdown("Browse the **full** UN SDG hierarchy. Pick a *Series* to plot (when available).")

        # UN Goals (1..17); align default with selected WDI goal
        goals = un_goals()
        goal_codes = [g["code"] for g in goals]
        goal_titles = [f"SDG {g['code']} · {g['title']}" for g in goals]
        default_goal_num = str(int(goal.split()[1])) if goal.startswith("SDG ") else "1"
        g_sel = st.selectbox("Goal (UN SDG)", goal_titles,
                             index=goal_codes.index(default_goal_num) if default_goal_num in goal_codes else 0)
        g_code = goals[goal_titles.index(g_sel)]["code"]

        # Targets
        trgs = un_targets(g_code)
        if not trgs:
            st.info("No targets returned for this goal.")
            st.stop()
        t_titles = [f"{t['code']} — {t['title']}" for t in trgs]
        t_sel = st.selectbox("Target", t_titles, index=0)
        t_code = trgs[t_titles.index(t_sel)]["code"]

        # Indicators
        inds = un_indicators(t_code)
        if not inds:
            st.info("No indicators returned for this target.")
            st.stop()
        i_titles = [f"{i['code']} — {i.get('description','')}" for i in inds]
        i_sel = st.selectbox("Indicator", i_titles, index=0)
        i_code = inds[i_titles.index(i_sel)]["code"]

        # Series under the indicator
        sers = un_series(i_code)
        if not sers:
            st.info("This indicator currently has no published series in the UN Global Database.")
            st.stop()
        s_titles = [f"{s['code']} — {s.get('description','')}" for s in sers]
        s_sel = st.selectbox("Series (choose a headline/total series if available)", s_titles, index=0)
        s_code = sers[s_titles.index(s_sel)]["code"]

        with st.spinner("Fetching UN SDG series…"):
            dfu = un_fetch_series_timeseries(s_code, countries, yr1, yr2)

        if dfu.empty:
            st.warning(
                "Couldn’t retrieve a timeseries for this Series/country selection via the public UN endpoints. "
                "Some series require specific disaggregation filters in SDMX. "
                "Try another *Series* or switch to **World Bank (WDI subset)**."
            )
            st.caption("Tip: pick a series that looks like a headline or 'total' variant.")
        else:
            figu = px.line(dfu, x="date", y="value", color="country",
                           labels={"date":"Year", "value": f"{s_code} (UN SDG)"},
                           template=template, markers=True)
            if log_y: figu.update_yaxes(type="log")
            figu.update_layout(margin=dict(l=10, r=10, t=10, b=0), height=460)
            st.plotly_chart(figu, use_container_width=True)
            st.caption("Source: UN SDG Global Database (harmonized SDMX dataflow)")

# ------------------------------------------------------------
# Definitions (WDI metadata or UN descriptions)
# ------------------------------------------------------------
with tab_defs:
    st.subheader("Indicator definitions")

    if data_src == "World Bank (WDI subset)":
        st.caption("Source: World Bank World Development Indicators (WDI) metadata.")
        ind_all = indicators_for_goal(CATALOG, goal)
        if not ind_all:
            st.info("No indicators mapped for this goal in your WDI catalog yet.")
        else:
            options = [f"{c['name']} [{(c.get('code') or '—')}]" for c in ind_all]
            ind_label = st.selectbox("Indicator", options, index=0)
            code = ind_label.split("[")[-1].strip("]").strip()

            if code in ("—", ""):
                st.info("This catalog entry does not have a WDI code. Add `wb_code` in `data/sdg_catalogue.csv`.")
            else:
                meta = wb_indicator_meta(code)
                left, right = st.columns([2, 1], gap="large")
                with left:
                    st.markdown(f"### {meta.get('name', code)}")
                    st.code(code, language="text")
                    st.markdown("**Definition**")
                    st.write(meta.get("sourceNote") or "—")
                with right:
                    st.markdown("**Unit**")
                    st.write(meta.get("unit") or "—")
                    st.markdown("**Source**")
                    src = meta.get("source") or meta.get("sourceOrganization") or "—"
                    st.write(src)
                    st.markdown("**API endpoint**")
                    st.code(f"{WB_BASE}/indicator/{code}?format=json", language="text")

                with st.expander("See all definitions for this goal"):
                    rows = []
                    with st.spinner("Loading indicator metadata…"):
                        for c in ind_all:
                            k = (c.get("code") or "").strip()
                            if not k:
                                rows.append({"Indicator": c["name"], "Code": "—", "Unit": "—",
                                             "Definition (short)": "No WDI code in catalog"})
                                continue
                            m = wb_indicator_meta(k)
                            rows.append({
                                "Indicator": m.get("name") or c["name"],
                                "Code": k,
                                "Unit": m.get("unit") or "",
                                "Definition (short)": _short(m.get("sourceNote") or ""),
                            })
                    if rows:
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=420)

    else:
        st.caption("Source: UN SDG Global Database (official SDG hierarchy).")
        goals = un_goals()
        goal_codes = [g["code"] for g in goals]
        goal_titles = [f"SDG {g['code']} · {g['title']}" for g in goals]
        default_goal_num = str(int(goal.split()[1])) if goal.startswith("SDG ") else "1"
        g_sel = st.selectbox("Goal (UN SDG)", goal_titles,
                             index=goal_codes.index(default_goal_num) if default_goal_num in goal_codes else 0)
        g_code = goals[goal_titles.index(g_sel)]["code"]

        trgs = un_targets(g_code)
        if not trgs:
            st.info("No targets returned for this goal.")
        else:
            t_titles = [f"{t['code']} — {t['title']}" for t in trgs]
            t_sel = st.selectbox("Target", t_titles, index=0)
            t_code = trgs[t_titles.index(t_sel)]["code"]

            inds = un_indicators(t_code)
            if not inds:
                st.info("No indicators returned for this target.")
            else:
                i_titles = [f"{i['code']} — {i.get('description','')}" for i in inds]
                i_sel = st.selectbox("Indicator", i_titles, index=0)
                i_code = inds[i_titles.index(i_sel)]["code"]
                i_obj = inds[i_titles.index(i_sel)]

                sers = un_series(i_code)
                s_titles = [f"{s['code']} — {s.get('description','')}" for s in sers] if sers else []
                s_sel = st.selectbox("Series (optional)", ["(none)"] + s_titles, index=0)
                s_obj = None
                if s_sel != "(none)":
                    s_obj = sers[s_titles.index(s_sel)]

                st.markdown(f"### Indicator {i_code}")
                st.markdown("**Description**")
                st.write(i_obj.get("description") or i_obj.get("tier") or "—")

                if s_obj:
                    st.markdown("---")
                    st.markdown(f"### Series {s_obj.get('code')}")
                    st.markdown("**Description**")
                    st.write(s_obj.get("description") or "—")
                    st.markdown("**Note**")
                    st.write("Some series require specific disaggregation filters to retrieve data via SDMX.")

# ------------------------------------------------------------
# Data & Sources
# ------------------------------------------------------------
with tab_data:
    st.subheader("Data & Downloads")
    st.markdown(
        "- **World Bank WDI** via Indicators API (`api.worldbank.org/v2`) for the WDI subset.\n"
        "- **UN SDG Global Database** via the UN SDG API + SDMX for the full official hierarchy."
    )
    st.markdown(f"Baseline year: **{BASELINE_YEAR}**, target year: **{TARGET_YEAR}**. "
                "2030 status is a heuristic pace check vs target (when available).")

    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))
    ind_cfgs = indicators_for_goal(CATALOG, goal)

    with st.spinner("Assembling WDI CSV (current goal selection)…"):
        frames: List[pd.DataFrame] = []
        for cfg in ind_cfgs:
            code = (cfg.get("code") or "").strip()
            if not code:
                continue
            df_i = wb_fetch(code, countries)
            df_i = df_i[(df_i["date"] >= yr1) & (df_i["date"] <= yr2)]
            df_i["indicator_name"] = cfg["name"]
            frames.append(df_i)
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if combined.empty:
        st.info("No WDI data to download for this selection.")
    else:
        csv_bytes = combined.sort_values(["indicator","country","date"]).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download current selection (WDI CSV)",
            data=csv_bytes,
            file_name=f"sdg_wdi_{goal.replace(' ','_')}_{yr1}_{yr2}.csv",
            mime="text/csv",
        )

    st.markdown("### Notes & Attributions")
    st.markdown(
        "- **SDG icons** served via the Open SDG translations CDN (informational, non-commercial use).  \n"
        "- Indicator coverage varies by country/year; some UN series need specific disaggregation filters in SDMX."
    )
