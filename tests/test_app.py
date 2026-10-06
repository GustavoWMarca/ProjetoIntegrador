import tempfile
import unittest
import sqlite3
from contextlib import closing
from itertools import product as cartesian_product
from pathlib import Path
from random import Random

from app import create_app, optimize_inventory, parse_scaled_decimal


class KnapsackAlgorithmTests(unittest.TestCase):
    def test_finds_exact_bounded_solution_with_two_constraints(self):
        products = [
            {
                "id": 1,
                "quantity": 2,
                "weight_milli": 4,
                "cost_cents": 5,
                "value_units": 8,
            },
            {
                "id": 2,
                "quantity": 3,
                "weight_milli": 3,
                "cost_cents": 4,
                "value_units": 5,
            },
        ]

        result = optimize_inventory(products, max_weight=10, max_budget=12)

        self.assertEqual(result["total_value"], 16)
        self.assertEqual(result["total_weight"], 8)
        self.assertEqual(result["total_cost"], 10)
        self.assertEqual(result["quantities"], {1: 2})

    def test_never_exceeds_available_quantity(self):
        products = [
            {
                "id": 1,
                "quantity": 3,
                "weight_milli": 10,
                "cost_cents": 10,
                "value_units": 10,
            }
        ]

        result = optimize_inventory(products, max_weight=1_000, max_budget=1_000)

        self.assertEqual(result["quantities"], {1: 3})

    def test_can_use_quantity_as_second_constraint(self):
        products = [
            {
                "id": 1,
                "quantity": 8,
                "weight_milli": 2,
                "cost_cents": 1_000,
                "value_units": 5,
            }
        ]

        result = optimize_inventory(
            products,
            max_weight=100,
            max_units=3,
            constraint_mode="quantity",
        )

        self.assertEqual(result["quantities"], {1: 3})
        self.assertEqual(result["total_units"], 3)
        self.assertEqual(result["total_cost"], 3_000)

    def test_accepts_brazilian_decimal_format(self):
        self.assertEqual(
            parse_scaled_decimal("1.234,56", 100, "Valor", True), 123_456
        )
        self.assertEqual(parse_scaled_decimal("2,750", 1_000, "Peso", False), 2_750)

    def test_matches_brute_force_on_small_random_cases(self):
        random = Random(2026)
        for case_number in range(100):
            products = []
            for product_id in range(1, random.randint(2, 5) + 1):
                products.append(
                    {
                        "id": product_id,
                        "quantity": random.randint(0, 4),
                        "weight_milli": random.randint(1, 8),
                        "cost_cents": random.randint(0, 8),
                        "value_units": random.randint(0, 12),
                    }
                )
            max_weight = random.randint(4, 20)
            max_budget = random.randint(0, 20)

            expected_value = 0
            for quantities in cartesian_product(
                *(range(item["quantity"] + 1) for item in products)
            ):
                weight = sum(
                    item["weight_milli"] * quantity
                    for item, quantity in zip(products, quantities)
                )
                cost = sum(
                    item["cost_cents"] * quantity
                    for item, quantity in zip(products, quantities)
                )
                value = sum(
                    item["value_units"] * quantity
                    for item, quantity in zip(products, quantities)
                )
                if weight <= max_weight and cost <= max_budget:
                    expected_value = max(expected_value, value)

            actual = optimize_inventory(products, max_weight, max_budget)
            self.assertEqual(
                actual["total_value"],
                expected_value,
                msg=f"Falha no caso aleatório {case_number}",
            )


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temporary_directory.name) / "test.db")
        self.database_path = database_path
        self.loads_database_path = str(
            Path(self.temporary_directory.name) / "loads-test.db"
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE": database_path,
                "LOADS_DATABASE": self.loads_database_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_product(self):
        return self.client.post(
            "/products/new",
            data={
                "code": "P001",
                "name": "Cafeteira",
                "weight": "3,200",
                "cost": "180,00",
                "value": "270,00",
                "quantity": "4",
            },
            follow_redirects=True,
        )

    def create_second_product(self):
        return self.client.post(
            "/products/new",
            data={
                "code": "P002",
                "name": "Ferro",
                "weight": "8,000",
                "cost": "70,00",
                "value": "50,00",
                "quantity": "4",
            },
            follow_redirects=True,
        )

    def create_load(self, mode="budget"):
        data = {
            "name": "Entrega Centro",
            "truck_identifier": "ABC1D23",
            "max_weight": "6,400",
            "constraint_mode": mode,
            "max_budget": "360,00",
            "max_units": "2",
            "include_1": "1",
            "min_1": "1",
            "max_1": "4",
            "action": "save",
        }
        return self.client.post("/loads/plan", data=data, follow_redirects=True)

    def test_full_crud_flow(self):
        response = self.create_product()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cafeteira", response.data)

        response = self.client.post(
            "/products/1/edit",
            data={
                "code": "P001",
                "name": "Cafeteira Premium",
                "weight": "3,500",
                "cost": "200,00",
                "value": "310,00",
                "quantity": "2",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Cafeteira Premium", response.data)

        response = self.client.post("/products/1/delete", follow_redirects=True)
        self.assertNotIn(b"Cafeteira Premium</strong>", response.data)

    def test_load_preview_displays_selected_product(self):
        self.create_product()

        response = self.client.post(
            "/loads/plan",
            data={
                "name": "Entrega Centro",
                "truck_identifier": "ABC1D23",
                "max_weight": "6,400",
                "constraint_mode": "budget",
                "max_budget": "360,00",
                "include_1": "1",
                "min_1": "1",
                "max_1": "4",
                "action": "calculate",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Prévia calculada".encode(), response.data)
        self.assertIn(b"Cafeteira", response.data)
        self.assertIn(b">2</strong>", response.data)

    def test_load_is_saved_in_separate_database_and_reserves_stock(self):
        self.create_product()

        response = self.create_load()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Aguardando liberação".encode(), response.data)
        with closing(sqlite3.connect(self.loads_database_path)) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM loads").fetchone()[0], 1)
            self.assertEqual(
                database.execute("SELECT quantity FROM load_items").fetchone()[0], 2
            )
        products_page = self.client.get("/products")
        self.assertIn("2 reservadas".encode(), products_page.data)

    def test_release_decrements_inventory_and_deletes_pending_load(self):
        self.create_product()
        self.create_load()

        response = self.client.post("/loads/1/release", follow_redirects=True)

        self.assertIn("Nenhuma carga aguardando liberação".encode(), response.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            self.assertEqual(
                database.execute("SELECT quantity FROM products WHERE id = 1").fetchone()[0],
                2,
            )
        with closing(sqlite3.connect(self.loads_database_path)) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM loads").fetchone()[0], 0)

    def test_reserved_product_cannot_be_deleted(self):
        self.create_product()
        self.create_load()

        response = self.client.post("/products/1/delete", follow_redirects=True)

        self.assertIn("não pode ser excluído".encode(), response.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)

    def test_minimums_guarantee_diversity_before_optimizing_remainder(self):
        self.create_product()
        self.create_second_product()

        response = self.client.post(
            "/loads/plan",
            data={
                "name": "Carga diversificada",
                "truck_identifier": "DIV1234",
                "max_weight": "100,000",
                "constraint_mode": "quantity",
                "max_units": "5",
                "include_1": "1",
                "min_1": "1",
                "max_1": "4",
                "include_2": "1",
                "min_2": "2",
                "max_2": "4",
                "action": "save",
            },
            follow_redirects=True,
        )

        self.assertIn("Aguardando liberação".encode(), response.data)
        with closing(sqlite3.connect(self.loads_database_path)) as database:
            quantities = dict(
                database.execute(
                    "SELECT product_id, quantity FROM load_items ORDER BY product_id"
                ).fetchall()
            )
        self.assertEqual(quantities, {1: 3, 2: 2})

    def test_rejects_minimum_greater_than_maximum(self):
        self.create_product()

        response = self.client.post(
            "/loads/plan",
            data={
                "name": "Carga inválida",
                "truck_identifier": "INV1234",
                "max_weight": "100,000",
                "constraint_mode": "quantity",
                "max_units": "5",
                "include_1": "1",
                "min_1": "3",
                "max_1": "2",
                "action": "calculate",
            },
        )

        self.assertIn("não pode ser maior que o máximo".encode(), response.data)

    def test_rejects_duplicate_product_code(self):
        self.create_product()
        response = self.create_product()

        self.assertIn("Já existe um produto".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
