# app/sdg.py
# SDG Progress Monitor (India + peers) — with Overview page and UI best practices
# Python 3.8+; deps: streamlit, requests, pandas, plotly

from __future__ import annotations
import math
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

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

# Minimal, extensible SDG → indicators mapping
SDG_INDICATORS: Dict[str, List[Dict[str, object]]] = {
    "SDG 1 · No Poverty": [
        {"code": "SI.POV.DDAY", "name": "Poverty headcount (<$3.00, 2021 PPP) (% pop)",
         "better": "down", "target2030": 0.0},
    ],
    "SDG 2 · Zero Hunger": [
        {"code": "SN.ITK.DEFC.ZS", "name": "Undernourishment (% pop)",
         "better": "down", "target2030": None},
    ],
    "SDG 3 · Good Health & Well-being": [
        {"code": "SH.STA.MMRT", "name": "Maternal mortality (per 100k live births)",
         "better": "down", "target2030": 70.0},  # SDG 3.1
        {"code": "SP.DYN.IMRT.IN", "name": "Infant mortality (per 1,000)",
         "better": "down", "target2030": None},
    ],
    "SDG 4 · Quality Education": [
        {"code": "SE.PRM.NENR", "name": "Primary net enrollment (%)",
         "better": "up", "target2030": 100.0},
    ],
    "SDG 6 · Clean Water & Sanitation": [
        {"code": "SH.H2O.BASW.ZS", "name": "Basic drinking water (% pop)",
         "better": "up", "target2030": 100.0},
        {"code": "SH.STA.BASS.ZS", "name": "Basic sanitation (% pop)",
         "better": "up", "target2030": 100.0},
    ],
    "SDG 7 · Affordable & Clean Energy": [
        {"code": "EG.ELC.ACCS.ZS", "name": "Access to electricity (% pop)",
         "better": "up", "target2030": 100.0},
        {"code": "EG.FEC.RNEW.ZS", "name": "Renewable energy (% of TFEC)",
         "better": "up", "target2030": None},
    ],
    "SDG 8 · Decent Work & Growth": [
        {"code": "SL.UEM.TOTL.ZS", "name": "Unemployment (% of labor force)",
         "better": "down", "target2030": None},
    ],
    "SDG 9 · Industry, Innovation & Infra": [
        {"code": "IT.CEL.SETS.P2", "name": "Mobile subscriptions (per 100 people)",
         "better": "up", "target2030": None},
        {"code": "NV.IND.MANF.ZS", "name": "Manufacturing VA (% of GDP)",
         "better": "up", "target2030": None},
    ],
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
    SDG icons via Open SDG translations CDN (permitted for informational use).
    https://open-sdg.github.io/sdg-translations/
    """
    base = "https://open-sdg.github.io/sdg-translations/assets/img"
    return f"{base}/{'high-contrast/' if high_contrast else ''}goals/{language}/{goal}.png"

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
    countries = ";".join(iso3_list)
    url = f"{WB_BASE}/country/{countries}/indicator/{indicator}"
    params = {"format": "json", "per_page": 20000}
    rows = []; page = 1
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
    # friendly labels
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
    """Return (status label, progress ratio 0..1+ or None). Heuristic vs official."""
    if latest_year is None or latest_year <= BASELINE_YEAR:
        return ("insufficient data", None)
    if target is None:
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

    if progress is None or any(map(lambda x: x is None or math.isnan(x), [req_rate, act_rate])):
        return ("trend only", None)

    pace = act_rate / req_rate if req_rate not in (0, None) else 0.0
    if pace >= 1.0:
        return ("🟢 on track", progress)
    if pace >= 0.5:
        return ("🟠 needs acceleration", progress)
    return ("🔴 off track", progress)

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def _get_qp_val(qp, key: str) -> Optional[str]:
    if key not in qp:
        return None
    v = qp[key]
    return v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)

def fmt(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{x:,.2f}"

# ------------------------------------------------------------
# Sidebar — form-based controls (best-practice: fewer reruns)
# ------------------------------------------------------------
def init_defaults():
    if "controls" not in st.session_state:
        st.session_state.controls = {
            "goal": list(SDG_INDICATORS.keys())[0],
            "preset": "SAARC",
            "manual_peers": ["BGD", "PAK", "LKA", "NPL"],
            "yr1": 2000,
            "yr2": datetime.now().year,
            "log_y": False,
            "smooth3": False,
            "theme": "Light",
            "show_table": False,
        }
        # hydrate from URL
        qp = st.query_params
        if qp:
            goal = _get_qp_val(qp, "goal")
            peers = _get_qp_val(qp, "peers")
            yr1 = _get_qp_val(qp, "yr1")
            yr2 = _get_qp_val(qp, "yr2")
            theme = _get_qp_val(qp, "theme")
            if goal and goal in SDG_INDICATORS:
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
                # don't include India in manual peers; India is always on
                st.session_state.controls["manual_peers"] = [p for p in iso_list if p != DEFAULT_COUNTRY]

def controls_form() -> dict:
    init_defaults()
    c = st.session_state.controls

    with st.sidebar:
        st.header("Controls")
        with st.form("sdg_controls", clear_on_submit=False):
            goal = st.selectbox("Goal", list(SDG_INDICATORS.keys()),
                                index=list(SDG_INDICATORS.keys()).index(c["goal"]))
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
            apply_btn = st.form_submit_button("Apply")

        co1, co2 = st.columns(2)
        with co1:
            if st.button("Reset"):
                st.session_state.controls = {
                    "goal": list(SDG_INDICATORS.keys())[0],
                    "preset": "SAARC",
                    "manual_peers": ["BGD", "PAK", "LKA", "NPL"],
                    "yr1": 2000, "yr2": datetime.now().year,
                    "log_y": False, "smooth3": False, "theme": "Light",
                    "show_table": False,
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
            "theme": theme, "show_table": show_table,
        }
        c = st.session_state.controls
    return c

# ------------------------------------------------------------
# Main layout: Overview • Drilldown • Data/Sources
# ------------------------------------------------------------
controls = controls_form()
goal = controls["goal"]
preset = controls["preset"]
manual_peers = controls["manual_peers"]
yr1, yr2 = controls["yr1"], controls["yr2"]
log_y, smooth3 = controls["log_y"], controls["smooth3"]
template = "plotly_dark" if controls["theme"] == "Dark" else "plotly"
show_table = controls["show_table"]

tab_overview, tab_drill, tab_data = st.tabs(["Overview", "Drilldown", "Data & Sources"])

# ------------------------------------------------------------
# Overview
# ------------------------------------------------------------
with tab_overview:
    # Hero with SDG icon (try to infer goal number from label prefix)
    # Hero with SDG icon (more spacing)
 try:
    sdg_no = int(goal.split()[1])
 except Exception:
    sdg_no = 1

# wider right column + explicit gap
c1, c2 = st.columns([1, 5], gap="large")

with c1:
    # keep the icon, drop the image caption to reduce clutter
    st.image(sdg_icon_url(sdg_no), width=128)

with c2:
    # h1 without extra margin so caption sits close underneath
    st.markdown(f"<h1 style='margin:0'>{goal}</h1>", unsafe_allow_html=True)
    st.caption(f"Baseline: {BASELINE_YEAR} · Target year: {TARGET_YEAR} · India + peers")


    # Build country list
    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))
    # Fetch all indicators for this goal
    with st.spinner("Fetching World Bank data…"):
        dfs = {cfg["code"]: wb_fetch(cfg["code"], countries) for cfg in SDG_INDICATORS[goal]}

    # Quick KPI/status grid for India
    st.markdown("### 🇮🇳 India — Quick status")
    header = st.columns([2.5, 1.1, 1.1, 1.6, 1.8])
    header[0].markdown("**Indicator**")
    header[1].markdown(f"**Baseline {BASELINE_YEAR}**")
    header[2].markdown("**Latest**")
    header[3].markdown("**Δ since baseline**")
    header[4].markdown("**2030 check**")

    for cfg in SDG_INDICATORS[goal]:
        df_i = dfs[cfg["code"]]
        b_y, b_v = value_at_or_after(df_i, DEFAULT_COUNTRY, BASELINE_YEAR)
        l_y, l_v = latest_value(df_i, DEFAULT_COUNTRY)
        dv = (l_v - b_v) if (b_v is not None and l_v is not None) else None
        status, prog = ("—", None)
        if b_v is not None and l_v is not None:
            status, prog = progress_status(b_v, l_v, l_y, cfg.get("target2030"), cfg["better"])

        c0, c1, c2, c3, c4 = st.columns([2.5, 1.1, 1.1, 1.6, 1.8])
        c0.markdown(f"**{cfg['name']}**  \n`{cfg['code']}`")
        c1.write(fmt(b_v))
        c2.write(f"{fmt(l_v)}{' (' + str(l_y) + ')' if l_y else ''}")
        c3.write(("+" if (dv is not None and ((cfg['better']=='up' and dv>=0) or (cfg['better']=='down' and dv<0))) else "") + (fmt(dv) if dv is not None else "—"))

        if prog is None:
            c4.write(status)
        else:
            # small progress bar approximation
            pb = min(max(prog, 0.0), 1.0)
            c4.write(status)
            c4.progress(pb)

    st.markdown("### Peer snapshot (latest available)")
    # For each indicator show a small bar chart of latest values
    for cfg in SDG_INDICATORS[goal]:
        df_i = dfs[cfg["code"]]
        latest_vals = (
            df_i.dropna(subset=["value"])
               .sort_values(["country", "date"])
               .groupby("country", as_index=False).tail(1)
               .sort_values("value", ascending=(cfg["better"]=="down"))
        )
        if latest_vals.empty:
            continue
        st.markdown(f"**{cfg['name']}**  ·  `{cfg['code']}`")
        fig = px.bar(latest_vals, x="country", y="value", template=template)
        if log_y:
            fig.update_yaxes(type="log")
        fig.update_layout(margin=dict(l=10,r=10,t=10,b=0), height=300)
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# Drilldown
# ------------------------------------------------------------
with tab_drill:
    st.subheader("Drilldown by indicator")
    # Selector
    options = [f"{c['name']} [{c['code']}]" for c in SDG_INDICATORS[goal]]
    ind_label = st.selectbox("Indicator", options, index=0)
    code = ind_label.split("[")[-1].strip("]")

    # Countries & fetch
    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))
    df = wb_fetch(code, countries)
    df = df[(df["date"] >= yr1) & (df["date"] <= yr2)]

    if df.empty:
        st.info("No data available for this selection.")
    else:
        base_fig = px.line(df, x="date", y="value", color="country",
                           labels={"date": "Year", "value": ind_label},
                           template=template, markers=True)
        # optional smoothing (3y rolling mean per country)
        if smooth3:
            smoothed = (
                df.sort_values(["country", "date"])
                  .groupby("country", as_index=False)
                  .apply(lambda g: g.assign(value_smooth=g["value"].rolling(window=3, min_periods=1).mean()))
                  .reset_index(drop=True)
            )
            fig2 = px.line(smoothed, x="date", y="value_smooth", color="country", template=template)
            for tr in fig2.data:
                tr.update(line=dict(dash="dash"))
                base_fig.add_trace(tr)

        if log_y:
            base_fig.update_yaxes(type="log")
        base_fig.update_layout(margin=dict(l=10, r=10, t=10, b=0), height=460)
        st.plotly_chart(base_fig, use_container_width=True)

        # India focus KPIs
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

# ------------------------------------------------------------
# Data & Sources
# ------------------------------------------------------------
with tab_data:
    st.subheader("Data & Downloads")
    st.markdown("**Source:** World Bank **World Development Indicators** via Indicators API (`api.worldbank.org/v2`).")
    st.markdown(f"Baseline year: **{BASELINE_YEAR}**, target year: **{TARGET_YEAR}**. "
                "2030 status is a heuristic pace check vs target (when available).")

    # Recreate a combined dataframe for the current goal + peers (current year range)
    countries = [DEFAULT_COUNTRY] + list(dict.fromkeys(PEER_PRESETS[preset] + manual_peers))
    with st.spinner("Assembling CSV…"):
        frames = []
        for cfg in SDG_INDICATORS[goal]:
            df_i = wb_fetch(cfg["code"], countries)
            df_i = df_i[(df_i["date"] >= yr1) & (df_i["date"] <= yr2)]
            df_i["indicator_name"] = cfg["name"]
            frames.append(df_i)
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if combined.empty:
        st.info("No data to download for this selection.")
    else:
        csv_bytes = combined.sort_values(["indicator","country","date"]).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download current selection (CSV)",
            data=csv_bytes,
            file_name=f"sdg_{goal.replace(' ','_')}_{yr1}_{yr2}.csv",
            mime="text/csv",
        )

    st.markdown("### Notes & Attributions")
    st.markdown(
        "- **SDG icons** served via the Open SDG translations CDN (informational use).  \n"
        "- **Indicator codes** follow WDI conventions (e.g., `EG.ELC.ACCS.ZS`, `SH.STA.MMRT`).  \n"
        "- Some series are sparse or revised over time — always check **latest year** in KPIs."
    )
