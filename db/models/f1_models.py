from sqlalchemy import Column, Integer, String, Float,  Date, Time, PrimaryKeyConstraint, Index
from db.base import Base


class Circuit(Base):
    __tablename__ = 'circuits'
    __table_args__ = {'schema': 'f1db'}

    circuitid = Column(Integer, primary_key=True)
    circuitref = Column(String(255), nullable=False, default='')
    name = Column(String(255), nullable=False, default='')
    location = Column(String(255))
    country = Column(String(255))
    lat = Column(Float)
    lng = Column(Float)
    alt = Column(Integer)
    url = Column(String(255), nullable=False, default='', index=True, unique=True)

    def __repr__(self):
        return f"<Circuit(circuitid={self.circuitid}, name='{self.name}')>"


class ConstructorResult(Base):
    __tablename__ = 'constructorresults'
    __table_args__ = {'schema': 'f1db'}

    constructorresultsid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    constructorid = Column(Integer, nullable=False, default=0)
    points = Column(Float)
    status = Column(String(255))

    def __repr__(self):
        return f"<ConstructorResult(constructorresultsid={self.constructorresultsid}, raceid={self.raceid}, points={self.points})>"


class Constructor(Base):
    __tablename__ = 'constructors'
    __table_args__ = {'schema': 'f1db'}

    constructorid = Column(Integer, primary_key=True)
    constructorref = Column(String(255), nullable=False, default='')
    name = Column(String(255), nullable=False, default='', index=True, unique=True)
    nationality = Column(String(255))
    url = Column(String(255), nullable=False, default='')

    def __repr__(self):
        return f"<Constructor(constructorid={self.constructorid}, name='{self.name}')>"


class ConstructorStanding(Base):
    __tablename__ = 'constructorstandings'
    __table_args__ = {'schema': 'f1db'}

    constructorstandingsid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    constructorid = Column(Integer, nullable=False, default=0)
    points = Column(Float, nullable=False, default=0)
    position = Column(Integer)
    positiontext = Column(String(255))
    wins = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<ConstructorStanding(constructorstandingsid={self.constructorstandingsid}, raceid={self.raceid}, constructorid={self.constructorid})>"


class Driver(Base):
    __tablename__ = 'drivers'
    __table_args__ = {'schema': 'f1db'}

    driverid = Column(Integer, primary_key=True)
    driverref = Column(String(255), nullable=False, default='')
    number = Column(Integer)
    code = Column(String(3))
    forename = Column(String(255), nullable=False, default='')
    surname = Column(String(255), nullable=False, default='')
    dob = Column(Date)
    nationality = Column(String(255))
    url = Column(String(255), nullable=False, default='', index=True, unique=True)

    def __repr__(self):
        return f"<Driver(driverid={self.driverid}, name='{self.forename} {self.surname}')>"


class DriverStanding(Base):
    __tablename__ = 'driverstandings'
    __table_args__ = {'schema': 'f1db'}

    driverstandingsid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    driverid = Column(Integer, nullable=False, default=0)
    points = Column(Float, nullable=False, default=0)
    position = Column(Integer)
    positiontext = Column(String(255))
    wins = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<DriverStanding(driverstandingsid={self.driverstandingsid}, raceid={self.raceid}, driverid={self.driverid})>"


class LapTime(Base):
    __tablename__ = 'laptimes'
    __table_args__ = (
        PrimaryKeyConstraint('raceid', 'driverid', 'lap'),
        Index('idx_429196_raceid', 'raceid'),
        {'schema': 'f1db'}
    )

    raceid = Column(Integer, nullable=False)
    driverid = Column(Integer, nullable=False)
    lap = Column(Integer, nullable=False)
    position = Column(Integer)
    time = Column(String(255))
    milliseconds = Column(Integer)

    def __repr__(self):
        return f"<LapTime(raceid={self.raceid}, driverid={self.driverid}, lap={self.lap})>"


class PitStop(Base):
    __tablename__ = 'pitstops'
    __table_args__ = (
        PrimaryKeyConstraint('raceid', 'driverid', 'stop'),
        Index('idx_429199_raceid', 'raceid'),
        {'schema': 'f1db'}
    )

    raceid = Column(Integer, nullable=False)
    driverid = Column(Integer, nullable=False)
    stop = Column(Integer, nullable=False)
    lap = Column(Integer, nullable=False)
    time = Column(Time, nullable=False)
    duration = Column(String(255))
    milliseconds = Column(Integer)

    def __repr__(self):
        return f"<PitStop(raceid={self.raceid}, driverid={self.driverid}, stop={self.stop}, lap={self.lap})>"


class Qualifying(Base):
    __tablename__ = 'qualifying'
    __table_args__ = {'schema': 'f1db'}

    qualifyid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    driverid = Column(Integer, nullable=False, default=0)
    constructorid = Column(Integer, nullable=False, default=0)
    number = Column(Integer, nullable=False, default=0)
    position = Column(Integer)
    q1 = Column(String(255))
    q2 = Column(String(255))
    q3 = Column(String(255))

    def __repr__(self):
        return f"<Qualifying(qualifyid={self.qualifyid}, raceid={self.raceid}, driverid={self.driverid})>"


class Race(Base):
    __tablename__ = 'races'
    __table_args__ = {'schema': 'f1db'}

    raceid = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False, default=0)
    round = Column(Integer, nullable=False, default=0)
    circuitid = Column(Integer, nullable=False, default=0)
    name = Column(String(255), nullable=False, default='')
    date = Column(Date, nullable=False)
    time = Column(Time)
    url = Column(String(255), index=True, unique=True)
    fp1_date = Column(Date)
    fp1_time = Column(Time)
    fp2_date = Column(Date)
    fp2_time = Column(Time)
    fp3_date = Column(Date)
    fp3_time = Column(Time)
    quali_date = Column(Date)
    quali_time = Column(Time)
    sprint_date = Column(Date)
    sprint_time = Column(Time)

    def __repr__(self):
        return f"<Race(raceid={self.raceid}, name='{self.name}', year={self.year})>"


class Result(Base):
    __tablename__ = 'results'
    __table_args__ = {'schema': 'f1db'}

    resultid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    driverid = Column(Integer, nullable=False, default=0)
    constructorid = Column(Integer, nullable=False, default=0)
    number = Column(Integer)
    grid = Column(Integer, nullable=False, default=0)
    position = Column(Integer)
    positiontext = Column(String(255), nullable=False, default='')
    positionorder = Column(Integer, nullable=False, default=0)
    points = Column(Float, nullable=False, default=0)
    laps = Column(Integer, nullable=False, default=0)
    time = Column(String(255))
    milliseconds = Column(Integer)
    fastestlap = Column(Integer)
    rank = Column(Integer, default=0)
    fastestlaptime = Column(String(255))
    fastestlapspeed = Column(String(255))
    statusid = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<Result(resultid={self.resultid}, raceid={self.raceid}, driverid={self.driverid})>"


class Season(Base):
    __tablename__ = 'seasons'
    __table_args__ = {'schema': 'f1db'}

    year = Column(Integer, primary_key=True, default=0)
    url = Column(String(255), nullable=False, default='', index=True, unique=True)

    def __repr__(self):
        return f"<Season(year={self.year})>"


class SprintResult(Base):
    __tablename__ = 'sprintresults'
    __table_args__ = (
        Index('idx_429243_raceid', 'raceid'),
        {'schema': 'f1db'}
    )

    sprintresultid = Column(Integer, primary_key=True)
    raceid = Column(Integer, nullable=False, default=0)
    driverid = Column(Integer, nullable=False, default=0)
    constructorid = Column(Integer, nullable=False, default=0)
    number = Column(Integer, nullable=False, default=0)
    grid = Column(Integer, nullable=False, default=0)
    position = Column(Integer)
    positiontext = Column(String(255), nullable=False, default='')
    positionorder = Column(Integer, nullable=False, default=0)
    points = Column(Float, nullable=False, default=0)
    laps = Column(Integer, nullable=False, default=0)
    time = Column(String(255))
    milliseconds = Column(Integer)
    fastestlap = Column(Integer)
    fastestlaptime = Column(String(255))
    statusid = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<SprintResult(sprintresultid={self.sprintresultid}, raceid={self.raceid}, driverid={self.driverid})>"


class Status(Base):
    __tablename__ = 'status'
    __table_args__ = {'schema': 'f1db'}

    statusid = Column(Integer, primary_key=True)
    status = Column(String(255), nullable=False, default='')

    def __repr__(self):
        return f"<Status(statusid={self.statusid}, status='{self.status}')>"