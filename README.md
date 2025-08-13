# 🎯 SDG Progress Monitor (India & Peers)

An interactive **Streamlit** app that tracks progress on selected **UN Sustainable Development Goals (SDGs)** using **World Bank – World Development Indicators (WDI)**.  
It ships with an **Overview** page (SDG icon, India‑focused status cards, peer snapshots) and a **Drilldown** page (interactive time‑series with smoothing, log scale, theme toggle) plus a **Data & Sources** tab with CSV export.

> Portfolio‑ready, data‑informed, and easy to extend.

---

## 🧭 Table of Contents
- [Features](#-features)
- [Screens](#-screens)
- [Quickstart](#-quickstart)
- [Requirements](#-requirements)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [URL (Permalink) Parameters](#-url-permalink-parameters)
- [Supported SDG Indicators](#-supported-sdg-indicators)
- [How Progress Is Calculated](#-how-progress-is-calculated)
- [Architecture & Data Flow](#-architecture--data-flow)
- [Accessibility & UX](#-accessibility--ux)
- [Deployment](#-deployment)
- [API Reference (World Bank)](#-api-reference-world-bank)
- [Data Usage & Icon Licensing](#-data-usage--icon-licensing)
- [Security & Privacy](#-security--privacy)
- [Testing](#-testing)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgements](#-acknowledgements)

---

## ✨ Features
- **Overview** per goal:
  - SDG **icon**, title, baseline/target year.
  - 🇮🇳 **India quick status**: baseline, latest, Δ since baseline, and a **2030 pace check** badge (on track / needs acceleration / off track).
  - **Peer snapshot** mini bar charts (latest available values).
- **Drilldown**:
  - Multi‑country **time series** for a selected indicator.
  - **3‑year smoothing** overlay, **log scale** toggle, **light/dark** chart themes.
  - India KPI block (latest, baseline, delta) + optional data table.
- **Data & Sources**:
  - One‑click **CSV export** of the current selection (goal × countries × year range).
  - Clear notes & attributions.
- **Permalinks** via `st.query_params` to share your exact view.
- **Caching & resiliency**:
  - `@st.cache_data` (1h TTL) and light **retry** on API requests.
- **Python 3.8+** compatible; no secrets required.

---

## 🖼 Screens
- **Overview**: SDG icon, India status grid, peer snapshots.
- **Drilldown**: Interactive line chart + smoothing/log/theme toggles.
- **Data & Sources**: Download CSV, read notes.

*(Add screenshots/GIFs when ready.)*

---

## 🚀 Quickstart

### 1) Clone & enter
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### 2) Create a virtual environment
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3) Install requirements
```bash
pip install -r requirements.txt
```

### 4) Run the app
```bash
streamlit run app/sdg.py
```
Open the URL Streamlit prints (default `http://localhost:8501`).

---

## 📦 Requirements
Minimal deps (works on Python 3.8+):
```
streamlit==1.37.1
requests>=2.31
plotly>=5.22
pandas>=2.2      ; python_version >= "3.9"
pandas>=1.5,<2.2 ; python_version < "3.9"
```
> On Python 3.8, the conditional pin keeps pandas compatible.

---

## 📂 Project Structure
```
your-repo/
├─ app/
│  └─ sdg.py         # SDG Monitor (Overview + Drilldown + Data tabs)
├─ .streamlit/
│  └─ config.toml    # (optional) base theme
├─ requirements.txt
├─ README.md
└─ .gitignore
```

---

## ⚙️ Configuration
- **Theme**: `.streamlit/config.toml` (app‑wide) + in‑chart **Light/Dark** toggle.
- **Sidebar** (form‑based, fewer reruns):
  - Goal selection
  - Peer preset + manual peers (India always included)
  - Year range
  - Log scale, 3‑year smoothing
  - Chart theme (Light/Dark)
  - Data table toggle (Drilldown)
  - **Reset** & **Permalink**

---

## 🔗 URL (Permalink) Parameters
The **Permalink** button updates the URL with your selection. On load, the app reads them.

| Param | Meaning | Example |
|---|---|---|
| `goal` | Goal label key (must match `SDG_INDICATORS` mapping) | `SDG 2 · Zero Hunger` |
| `peers` | Comma‑separated ISO‑3 codes (India is automatic) | `CHN,PAK,BGD` |
| `yr1` / `yr2` | Year range | `2000` / `2024` |
| `theme` | `light` or `dark` | `dark` |

**Example:**  
```
?goal=SDG%202%20%C2%B7%20Zero%20Hunger&yr1=2000&yr2=2024&peers=CHN,PAK,BGD&theme=dark
```

---

## ✅ Supported SDG Indicators
> Add/modify indicators in the `SDG_INDICATORS` dict inside `app/sdg.py`.

**SDG 1 · No Poverty**
- `SI.POV.DDAY` — Poverty headcount (<$3.00, 2021 PPP) (% population). *(Target 2030: 0%)*

**SDG 2 · Zero Hunger**
- `SN.ITK.DEFC.ZS` — Prevalence of undernourishment (% population).

**SDG 3 · Good Health & Well‑being**
- `SH.STA.MMRT` — Maternal mortality ratio (per 100,000 live births). *(Target 2030: <70)*
- `SP.DYN.IMRT.IN` — Infant mortality rate (per 1,000 live births).

**SDG 4 · Quality Education**
- `SE.PRM.NENR` — Primary school net enrollment (%). *(Target 2030: 100%)*

**SDG 6 · Clean Water & Sanitation**
- `SH.H2O.BASW.ZS` — People using at least basic drinking water (%). *(Target 2030: 100%)*
- `SH.STA.BASS.ZS` — People using at least basic sanitation (%). *(Target 2030: 100%)*

**SDG 7 · Affordable & Clean Energy**
- `EG.ELC.ACCS.ZS` — Access to electricity (% of population). *(Target 2030: 100%)*
- `EG.FEC.RNEW.ZS` — Renewable energy consumption (% of TFEC).

**SDG 8 · Decent Work & Growth**
- `SL.UEM.TOTL.ZS` — Unemployment (% of total labor force).

**SDG 9 · Industry, Innovation & Infrastructure**
- `IT.CEL.SETS.P2` — Mobile cellular subscriptions (per 100 people).
- `NV.IND.MANF.ZS` — Manufacturing value added (% of GDP).

---

## 📏 How Progress Is Calculated
- **Baseline**: first value at/after **2015**.
- **Target year**: **2030**.
- For series with a numeric **target** (e.g., MMR < 70; Access = 100%), compare:
  - **Required annual change** from baseline to target (2015→2030), and
  - **Observed annual change** from baseline to latest year.
- Status:
  - **🟢 on track** – observed pace ≥ required pace
  - **🟠 needs acceleration** – 50–99% of required pace
  - **🔴 off track** – <50% of required pace
  - **trend only** – no numeric target or not enough data

> This is a **heuristic** progress check for exploration; not an official UN assessment.

---

## 🏗 Architecture & Data Flow
```
World Bank API (WDI, v2 JSON)
        │
        ▼
Requests ──► Cache (@st.cache_data, 1h TTL) + retry
        │
        ▼
Pandas ──► Baseline/Latest/Δ ──► 2030 pace check
        │
        ▼
Plotly (line/bar) + Streamlit UI (tabs, sidebar form) + CSV export
```

---

## ♿ Accessibility & UX
- **Form-based** sidebar to batch changes → fewer reruns.
- **Light/Dark** chart templates, **log scale**, **3‑year smoothing** for readability.
- Clear **empty states** and **error handling**.
- CSV export for offline analysis.

---

## ☁️ Deployment
### Streamlit Community Cloud
1. Push this repo to GitHub.
2. New app → choose repo → main file `app/sdg.py`.
3. Deploy. (Future pushes auto‑update.)

### Docker (optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app/sdg.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

## 📚 API Reference (World Bank)
- **Base**: `https://api.worldbank.org/v2`
- **Endpoint shape**:
  ```
  /country/{ISO3;ISO3;...}/indicator/{INDICATOR_CODE}?format=json&per_page=20000&page=1
  ```
- Response is `[metadata, data]`; the app normalizes the `data` array and concatenates pages.
- Some series are sparse or revised; always check the **latest year** displayed.

---

## 📝 Data Usage & Icon Licensing
- **Data**: World Bank **WDI** (public). Review terms and attribution on the World Bank site.
- **SDG icons**: Loaded from **Open SDG translations** CDN for informational use. Follow UN SDG icon guidance for non‑commercial contexts.
- Please include attribution when reproducing outputs.

---

## 🔒 Security & Privacy
- No API keys or credentials.
- Only anonymous GET requests to a public API.
- Avoid committing private data.

---

## ✅ Testing
```bash
pip install pytest
pytest
```
**Ideas**: indicator coverage, baseline/latest logic, pace check math, URL hydration parsing.

---

## 🗺 Roadmap
- [ ] Add more goals/indicators (toward full SDG coverage).
- [ ] Country profile cards.
- [ ] Global choropleth per indicator.
- [ ] Forecast options (with uncertainty).
- [ ] CI: lint + tests (GitHub Actions).

---

## 🤝 Contributing
1. Open an issue describing the enhancement or fix.
2. Fork, branch, and submit a focused PR.
3. Include screenshots/GIFs for UI changes when possible.

---

## 📄 License
This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2025 Kumar Suyash Rituraj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```


---

## 🙏 Acknowledgements
- **World Bank WDI**, **Streamlit**, **Plotly**.
- **Open SDG translations** for SDG icons.
