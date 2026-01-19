"""
Repository for F1 data access (Jolpica schema).

This module provides methods to access Formula 1 data from the database,
using both SQLAlchemy ORM and raw SQL queries when needed.

Key changes from Ergast schema:
- Races are now 'rounds' with multiple 'sessions'
- Results are now 'session_entries' linked via round_entries and team_drivers
- Qualifying data is in separate Q1/Q2/Q3 sessions
- Constructors are now 'teams'
- Standings are now 'driver_championships' and 'team_championships'
"""
from typing import List, Dict, Any, Optional, TypeVar, Type

import pandas as pd
from sqlalchemy import text

from gonzo_pit_strategy.db.base import db_session, Base
from gonzo_pit_strategy.db.models.f1_models import (
    BaseTeam, ChampionshipSystem, PointSystem,
    Season, Circuit, Driver, Team, TeamDriver,
    Round, Session, RoundEntry, SessionEntry,
    Lap, Pitstop, Penalty,
    ChampionshipAdjustment, DriverChampionship, TeamChampionship
)
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T', bound=Base)


class F1DataRepository:
    """Repository for accessing F1 data from the database (Jolpica schema)."""

    # =========================================================================
    # Generic CRUD Methods
    # =========================================================================

    @staticmethod
    def get_all(model_class: Type[T]) -> List[T]:
        """Get all records for a given model.

        Args:
            model_class: The SQLAlchemy model class

        Returns:
            List of model instances
        """
        with db_session() as session:
            logger.debug(f"Fetching all records from {model_class.__tablename__}")
            return session.query(model_class).all()

    @staticmethod
    def get_by_id(model_class: Type[T], id_value: Any) -> Optional[T]:
        """Get a record by its primary key.

        Args:
            model_class: The SQLAlchemy model class
            id_value: The primary key value

        Returns:
            Model instance or None if not found
        """
        primary_key = model_class.__mapper__.primary_key[0].name
        with db_session() as session:
            logger.debug(f"Fetching {model_class.__tablename__} with {primary_key}={id_value}")
            return session.query(model_class).filter(
                getattr(model_class, primary_key) == id_value
            ).first()

    @staticmethod
    def filter_by(model_class: Type[T], **kwargs) -> List[T]:
        """Filter records by the given criteria.

        Args:
            model_class: The SQLAlchemy model class
            **kwargs: Filter criteria

        Returns:
            List of model instances matching the criteria
        """
        with db_session() as session:
            logger.debug(f"Filtering {model_class.__tablename__} by {kwargs}")
            return session.query(model_class).filter_by(**kwargs).all()

    @staticmethod
    def execute_raw_sql(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a raw SQL query.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of dictionaries containing the query results
        """
        with db_session() as session:
            logger.debug(f"Executing raw SQL: {sql[:100]}...")
            result = session.execute(text(sql), params or {})
            return [dict(row._mapping) for row in result]

    @staticmethod
    def execute_raw_sql_to_df(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Execute a raw SQL query and return results as a pandas DataFrame.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            pandas DataFrame containing the query results
        """
        with db_session() as session:
            logger.debug(f"Executing raw SQL to DataFrame: {sql[:100]}...")
            result = session.execute(text(sql), params or {})
            return pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    # =========================================================================
    # Session Entry (Results) Methods
    # =========================================================================

    @staticmethod
    def get_session_entries_by_round(
        round_id: int,
        session_type: Optional[str] = 'R'
    ) -> List[SessionEntry]:
        """Get session entries for a specific round and session type.

        Args:
            round_id: The round ID
            session_type: Session type filter ('R' for race, 'Q1', 'Q2', 'Q3', etc.)

        Returns:
            List of SessionEntry objects
        """
        with db_session() as session:
            query = session.query(SessionEntry).join(
                Session, SessionEntry.session_id == Session.id
            ).filter(Session.round_id == round_id)
            
            if session_type:
                query = query.filter(Session.type == session_type)
            
            return query.all()

    @staticmethod
    def get_round_results(round_id: int) -> pd.DataFrame:
        """Get detailed race results for a specific round.

        Args:
            round_id: The round ID

        Returns:
            DataFrame with race results including driver and team information
        """
        sql = """
        SELECT 
            se.id AS session_entry_id,
            r.id AS round_id,
            r.name AS round_name,
            s.type AS session_type,
            d.id AS driver_id,
            d.abbreviation AS driver_abbreviation,
            d.forename || ' ' || d.surname AS driver_name,
            t.id AS team_id,
            t.name AS team_name,
            se.position,
            se.grid,
            se.points,
            se.laps_completed,
            se.time,
            se.status,
            se.detail AS status_detail,
            se.fastest_lap_rank
        FROM f1db.session_entries se
        JOIN f1db.sessions s ON se.session_id = s.id
        JOIN f1db.rounds r ON s.round_id = r.id
        JOIN f1db.round_entries re ON se.round_entry_id = re.id
        JOIN f1db.team_drivers td ON re.team_driver_id = td.id
        JOIN f1db.drivers d ON td.driver_id = d.id
        JOIN f1db.teams t ON td.team_id = t.id
        WHERE r.id = :round_id AND s.type = 'R'
        ORDER BY se.position NULLS LAST
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {"round_id": round_id})

    # =========================================================================
    # Pitstop Methods
    # =========================================================================

    @staticmethod
    def get_pitstops_by_round_and_driver(round_id: int, driver_id: int) -> List[Pitstop]:
        """Get all pit stops for a specific round and driver.

        Args:
            round_id: The round ID
            driver_id: The driver ID

        Returns:
            List of Pitstop objects
        """
        with db_session() as session:
            return session.query(Pitstop).join(
                SessionEntry, Pitstop.session_entry_id == SessionEntry.id
            ).join(
                Session, SessionEntry.session_id == Session.id
            ).join(
                RoundEntry, SessionEntry.round_entry_id == RoundEntry.id
            ).join(
                TeamDriver, RoundEntry.team_driver_id == TeamDriver.id
            ).filter(
                Session.round_id == round_id,
                TeamDriver.driver_id == driver_id,
                Session.type == 'R'  # Race session pitstops
            ).all()

    @staticmethod
    def get_pitstops_by_round(round_id: int) -> pd.DataFrame:
        """Get all pit stops for a specific round.

        Args:
            round_id: The round ID

        Returns:
            DataFrame with pit stop data
        """
        sql = """
        SELECT 
            p.id AS pitstop_id,
            r.id AS round_id,
            d.id AS driver_id,
            d.abbreviation AS driver_abbreviation,
            d.forename || ' ' || d.surname AS driver_name,
            t.name AS team_name,
            p.number AS stop_number,
            l.number AS lap_number,
            p.duration,
            p.local_timestamp
        FROM f1db.pitstops p
        JOIN f1db.session_entries se ON p.session_entry_id = se.id
        JOIN f1db.sessions s ON se.session_id = s.id
        JOIN f1db.rounds r ON s.round_id = r.id
        JOIN f1db.round_entries re ON se.round_entry_id = re.id
        JOIN f1db.team_drivers td ON re.team_driver_id = td.id
        JOIN f1db.drivers d ON td.driver_id = d.id
        JOIN f1db.teams t ON td.team_id = t.id
        LEFT JOIN f1db.laps l ON p.lap_id = l.id
        WHERE r.id = :round_id AND s.type = 'R'
        ORDER BY d.id, p.number
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {"round_id": round_id})

    # =========================================================================
    # Lap Time Methods
    # =========================================================================

    @staticmethod
    def get_lap_time_analysis(round_id: int, driver_id: Optional[int] = None) -> pd.DataFrame:
        """Get lap time analysis for a round, optionally filtered by driver.

        Args:
            round_id: The round ID
            driver_id: Optional driver ID to filter by

        Returns:
            DataFrame with lap time analysis
        """
        params: Dict[str, Any] = {"round_id": round_id}
        driver_filter = ""

        if driver_id is not None:
            driver_filter = "AND td.driver_id = :driver_id"
            params["driver_id"] = driver_id

        sql = f"""
        SELECT 
            r.id AS round_id,
            d.id AS driver_id,
            d.abbreviation AS driver_abbreviation,
            d.forename || ' ' || d.surname AS driver_name,
            l.number AS lap_number,
            l.position,
            l.time,
            l.average_speed,
            l.is_entry_fastest_lap,
            l.is_deleted
        FROM f1db.laps l
        JOIN f1db.session_entries se ON l.session_entry_id = se.id
        JOIN f1db.sessions s ON se.session_id = s.id
        JOIN f1db.rounds r ON s.round_id = r.id
        JOIN f1db.round_entries re ON se.round_entry_id = re.id
        JOIN f1db.team_drivers td ON re.team_driver_id = td.id
        JOIN f1db.drivers d ON td.driver_id = d.id
        WHERE r.id = :round_id AND s.type = 'R' {driver_filter}
        ORDER BY d.id, l.number
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, params)

    # =========================================================================
    # Main Race History Method
    # =========================================================================

    @staticmethod
    def get_all_race_history(year: Optional[int] = None) -> pd.DataFrame:
        """Get comprehensive race history data with qualifying and standings.

        This method returns a rich dataset containing race results, qualifying data,
        driver and team information, and championship standings from the Jolpica schema.

        The data structure joins:
        - rounds (race weekends)
        - sessions (R for race, Q1/Q2/Q3/QB for qualifying)
        - session_entries (results per driver per session)
        - round_entries -> team_drivers -> drivers, teams
        - circuits
        - seasons
        - driver_championships and team_championships (standings after each round)

        Qualifying times are retrieved from Q1, Q2, Q3 sessions (modern format) or
        QB sessions (legacy combined qualifying). The final qualifying position is
        determined from the last qualifying session the driver participated in.

        Args:
            year: Optional filter for a specific year/season

        Returns:
            DataFrame with columns:
            - round_id, circuit_id, circuit_name, season_year, round_date, round_number
            - team_id, team_name, driver_id, driver_abbreviation
            - q1_time, q2_time, q3_time, qualifying_position
            - grid, finish_position, status, status_detail
            - laps_completed, points, time, fastest_lap_rank
            - driver_championship_points, driver_championship_position, driver_wins
            - team_championship_points, team_championship_position, team_wins
        """
        params: Dict[str, Any] = {}
        year_filter = ""

        if year is not None:
            year_filter = "AND sn.year = :year"
            params["year"] = year

        # Main query joins race results with qualifying data via lateral subqueries
        # This handles both modern (Q1/Q2/Q3) and legacy (QB) qualifying formats
        sql = f"""
        WITH race_results AS (
            -- Get race session results
            SELECT 
                r.id AS round_id,
                r.circuit_id,
                c.name AS circuit_name,
                sn.year AS season_year,
                r.date AS round_date,
                r.number AS round_number,
                r.wikipedia AS round_url,
                t.id AS team_id,
                t.name AS team_name,
                d.id AS driver_id,
                d.abbreviation AS driver_abbreviation,
                re.id AS round_entry_id,
                se.grid,
                se.position AS finish_position,
                se.status,
                se.detail AS status_detail,
                se.laps_completed,
                se.points,
                se.time,
                se.fastest_lap_rank,
                s.id AS race_session_id
            FROM f1db.session_entries se
            JOIN f1db.sessions s ON se.session_id = s.id
            JOIN f1db.rounds r ON s.round_id = r.id
            JOIN f1db.seasons sn ON r.season_id = sn.id
            JOIN f1db.circuits c ON r.circuit_id = c.id
            JOIN f1db.round_entries re ON se.round_entry_id = re.id
            JOIN f1db.team_drivers td ON re.team_driver_id = td.id
            JOIN f1db.drivers d ON td.driver_id = d.id
            JOIN f1db.teams t ON td.team_id = t.id
            WHERE s.type = 'R'  -- Race sessions only
            AND r.is_cancelled = false
            {year_filter}
        ),
        qualifying_times AS (
            -- Get qualifying times from Q1, Q2, Q3 sessions
            -- For legacy data, QB sessions contain the overall qualifying result
            SELECT 
                re.id AS round_entry_id,
                MAX(CASE WHEN s.type = 'Q1' THEN se.time END) AS q1_time,
                MAX(CASE WHEN s.type = 'Q2' THEN se.time END) AS q2_time,
                MAX(CASE WHEN s.type = 'Q3' THEN se.time END) AS q3_time,
                -- For modern qualifying, position comes from their last session
                -- For legacy (QB), there's typically one session with position
                COALESCE(
                    MAX(CASE WHEN s.type = 'Q3' THEN se.position END),
                    MAX(CASE WHEN s.type = 'Q2' THEN se.position END),
                    MAX(CASE WHEN s.type = 'Q1' THEN se.position END),
                    MAX(CASE WHEN s.type = 'QB' THEN se.position END)
                ) AS qualifying_position
            FROM f1db.session_entries se
            JOIN f1db.sessions s ON se.session_id = s.id
            JOIN f1db.round_entries re ON se.round_entry_id = re.id
            WHERE s.type IN ('Q1', 'Q2', 'Q3', 'QB')
            GROUP BY re.id
        ),
        driver_standings AS (
            -- Get driver championship standings after each round's race session
            SELECT DISTINCT ON (dc.round_id, dc.driver_id)
                dc.round_id,
                dc.driver_id,
                dc.points AS driver_championship_points,
                dc.position AS driver_championship_position,
                dc.win_count AS driver_wins
            FROM f1db.driver_championships dc
            JOIN f1db.sessions s ON dc.session_id = s.id
            WHERE s.type = 'R'  -- Standings after race
            ORDER BY dc.round_id, dc.driver_id, dc.session_number DESC
        ),
        team_standings AS (
            -- Get team championship standings after each round's race session
            SELECT DISTINCT ON (tc.round_id, tc.team_id)
                tc.round_id,
                tc.team_id,
                tc.points AS team_championship_points,
                tc.position AS team_championship_position,
                tc.win_count AS team_wins
            FROM f1db.team_championships tc
            JOIN f1db.sessions s ON tc.session_id = s.id
            WHERE s.type = 'R'  -- Standings after race
            ORDER BY tc.round_id, tc.team_id, tc.session_number DESC
        )
        SELECT 
            rr.round_id,
            rr.circuit_id,
            rr.circuit_name,
            rr.season_year,
            rr.round_date,
            rr.round_number,
            rr.round_url,
            rr.team_id,
            rr.team_name,
            rr.driver_id,
            rr.driver_abbreviation,
            qt.q1_time,
            qt.q2_time,
            qt.q3_time,
            qt.qualifying_position,
            rr.grid,
            rr.finish_position,
            rr.status,
            rr.status_detail,
            rr.laps_completed,
            rr.points,
            rr.time,
            rr.fastest_lap_rank,
            ds.driver_championship_points,
            ds.driver_championship_position,
            ds.driver_wins,
            ts.team_championship_points,
            ts.team_championship_position,
            ts.team_wins
        FROM race_results rr
        LEFT JOIN qualifying_times qt ON rr.round_entry_id = qt.round_entry_id
        LEFT JOIN driver_standings ds ON rr.round_id = ds.round_id AND rr.driver_id = ds.driver_id
        LEFT JOIN team_standings ts ON rr.round_id = ts.round_id AND rr.team_id = ts.team_id
        ORDER BY rr.season_year, rr.round_number, rr.finish_position NULLS LAST
        """

        logger.debug(f"Fetching race history data{' for year ' + str(year) if year else ''}")
        return F1DataRepository.execute_raw_sql_to_df(sql, params)

    # =========================================================================
    # Additional Utility Methods
    # =========================================================================

    @staticmethod
    def get_seasons() -> List[Season]:
        """Get all seasons."""
        return F1DataRepository.get_all(Season)

    @staticmethod
    def get_rounds_by_season(season_year: int) -> pd.DataFrame:
        """Get all rounds for a specific season.

        Args:
            season_year: The season year

        Returns:
            DataFrame with round information
        """
        sql = """
        SELECT 
            r.id AS round_id,
            r.number AS round_number,
            r.name AS round_name,
            r.date AS round_date,
            r.is_cancelled,
            c.id AS circuit_id,
            c.name AS circuit_name,
            c.country,
            c.locality
        FROM f1db.rounds r
        JOIN f1db.seasons s ON r.season_id = s.id
        JOIN f1db.circuits c ON r.circuit_id = c.id
        WHERE s.year = :year
        ORDER BY r.number
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {"year": season_year})

    @staticmethod
    def get_driver_season_stats(driver_id: int, season_year: int) -> pd.DataFrame:
        """Get driver statistics for a specific season.

        Args:
            driver_id: The driver ID
            season_year: The season year

        Returns:
            DataFrame with driver season statistics
        """
        sql = """
        SELECT 
            d.id AS driver_id,
            d.forename || ' ' || d.surname AS driver_name,
            t.name AS team_name,
            COUNT(CASE WHEN se.position IS NOT NULL THEN 1 END) AS races_finished,
            COUNT(CASE WHEN se.position = 1 THEN 1 END) AS wins,
            COUNT(CASE WHEN se.position <= 3 THEN 1 END) AS podiums,
            SUM(se.points) AS total_points,
            MIN(se.position) AS best_finish,
            AVG(se.position) AS avg_finish
        FROM f1db.session_entries se
        JOIN f1db.sessions s ON se.session_id = s.id
        JOIN f1db.rounds r ON s.round_id = r.id
        JOIN f1db.seasons sn ON r.season_id = sn.id
        JOIN f1db.round_entries re ON se.round_entry_id = re.id
        JOIN f1db.team_drivers td ON re.team_driver_id = td.id
        JOIN f1db.drivers d ON td.driver_id = d.id
        JOIN f1db.teams t ON td.team_id = t.id
        WHERE s.type = 'R'
        AND d.id = :driver_id
        AND sn.year = :year
        GROUP BY d.id, d.forename, d.surname, t.name
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {
            "driver_id": driver_id,
            "year": season_year
        })

    @staticmethod
    def get_team_season_stats(team_id: int, season_year: int) -> pd.DataFrame:
        """Get team statistics for a specific season.

        Args:
            team_id: The team ID
            season_year: The season year

        Returns:
            DataFrame with team season statistics
        """
        sql = """
        SELECT 
            t.id AS team_id,
            t.name AS team_name,
            COUNT(DISTINCT d.id) AS num_drivers,
            COUNT(CASE WHEN se.position IS NOT NULL THEN 1 END) AS races_finished,
            COUNT(CASE WHEN se.position = 1 THEN 1 END) AS wins,
            COUNT(CASE WHEN se.position <= 3 THEN 1 END) AS podiums,
            SUM(se.points) AS total_points,
            MIN(se.position) AS best_finish
        FROM f1db.session_entries se
        JOIN f1db.sessions s ON se.session_id = s.id
        JOIN f1db.rounds r ON s.round_id = r.id
        JOIN f1db.seasons sn ON r.season_id = sn.id
        JOIN f1db.round_entries re ON se.round_entry_id = re.id
        JOIN f1db.team_drivers td ON re.team_driver_id = td.id
        JOIN f1db.drivers d ON td.driver_id = d.id
        JOIN f1db.teams t ON td.team_id = t.id
        WHERE s.type = 'R'
        AND t.id = :team_id
        AND sn.year = :year
        GROUP BY t.id, t.name
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {
            "team_id": team_id,
            "year": season_year
        })
