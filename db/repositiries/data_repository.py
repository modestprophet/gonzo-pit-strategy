"""
Repository for F1 data access.

This module provides methods to access Formula 1 data from the database,
using both SQLAlchemy ORM and raw SQL queries when needed.
"""
from typing import List, Dict, Any, Optional, TypeVar, Type, Union
import pandas as pd

from sqlalchemy import text
from sqlalchemy.orm import Session

from db.base import db_session, Base
from db.models.f1_models import (
    Circuit, Constructor, ConstructorResult, ConstructorStanding,
    Driver, DriverStanding, LapTime, PitStop, Qualifying,
    Race, Result, Season, SprintResult, Status
)
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)

T = TypeVar('T', bound=Base)


class F1DataRepository:
    """Repository for accessing F1 data from the database."""

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
            logger.debug(f"Executing raw SQL: {sql}")
            result = session.execute(text(sql), params or {})
            return [dict(row) for row in result]

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
            logger.debug(f"Executing raw SQL to DataFrame: {sql}")
            result = session.execute(text(sql), params or {})
            return pd.DataFrame(result.fetchall(), columns=result.keys())

    # Specific F1 data methods
    @staticmethod
    def get_constructor_results_by_race(race_id: int) -> List[ConstructorResult]:
        """Get constructor results for a specific race.

        Args:
            race_id: The race ID

        Returns:
            List of ConstructorResult objects
        """
        return F1DataRepository.filter_by(ConstructorResult, raceid=race_id)

    @staticmethod
    def get_pit_stops_by_race_and_driver(race_id: int, driver_id: int) -> List[PitStop]:
        """Get all pit stops for a specific race and driver.

        Args:
            race_id: The race ID
            driver_id: The driver ID

        Returns:
            List of PitStop objects
        """
        return F1DataRepository.filter_by(PitStop, raceid=race_id, driverid=driver_id)

    @staticmethod
    def get_race_results(race_id: int) -> pd.DataFrame:
        """Get detailed race results including driver and constructor information.

        Args:
            race_id: The race ID

        Returns:
            DataFrame with race results
        """
        sql = """
        SELECT 
            r.resultid, r.raceid, 
            d.driverid, d.code, d.forename || ' ' || d.surname AS driver_name,
            c.constructorid, c.name AS constructor_name,
            r.position, r.positiontext, r.points, r.laps,
            r.time, r.fastestlaptime, r.fastestlapspeed,
            s.status
        FROM f1db.results r
        JOIN f1db.drivers d ON r.driverid = d.driverid
        JOIN f1db.constructors c ON r.constructorid = c.constructorid
        JOIN f1db.status s ON r.statusid = s.statusid
        WHERE r.raceid = :race_id
        ORDER BY r.positionorder
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, {"race_id": race_id})

    @staticmethod
    def get_lap_time_analysis(race_id: int, driver_id: Optional[int] = None) -> pd.DataFrame:
        """Get lap time analysis for a race, optionally filtered by driver.

        Args:
            race_id: The race ID
            driver_id: Optional driver ID to filter by

        Returns:
            DataFrame with lap time analysis
        """
        params = {"race_id": race_id}
        where_clause = "WHERE lt.raceid = :race_id"

        if driver_id is not None:
            where_clause += " AND lt.driverid = :driver_id"
            params["driver_id"] = driver_id

        sql = f"""
        SELECT 
            lt.raceid, lt.driverid, 
            d.code, d.forename || ' ' || d.surname AS driver_name,
            lt.lap, lt.position, lt.time, lt.milliseconds
        FROM f1db.laptimes lt
        JOIN f1db.drivers d ON lt.driverid = d.driverid
        {where_clause}
        ORDER BY lt.driverid, lt.lap
        """
        return F1DataRepository.execute_raw_sql_to_df(sql, params)

    @staticmethod
    def get_all_race_history(year: Optional[int] = None) -> pd.DataFrame:
        """Get comprehensive race history data with qualifying and standings.

        This method returns a rich dataset containing race results, qualifying data,
        driver and constructor information, and championship standings.

        Args:
            year: Optional filter for a specific year/season

        Returns:
            DataFrame with complete race history data
        """
        # Build where clause based on optional year filter
        where_clause = ""
        params = {}

        if year is not None:
            where_clause = "WHERE races.year = :year"
            params["year"] = year

        sql = f"""
        SELECT 
            races.raceId AS raceId,
            races.circuitId AS circuitId,
            circuits.name AS circuitName,
            races.year AS raceYear,
            races.date AS raceDate,
            races.time AS raceTime,
            races.round AS roundNumber,
            races.url AS raceURL,
            constructors.constructorId AS constructorId,
            constructors.name AS constructorName,
            drivers.driverId AS driverId,
            drivers.code AS driverCode,
            qualifying.q1 AS q1,
            qualifying.q2 AS q2,
            qualifying.q3 AS q3,
            qualifying.position AS qualifyingPosition,
            results.grid AS startingGrid,
            results.positionOrder AS finishPositionOrder,
            results.positionText AS finishPositionText,
            status.status AS status,
            results.milliseconds AS milliseconds,
            results.points AS points,
            results.fastestLap AS fastestLap,
            results.fastestLapTime AS fastestLapTime,
            results.fastestLapSpeed AS fastestLapSpeed,
            driverStandings.points AS driverTotalPoints,
            driverStandings.positionText AS driverRank,
            driverStandings.wins AS driverWins,
            constructorStandings.points AS constructorTotalPoints,
            constructorStandings.positionText AS constructorRank,
            constructorStandings.wins AS constructorWins
        FROM f1db.races
        INNER JOIN f1db.results ON (races.raceId = results.raceId)
        INNER JOIN f1db.qualifying ON ((results.raceId = qualifying.raceId) AND (results.driverId = qualifying.driverId))
        INNER JOIN f1db.circuits ON (races.circuitId = circuits.circuitId)
        INNER JOIN f1db.status ON (results.statusId = status.statusId)
        INNER JOIN f1db.drivers ON (results.driverId = drivers.driverId)
        INNER JOIN f1db.constructors ON (results.constructorId = constructors.constructorId)
        LEFT OUTER JOIN f1db.driverStandings ON ((results.driverId = driverStandings.driverId) AND (results.raceId = driverStandings.raceId))
        LEFT OUTER JOIN f1db.constructorStandings ON ((results.raceId = constructorStandings.raceId) AND (results.constructorId = constructorStandings.constructorId))
        {where_clause}
        ORDER BY races.year, races.round, results.positionOrder
        """

        logger.debug(f"Fetching race history data{' for year ' + str(year) if year else ''}")
        return F1DataRepository.execute_raw_sql_to_df(sql, params)

