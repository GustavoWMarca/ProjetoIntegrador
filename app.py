from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import click
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)


WEIGHT_SCALE = 1_000
MONEY_SCALE = 100
VALUE_SCALE = 100
MAX_PARETO_STATES = 250_000


class ValidationError(ValueError):
    """Erro de entrada que pode ser apresentado diretamente ao usuário."""


class OptimizationTooLargeError(RuntimeError):
    """Protege a aplicação contra uma otimização grande demais para a memória."""


@dataclass(frozen=True)
class KnapsackState:
    total_weight: int
    total_constraint: int
    total_value: int
    previous: "KnapsackState | None" = None
    product_id: int | None = None
    quantity: int = 0


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this-key"),
        DATABASE=str(Path(app.instance_path) / "estoque.db"),
        LOADS_DATABASE=str(Path(app.instance_path) / "cargas.db"),
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["number_pt"] = format_number_pt
    app.jinja_env.filters["weight"] = format_weight
    app.jinja_env.filters["score"] = format_score
    app.jinja_env.filters["datetime_pt"] = format_datetime_pt

    register_routes(app)

    with app.app_context():
        init_db()
        init_loads_db()

    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_database_path(),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def get_loads_db() -> sqlite3.Connection:
    if "loads_db" not in g:
        g.loads_db = sqlite3.connect(
            current_loads_database_path(),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.loads_db.row_factory = sqlite3.Row
        g.loads_db.execute("PRAGMA foreign_keys = ON")
    return g.loads_db


def current_database_path() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def current_loads_database_path() -> str:
    from flask import current_app

    return current_app.config["LOADS_DATABASE"]


def close_db(_error: BaseException | None = None) -> None:
    for key in ("db", "loads_db"):
        database = g.pop(key, None)
        if database is not None:
            database.close()


def init_db() -> None:
    database = get_db()
    from flask import current_app

    with current_app.open_resource("schema.sql") as schema_file:
        database.executescript(schema_file.read().decode("utf-8"))
    database.commit()


def init_loads_db() -> None:
    database = get_loads_db()
    from flask import current_app

    with current_app.open_resource("loads_schema.sql") as schema_file:
        database.executescript(schema_file.read().decode("utf-8"))
    database.execute("PRAGMA optimize")
    database.commit()


@click.command("init-db")
def init_db_command() -> None:
    init_db()
    init_loads_db()
    click.echo("Bancos de estoque e cargas inicializados.")


@click.command("seed-demo")
def seed_demo_command() -> None:
    database = get_db()
    demo_products = [
        ("P001", "Cafeteira", 3_200, 18_000, 27_000, 4),
        ("P002", "Liquidificador", 2_100, 11_000, 16_500, 7),
        ("P003", "Ferro elétrico", 1_350, 7_500, 10_000, 8),
        ("P004", "Ventilador", 4_800, 22_000, 33_000, 3),
        ("P005", "Sanduicheira", 2_700, 13_500, 20_000, 5),
    ]
    database.executemany(
        """
        INSERT OR IGNORE INTO products
            (code, name, weight_milli, cost_cents, value_units, quantity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        demo_products,
    )
    database.commit()
    click.echo("Produtos de demonstração adicionados.")


def register_routes(app: Flask) -> None:
    @app.get("/")
    def index():
        database = get_db()
        loads_database = get_loads_db()
        summary = database.execute(
            """
            SELECT
                COUNT(*) AS product_types,
                COALESCE(SUM(quantity), 0) AS total_units,
                COALESCE(SUM(weight_milli * quantity), 0) AS total_weight,
                COALESCE(SUM(cost_cents * quantity), 0) AS total_cost
            FROM products
            """
        ).fetchone()
        load_summary = loads_database.execute(
            """
            SELECT
                COUNT(*) AS pending_loads,
                COALESCE(SUM(total_units), 0) AS reserved_units,
                COALESCE(SUM(total_weight_milli), 0) AS reserved_weight
            FROM loads
            """
        ).fetchone()
        recent_products = enrich_products_with_availability(database.execute(
            "SELECT * FROM products ORDER BY updated_at DESC, id DESC LIMIT 5"
        ).fetchall())
        return render_template(
            "index.html",
            summary=summary,
            load_summary=load_summary,
            recent_products=recent_products,
        )

    @app.get("/products")
    def products():
        search = request.args.get("q", "").strip()
        database = get_db()
        if search:
            rows = database.execute(
                """
                SELECT * FROM products
                WHERE code LIKE ? OR name LIKE ?
                ORDER BY name COLLATE NOCASE
                """,
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = database.execute(
                "SELECT * FROM products ORDER BY name COLLATE NOCASE"
            ).fetchall()
        rows = enrich_products_with_availability(rows)
        return render_template("products.html", products=rows, search=search)

    @app.route("/products/new", methods=("GET", "POST"))
    def product_new():
        form = empty_product_form()
        if request.method == "POST":
            form = product_form_from_request()
            try:
                product = validate_product_form(form)
                database = get_db()
                database.execute(
                    """
                    INSERT INTO products
                        (code, name, weight_milli, cost_cents, value_units, quantity)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    product,
                )
                database.commit()
            except ValidationError as error:
                flash(str(error), "error")
            except sqlite3.IntegrityError:
                flash("Já existe um produto com esse código.", "error")
            else:
                flash("Produto cadastrado com sucesso.", "success")
                return redirect(url_for("products"))
        return render_template(
            "product_form.html",
            title="Novo produto",
            submit_label="Cadastrar produto",
            form=form,
        )

    @app.route("/products/<int:product_id>/edit", methods=("GET", "POST"))
    def product_edit(product_id: int):
        database = get_db()
        row = get_product_or_404(database, product_id)
        form = product_form_from_row(row)

        if request.method == "POST":
            form = product_form_from_request()
            try:
                product = validate_product_form(form)
                reserved = reserved_quantities().get(product_id, 0)
                if product[-1] < reserved:
                    raise ValidationError(
                        f"Este produto possui {reserved} unidade(s) reservada(s) em "
                        "cargas pendentes. A quantidade não pode ficar abaixo da reserva."
                    )
                database.execute(
                    """
                    UPDATE products
                    SET code = ?, name = ?, weight_milli = ?, cost_cents = ?,
                        value_units = ?, quantity = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (*product, product_id),
                )
                database.commit()
            except ValidationError as error:
                flash(str(error), "error")
            except sqlite3.IntegrityError:
                flash("Já existe outro produto com esse código.", "error")
            else:
                flash("Produto atualizado com sucesso.", "success")
                return redirect(url_for("products"))

        return render_template(
            "product_form.html",
            title="Editar produto",
            submit_label="Salvar alterações",
            form=form,
            product=row,
        )

    @app.post("/products/<int:product_id>/delete")
    def product_delete(product_id: int):
        database = get_db()
        row = get_product_or_404(database, product_id)
        reserved = reserved_quantities().get(product_id, 0)
        if reserved:
            flash(
                f"O produto “{row['name']}” possui {reserved} unidade(s) reservada(s) "
                "e não pode ser excluído antes da liberação da carga.",
                "error",
            )
            return redirect(url_for("products"))
        database.execute("DELETE FROM products WHERE id = ?", (product_id,))
        database.commit()
        flash(f"Produto “{row['name']}” excluído.", "success")
        return redirect(url_for("products"))

    @app.route("/optimize", methods=("GET", "POST"))
    def optimize():
        return redirect(url_for("load_plan"))

    @app.route("/loads/plan", methods=("GET", "POST"))
    def load_plan():
        products_available = get_available_products()
        form = load_form_from_request(products_available)
        result = None

        if request.method == "POST":
            try:
                result = calculate_load_plan(form, products_available)
                if request.form.get("action") == "save":
                    load_id = save_load(form, result)
                    flash(
                        f"Carga “{form['name']}” salva e reservada com sucesso.",
                        "success",
                    )
                    return redirect(url_for("loads", highlight=load_id))
            except (ValidationError, OptimizationTooLargeError) as error:
                flash(str(error), "error")

        return render_template(
            "load_plan.html",
            form=form,
            result=result,
            products=products_available,
        )

    @app.get("/loads")
    def loads():
        database = get_loads_db()
        load_rows = [dict(row) for row in database.execute(
            "SELECT * FROM loads ORDER BY created_at DESC, id DESC"
        ).fetchall()]
        items = database.execute(
            "SELECT * FROM load_items ORDER BY product_name COLLATE NOCASE"
        ).fetchall()
        items_by_load: dict[int, list[sqlite3.Row]] = {}
        for item in items:
            items_by_load.setdefault(item["load_id"], []).append(item)
        for load in load_rows:
            load["items"] = items_by_load.get(load["id"], [])
        return render_template(
            "loads.html",
            loads=load_rows,
            highlight=request.args.get("highlight", type=int),
        )

    @app.post("/loads/<int:load_id>/release")
    def load_release(load_id: int):
        try:
            load_name = release_load(load_id)
        except LookupError:
            from flask import abort

            abort(404)
        except ValidationError as error:
            flash(str(error), "error")
        else:
            flash(
                f"Carga “{load_name}” liberada. O estoque foi baixado e a carga "
                "removida das pendências.",
                "success",
            )
        return redirect(url_for("loads"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404


def reserved_quantities() -> dict[int, int]:
    rows = get_loads_db().execute(
        """
        SELECT product_id, COALESCE(SUM(quantity), 0) AS reserved
        FROM load_items
        GROUP BY product_id
        """
    ).fetchall()
    return {int(row["product_id"]): int(row["reserved"]) for row in rows}


def enrich_products_with_availability(rows: Iterable[Any]) -> list[dict[str, Any]]:
    reservations = reserved_quantities()
    enriched = []
    for row in rows:
        product = dict(row)
        product["reserved"] = reservations.get(int(product["id"]), 0)
        product["available"] = max(
            0, int(product["quantity"]) - int(product["reserved"])
        )
        enriched.append(product)
    return enriched


def get_available_products() -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT * FROM products ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return enrich_products_with_availability(rows)


def load_form_from_request(products: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected_ids: set[int] = set()
    minimums: dict[int, str] = {}
    maximums: dict[int, str] = {}
    for product in products:
        product_id = int(product["id"])
        if request.method == "POST" and request.form.get(f"include_{product_id}"):
            selected_ids.add(product_id)
        minimums[product_id] = request.form.get(
            f"min_{product_id}", "1" if product["available"] else "0"
        ).strip()
        maximums[product_id] = request.form.get(
            f"max_{product_id}", str(product["available"])
        ).strip()

    return {
        "name": request.form.get("name", "").strip(),
        "truck_identifier": request.form.get("truck_identifier", "").strip(),
        "max_weight": request.form.get("max_weight", "").strip(),
        "constraint_mode": request.form.get("constraint_mode", "budget").strip(),
        "max_budget": request.form.get("max_budget", "").strip(),
        "max_units": request.form.get("max_units", "").strip(),
        "selected_ids": selected_ids,
        "minimums": minimums,
        "maximums": maximums,
    }


def calculate_load_plan(
    form: dict[str, Any], products: list[dict[str, Any]]
) -> dict[str, Any]:
    if not form["name"]:
        raise ValidationError("Informe um nome ou referência para a carga.")
    if len(form["name"]) > 100:
        raise ValidationError("O nome da carga deve ter no máximo 100 caracteres.")
    if not form["truck_identifier"]:
        raise ValidationError("Informe a placa ou identificação do caminhão.")
    if len(form["truck_identifier"]) > 60:
        raise ValidationError(
            "A identificação do caminhão deve ter no máximo 60 caracteres."
        )

    max_weight = parse_scaled_decimal(
        form["max_weight"], WEIGHT_SCALE, "Capacidade do caminhão", False
    )
    mode = form["constraint_mode"]
    if mode not in {"budget", "quantity"}:
        raise ValidationError("Escolha orçamento ou quantidade como segundo limite.")

    max_budget: int | None = None
    max_units: int | None = None
    if mode == "budget":
        max_budget = parse_scaled_decimal(
            form["max_budget"], MONEY_SCALE, "Orçamento", True
        )
    else:
        try:
            max_units = int(form["max_units"])
        except (TypeError, ValueError):
            raise ValidationError(
                "A quantidade máxima deve ser um número inteiro."
            ) from None
        if max_units <= 0:
            raise ValidationError("A quantidade máxima deve ser maior que zero.")
        if max_units > 1_000_000:
            raise ValidationError("A quantidade máxima informada é muito alta.")

    products_by_id = {int(product["id"]): product for product in products}
    extra_candidates = []
    mandatory_quantities: dict[int, int] = {}
    for product_id in form["selected_ids"]:
        product = products_by_id.get(product_id)
        if product is None:
            continue
        try:
            requested_minimum = int(form["minimums"].get(product_id, ""))
            requested_maximum = int(form["maximums"].get(product_id, ""))
        except (TypeError, ValueError):
            raise ValidationError(
                f"Informe quantidades mínima e máxima válidas para {product['name']}."
            ) from None
        if requested_minimum < 0:
            raise ValidationError(
                f"A quantidade mínima de {product['name']} não pode ser negativa."
            )
        if requested_maximum <= 0:
            raise ValidationError(
                f"A quantidade máxima de {product['name']} deve ser maior que zero."
            )
        if requested_minimum > requested_maximum:
            raise ValidationError(
                f"O mínimo de {product['name']} não pode ser maior que o máximo."
            )
        if requested_maximum > int(product["available"]):
            raise ValidationError(
                f"Há somente {product['available']} unidade(s) disponível(is) de "
                f"{product['name']} após as reservas existentes."
            )
        candidate = dict(product)
        candidate["quantity"] = requested_maximum - requested_minimum
        extra_candidates.append(candidate)
        if requested_minimum:
            mandatory_quantities[product_id] = requested_minimum

    if not extra_candidates:
        raise ValidationError("Selecione pelo menos um produto disponível para a carga.")

    mandatory_weight = sum(
        int(products_by_id[product_id]["weight_milli"]) * quantity
        for product_id, quantity in mandatory_quantities.items()
    )
    mandatory_cost = sum(
        int(products_by_id[product_id]["cost_cents"]) * quantity
        for product_id, quantity in mandatory_quantities.items()
    )
    mandatory_value = sum(
        int(products_by_id[product_id]["value_units"]) * quantity
        for product_id, quantity in mandatory_quantities.items()
    )
    mandatory_units = sum(mandatory_quantities.values())

    if mandatory_weight > max_weight:
        raise ValidationError(
            "As quantidades mínimas ultrapassam a capacidade do caminhão."
        )
    if mode == "budget" and mandatory_cost > max_budget:
        raise ValidationError(
            "As quantidades mínimas ultrapassam o orçamento informado."
        )
    if mode == "quantity" and mandatory_units > max_units:
        raise ValidationError(
            "A soma das quantidades mínimas ultrapassa o limite de unidades."
        )

    remaining_weight = max_weight - mandatory_weight
    remaining_budget = (
        max_budget - mandatory_cost if mode == "budget" else None
    )
    remaining_units = max_units - mandatory_units if mode == "quantity" else None
    has_extra_options = any(candidate["quantity"] > 0 for candidate in extra_candidates)
    can_add_extra = remaining_weight > 0 and (
        mode == "budget" or (remaining_units is not None and remaining_units > 0)
    )

    extra_solution: dict[str, Any] = {
        "quantities": {},
        "total_weight": 0,
        "total_cost": 0,
        "total_units": 0,
        "total_value": 0,
        "states_evaluated": 1,
    }
    if has_extra_options and can_add_extra:
        extra_solution = optimize_inventory(
            extra_candidates,
            max_weight=remaining_weight,
            max_budget=remaining_budget,
            max_units=remaining_units,
            constraint_mode=mode,
        )

    quantities = dict(mandatory_quantities)
    for product_id, quantity in extra_solution["quantities"].items():
        quantities[product_id] = quantities.get(product_id, 0) + quantity

    total_weight = mandatory_weight + extra_solution["total_weight"]
    total_cost = mandatory_cost + extra_solution["total_cost"]
    total_units = mandatory_units + extra_solution["total_units"]
    total_value = mandatory_value + extra_solution["total_value"]
    solution = {
        "quantities": quantities,
        "total_weight": total_weight,
        "total_cost": total_cost,
        "total_units": total_units,
        "total_value": total_value,
        "states_evaluated": extra_solution["states_evaluated"],
    }

    if not quantities:
        raise ValidationError(
            "Nenhum dos produtos selecionados cabe nos limites informados."
        )

    selected = []
    for product_id, quantity in sorted(
        solution["quantities"].items(),
        key=lambda pair: products_by_id[pair[0]]["name"].casefold(),
    ):
        product = products_by_id[product_id]
        selected.append(
            {
                "product": product,
                "quantity": quantity,
                "subtotal_weight": int(product["weight_milli"]) * quantity,
                "subtotal_cost": int(product["cost_cents"]) * quantity,
                "subtotal_value": int(product["value_units"]) * quantity,
            }
        )

    constraint_limit = max_budget if mode == "budget" else max_units
    constraint_used = (
        solution["total_cost"] if mode == "budget" else solution["total_units"]
    )
    assert constraint_limit is not None
    return {
        **solution,
        "selected": selected,
        "max_weight": max_weight,
        "max_budget": max_budget,
        "max_units": max_units,
        "constraint_mode": mode,
        "mandatory_units": mandatory_units,
        "remaining_weight": max_weight - solution["total_weight"],
        "remaining_constraint": constraint_limit - constraint_used,
    }


def save_load(form: dict[str, Any], result: dict[str, Any]) -> int:
    database = get_loads_db()
    try:
        cursor = database.execute(
            """
            INSERT INTO loads (
                name, truck_identifier, constraint_mode, max_weight_milli,
                max_budget_cents, max_units, total_weight_milli,
                total_cost_cents, total_value_units, total_units
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                form["name"],
                form["truck_identifier"],
                result["constraint_mode"],
                result["max_weight"],
                result["max_budget"],
                result["max_units"],
                result["total_weight"],
                result["total_cost"],
                result["total_value"],
                result["total_units"],
            ),
        )
        load_id = int(cursor.lastrowid)
        database.executemany(
            """
            INSERT INTO load_items (
                load_id, product_id, product_code, product_name,
                unit_weight_milli, unit_cost_cents, unit_value_units, quantity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    load_id,
                    item["product"]["id"],
                    item["product"]["code"],
                    item["product"]["name"],
                    item["product"]["weight_milli"],
                    item["product"]["cost_cents"],
                    item["product"]["value_units"],
                    item["quantity"],
                )
                for item in result["selected"]
            ],
        )
        database.execute("PRAGMA optimize")
        database.commit()
    except Exception:
        database.rollback()
        raise
    return load_id


def release_load(load_id: int) -> str:
    database = get_db()
    database.execute(
        "ATTACH DATABASE ? AS loads_store", (current_loads_database_path(),)
    )
    try:
        database.execute("BEGIN IMMEDIATE")
        load = database.execute(
            "SELECT * FROM loads_store.loads WHERE id = ?", (load_id,)
        ).fetchone()
        if load is None:
            raise LookupError(load_id)
        items = database.execute(
            "SELECT * FROM loads_store.load_items WHERE load_id = ?", (load_id,)
        ).fetchall()
        for item in items:
            updated = database.execute(
                """
                UPDATE products
                SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND quantity >= ?
                """,
                (item["quantity"], item["product_id"], item["quantity"]),
            )
            if updated.rowcount != 1:
                raise ValidationError(
                    f"Não foi possível liberar a carga porque o estoque de "
                    f"{item['product_name']} ficou abaixo da quantidade reservada."
                )
        database.execute(
            "DELETE FROM loads_store.load_items WHERE load_id = ?", (load_id,)
        )
        database.execute("DELETE FROM loads_store.loads WHERE id = ?", (load_id,))
        database.commit()
        load_name = str(load["name"])
    except Exception:
        database.rollback()
        raise
    finally:
        database.execute("DETACH DATABASE loads_store")
    return load_name


def get_product_or_404(database: sqlite3.Connection, product_id: int):
    from flask import abort

    row = database.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


def empty_product_form() -> dict[str, str]:
    return {
        "code": "",
        "name": "",
        "weight": "",
        "cost": "",
        "value": "",
        "quantity": "",
    }


def product_form_from_request() -> dict[str, str]:
    return {field: request.form.get(field, "").strip() for field in empty_product_form()}


def product_form_from_row(row: sqlite3.Row) -> dict[str, str]:
    return {
        "code": row["code"],
        "name": row["name"],
        "weight": scaled_decimal_string(row["weight_milli"], WEIGHT_SCALE, 3),
        "cost": scaled_decimal_string(row["cost_cents"], MONEY_SCALE, 2),
        "value": scaled_decimal_string(row["value_units"], VALUE_SCALE, 2),
        "quantity": str(row["quantity"]),
    }


def validate_product_form(form: dict[str, str]) -> tuple[str, str, int, int, int, int]:
    code = form["code"].strip().upper()
    name = form["name"].strip()
    if not code:
        raise ValidationError("Informe o código do produto.")
    if len(code) > 30:
        raise ValidationError("O código deve ter no máximo 30 caracteres.")
    if not name:
        raise ValidationError("Informe o nome do produto.")
    if len(name) > 120:
        raise ValidationError("O nome deve ter no máximo 120 caracteres.")

    weight = parse_scaled_decimal(
        form["weight"], WEIGHT_SCALE, "Peso/carga unitária", False
    )
    cost = parse_scaled_decimal(form["cost"], MONEY_SCALE, "Custo", True)
    value = parse_scaled_decimal(form["value"], VALUE_SCALE, "Valor agregado", True)

    try:
        quantity = int(form["quantity"])
    except (TypeError, ValueError):
        raise ValidationError("A quantidade deve ser um número inteiro.") from None
    if quantity < 0:
        raise ValidationError("A quantidade não pode ser negativa.")
    if quantity > 1_000_000:
        raise ValidationError("A quantidade informada é muito alta.")

    return code, name, weight, cost, value, quantity


def parse_scaled_decimal(
    raw_value: str,
    scale: int,
    label: str,
    allow_zero: bool,
) -> int:
    normalized = (raw_value or "").strip().replace(" ", "")
    if not normalized:
        raise ValidationError(f"Informe {label.lower()}.")

    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    else:
        normalized = normalized.replace(",", ".")

    try:
        number = Decimal(normalized)
    except InvalidOperation:
        raise ValidationError(f"{label} deve ser um número válido.") from None

    if not number.is_finite():
        raise ValidationError(f"{label} deve ser um número válido.")
    if number < 0 or (number == 0 and not allow_zero):
        comparison = "maior ou igual a zero" if allow_zero else "maior que zero"
        raise ValidationError(f"{label} deve ser {comparison}.")

    scaled = (number * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if scaled > 2_000_000_000:
        raise ValidationError(f"{label} informado é muito alto.")
    return int(scaled)


def optimize_inventory(
    products: Iterable[Any],
    max_weight: int,
    max_budget: int | None = None,
    *,
    max_units: int | None = None,
    constraint_mode: str = "budget",
) -> dict[str, Any]:
    """Resolve o Knapsack limitado com duas restrições por programação dinâmica.

    Cada quantidade é decomposta em blocos binários. A fronteira de estados mantém
    somente combinações não dominadas por peso, segundo limite e valor,
    preservando a solução exata sem alocar uma matriz densa potencialmente enorme.
    """

    if max_weight <= 0:
        raise ValidationError("A capacidade de carga deve ser maior que zero.")
    if constraint_mode == "budget":
        if max_budget is None or max_budget < 0:
            raise ValidationError("O orçamento não pode ser negativo.")
        max_constraint = max_budget
    elif constraint_mode == "quantity":
        if max_units is None or max_units <= 0:
            raise ValidationError("A quantidade máxima deve ser maior que zero.")
        max_constraint = max_units
    else:
        raise ValidationError("Modo de restrição inválido.")

    initial = KnapsackState(0, 0, 0)
    frontier: dict[tuple[int, int], KnapsackState] = {(0, 0): initial}
    product_list = list(products)
    products_by_id = {int(product["id"]): product for product in product_list}

    for product in product_list:
        available = int(product["quantity"])
        if available <= 0:
            continue

        for chunk in binary_chunks(available):
            chunk_weight = int(product["weight_milli"]) * chunk
            chunk_constraint = (
                int(product["cost_cents"]) * chunk
                if constraint_mode == "budget"
                else chunk
            )
            chunk_value = int(product["value_units"]) * chunk

            next_frontier = dict(frontier)
            for state in tuple(frontier.values()):
                new_weight = state.total_weight + chunk_weight
                new_constraint = state.total_constraint + chunk_constraint
                if new_weight > max_weight or new_constraint > max_constraint:
                    continue

                key = (new_weight, new_constraint)
                candidate_value = state.total_value + chunk_value
                existing = next_frontier.get(key)
                if existing is None or candidate_value > existing.total_value:
                    next_frontier[key] = KnapsackState(
                        total_weight=new_weight,
                        total_constraint=new_constraint,
                        total_value=candidate_value,
                        previous=state,
                        product_id=int(product["id"]),
                        quantity=chunk,
                    )

            frontier = prune_dominated_states(next_frontier)
            if len(frontier) > MAX_PARETO_STATES:
                raise OptimizationTooLargeError(
                    "A combinação gerou estados demais para este computador. "
                    "Reduza as quantidades ou use limites menores."
                )

    best = max(
        frontier.values(),
        key=lambda state: (
            state.total_value,
            -state.total_weight,
            -state.total_constraint,
        ),
    )
    quantities: dict[int, int] = {}
    cursor = best
    while cursor.previous is not None:
        assert cursor.product_id is not None
        quantities[cursor.product_id] = (
            quantities.get(cursor.product_id, 0) + cursor.quantity
        )
        cursor = cursor.previous

    total_cost = sum(
        int(products_by_id[product_id]["cost_cents"]) * quantity
        for product_id, quantity in quantities.items()
    )
    total_units = sum(quantities.values())

    return {
        "quantities": quantities,
        "total_weight": best.total_weight,
        "total_cost": total_cost,
        "total_units": total_units,
        "total_value": best.total_value,
        "states_evaluated": len(frontier),
    }


def binary_chunks(quantity: int):
    block = 1
    remaining = quantity
    while remaining > 0:
        current = min(block, remaining)
        yield current
        remaining -= current
        block *= 2


def prune_dominated_states(
    states: dict[tuple[int, int], KnapsackState],
) -> dict[tuple[int, int], KnapsackState]:
    """Remove estados que usam mais recursos sem produzir valor maior."""

    ordered = sorted(
        states.values(),
        key=lambda state: (
            state.total_weight,
            state.total_constraint,
            -state.total_value,
        ),
    )
    resources = sorted({state.total_constraint for state in ordered})
    resource_indexes = {
        resource: index + 1 for index, resource in enumerate(resources)
    }
    fenwick = [-1] * (len(resources) + 1)
    kept: dict[tuple[int, int], KnapsackState] = {}

    def best_value_until(index: int) -> int:
        best_value = -1
        while index > 0:
            best_value = max(best_value, fenwick[index])
            index -= index & -index
        return best_value

    def update(index: int, value: int) -> None:
        while index < len(fenwick):
            fenwick[index] = max(fenwick[index], value)
            index += index & -index

    for state in ordered:
        index = resource_indexes[state.total_constraint]
        if best_value_until(index) >= state.total_value:
            continue
        kept[(state.total_weight, state.total_constraint)] = state
        update(index, state.total_value)

    return kept


def scaled_decimal_string(value: int, scale: int, decimal_places: int) -> str:
    number = Decimal(value) / Decimal(scale)
    return f"{number:.{decimal_places}f}".rstrip("0").rstrip(".")


def format_number_pt(value: int | float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def format_money(value: int) -> str:
    number = Decimal(value) / MONEY_SCALE
    formatted = f"{number:,.2f}"
    return "R$ " + formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_weight(value: int) -> str:
    number = Decimal(value) / WEIGHT_SCALE
    formatted = f"{number:,.3f}".rstrip("0").rstrip(".")
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_score(value: int) -> str:
    number = Decimal(value) / VALUE_SCALE
    formatted = f"{number:,.2f}".rstrip("0").rstrip(".")
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_datetime_pt(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d/%m/%Y às %H:%M")


if __name__ == "__main__":
    create_app().run(debug=True)
