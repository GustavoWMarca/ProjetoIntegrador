CREATE TABLE IF NOT EXISTS loads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    truck_identifier TEXT NOT NULL,
    constraint_mode TEXT NOT NULL CHECK (constraint_mode IN ('budget', 'quantity')),
    max_weight_milli INTEGER NOT NULL CHECK (max_weight_milli > 0),
    max_budget_cents INTEGER CHECK (max_budget_cents IS NULL OR max_budget_cents >= 0),
    max_units INTEGER CHECK (max_units IS NULL OR max_units > 0),
    total_weight_milli INTEGER NOT NULL CHECK (total_weight_milli >= 0),
    total_cost_cents INTEGER NOT NULL CHECK (total_cost_cents >= 0),
    total_value_units INTEGER NOT NULL CHECK (total_value_units >= 0),
    total_units INTEGER NOT NULL CHECK (total_units > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS load_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    load_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_weight_milli INTEGER NOT NULL CHECK (unit_weight_milli > 0),
    unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
    unit_value_units INTEGER NOT NULL CHECK (unit_value_units >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (load_id) REFERENCES loads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_load_items_load_id ON load_items(load_id);
CREATE INDEX IF NOT EXISTS idx_load_items_product_id ON load_items(product_id);
CREATE INDEX IF NOT EXISTS idx_loads_created_at ON loads(created_at DESC);
