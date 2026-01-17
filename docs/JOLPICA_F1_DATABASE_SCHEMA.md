# Jolpica F1 Database Schema Documentation

This document provides a comprehensive catalog of tables, fields, and field types for the Jolpica F1 database, which stores Formula 1 racing data from the modern era through historical seasons.

## Overview

The Jolpica F1 database is designed to handle the complexity of Formula 1 racing including:
- Multiple scoring systems across different eras
- Detailed race weekend sessions (practice, qualifying, sprint races)
- Championship standings and adjustments
- Team and driver relationships
- Comprehensive timing and pit stop data

## Core Entity Tables

### 1. base_teams
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| name | VARCHAR(255) | Base team name |

### 2. teams (Constructors)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| base_team_id | INTEGER REFERENCES base_teams(id) | Link to base team |
| country_code | VARCHAR(10) | 3-letter ISO country code |
| name | VARCHAR(255) | Team name |
| nationality | VARCHAR(100) | Team nationality |
| reference | VARCHAR(100) | Reference code |
| wikipedia | TEXT | Wikipedia URL |
| primary_color | VARCHAR(7) | Hex color code |

### 3. drivers
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| abbreviation | VARCHAR(10) | Driver abbreviation |
| country_code | VARCHAR(10) | 3-letter ISO country code |
| date_of_birth | DATE | Birth date |
| forename | VARCHAR(100) | First name |
| nationality | VARCHAR(100) | Nationality |
| permanent_car_number | INTEGER | Permanent driver number |
| reference | VARCHAR(100) | Reference code |
| surname | VARCHAR(100) | Last name |
| wikipedia | TEXT | Wikipedia URL |

### 4. circuits
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| altitude | INTEGER | Circuit altitude |
| country | VARCHAR(100) | Country name |
| country_code | VARCHAR(10) | 3-letter ISO country code |
| latitude | FLOAT | Latitude coordinate |
| locality | VARCHAR(100) | City/location |
| longitude | FLOAT | Longitude coordinate |
| name | VARCHAR(255) | Circuit name |
| reference | VARCHAR(100) | Reference code |
| wikipedia | TEXT | Wikipedia URL |

## Season and Championship Tables

### 5. seasons
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| championship_system_id | INTEGER REFERENCES championship_systems(id) | Scoring system |
| wikipedia | TEXT | Wikipedia URL |
| year | INTEGER | Season year |

### 6. championship_systems
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| driver_best_results | INTEGER | Best results counted |
| driver_season_split | INTEGER | Season split method |
| eligibility | INTEGER | Eligibility criteria |
| name | VARCHAR(255) | System name |
| reference | VARCHAR(100) | Reference code |
| team_best_results | INTEGER | Team best results |
| team_points_per_session | INTEGER | Points calculation |
| team_season_split | INTEGER | Team season split |

### 7. point_systems
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| driver_fastest_lap | INTEGER | Fastest lap points |
| driver_position_points | TEXT | Position points (CSV/JSON) |
| is_double_points | BOOLEAN | Double points flag |
| name | VARCHAR(255) | System name |
| partial | INTEGER | Partial point rules |
| reference | VARCHAR(100) | Reference code |
| shared_drive | INTEGER | Shared drive points |
| team_fastest_lap | INTEGER | Team fastest lap points |
| team_position_points | TEXT | Team position points |

## Race Weekend Tables

### 8. rounds (Races)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| circuit_id | INTEGER REFERENCES circuits(id) | Circuit |
| date | DATE | Race date |
| is_cancelled | BOOLEAN | Cancellation flag |
| name | VARCHAR(255) | Race name |
| number | INTEGER | Round number |
| race_number | INTEGER | Race number |
| season_id | INTEGER REFERENCES seasons(id) | Season |
| wikipedia | TEXT | Wikipedia URL |

### 9. sessions
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| has_time_data | BOOLEAN | Time data available |
| is_cancelled | BOOLEAN | Cancellation flag |
| number | INTEGER | Session number |
| point_system_id | INTEGER REFERENCES point_systems(id) | Scoring system |
| round_id | INTEGER REFERENCES rounds(id) | Round |
| scheduled_laps | INTEGER | Planned laps |
| timestamp | TIMESTAMP WITH TIME ZONE | Start time |
| timezone | VARCHAR(50) | Timezone |
| type | VARCHAR(10) | Session type (R, Q, FP1, etc.) |

### 10. team_drivers (Link Table)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| driver_id | INTEGER REFERENCES drivers(id) | Driver |
| role | VARCHAR(50) | Role (PERMANENT, RESERVE, JUNIOR) |
| season_id | INTEGER REFERENCES seasons(id) | Season |
| team_id | INTEGER REFERENCES teams(id) | Team |

### 11. round_entries
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| car_number | INTEGER | Car number |
| round_id | INTEGER REFERENCES rounds(id) | Round |
| team_driver_id | INTEGER REFERENCES team_drivers(id) | Team driver |

### 12. session_entries (Results)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| detail | TEXT | Status detail |
| fastest_lap_rank | INTEGER | Fastest lap rank |
| grid | INTEGER | Grid position |
| is_classified | BOOLEAN | Classification flag |
| is_eligible_for_points | BOOLEAN | Points eligibility |
| laps_completed | INTEGER | Laps completed |
| points | FLOAT | Points earned |
| position | INTEGER | Finishing position |
| round_entry_id | INTEGER REFERENCES round_entries(id) | Round entry |
| session_id | INTEGER REFERENCES sessions(id) | Session |
| status | INTEGER | Status code |
| time | VARCHAR(50) | Race time/interval |

## Detailed Data Tables

### 13. laps
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| average_speed | FLOAT | Average speed |
| is_deleted | BOOLEAN | Deletion flag |
| is_entry_fastest_lap | BOOLEAN | Fastest lap flag |
| number | INTEGER | Lap number |
| position | INTEGER | Position |
| session_entry_id | INTEGER REFERENCES session_entries(id) | Session entry |
| time | VARCHAR(50) | Lap time |

### 14. pitstops
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| duration | VARCHAR(50) | Pit stop duration |
| lap_id | INTEGER REFERENCES laps(id) | Lap |
| local_timestamp | TIME | Local timestamp |
| number | INTEGER | Pit stop number |
| session_entry_id | INTEGER REFERENCES session_entries(id) | Session entry |

### 15. penalties
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| earned_id | INTEGER | Dynamic reference |
| is_time_served_in_pit | BOOLEAN | Time served flag |
| license_points | INTEGER | License points |
| position | INTEGER | Position penalty |
| served_id | INTEGER | Served reference |
| time | VARCHAR(50) | Time penalty |

## Championship Tables

### 16. championship_adjustments
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| adjustment | INTEGER | Adjustment type |
| api_id | VARCHAR(50) | API identifier |
| driver_id | INTEGER REFERENCES drivers(id) | Driver |
| points | FLOAT | Points adjustment |
| season_id | INTEGER REFERENCES seasons(id) | Season |
| team_id | INTEGER REFERENCES teams(id) | Team |

### 17. driver_championships
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| adjustment_type | INTEGER | Adjustment type |
| driver_id | INTEGER REFERENCES drivers(id) | Driver |
| highest_finish | INTEGER | Best finish |
| is_eligible | BOOLEAN | Championship eligibility |
| points | FLOAT | Championship points |
| position | INTEGER | Championship position |
| round_id | INTEGER | Round when calculated |
| round_number | INTEGER | Round number |
| season_id | INTEGER REFERENCES seasons(id) | Season |
| session_id | INTEGER REFERENCES sessions(id) | Session |
| session_number | INTEGER | Session number |
| win_count | INTEGER | Number of wins |
| year | INTEGER | Season year |

### 18. team_championships
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| adjustment_type | INTEGER | Adjustment type |
| highest_finish | INTEGER | Best finish |
| is_eligible | BOOLEAN | Championship eligibility |
| points | FLOAT | Championship points |
| position | INTEGER | Championship position |
| round_id | INTEGER | Round when calculated |
| round_number | INTEGER | Round number |
| season_id | INTEGER REFERENCES seasons(id) | Season |
| session_id | INTEGER REFERENCES sessions(id) | Session |
| session_number | INTEGER | Session number |
| team_id | INTEGER REFERENCES teams(id) | Team |
| win_count | INTEGER | Number of wins |
| year | INTEGER | Season year |

## Enums and Reference Data

### Session Types
| Code | Description |
|------|-------------|
| R | Race |
| Q1/Q2/Q3 | Qualifying sessions |
| FP1/FP2/FP3 | Practice sessions |
| SR | Sprint Race |
| SQ1/SQ2/SQ3 | Sprint Qualifying |

### Session Status Codes
| Code | Description |
|------|-------------|
| 0 | Finished |
| 1 | Lapped |
| 10 | Accident/Collision |
| 11 | Mechanical Retirement |
| 20 | Disqualified |
| 30 | Did Not Start |
| 40 | Did Not Qualify |

### Point System Rules
- **Position Points**: Various systems from 1950-2010 formats
- **Fastest Lap Points**: None, Any, Shared, Top 10, Top 10 + 50% race
- **Partial Points**: Various rules for shortened races

## Performance Indices

| Index | Table | Purpose |
|-------|-------|---------|
| idx_rounds_season | rounds | Fast season queries |
| idx_sessions_round | sessions | Fast round lookups |
| idx_round_entries_round | round_entries | Round entry queries |
| idx_session_entries_session | session_entries | Session results |
| idx_laps_session_entry | laps | Lap time queries |
| idx_seasons_year | seasons | Year-based lookups |
| idx_driver_championships_season | driver_championships | Driver standings |
| idx_team_championships_season | team_championships | Team standings |

## Schema Relationships

The database follows these key relationship patterns:
- **teams** → **team_drivers** → **drivers** (many-to-many relationship via seasons)
- **seasons** → **rounds** → **sessions** → **session_entries**
- **circuits** → **rounds** (circuit hosts multiple races over time)
- **championship_systems** and **point_systems** handle changing F1 regulations

This schema represents a modern, flexible approach to F1 data management capable of handling:
- Evolving F1 regulations and scoring systems
- Historical and contemporary race formats
- Comprehensive race weekend data
- Detailed championship tracking
- Performance analytics and timing data