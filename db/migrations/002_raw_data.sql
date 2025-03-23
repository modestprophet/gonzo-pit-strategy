-- +goose Up
-- Create circuits table
CREATE TABLE IF NOT EXISTS f1db.circuits (
    circuitid int4 NOT NULL,
    circuitref varchar(255) DEFAULT ''::character varying NOT NULL,
    "name" varchar(255) DEFAULT ''::character varying NOT NULL,
    "location" varchar(255) NULL,
    country varchar(255) NULL,
    lat float8 NULL,
    lng float8 NULL,
    alt int4 NULL,
    url varchar(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT idx_429149_primary PRIMARY KEY (circuitid)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_429149_url ON f1db.circuits USING btree (url);

-- Create constructorresults table
CREATE TABLE IF NOT EXISTS f1db.constructorresults (
    constructorresultsid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    constructorid int4 DEFAULT 0 NOT NULL,
    points float8 NULL,
    status varchar(255) NULL,
    CONSTRAINT idx_429158_primary PRIMARY KEY (constructorresultsid)
);

-- Create constructors table
CREATE TABLE IF NOT EXISTS f1db.constructors (
    constructorid int4 NOT NULL,
    constructorref varchar(255) DEFAULT ''::character varying NOT NULL,
    "name" varchar(255) DEFAULT ''::character varying NOT NULL,
    nationality varchar(255) NULL,
    url varchar(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT idx_429170_primary PRIMARY KEY (constructorid)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_429170_name ON f1db.constructors USING btree (name);

-- Create constructorstandings table
CREATE TABLE IF NOT EXISTS f1db.constructorstandings (
    constructorstandingsid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    constructorid int4 DEFAULT 0 NOT NULL,
    points float8 DEFAULT '0'::double precision NOT NULL,
    "position" int4 NULL,
    positiontext varchar(255) NULL,
    wins int4 DEFAULT 0 NOT NULL,
    CONSTRAINT idx_429163_primary PRIMARY KEY (constructorstandingsid)
);

-- Create drivers table
CREATE TABLE IF NOT EXISTS f1db.drivers (
    driverid int4 NOT NULL,
    driverref varchar(255) DEFAULT ''::character varying NOT NULL,
    "number" int4 NULL,
    code varchar(3) NULL,
    forename varchar(255) DEFAULT ''::character varying NOT NULL,
    surname varchar(255) DEFAULT ''::character varying NOT NULL,
    dob date NULL,
    nationality varchar(255) NULL,
    url varchar(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT idx_429186_primary PRIMARY KEY (driverid)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_429186_url ON f1db.drivers USING btree (url);

-- Create driverstandings table
CREATE TABLE IF NOT EXISTS f1db.driverstandings (
    driverstandingsid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    driverid int4 DEFAULT 0 NOT NULL,
    points float8 DEFAULT '0'::double precision NOT NULL,
    "position" int4 NULL,
    positiontext varchar(255) NULL,
    wins int4 DEFAULT 0 NOT NULL,
    CONSTRAINT idx_429179_primary PRIMARY KEY (driverstandingsid)
);

-- Create laptimes table
CREATE TABLE IF NOT EXISTS f1db.laptimes (
    raceid int4 NOT NULL,
    driverid int4 NOT NULL,
    lap int4 NOT NULL,
    "position" int4 NULL,
    "time" varchar(255) NULL,
    milliseconds int4 NULL,
    CONSTRAINT idx_429196_primary PRIMARY KEY (raceid, driverid, lap)
);
CREATE INDEX IF NOT EXISTS idx_429196_raceid ON f1db.laptimes USING btree (raceid);
CREATE INDEX IF NOT EXISTS idx_429196_raceid_2 ON f1db.laptimes USING btree (raceid);

-- Create pitstops table
CREATE TABLE IF NOT EXISTS f1db.pitstops (
    raceid int4 NOT NULL,
    driverid int4 NOT NULL,
    stop int4 NOT NULL,
    lap int4 NOT NULL,
    "time" time NOT NULL,
    duration varchar(255) NULL,
    milliseconds int4 NULL,
    CONSTRAINT idx_429199_primary PRIMARY KEY (raceid, driverid, stop)
);
CREATE INDEX IF NOT EXISTS idx_429199_raceid ON f1db.pitstops USING btree (raceid);

-- Create qualifying table
CREATE TABLE IF NOT EXISTS f1db.qualifying (
    qualifyid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    driverid int4 DEFAULT 0 NOT NULL,
    constructorid int4 DEFAULT 0 NOT NULL,
    "number" int4 DEFAULT 0 NOT NULL,
    "position" int4 NULL,
    q1 varchar(255) NULL,
    q2 varchar(255) NULL,
    q3 varchar(255) NULL,
    CONSTRAINT idx_429202_primary PRIMARY KEY (qualifyid)
);

-- Create races table
CREATE TABLE IF NOT EXISTS f1db.races (
    raceid int4 NOT NULL,
    "year" int4 DEFAULT 0 NOT NULL,
    round int4 DEFAULT 0 NOT NULL,
    circuitid int4 DEFAULT 0 NOT NULL,
    "name" varchar(255) DEFAULT ''::character varying NOT NULL,
    "date" date NOT NULL,
    "time" time NULL,
    url varchar(255) NULL,
    fp1_date date NULL,
    fp1_time time NULL,
    fp2_date date NULL,
    fp2_time time NULL,
    fp3_date date NULL,
    fp3_time time NULL,
    quali_date date NULL,
    quali_time time NULL,
    sprint_date date NULL,
    sprint_time time NULL,
    CONSTRAINT idx_429212_primary PRIMARY KEY (raceid)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_429212_url ON f1db.races USING btree (url);

-- Create results table
CREATE TABLE IF NOT EXISTS f1db.results (
    resultid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    driverid int4 DEFAULT 0 NOT NULL,
    constructorid int4 DEFAULT 0 NOT NULL,
    "number" int4 NULL,
    grid int4 DEFAULT 0 NOT NULL,
    "position" int4 NULL,
    positiontext varchar(255) DEFAULT ''::character varying NOT NULL,
    positionorder int4 DEFAULT 0 NOT NULL,
    points float8 DEFAULT '0'::double precision NOT NULL,
    laps int4 DEFAULT 0 NOT NULL,
    "time" varchar(255) NULL,
    milliseconds int4 NULL,
    fastestlap int4 NULL,
    "rank" int4 DEFAULT 0 NULL,
    fastestlaptime varchar(255) NULL,
    fastestlapspeed varchar(255) NULL,
    statusid int4 DEFAULT 0 NOT NULL,
    CONSTRAINT idx_429222_primary PRIMARY KEY (resultid)
);

-- Create seasons table
CREATE TABLE IF NOT EXISTS f1db.seasons (
    "year" int4 DEFAULT 0 NOT NULL,
    url varchar(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT idx_429238_primary PRIMARY KEY (year)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_429238_url ON f1db.seasons USING btree (url);

-- Create sprintresults table
CREATE TABLE IF NOT EXISTS f1db.sprintresults (
    sprintresultid int4 NOT NULL,
    raceid int4 DEFAULT 0 NOT NULL,
    driverid int4 DEFAULT 0 NOT NULL,
    constructorid int4 DEFAULT 0 NOT NULL,
    "number" int4 DEFAULT 0 NOT NULL,
    grid int4 DEFAULT 0 NOT NULL,
    "position" int4 NULL,
    positiontext varchar(255) DEFAULT ''::character varying NOT NULL,
    positionorder int4 DEFAULT 0 NOT NULL,
    points float8 DEFAULT '0'::double precision NOT NULL,
    laps int4 DEFAULT 0 NOT NULL,
    "time" varchar(255) NULL,
    milliseconds int4 NULL,
    fastestlap int4 NULL,
    fastestlaptime varchar(255) NULL,
    statusid int4 DEFAULT 0 NOT NULL,
    CONSTRAINT idx_429243_primary PRIMARY KEY (sprintresultid)
);
CREATE INDEX IF NOT EXISTS idx_429243_raceid ON f1db.sprintresults USING btree (raceid);

-- Create status table
CREATE TABLE IF NOT EXISTS f1db.status (
    statusid int4 NOT NULL,
    status varchar(255) DEFAULT ''::character varying NOT NULL,
    CONSTRAINT idx_429259_primary PRIMARY KEY (statusid)
);

-- +goose Down
-- Drop tables in reverse order to avoid foreign key constraints issues
DROP TABLE IF EXISTS f1db.status;
DROP TABLE IF EXISTS f1db.sprintresults;
DROP TABLE IF EXISTS f1db.seasons;
DROP TABLE IF EXISTS f1db.results;
DROP TABLE IF EXISTS f1db.races;
DROP TABLE IF EXISTS f1db.qualifying;
DROP TABLE IF EXISTS f1db.pitstops;
DROP TABLE IF EXISTS f1db.laptimes;
DROP TABLE IF EXISTS f1db.driverstandings;
DROP TABLE IF EXISTS f1db.drivers;
DROP TABLE IF EXISTS f1db.constructorstandings;
DROP TABLE IF EXISTS f1db.constructors;
DROP TABLE IF EXISTS f1db.constructorresults;
DROP TABLE IF EXISTS f1db.circuits;

-- Finally, drop the schema if needed
DROP SCHEMA IF EXISTS f1db CASCADE;