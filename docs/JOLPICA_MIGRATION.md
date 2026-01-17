# Jolpica Dataset Migration Summary

## Overview
This document details the migration from the legacy Ergast API dataset (TSV files) to the modern Jolpica F1 dataset (CSV files). The migration involves a complete schema overhaul, updating the database initialization process, replacing SQLAlchemy ORM models, and rewriting the data access repository.

## Status: Models & Repository Layer Complete
**Date:** January 16, 2026

The core database layer has been fully migrated. The application now uses the Jolpica schema structure.

## 1. Database Schema Changes

The schema has expanded from **13 tables** (Ergast) to **18 tables** (Jolpica).

### Key Structural Shifts
*   **Race vs. Round/Session:**
    *   *Old:* A single `races` table contained dates/times for FP1, FP2, FP3, Quali, Sprint.
    *   *New:* A `rounds` table represents the event weekend. A linked `sessions` table contains individual rows for every session type (`FP1`, `FP2`, `FP3`, `Q1`, `Q2`, `Q3`, `R`, `SR`, etc.).
*   **Qualifying:**
    *   *Old:* Single `qualifying` table with `q1`, `q2`, `q3` columns.
    *   *New:* Qualifying consists of separate sessions (`type='Q1'`, etc.). Results are stored in `session_entries`.
*   **Results:**
    *   *Old:* Separate `results`, `sprint_results`, `qualifying` tables.
    *   *New:* Unified `session_entries` table. The `session.type` determines if it's a race result, qualifying result, etc.
*   **Constructors -> Teams:**
    *   Renamed table and entities to `Teams`. Added `BaseTeam` for parent organizations.

### New Tables
*   `base_teams`
*   `championship_systems`
*   `point_systems`
*   `team_drivers` (Season-level driver/team assignments)
*   `round_entries` (Driver participation per round)
*   `penalties`
*   `championship_adjustments`

## 2. Codebase Updates

### Database Setup (`gonzo_pit_strategy/utils/`)
*   **`db_setup.py`**: Updated to load the Jolpica CSV set (`formula_one_*.csv`).
*   **`db_utils.py`**: Connection string logic maintained.
*   **Migrations**: Added `002_jolpica_setup.sql`.

### ORM Models (`db/models/f1_models.py`)
Replaced the entire file. All models now map to the `f1db` schema tables in Postgres.

| New Model | Notes |
|-----------|-------|
| `Round` | Replaces `Race`. Links to `Session`. |
| `Session` | **New**. Critical for filtering data types (Race vs Quali). |
| `SessionEntry`| Replaces `Result`. Contains `position`, `points`, `status`, `time`. |
| `Team` | Replaces `Constructor`. |
| `DriverChampionship` | Replaces `DriverStanding`. |
| `TeamChampionship` | Replaces `ConstructorStanding`. |

### Data Repository (`db/repositories/data_repository.py`)
Complete rewrite of `F1DataRepository`.

*   **`get_all_race_history(year)`**:
    *   This is the primary feeder for the ML pipeline.
    *   **Logic Change**: It now constructs a "flat" view of a race by joining `rounds` -> `sessions(type='R')` -> `session_entries`.
    *   **Qualifying Handling**: Uses CTEs (Common Table Expressions) to aggregate `Q1`, `Q2`, `Q3` times from separate sessions into single rows for the race result, mimicking the old "wide" format.
*   **`get_round_results(round_id)`**: Replaces `get_race_results`.
*   **`get_lap_time_analysis`**: Updated for the new `laps` table which now links to `session_entries`.

## 3. Breaking Changes & Next Steps

### Column Naming Conventions
The `get_all_race_history` output columns have been standardized to snake_case and Jolpica native names. This affects downstream data pipelines.

| Concept | Old Column Name | New Column Name |
|---------|-----------------|-----------------|
| Round Number | `roundnumber` | `round_number` |
| Season Year | `raceyear` | `season_year` |
| Driver Code | `drivercode` | `driver_abbreviation` |
| Q1 Time | `q1` | `q1_time` |
| Q2 Time | `q2` | `q2_time` |
| Q3 Time | `q3` | `q3_time` |
| Finish Pos Text | `finishpositiontext` | `finish_position` (Note: Now Numeric/Int) |
| Grid | `startinggrid` | `grid` |
| Team Name | `constructorname` | `team_name` |

### Required Next Actions
1.  **Update Data Pipeline**: The `data_pipeline.py` and `pipeline_steps/` rely on old column names (e.g., `raceyear`). These must be mapped to the new schema.
3.  **Training Config**: Update `config/training.json` target column (currently `finishpositiontext`).
4.  **Notebooks**: Update `race_data_eda.ipynb` to use new columns.
