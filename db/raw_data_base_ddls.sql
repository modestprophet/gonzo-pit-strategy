-- DDLs taken from a Postgres DB via DBeaver
-- Postgres DB based on import from a MySQL DB dump

-- f1db.circuits definition

-- Drop table

-- DROP TABLE f1db.circuits;

CREATE TABLE f1db.circuits (
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
CREATE UNIQUE INDEX idx_429149_url ON f1db.circuits USING btree (url);


-- f1db.constructorresults definition

-- Drop table

-- DROP TABLE f1db.constructorresults;

CREATE TABLE f1db.constructorresults (
	constructorresultsid int4 NOT NULL,
	raceid int4 DEFAULT 0 NOT NULL,
	constructorid int4 DEFAULT 0 NOT NULL,
	points float8 NULL,
	status varchar(255) NULL,
	CONSTRAINT idx_429158_primary PRIMARY KEY (constructorresultsid)
);


-- f1db.constructors definition

-- Drop table

-- DROP TABLE f1db.constructors;

CREATE TABLE f1db.constructors (
	constructorid int4 NOT NULL,
	constructorref varchar(255) DEFAULT ''::character varying NOT NULL,
	"name" varchar(255) DEFAULT ''::character varying NOT NULL,
	nationality varchar(255) NULL,
	url varchar(255) DEFAULT ''::character varying NOT NULL,
	CONSTRAINT idx_429170_primary PRIMARY KEY (constructorid)
);
CREATE UNIQUE INDEX idx_429170_name ON f1db.constructors USING btree (name);


-- f1db.constructorstandings definition

-- Drop table

-- DROP TABLE f1db.constructorstandings;

CREATE TABLE f1db.constructorstandings (
	constructorstandingsid int4 NOT NULL,
	raceid int4 DEFAULT 0 NOT NULL,
	constructorid int4 DEFAULT 0 NOT NULL,
	points float8 DEFAULT '0'::double precision NOT NULL,
	"position" int4 NULL,
	positiontext varchar(255) NULL,
	wins int4 DEFAULT 0 NOT NULL,
	CONSTRAINT idx_429163_primary PRIMARY KEY (constructorstandingsid)
);


-- f1db.drivers definition

-- Drop table

-- DROP TABLE f1db.drivers;

CREATE TABLE f1db.drivers (
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
CREATE UNIQUE INDEX idx_429186_url ON f1db.drivers USING btree (url);


-- f1db.driverstandings definition

-- Drop table

-- DROP TABLE f1db.driverstandings;

CREATE TABLE f1db.driverstandings (
	driverstandingsid int4 NOT NULL,
	raceid int4 DEFAULT 0 NOT NULL,
	driverid int4 DEFAULT 0 NOT NULL,
	points float8 DEFAULT '0'::double precision NOT NULL,
	"position" int4 NULL,
	positiontext varchar(255) NULL,
	wins int4 DEFAULT 0 NOT NULL,
	CONSTRAINT idx_429179_primary PRIMARY KEY (driverstandingsid)
);


-- f1db.laptimes definition

-- Drop table

-- DROP TABLE f1db.laptimes;

CREATE TABLE f1db.laptimes (
	raceid int4 NOT NULL,
	driverid int4 NOT NULL,
	lap int4 NOT NULL,
	"position" int4 NULL,
	"time" varchar(255) NULL,
	milliseconds int4 NULL,
	CONSTRAINT idx_429196_primary PRIMARY KEY (raceid, driverid, lap)
);
CREATE INDEX idx_429196_raceid ON f1db.laptimes USING btree (raceid);
CREATE INDEX idx_429196_raceid_2 ON f1db.laptimes USING btree (raceid);


-- f1db.pitstops definition

-- Drop table

-- DROP TABLE f1db.pitstops;

CREATE TABLE f1db.pitstops (
	raceid int4 NOT NULL,
	driverid int4 NOT NULL,
	stop int4 NOT NULL,
	lap int4 NOT NULL,
	"time" time NOT NULL,
	duration varchar(255) NULL,
	milliseconds int4 NULL,
	CONSTRAINT idx_429199_primary PRIMARY KEY (raceid, driverid, stop)
);
CREATE INDEX idx_429199_raceid ON f1db.pitstops USING btree (raceid);


-- f1db.qualifying definition

-- Drop table

-- DROP TABLE f1db.qualifying;

CREATE TABLE f1db.qualifying (
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


-- f1db.races definition

-- Drop table

-- DROP TABLE f1db.races;

CREATE TABLE f1db.races (
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
CREATE UNIQUE INDEX idx_429212_url ON f1db.races USING btree (url);


-- f1db.results definition

-- Drop table

-- DROP TABLE f1db.results;

CREATE TABLE f1db.results (
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


-- f1db.seasons definition

-- Drop table

-- DROP TABLE f1db.seasons;

CREATE TABLE f1db.seasons (
	"year" int4 DEFAULT 0 NOT NULL,
	url varchar(255) DEFAULT ''::character varying NOT NULL,
	CONSTRAINT idx_429238_primary PRIMARY KEY (year)
);
CREATE UNIQUE INDEX idx_429238_url ON f1db.seasons USING btree (url);


-- f1db.sprintresults definition

-- Drop table

-- DROP TABLE f1db.sprintresults;

CREATE TABLE f1db.sprintresults (
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
CREATE INDEX idx_429243_raceid ON f1db.sprintresults USING btree (raceid);


-- f1db.status definition

-- Drop table

-- DROP TABLE f1db.status;

CREATE TABLE f1db.status (
	statusid int4 NOT NULL,
	status varchar(255) DEFAULT ''::character varying NOT NULL,
	CONSTRAINT idx_429259_primary PRIMARY KEY (statusid)
);