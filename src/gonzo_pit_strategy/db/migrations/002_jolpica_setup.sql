-- +goose Up
-- Jolpica F1 Data Schema

-- 0. Base Tables & Systems
CREATE TABLE f1db.base_teams (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    name VARCHAR(255)
);

CREATE TABLE f1db.championship_systems (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    driver_best_results INTEGER,
    driver_season_split INTEGER,
    eligibility INTEGER,
    name VARCHAR(255),
    reference VARCHAR(100),
    team_best_results INTEGER,
    team_points_per_session INTEGER,
    team_season_split INTEGER
);

CREATE TABLE f1db.point_systems (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    driver_fastest_lap INTEGER,
    driver_position_points TEXT, -- CSV string or JSON? Keeping generic text for now based on header possibility
    is_double_points BOOLEAN DEFAULT FALSE,
    name VARCHAR(255),
    partial INTEGER,
    reference VARCHAR(100),
    shared_drive INTEGER,
    team_fastest_lap INTEGER,
    team_position_points TEXT
);

-- 1. Seasons
CREATE TABLE f1db.seasons (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    championship_system_id INTEGER REFERENCES f1db.championship_systems(id),
    wikipedia TEXT,
    year INTEGER NOT NULL
);

-- 2. Circuits
CREATE TABLE f1db.circuits (
    id INTEGER PRIMARY KEY,
    altitude INTEGER,
    api_id VARCHAR(50),
    country VARCHAR(100),
    country_code VARCHAR(10),
    latitude FLOAT,
    locality VARCHAR(100),
    longitude FLOAT,
    name VARCHAR(255) NOT NULL,
    reference VARCHAR(100),
    wikipedia TEXT
);

-- 3. Drivers
CREATE TABLE f1db.drivers (
    id INTEGER PRIMARY KEY,
    abbreviation VARCHAR(10),
    api_id VARCHAR(50),
    country_code VARCHAR(10),
    date_of_birth DATE,
    forename VARCHAR(100),
    nationality VARCHAR(100),
    permanent_car_number INTEGER,
    reference VARCHAR(100),
    surname VARCHAR(100),
    wikipedia TEXT
);

-- 4. Teams (Constructors)
CREATE TABLE f1db.teams (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    base_team_id INTEGER REFERENCES f1db.base_teams(id),
    country_code VARCHAR(10),
    name VARCHAR(255) NOT NULL,
    nationality VARCHAR(100),
    reference VARCHAR(100),
    wikipedia TEXT
);

-- 5. Team Drivers (Link table: Season <-> Team <-> Driver)
CREATE TABLE f1db.team_drivers (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    driver_id INTEGER REFERENCES f1db.drivers(id),
    role VARCHAR(50),
    season_id INTEGER REFERENCES f1db.seasons(id),
    team_id INTEGER REFERENCES f1db.teams(id)
);

-- 6. Rounds (Races)
CREATE TABLE f1db.rounds (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    circuit_id INTEGER REFERENCES f1db.circuits(id),
    date DATE,
    is_cancelled BOOLEAN DEFAULT FALSE,
    name VARCHAR(255),
    number INTEGER,
    race_number INTEGER,
    season_id INTEGER REFERENCES f1db.seasons(id),
    wikipedia TEXT
);

-- 7. Sessions (e.g. FP1, Quali, Race)
CREATE TABLE f1db.sessions (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    has_time_data BOOLEAN DEFAULT FALSE,
    is_cancelled BOOLEAN DEFAULT FALSE,
    number INTEGER,
    point_system_id INTEGER REFERENCES f1db.point_systems(id),
    round_id INTEGER REFERENCES f1db.rounds(id),
    scheduled_laps INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE,
    timezone VARCHAR(50),
    type VARCHAR(10) -- 'R', 'Q', 'FP1', etc.
);

-- 8. Round Entries (Driver/Team participation in a Round)
CREATE TABLE f1db.round_entries (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    car_number INTEGER,
    round_id INTEGER REFERENCES f1db.rounds(id),
    team_driver_id INTEGER REFERENCES f1db.team_drivers(id)
);

-- 9. Session Entries (Results)
CREATE TABLE f1db.session_entries (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    detail TEXT,
    fastest_lap_rank INTEGER,
    grid INTEGER,
    is_classified BOOLEAN DEFAULT FALSE,
    is_eligible_for_points BOOLEAN DEFAULT TRUE,
    laps_completed INTEGER,
    points FLOAT,
    position INTEGER,
    round_entry_id INTEGER REFERENCES f1db.round_entries(id),
    session_id INTEGER REFERENCES f1db.sessions(id),
    status INTEGER,
    time VARCHAR(50) -- Kept as string for duration/interval parsing flexibility
);

-- 10. Laps
CREATE TABLE f1db.laps (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    average_speed FLOAT,
    is_deleted BOOLEAN DEFAULT FALSE,
    is_entry_fastest_lap BOOLEAN DEFAULT FALSE,
    number INTEGER,
    position INTEGER,
    session_entry_id INTEGER REFERENCES f1db.session_entries(id),
    time VARCHAR(50) -- Duration string
);

-- 11. Pitstops
CREATE TABLE f1db.pitstops (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    duration VARCHAR(50),
    lap_id INTEGER REFERENCES f1db.laps(id),
    local_timestamp TIME, -- or string if time zone issues
    number INTEGER,
    session_entry_id INTEGER REFERENCES f1db.session_entries(id)
);

-- 12. Penalties
CREATE TABLE f1db.penalties (
    id INTEGER PRIMARY KEY,
    api_id VARCHAR(50),
    earned_id INTEGER, -- Dynamic reference (likely lap or session_entry)
    is_time_served_in_pit BOOLEAN DEFAULT FALSE,
    license_points INTEGER,
    position INTEGER,
    served_id INTEGER,
    time VARCHAR(50)
);

-- 13. Championship Adjustments
CREATE TABLE f1db.championship_adjustments (
    id INTEGER PRIMARY KEY,
    adjustment INTEGER,
    api_id VARCHAR(50),
    driver_id INTEGER REFERENCES f1db.drivers(id),
    points FLOAT,
    season_id INTEGER REFERENCES f1db.seasons(id),
    team_id INTEGER REFERENCES f1db.teams(id)
);

-- 14. Driver Championships
CREATE TABLE f1db.driver_championships (
    id INTEGER PRIMARY KEY,
    adjustment_type INTEGER,
    driver_id INTEGER REFERENCES f1db.drivers(id),
    highest_finish INTEGER,
    is_eligible BOOLEAN DEFAULT TRUE,
    points FLOAT,
    position INTEGER,
    round_id INTEGER, -- Nullable if mid-season or final
    round_number INTEGER,
    season_id INTEGER REFERENCES f1db.seasons(id),
    session_id INTEGER REFERENCES f1db.sessions(id),
    session_number INTEGER,
    win_count INTEGER,
    year INTEGER
);

-- 15. Team Championships
CREATE TABLE f1db.team_championships (
    id INTEGER PRIMARY KEY,
    adjustment_type INTEGER,
    highest_finish INTEGER,
    is_eligible BOOLEAN DEFAULT TRUE,
    points FLOAT,
    position INTEGER,
    round_id INTEGER,
    round_number INTEGER,
    season_id INTEGER REFERENCES f1db.seasons(id),
    session_id INTEGER REFERENCES f1db.sessions(id),
    session_number INTEGER,
    team_id INTEGER REFERENCES f1db.teams(id),
    win_count INTEGER,
    year INTEGER
);

-- Indexes for performance
CREATE INDEX idx_rounds_season ON f1db.rounds(season_id);
CREATE INDEX idx_sessions_round ON f1db.sessions(round_id);
CREATE INDEX idx_round_entries_round ON f1db.round_entries(round_id);
CREATE INDEX idx_session_entries_session ON f1db.session_entries(session_id);
CREATE INDEX idx_laps_session_entry ON f1db.laps(session_entry_id);
CREATE INDEX idx_seasons_year ON f1db.seasons(year);
CREATE INDEX idx_driver_championships_season ON f1db.driver_championships(season_id);
CREATE INDEX idx_team_championships_season ON f1db.team_championships(season_id);

-- +goose Down
DROP TABLE IF EXISTS f1db.team_championships;
DROP TABLE IF EXISTS f1db.driver_championships;
DROP TABLE IF EXISTS f1db.championship_adjustments;
DROP TABLE IF EXISTS f1db.penalties;
DROP TABLE IF EXISTS f1db.pitstops;
DROP TABLE IF EXISTS f1db.laps;
DROP TABLE IF EXISTS f1db.session_entries;
DROP TABLE IF EXISTS f1db.round_entries;
DROP TABLE IF EXISTS f1db.sessions;
DROP TABLE IF EXISTS f1db.rounds;
DROP TABLE IF EXISTS f1db.team_drivers;
DROP TABLE IF EXISTS f1db.teams;
DROP TABLE IF EXISTS f1db.drivers;
DROP TABLE IF EXISTS f1db.circuits;
DROP TABLE IF EXISTS f1db.seasons;
DROP TABLE IF EXISTS f1db.point_systems;
DROP TABLE IF EXISTS f1db.championship_systems;
DROP TABLE IF EXISTS f1db.base_teams;
