CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    weight_milli INTEGER NOT NULL CHECK (weight_milli > 0),
    length_centimeters INTEGER NOT NULL DEFAULT 100 CHECK (length_centimeters > 0),
    width_centimeters INTEGER NOT NULL DEFAULT 100 CHECK (width_centimeters > 0),
    height_centimeters INTEGER NOT NULL DEFAULT 100 CHECK (height_centimeters > 0),
    cost_cents INTEGER NOT NULL CHECK (cost_cents >= 0),
    value_units INTEGER NOT NULL CHECK (value_units >= 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name COLLATE NOCASE);
