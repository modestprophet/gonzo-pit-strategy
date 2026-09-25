# Jolpica F1 database schema

The Jolpica tables in schema `f1db` are defined by [migration 002](../src/gonzo_pit_strategy/db/migrations/002_jolpica_setup.sql). References below use that schema. Columns are nullable unless marked `PRIMARY KEY` or `NOT NULL`.

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
| country_code | VARCHAR(10) | Country code |
| name | VARCHAR(255) NOT NULL | Team name |
| nationality | VARCHAR(100) | Team nationality |
| reference | VARCHAR(100) | Reference code |
| wikipedia | TEXT | Wikipedia URL |

### 3. drivers
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| abbreviation | VARCHAR(10) | Driver abbreviation |
| country_code | VARCHAR(10) | Country code |
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
| country_code | VARCHAR(10) | Country code |
| latitude | FLOAT | Latitude coordinate |
| locality | VARCHAR(100) | City/location |
| longitude | FLOAT | Longitude coordinate |
| name | VARCHAR(255) NOT NULL | Circuit name |
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
| year | INTEGER NOT NULL | Season year |

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
| driver_fastest_lap | INTEGER | Driver fastest lap setting |
| driver_position_points | TEXT | Position points |
| is_double_points | BOOLEAN DEFAULT FALSE | Double points flag |
| name | VARCHAR(255) | System name |
| partial | INTEGER | Partial point rules |
| reference | VARCHAR(100) | Reference code |
| shared_drive | INTEGER | Shared drive points |
| team_fastest_lap | INTEGER | Team fastest lap setting |
| team_position_points | TEXT | Team position points |

## Race Weekend Tables

### 8. rounds (Races)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| circuit_id | INTEGER REFERENCES circuits(id) | Circuit |
| date | DATE | Race date |
| is_cancelled | BOOLEAN DEFAULT FALSE | Cancellation flag |
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
| has_time_data | BOOLEAN DEFAULT FALSE | Time data available |
| is_cancelled | BOOLEAN DEFAULT FALSE | Cancellation flag |
| number | INTEGER | Session number |
| point_system_id | INTEGER REFERENCES point_systems(id) | Scoring system |
| round_id | INTEGER REFERENCES rounds(id) | Round |
| scheduled_laps | INTEGER | Planned laps |
| timestamp | TIMESTAMP WITH TIME ZONE | Start time |
| timezone | VARCHAR(50) | Timezone |
| type | VARCHAR(10) | Session type code |

### 10. team_drivers (Link Table)
| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique identifier |
| api_id | VARCHAR(50) | API identifier |
| driver_id | INTEGER REFERENCES drivers(id) | Driver |
| role | VARCHAR(50) | Driver role |
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
| is_classified | BOOLEAN DEFAULT FALSE | Classification flag |
| is_eligible_for_points | BOOLEAN DEFAULT TRUE | Points eligibility |
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
| is_deleted | BOOLEAN DEFAULT FALSE | Deletion flag |
| is_entry_fastest_lap | BOOLEAN DEFAULT FALSE | Fastest lap flag |
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
| earned_id | INTEGER | Earned reference, no foreign key |
| is_time_served_in_pit | BOOLEAN DEFAULT FALSE | Time served flag |
| license_points | INTEGER | License points |
| position | INTEGER | Position penalty |
| served_id | INTEGER | Served reference, no foreign key |
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
| is_eligible | BOOLEAN DEFAULT TRUE | Championship eligibility |
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
| is_eligible | BOOLEAN DEFAULT TRUE | Championship eligibility |
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
