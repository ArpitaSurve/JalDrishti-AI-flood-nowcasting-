# 🌧️ JalDrishti AI

### Urban Flood Nowcasting through Rainfall–Runoff–Drainage Coupling

> **From rainfall forecasts to street-level flood-risk intelligence.**

[![Smart India Hackathon 2026](https://img.shields.io/badge/Smart%20India%20Hackathon-2026-blue)]()
[![Problem Statement](https://img.shields.io/badge/SIH26085-Urban%20Flood%20Nowcasting-0A66C2)]()
[![Domain](https://img.shields.io/badge/Domain-Disaster%20Management-orange)]()
[![Prototype Area](https://img.shields.io/badge/Prototype-Velachery%2C%20Chennai-teal)]()

---

## 📌 Overview

**JalDrishti AI** is an urban flood nowcasting prototype developed for **SIH26085 — Urban Flood Nowcasting System (Drainage and Rainfall Coupling)** under the Ministry of Earth Sciences (MoES).

The system addresses a key limitation of rainfall-only flood forecasting:

> **Rainfall alone does not determine where an urban flood will occur.**

JalDrishti AI couples:

**Rainfall → Runoff → Drainage Network → Effective Capacity → Segment-Level Flood Risk**

The prototype focuses on **Velachery, Chennai**, with upstream contributing areas included for inflow modeling.

---

## 🎯 Problem Statement

### SIH26085 — Urban Flood Nowcasting System (Drainage and Rainfall Coupling)

**Ministry:** Ministry of Earth Sciences (MoES)
**Theme:** Disaster Management
**Category:** Software

Traditional rainfall forecasts indicate how much rain may occur, but they do not directly identify which streets or drainage segments are likely to become waterlogged.

Urban flooding is influenced by:

* rainfall intensity and duration
* local elevation and terrain
* impervious surfaces
* upstream inflow
* drainage-network structure
* drainage bottlenecks
* historically recurring waterlogging

JalDrishti AI models these factors together.

---

## 💡 Solution

```text
IMD Rainfall / Nowcast
          ↓
Rainfall Processing
          ↓
SCS-CN Rainfall → Runoff
          ↓
Drainage Network Graph
          ↓
Predicted Flow vs Effective Capacity
          ↓
Interpretable ML Risk Model
          ↓
Segment-Level Flood Risk
          ↓
Maps & Alerts
```

---

## 🧠 Core Technical Approach

### 1. Physics-Based Runoff

The **SCS Curve Number (SCS-CN)** methodology is used to estimate rainfall excess and runoff based on rainfall and land-surface characteristics.

### 2. Drainage Network Graph

The stormwater drainage system is represented as a **directed graph**:

```text
Small Drains
     ↓
Feeder Drains
     ↓
Main / Arterial Drains
     ↓
Outfall
```

This represents the directional movement of water through the drainage network.

### 3. Effective Capacity Inference

Real-time information about drain blockage, underground pipe condition, pump status, and continuous drain sensors is not available for the prototype.

Instead, **effective drainage capacity is inferred from historical flood recurrence**.

Locations that repeatedly experience flooding under comparatively lower rainfall conditions can indicate reduced effective drainage capacity.

### 4. Interpretable Machine Learning

A lightweight model such as **Logistic Regression or XGBoost** is used to learn relationships between rainfall/runoff conditions and historical flood occurrence.

Potential features include:

* rainfall intensity
* rainfall duration
* antecedent rainfall
* runoff estimate
* land-use characteristics
* drainage segment
* historical flood occurrence

### Core principle

> **Physics predicts what should happen; machine learning learns what actually happens under real-world drainage conditions.**

---

## 🗺️ Study Area

### Velachery, Chennai

The prototype focuses on **Velachery and upstream contributing areas**.

The drainage network is modeled as a connected system rather than treating Velachery as an isolated location.

```text
Upstream Areas
      ↓
Drainage Network
      ↓
Velachery
      ↓
Downstream / Outfall
```

---

## 📊 Data Sources

| Data Source                  | Purpose                    |
| ---------------------------- | -------------------------- |
| GCC Stormwater Drain KML/KMZ | Drainage-network structure |
| IMD rainfall data            | Historical rainfall        |
| IMD nowcasting information   | Short-range rainfall input |
| SRTM / Bhuvan DEM            | Elevation and terrain      |
| Sentinel-2 / Bhuvan          | Land-use information       |
| Historical flood reports     | Flood occurrence           |
| Cyclone Michaung data        | Historical backtest        |
| Published drainage reports   | Basin and drainage context |
| SCS-CN methodology           | Rainfall-runoff estimation |

---

## 🌊 Cyclone Michaung Backtest

The primary historical proof-of-concept event is:

### Cyclone Michaung — December 2023

Historical rainfall can be replayed through the pipeline as if it were arriving sequentially.

```text
Historical Rainfall
        ↓
JalDrishti AI
        ↓
Predicted Risk Segments
        ↓
Reported Flooded Locations
        ↓
Predicted vs Observed Comparison
```

The validation is treated as an **event-based historical backtest**, not as proof of universal model accuracy.

Performance metrics such as precision, recall, and spatial agreement should only be reported after the actual validation pipeline produces them.

---

## 🚦 Risk Classification

| Risk Level | Meaning                  | Action                       |
| ---------- | ------------------------ | ---------------------------- |
| 🟢 Low     | Low immediate flood risk | Monitor                      |
| 🟡 Medium  | Increasing flood risk    | Notify ward officials        |
| 🔴 High    | High flood risk          | Public alert / response flag |

The system is designed to provide both:

### Public View

Simple location-based warnings such as:

> **Avoid this road — high flood risk expected.**

### Official View

Detailed information including:

* drainage segments
* predicted risk
* rainfall conditions
* runoff
* upstream contribution
* inferred effective capacity
* affected locations

---

## 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │  IMD Rainfall Data   │
                    │ Historical / Nowcast │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Rainfall Processing  │
                    │ Intensity / Duration │
                    │ Antecedent Rainfall  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │     SCS-CN Model     │
                    │   Rainfall → Runoff  │
                    └──────────┬───────────┘
                               ↓
              ┌───────────────────────────────┐
              │    Drainage Network Graph     │
              │                               │
              │ Upstream → Feeder → Main     │
              │              → Outfall        │
              └──────────────┬────────────────┘
                             ↓
              ┌───────────────────────────────┐
              │ Effective Capacity Inference  │
              │ Historical Flood Recurrence   │
              └──────────────┬────────────────┘
                             ↓
              ┌───────────────────────────────┐
              │   Interpretable ML Model      │
              │ Logistic Regression / XGBoost │
              └──────────────┬────────────────┘
                             ↓
              ┌───────────────────────────────┐
              │     Segment-Level Risk        │
              │       Low / Medium / High     │
              └──────────────┬────────────────┘
                             ↓
              ┌───────────────────────────────┐
              │       Dashboard & Alerts      │
              └───────────────────────────────┘
```

---

## 🆚 What Makes JalDrishti AI Different?

JalDrishti AI is **not intended to replace existing government flood-warning systems**.

It focuses on a more localized decision-support problem:

```text
Rainfall Forecast
      ↓
How much rain?
      ↓
JalDrishti AI
      ↓
Where is the drainage system
likely to become stressed?
      ↓
Which segment should be flagged?
```

The key distinction is the coupling of:

**Rainfall + Runoff + Drainage Network + Effective Capacity + Historical Flood Recurrence**

for **segment-level flood-risk intelligence**.

---

## ⚠️ Data & Deployment Limitations

The prototype does not claim access to:

* live municipal drain sensors
* live blockage sensors
* underground pipe-condition monitoring
* live pump telemetry
* complete municipal SCADA infrastructure

These limitations are explicitly considered in the system design.

The effective capacity component is therefore treated as an **inferred parameter**, not a direct measurement of physical pipe condition.

---

## 🌊 Tidal Backwater

Chennai's drainage outfalls can be influenced by tidal conditions.
Tidal backwater/surcharge is therefore considered a technically relevant factor.
However, it is treated as a **conceptual future extension** unless a validated dataset and implementation are available.

---

## 📈 Scalability
The same processing pipeline can be adapted to additional wards where suitable drainage, rainfall, terrain, and historical flood data are available.

```text
New Ward
   +
Drainage Data
   +
Rainfall Data
   +
Flood History
   +
DEM / Land Use
        ↓
Same Processing Pipeline
```

The current prototype remains focused on **Velachery and its upstream contributing areas** rather than claiming immediate pan-India deployment.
## 🛠️ Technology Stack

### Data & Geospatial
* Python
* Pandas
* GeoPandas
* GIS
* NetworkX

### Hydrology
* SCS Curve Number methodology
* Rainfall-runoff estimation

### Machine Learning
* Scikit-learn
* Logistic Regression
* XGBoost

### Visualization

* Interactive maps
* Flood-risk overlays
* Alert visualization

### Development
* Git
* GitHub
* VS Code

## 📚 References

1. Smart India Hackathon 2026 — SIH26085, *Urban Flood Nowcasting System (Drainage and Rainfall Coupling)*, Ministry of Earth Sciences.
2. Greater Chennai Corporation — Stormwater Drain Department, ward-wise drainage information and KML/KMZ datasets.
3. Asian Development Bank — Environmental Monitoring Report, Chennai.
4. Greater Chennai Corporation — Missing Links Stormwater Drain EIA Report.
5. India Meteorological Department — Historical rainfall records and rainfall nowcasting information.
6. ISRO Bhuvan / SRTM — Digital Elevation Model and geospatial datasets.
7. OpenCity Chennai — Public stormwater-drain datasets.
8. USDA Natural Resources Conservation Service — Curve Number rainfall-runoff methodology.

---

# 👥 Team — JalDrishti AI

| Role                    | Responsibility                                      |
| ----------------------- | --------------------------------------------------- |
| Data Lead               | KML, rainfall and historical data collection        |
| Model A                 | Rainfall-runoff modeling and drainage graph         |
| Model B                 | Capacity inference and flood-risk model             |
| Backend / Integration   | Pipeline and system integration                     |
| Frontend / Dashboard    | Maps, visualization and alerts                      |
| Domain Research / Pitch | Research, documentation and evaluator communication |

---

## 🎯 Objective
JalDrishti AI aims to bridge the gap between:
**City-scale rainfall forecasting**
and
**Street-level flood-risk intelligence.**
> **The question is not only how much rain will fall — but where that rainfall is most likely to overwhelm the urban drainage system.**
---
### 🌧️ JalDrishti AI

**Smarter Drainage • Safer Cities**
