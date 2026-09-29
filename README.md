# 🌊 JalDrishti AI
###jaldrishti-ai-flood-nowcasting.vercel.app
### Street-Level Urban Flood Nowcasting System (0–3 Hours)

**JalDrishti AI** is a real-time, street-level urban flood nowcasting system designed to predict **where flooding will occur before it happens**.

The system combines rainfall nowcasting, high-resolution terrain data, urban drainage networks, hydraulic simulation, 2D surface-water modelling, and flood-aware route planning to provide predictions up to **3 hours ahead**.

> **"Don't just know where it is flooded — know which roads will be flooded by the time you reach them."**

---



## 🚨 Problem

Urban flooding is highly localized. Knowing how much rain will fall does not tell us which particular streets or intersections will flood.

Flooding depends on:

* 🌧️ Rainfall intensity and movement
* 🗺️ Micro-topography and elevation
* 🏙️ Impervious urban surfaces
* 🚧 Drainage capacity and blockages
* 🌊 River/sea backwater effects
* 🚗 Traffic and road accessibility

Traditional weather forecasts therefore cannot provide reliable **street-level flood information**.

JalDrishti AI addresses this gap by coupling **rainfall + terrain + drainage + surface flow + routing** into a single pipeline.

---

## 🎯 Key Objectives

* Predict street-level flooding **0–3 hours in advance**
* Estimate water depth for individual road segments
* Model urban drainage capacity and surcharge
* Simulate surface-water movement
* Identify potentially blocked or overloaded drainage
* Provide flood-safe routes for different vehicle types
* Provide APIs for navigation and emergency services
* Display real-time flood information through a web GIS dashboard

---

## 🧠 How It Works

```text
Rainfall Radar
      ↓
Rainfall Nowcasting
      ↓
Rainfall → Runoff
      ↓
EPA SWMM Drainage Model
      ↓
Drain Overflow / Surcharge
      ↓
2D Surface Water Flow
      ↓
Road-Level Water Depth
      ↓
Flood Risk Assessment
      ↓
Time-Dependent Routing
      ↓
Dashboard + API + Alerts
```

---

## 🏗️ System Architecture

### 1. 🌧️ Rainfall Data

The system uses:

* Doppler radar rainfall data
* RainViewer radar composites
* Open-Meteo historical/forecast rainfall
* NASA GPM IMERG data for historical replay

Radar frames are converted from **dBZ → rainfall intensity** and used for short-term extrapolation.

---

### 2. 🔮 Rainfall Nowcasting

An optical-flow based approach estimates the movement of rainfall cells.

```text
Radar Frame T-1
      ↓
Radar Frame T
      ↓
Motion Estimation
      ↓
Optical Flow
      ↓
Rainfall Extrapolation
      ↓
0–180 Minute Forecast
```

A persistence model is also used as a baseline for comparison.

---

### 3. 🚰 Drainage Network Modelling

The urban stormwater network is represented as a directed graph:

* **Nodes → Manholes / inlets**
* **Edges → Drains / conduits**

The hydraulic system is simulated using **EPA SWMM 5.2**.

Current model:

* 4,896 drainage nodes
* 4,869 drainage edges
* 403 outfalls
* Manning's roughness coefficient: 0.013

The model calculates drainage capacity, surcharge and flooding.

---

### 4. 🗺️ Terrain Modelling

The surface model uses **Copernicus GLO-30 DEM** combined with available Chennai survey elevation data.

The model includes:

* Elevation correction
* Road burning
* Urban terrain
* Building obstacles
* Low-lying areas

The resulting terrain is used to determine how water flows across the city.

---

### 5. 🌊 2D Surface Water Flow

A diffusion-wave based model simulates water movement across a **30 m grid**.

The model determines:

* Water accumulation
* Flow direction
* Flood extent
* Water depth
* Low-lying flood zones

The current implementation uses a one-way coupling from drainage overflow to surface water.

---

### 6. 🚗 Flood-Safe Routing

JalDrishti AI uses **time-dependent routing** instead of simply avoiding roads that are currently flooded.

A road is evaluated based on the water depth expected **when the vehicle reaches that road**.

Supported vehicle categories include:

| Vehicle        | Water-depth limit |
| -------------- | ----------------: |
| 🚶 Walking     |             10 cm |
| 🛵 Two-wheeler |             15 cm |
| 🛺 Auto        |             20 cm |
| 🚗 Car         |             25 cm |
| 🚑 Ambulance   |             30 cm |
| 🚌 MTC Bus     |             40 cm |

The system can generate safer alternatives for commuters, emergency services and public transport.

---

# 🖥️ Dashboard

The web GIS dashboard provides:

* 🗺️ Street and satellite map views
* 🌊 Flood extent visualization
* 📏 Road water-depth estimation
* 🌧️ Rainfall nowcast
* 🚰 Drainage status
* ⚠️ Flood alerts
* 🏥 Hospital accessibility
* 🚇 Subway closure information
* 🚌 Bus diversion information
* 🚗 Flood-safe routing
* 📊 City-level flood statistics
* 🔄 Historical flood-event replay
* 🔬 Multiple simulation scenarios

### Simulation Scenarios

```text
Nowcast
Persistence
Culvert Blocked
River Backwater
Hindsight
Historical Events
```

---

# ⚙️ Technology Stack

### Backend / Simulation

* Python
* NumPy
* SciPy
* Pandas
* Numba
* Rasterio
* PyProj
* EPA SWMM 5.2
* swmm-toolkit

### API

* FastAPI
* Uvicorn
* GeoJSON
* CAP 1.2 alerts

### Frontend

* HTML
* JavaScript
* Canvas
* GIS map layers
* Esri tiles
* OpenStreetMap data

### Automation

* GitHub Actions
* 15-minute scheduled processing

---

# 📡 API

The system provides APIs for applications and navigation systems.

### Route

```http
GET /route?from=lat,lon&to=lat,lon&vehicle=amb&depart=0
```

### Flood Closures

```http
GET /closures?t=60&vehicle=car
```

Returns GeoJSON road closures.

### Flood Depth

```http
GET /nowcast/depth?t=90&bbox=...
```

### Point Forecast

```http
GET /point?lat=...&lon=...
```

Returns the predicted 3-hour flood-depth series.

### Drainage Status

```http
GET /drains/status?t=60
```

### Alerts

```http
GET /alerts
```

Returns CAP 1.2 alert information.

### Bus Diversions

```http
GET /bus/diversions
```

### Live Rainfall

```http
GET /live/rain
```

---

# 📊 Results

The system was evaluated using historical Chennai rainfall and flood-event replays.

### Cyclone Michaung — December 2023

* **33.2 km²** predicted under >15 cm water at +3 hours
* Optical-flow flood-cell CSI: **0.90**
* Persistence baseline CSI: **0.85**
* Optical-flow depth error: **3.8 cm**
* Persistence depth error: **4.8 cm**

### Rainfall Nowcasting

For selected heavy-rainfall days from 2021–2026:

* Optical-flow +3h rainfall error: **2.83 mm/h**
* Persistence error: **3.39 mm/h**

### Runtime

```text
SWMM simulation      ≈ 7 minutes
2D surface model     ≈ 2.5 minutes
Full live cycle      ≈ 4–11 minutes
```

The target is a **15-minute operational cycle**.

---

# 🕒 Historical Event Replay

The system supports replay of multiple Chennai flood events:

| Event                | Flooded area >15 cm @ +180 min |
| -------------------- | -----------------------------: |
| 2021 Deep Depression |                       43.2 km² |
| Cyclone Mandous 2022 |                       19.9 km² |
| October 2024 Event   |                       12.2 km² |
| Cyclone Fengal 2024  |                       29.7 km² |
| December 2025 Event  |                       17.9 km² |

---

# 🗃️ Datasets

The project uses multiple public and open datasets.

| Dataset                       | Purpose                          |
| ----------------------------- | -------------------------------- |
| GCC Storm Water Drain Network | Drainage modelling               |
| GCC Ward Survey Sheets        | Elevation & drainage information |
| NASA GPM IMERG                | Historical rainfall              |
| Open-Meteo / ERA5             | Historical & forecast rainfall   |
| RainViewer                    | Live radar                       |
| Copernicus GLO-30             | Terrain / DEM                    |
| OpenStreetMap                 | Roads & buildings                |
| Chennai Ward Boundaries       | Administrative mapping           |
| EPA SWMM 5.2                  | Hydraulic simulation             |

---

# 🔬 Validation

### Completed

* Rainfall nowcast vs hindsight comparison
* Terrain holdout validation
* Historical event replay

### Planned

Field validation using:

* Flood-depth observations
* Flood-meter cameras
* Citizen reports
* GCC complaints
* Geotagged flood photographs

The current system does **not yet include field-observed street water depths**.

---

# ⚠️ Current Limitations

The current prototype has several limitations:

* Radar archives are not publicly available for all historical events
* Terrain resolution is approximately 30 m rather than 1–5 m LiDAR
* Drainage data currently covers 107 of 200 wards
* Drain-to-surface coupling is currently one-way
* MTC routes are approximated because GTFS data is not publicly available
* Field validation has not yet been completed

These limitations are explicitly considered in the system design.

---

# 🚀 Future Scope

Future development includes:

* 📡 Direct IMD radar integration
* 🔮 Ensemble rainfall nowcasting using PySTEPS
* 🛰️ 1–5 m LiDAR DEM
* 🚰 Complete Chennai drainage network
* 🔄 Two-way drainage/surface coupling
* 📹 Camera-based flood detection
* 📞 1913 complaint integration
* 🗣️ Tamil + English alerts
* 📱 SMS / cell-broadcast integration
* 🚌 MTC GTFS integration
* 🤖 Improved blockage detection

---

# 🌍 Potential Applications

JalDrishti AI can support:

* 🏛️ Municipal disaster-management control rooms
* 🚑 Ambulance services
* 🚒 Fire & rescue teams
* 🚔 Traffic police
* 🚌 Public transportation
* 🚗 Daily commuters
* 🏥 Emergency hospital access
* 🚧 Road-closure planning
* 🌧️ Flood preparedness

The architecture can also be adapted to other Indian cities when suitable drainage and terrain datasets are available.

---

# 🎯 Impact

JalDrishti AI aims to shift urban flood management from:

```text
Reactive
   ↓
"Water is already on the road"
```

to:

```text
Predictive
   ↓
"This road is expected to flood in 60 minutes"
```

This can enable authorities and emergency services to act before flooding reaches critical levels.

---

# 🔐 Legal & Ethics

* The system provides decision-support information; official public warnings remain the responsibility of authorized authorities.
* No personal data is collected by the system.
* OpenStreetMap data follows the ODbL license.
* Reclaim Chennai datasets are used under their stated license.
* Copernicus and NASA datasets follow their respective data policies.

---

# 👥 Team

### JalDrishti AI

**Annasaheb Dange College of Engineering and Technology, Ashta**

Team members:

* Arpita Surve
* Parth Lande
* Sharvil Ghatge
* Shravani Chougule
* Shreya Shete
* Amruta More

### Smart India Hackathon 2026

**Problem Statement:** 26085
**Organization:** Ministry of Earth Sciences (MoES)
**Department:** National Centre for Medium Range Weather Forecasting (NCMRWF)
**Category:** Software
**Theme:** Disaster Management

---

# 📁 Project Structure

```text
JalDrishti-AI/
│
├── backend/
│   ├── api/
│   ├── routing/
│   └── services/
│
├── models/
│   ├── rainfall/
│   ├── swmm/
│   ├── terrain/
│   └── surface_flow/
│
├── data/
│   ├── rainfall/
│   ├── terrain/
│   ├── drainage/
│   └── roads/
│
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
│
├── notebooks/
│
├── tests/
│
├── requirements.txt
├── README.md
└── LICENSE
```

> Update the structure above to match the actual folders in your GitHub repository.

---

# ⭐ Why JalDrishti AI?

JalDrishti AI brings multiple components together into one operational pipeline:

**Rainfall → Nowcast → Runoff → Drainage → Surface Flow → Road Depth → Routing → Alerts**

Instead of only showing existing flood conditions, the system focuses on **forecasting future street-level flooding and helping people choose safer routes before they reach the flooded road.**

---

## 📚 References

* EPA Storm Water Management Model (SWMM)
* NASA GPM IMERG
* Copernicus GLO-30 DEM
* OpenStreetMap
* Open-Meteo
* RainViewer
* GCC Storm Water Drainage Survey
* Reclaim Chennai
* C-FLOWS
* IMD SWIRLS
* PySTEPS

---

## 📜 License

Add your project's license here, for example:

```text
MIT License
```

---

## ⭐ Support the Project

If you find **JalDrishti AI** useful, consider giving the repository a ⭐ on GitHub.

**Built for safer, smarter and more resilient cities. 🌧️🌊🏙️**
