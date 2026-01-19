"""
SQLAlchemy ORM models for Jolpica F1 database schema.

This module defines all models for the Jolpica F1 data schema, which replaces
the previous Ergast schema. Key structural changes:
- Races are now 'rounds' with multiple 'sessions' (FP1, Q1, Q2, Q3, R, SR, etc.)
- Results are now 'session_entries' linked via round_entries and team_drivers
- Qualifying data is in separate Q1/Q2/Q3 sessions, not a single table
- Constructors are now 'teams' with optional base_team linkage
- Standings are now 'driver_championships' and 'team_championships'
"""
from sqlalchemy import (
    Column, Integer, String, Float, Date, Time, Boolean, Text,
    PrimaryKeyConstraint, Index, ForeignKey, TIMESTAMP
)
from sqlalchemy.orm import relationship
from gonzo_pit_strategy.db.base import Base


# =============================================================================
# Core Reference Tables
# =============================================================================

class BaseTeam(Base):
    """Parent team organizations (e.g., Red Bull Racing's parent company)."""
    __tablename__ = 'base_teams'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    name = Column(String(255))

    # Relationships
    teams = relationship("Team", back_populates="base_team")

    def __repr__(self):
        return f"<BaseTeam(id={self.id}, name='{self.name}')>"


class ChampionshipSystem(Base):
    """Championship rules and point allocation systems by era."""
    __tablename__ = 'championship_systems'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    driver_best_results = Column(Integer)
    driver_season_split = Column(Integer)
    eligibility = Column(Integer)
    name = Column(String(255))
    reference = Column(String(100))
    team_best_results = Column(Integer)
    team_points_per_session = Column(Integer)
    team_season_split = Column(Integer)

    # Relationships
    seasons = relationship("Season", back_populates="championship_system")

    def __repr__(self):
        return f"<ChampionshipSystem(id={self.id}, name='{self.name}')>"


class PointSystem(Base):
    """Points allocation rules for different session types."""
    __tablename__ = 'point_systems'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    driver_fastest_lap = Column(Integer)
    driver_position_points = Column(Text)  # CSV or JSON string
    is_double_points = Column(Boolean, default=False)
    name = Column(String(255))
    partial = Column(Integer)
    reference = Column(String(100))
    shared_drive = Column(Integer)
    team_fastest_lap = Column(Integer)
    team_position_points = Column(Text)

    # Relationships
    sessions = relationship("Session", back_populates="point_system")

    def __repr__(self):
        return f"<PointSystem(id={self.id}, name='{self.name}')>"


# =============================================================================
# Season and Circuit Tables
# =============================================================================

class Season(Base):
    """F1 seasons with championship system reference."""
    __tablename__ = 'seasons'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    championship_system_id = Column(Integer, ForeignKey('f1db.championship_systems.id'))
    wikipedia = Column(Text)
    year = Column(Integer, nullable=False)

    # Relationships
    championship_system = relationship("ChampionshipSystem", back_populates="seasons")
    rounds = relationship("Round", back_populates="season")
    team_drivers = relationship("TeamDriver", back_populates="season")
    driver_championships = relationship("DriverChampionship", back_populates="season")
    team_championships = relationship("TeamChampionship", back_populates="season")
    championship_adjustments = relationship("ChampionshipAdjustment", back_populates="season")

    def __repr__(self):
        return f"<Season(id={self.id}, year={self.year})>"


class Circuit(Base):
    """Racing circuits/tracks."""
    __tablename__ = 'circuits'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    altitude = Column(Integer)
    api_id = Column(String(50))
    country = Column(String(100))
    country_code = Column(String(10))
    latitude = Column(Float)
    locality = Column(String(100))
    longitude = Column(Float)
    name = Column(String(255), nullable=False)
    reference = Column(String(100))
    wikipedia = Column(Text)

    # Relationships
    rounds = relationship("Round", back_populates="circuit")

    def __repr__(self):
        return f"<Circuit(id={self.id}, name='{self.name}')>"


# =============================================================================
# Driver and Team Tables
# =============================================================================

class Driver(Base):
    """F1 drivers."""
    __tablename__ = 'drivers'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    abbreviation = Column(String(10))  # Was 'code' in Ergast
    api_id = Column(String(50))
    country_code = Column(String(10))
    date_of_birth = Column(Date)  # Was 'dob' in Ergast
    forename = Column(String(100))
    nationality = Column(String(100))
    permanent_car_number = Column(Integer)  # Was 'number' in Ergast
    reference = Column(String(100))  # Was 'driverref' in Ergast
    surname = Column(String(100))
    wikipedia = Column(Text)  # Was 'url' in Ergast

    # Relationships
    team_drivers = relationship("TeamDriver", back_populates="driver")
    driver_championships = relationship("DriverChampionship", back_populates="driver")
    championship_adjustments = relationship("ChampionshipAdjustment", back_populates="driver")

    @property
    def full_name(self):
        """Return driver's full name."""
        return f"{self.forename} {self.surname}"

    def __repr__(self):
        return f"<Driver(id={self.id}, name='{self.full_name}')>"


class Team(Base):
    """F1 teams (constructors)."""
    __tablename__ = 'teams'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    base_team_id = Column(Integer, ForeignKey('f1db.base_teams.id'))
    country_code = Column(String(10))
    name = Column(String(255), nullable=False)
    nationality = Column(String(100))
    reference = Column(String(100))  # Was 'constructorref' in Ergast
    wikipedia = Column(Text)  # Was 'url' in Ergast

    # Relationships
    base_team = relationship("BaseTeam", back_populates="teams")
    team_drivers = relationship("TeamDriver", back_populates="team")
    team_championships = relationship("TeamChampionship", back_populates="team")
    championship_adjustments = relationship("ChampionshipAdjustment", back_populates="team")

    def __repr__(self):
        return f"<Team(id={self.id}, name='{self.name}')>"


class TeamDriver(Base):
    """Season-level driver-team assignments."""
    __tablename__ = 'team_drivers'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    driver_id = Column(Integer, ForeignKey('f1db.drivers.id'))
    role = Column(String(50))
    season_id = Column(Integer, ForeignKey('f1db.seasons.id'))
    team_id = Column(Integer, ForeignKey('f1db.teams.id'))

    # Relationships
    driver = relationship("Driver", back_populates="team_drivers")
    season = relationship("Season", back_populates="team_drivers")
    team = relationship("Team", back_populates="team_drivers")
    round_entries = relationship("RoundEntry", back_populates="team_driver")

    def __repr__(self):
        return f"<TeamDriver(id={self.id}, driver_id={self.driver_id}, team_id={self.team_id}, season_id={self.season_id})>"


# =============================================================================
# Round and Session Tables
# =============================================================================

class Round(Base):
    """Race weekends (formerly 'races' in Ergast)."""
    __tablename__ = 'rounds'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    circuit_id = Column(Integer, ForeignKey('f1db.circuits.id'))
    date = Column(Date)
    is_cancelled = Column(Boolean, default=False)
    name = Column(String(255))
    number = Column(Integer)  # Round number in season
    race_number = Column(Integer)  # Actual race number (may differ if cancellations)
    season_id = Column(Integer, ForeignKey('f1db.seasons.id'))
    wikipedia = Column(Text)

    # Relationships
    circuit = relationship("Circuit", back_populates="rounds")
    season = relationship("Season", back_populates="rounds")
    sessions = relationship("Session", back_populates="round")
    round_entries = relationship("RoundEntry", back_populates="round")
    driver_championships = relationship("DriverChampionship", back_populates="round")
    team_championships = relationship("TeamChampionship", back_populates="round")

    def __repr__(self):
        return f"<Round(id={self.id}, name='{self.name}', number={self.number})>"


class Session(Base):
    """
    Individual sessions within a race weekend.
    
    Session types:
    - FP1, FP2, FP3: Free practice sessions
    - Q1, Q2, Q3: Qualifying sessions (modern format)
    - QB: Qualifying (legacy/combined)
    - QO: Qualifying (one-shot format)
    - QA: Qualifying (aggregate format)
    - SQ1, SQ2, SQ3: Sprint qualifying sessions
    - SR: Sprint race
    - R: Main race
    """
    __tablename__ = 'sessions'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    has_time_data = Column(Boolean, default=False)
    is_cancelled = Column(Boolean, default=False)
    number = Column(Integer)  # Session number within round
    point_system_id = Column(Integer, ForeignKey('f1db.point_systems.id'))
    round_id = Column(Integer, ForeignKey('f1db.rounds.id'))
    scheduled_laps = Column(Integer)
    timestamp = Column(TIMESTAMP(timezone=True))
    timezone = Column(String(50))
    type = Column(String(10))  # 'R', 'Q1', 'Q2', 'Q3', 'FP1', 'SR', etc.

    # Relationships
    point_system = relationship("PointSystem", back_populates="sessions")
    round = relationship("Round", back_populates="sessions")
    session_entries = relationship("SessionEntry", back_populates="session")
    driver_championships = relationship("DriverChampionship", back_populates="session")
    team_championships = relationship("TeamChampionship", back_populates="session")

    def __repr__(self):
        return f"<Session(id={self.id}, round_id={self.round_id}, type='{self.type}')>"


# =============================================================================
# Entry and Result Tables
# =============================================================================

class RoundEntry(Base):
    """Driver participation in a round (race weekend)."""
    __tablename__ = 'round_entries'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    car_number = Column(Integer)
    round_id = Column(Integer, ForeignKey('f1db.rounds.id'))
    team_driver_id = Column(Integer, ForeignKey('f1db.team_drivers.id'))

    # Relationships
    round = relationship("Round", back_populates="round_entries")
    team_driver = relationship("TeamDriver", back_populates="round_entries")
    session_entries = relationship("SessionEntry", back_populates="round_entry")

    def __repr__(self):
        return f"<RoundEntry(id={self.id}, round_id={self.round_id}, team_driver_id={self.team_driver_id})>"


class SessionEntry(Base):
    """
    Results for a driver in a specific session.
    
    This replaces the separate results, qualifying, and sprintresults tables
    from the Ergast schema. Each entry represents one driver's performance
    in one session (race, qualifying segment, practice, sprint, etc.)
    
    Status codes (integer):
    - 0: Finished
    - 1: +N Laps (lapped)
    - 10: Accident/Collision
    - 11: Mechanical/Technical
    - 20: Disqualified
    - 30: Did not start
    - 40: Excluded
    """
    __tablename__ = 'session_entries'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    detail = Column(Text)  # Human-readable status (e.g., "Finished", "+2 Laps", "Engine")
    fastest_lap_rank = Column(Integer)
    grid = Column(Integer)  # Starting position (for races)
    is_classified = Column(Boolean, default=False)
    is_eligible_for_points = Column(Boolean, default=True)
    laps_completed = Column(Integer)
    points = Column(Float)
    position = Column(Integer)  # Finish position
    round_entry_id = Column(Integer, ForeignKey('f1db.round_entries.id'))
    session_id = Column(Integer, ForeignKey('f1db.sessions.id'))
    status = Column(Integer)  # Status code (see docstring)
    time = Column(String(50))  # Duration/time string

    # Relationships
    round_entry = relationship("RoundEntry", back_populates="session_entries")
    session = relationship("Session", back_populates="session_entries")
    laps = relationship("Lap", back_populates="session_entry")
    pitstops = relationship("Pitstop", back_populates="session_entry")

    def __repr__(self):
        return f"<SessionEntry(id={self.id}, session_id={self.session_id}, position={self.position})>"


# =============================================================================
# Lap and Pitstop Tables
# =============================================================================

class Lap(Base):
    """Individual lap times within a session."""
    __tablename__ = 'laps'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    average_speed = Column(Float)
    is_deleted = Column(Boolean, default=False)
    is_entry_fastest_lap = Column(Boolean, default=False)
    number = Column(Integer)  # Lap number
    position = Column(Integer)  # Position at end of lap
    session_entry_id = Column(Integer, ForeignKey('f1db.session_entries.id'))
    time = Column(String(50))  # Lap time as duration string

    # Relationships
    session_entry = relationship("SessionEntry", back_populates="laps")
    pitstops = relationship("Pitstop", back_populates="lap")

    def __repr__(self):
        return f"<Lap(id={self.id}, session_entry_id={self.session_entry_id}, number={self.number})>"


class Pitstop(Base):
    """Pit stop records."""
    __tablename__ = 'pitstops'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    duration = Column(String(50))  # Pit stop duration
    lap_id = Column(Integer, ForeignKey('f1db.laps.id'))
    local_timestamp = Column(Time)  # Local time of pit stop
    number = Column(Integer)  # Pit stop number (1st, 2nd, etc.)
    session_entry_id = Column(Integer, ForeignKey('f1db.session_entries.id'))

    # Relationships
    lap = relationship("Lap", back_populates="pitstops")
    session_entry = relationship("SessionEntry", back_populates="pitstops")

    def __repr__(self):
        return f"<Pitstop(id={self.id}, session_entry_id={self.session_entry_id}, number={self.number})>"


# =============================================================================
# Penalty Table
# =============================================================================

class Penalty(Base):
    """Penalties issued during sessions."""
    __tablename__ = 'penalties'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    api_id = Column(String(50))
    earned_id = Column(Integer)  # Reference to lap or session_entry where penalty was earned
    is_time_served_in_pit = Column(Boolean, default=False)
    license_points = Column(Integer)  # Super license penalty points
    position = Column(Integer)  # Position penalty
    served_id = Column(Integer)  # Reference to where penalty was served
    time = Column(String(50))  # Time penalty

    def __repr__(self):
        return f"<Penalty(id={self.id}, time='{self.time}', position={self.position})>"


# =============================================================================
# Championship Tables
# =============================================================================

class ChampionshipAdjustment(Base):
    """Manual championship point adjustments (penalties, exclusions, etc.)."""
    __tablename__ = 'championship_adjustments'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    adjustment = Column(Integer)  # Adjustment type code
    api_id = Column(String(50))
    driver_id = Column(Integer, ForeignKey('f1db.drivers.id'))
    points = Column(Float)
    season_id = Column(Integer, ForeignKey('f1db.seasons.id'))
    team_id = Column(Integer, ForeignKey('f1db.teams.id'))

    # Relationships
    driver = relationship("Driver", back_populates="championship_adjustments")
    season = relationship("Season", back_populates="championship_adjustments")
    team = relationship("Team", back_populates="championship_adjustments")

    def __repr__(self):
        return f"<ChampionshipAdjustment(id={self.id}, points={self.points})>"


class DriverChampionship(Base):
    """Driver championship standings (snapshot after each session/round)."""
    __tablename__ = 'driver_championships'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    adjustment_type = Column(Integer)
    driver_id = Column(Integer, ForeignKey('f1db.drivers.id'))
    highest_finish = Column(Integer)
    is_eligible = Column(Boolean, default=True)
    points = Column(Float)
    position = Column(Integer)
    round_id = Column(Integer, ForeignKey('f1db.rounds.id'))
    round_number = Column(Integer)
    season_id = Column(Integer, ForeignKey('f1db.seasons.id'))
    session_id = Column(Integer, ForeignKey('f1db.sessions.id'))
    session_number = Column(Integer)
    win_count = Column(Integer)
    year = Column(Integer)

    # Relationships
    driver = relationship("Driver", back_populates="driver_championships")
    round = relationship("Round", back_populates="driver_championships")
    season = relationship("Season", back_populates="driver_championships")
    session = relationship("Session", back_populates="driver_championships")

    def __repr__(self):
        return f"<DriverChampionship(id={self.id}, driver_id={self.driver_id}, position={self.position}, points={self.points})>"


class TeamChampionship(Base):
    """Team (constructor) championship standings (snapshot after each session/round)."""
    __tablename__ = 'team_championships'
    __table_args__ = {'schema': 'f1db'}

    id = Column(Integer, primary_key=True)
    adjustment_type = Column(Integer)
    highest_finish = Column(Integer)
    is_eligible = Column(Boolean, default=True)
    points = Column(Float)
    position = Column(Integer)
    round_id = Column(Integer, ForeignKey('f1db.rounds.id'))
    round_number = Column(Integer)
    season_id = Column(Integer, ForeignKey('f1db.seasons.id'))
    session_id = Column(Integer, ForeignKey('f1db.sessions.id'))
    session_number = Column(Integer)
    team_id = Column(Integer, ForeignKey('f1db.teams.id'))
    win_count = Column(Integer)
    year = Column(Integer)

    # Relationships
    round = relationship("Round", back_populates="team_championships")
    season = relationship("Season", back_populates="team_championships")
    session = relationship("Session", back_populates="team_championships")
    team = relationship("Team", back_populates="team_championships")

    def __repr__(self):
        return f"<TeamChampionship(id={self.id}, team_id={self.team_id}, position={self.position}, points={self.points})>"
