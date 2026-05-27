-- Schema SQLite per Sciopero Treni
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL,
    region TEXT,
    lat REAL,
    lng REAL
);

CREATE INDEX IF NOT EXISTS idx_stations_normalized ON stations(normalized_name);

-- Treni garantiti in giornata di sciopero
CREATE TABLE IF NOT EXISTS guaranteed_trains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    train_number TEXT NOT NULL,
    category TEXT,            -- REG, RV, IC, FA, FR, FB, EC, MET, BUS, A, B, C, D
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    dep_time TEXT,            -- HH:MM
    arr_time TEXT,            -- HH:MM  (solo per tabella A/B)
    day_type TEXT NOT NULL,   -- 'feriale', 'festivo', 'entrambi'
    table_type TEXT NOT NULL, -- 'regionale', 'tabella_a', 'tabella_b'
    region TEXT,
    line TEXT,
    notes TEXT,
    validity TEXT
);

CREATE INDEX IF NOT EXISTS idx_gt_number ON guaranteed_trains(train_number);
CREATE INDEX IF NOT EXISTS idx_gt_day_type ON guaranteed_trains(day_type);
CREATE INDEX IF NOT EXISTS idx_gt_table_type ON guaranteed_trains(table_type);

-- Fermate intermedie (da orario completo)
CREATE TABLE IF NOT EXISTS train_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    train_number TEXT NOT NULL,
    station TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    arrival TEXT,     -- HH:MM or NULL
    departure TEXT,   -- HH:MM or NULL
    UNIQUE(train_number, sequence)
);

CREATE INDEX IF NOT EXISTS idx_stops_number ON train_stops(train_number);
CREATE INDEX IF NOT EXISTS idx_stops_station ON train_stops(station);
