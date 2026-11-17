"""Catálogo fictício para demonstração. Sem --apply, apenas mostra os totais.

Ao aplicar, faz backup dos dois bancos antes de substituir produtos e remover
cargas de demonstração. Cargas que não sejam de demonstração bloqueiam a ação.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path


# Código, nome, peso em kg, comprimento/largura/altura da embalagem em cm,
# custo em reais, pontuação de valor e quantidade física.
# Medidas, custos e quantidades são fictícios; não são dados de fabricantes.
CATALOG = [
    ("PEQ001", "Cabo USB-C", "0.08", 12, 8, 3, 15, 25, 80000),
    ("PEQ002", "Carregador USB", "0.18", 10, 8, 5, 35, 45, 60000),
    ("PEQ003", "Fone de ouvido", "0.12", 12, 10, 4, 40, 60, 50000),
    ("PEQ004", "Mouse sem fio", "0.15", 15, 10, 6, 45, 55, 40000),
    ("PEQ005", "Lâmpada LED", "0.10", 12, 7, 7, 12, 20, 80000),
    ("PEQ006", "Pilha AA - pacote com 4", "0.10", 10, 8, 2, 10, 15, 100000),
    ("PEQ007", "Caneta - caixa com 50", "0.35", 16, 10, 6, 30, 35, 30000),
    ("PEQ008", "Caderno universitário", "0.45", 28, 21, 2, 18, 25, 40000),
    ("PEQ009", "Sabonete - caixa com 12", "1.20", 22, 15, 10, 24, 30, 50000),
    ("PEQ010", "Toalha de rosto embalada", "0.25", 25, 18, 4, 12, 20, 50000),
    ("PEQ011", "Garrafa térmica 500 ml", "0.40", 26, 9, 9, 35, 45, 20000),
    ("PEQ012", "Caneca de cerâmica embalada", "0.45", 14, 12, 12, 20, 25, 25000),
    ("MED001", "Teclado USB", "0.65", 48, 18, 5, 60, 70, 15000),
    ("MED002", "Roteador Wi-Fi", "0.70", 30, 22, 8, 150, 180, 12000),
    ("MED003", "Caixa de som portátil", "1.20", 28, 15, 14, 180, 210, 10000),
    ("MED004", "Ferro elétrico", "1.35", 30, 15, 15, 75, 100, 14000),
    ("MED005", "Sanduicheira", "2.70", 30, 25, 12, 135, 200, 12000),
    ("MED006", "Liquidificador", "2.10", 25, 20, 40, 110, 165, 10000),
    ("MED007", "Cafeteira", "3.20", 30, 25, 35, 180, 270, 12000),
    ("MED008", "Batedeira", "3.50", 38, 28, 35, 220, 290, 8000),
    ("MED009", "Panela elétrica", "3.00", 35, 30, 30, 200, 260, 10000),
    ("MED010", "Air fryer", "5.50", 40, 35, 40, 350, 420, 8000),
    ("MED011", "Aspirador compacto", "4.50", 48, 32, 30, 300, 360, 6000),
    ("MED012", "Ventilador de mesa", "4.80", 45, 20, 50, 220, 330, 10000),
    ("MED013", "Impressora multifuncional", "6.00", 50, 40, 30, 650, 720, 5000),
    ("MED014", "Monitor 24 polegadas", "4.00", 65, 45, 15, 750, 820, 5000),
    ("MED015", "Micro-ondas", "12.00", 55, 45, 35, 450, 650, 4000),
    ("MED016", "Forno elétrico", "10.00", 60, 50, 40, 500, 620, 4000),
    ("GRA001", "Televisor 55 polegadas", "18.00", 140, 90, 20, 2200, 2500, 2000),
    ("GRA002", "Televisor 75 polegadas", "35.00", 190, 115, 25, 4800, 5200, 1000),
    ("GRA003", "Geladeira duplex", "75.00", 75, 80, 190, 3000, 3500, 1500),
    ("GRA004", "Freezer horizontal", "65.00", 120, 75, 95, 2600, 3000, 1000),
    ("GRA005", "Máquina de lavar", "65.00", 70, 75, 110, 2000, 2400, 2000),
    ("GRA006", "Secadora de roupas", "50.00", 70, 70, 95, 2300, 2700, 1000),
    ("GRA007", "Fogão de cinco bocas", "40.00", 85, 75, 100, 1400, 1800, 1800),
    ("GRA008", "Lava-louças", "45.00", 65, 65, 90, 2400, 2800, 1200),
    ("GRA009", "Ar-condicionado portátil", "32.00", 50, 45, 90, 2100, 2500, 1800),
    ("GRA010", "Bebedouro de coluna", "18.00", 40, 40, 110, 700, 900, 2500),
    ("MOV001", "Sofá de três lugares embalado", "80.00", 220, 100, 90, 1800, 2300, 800),
    ("MOV002", "Poltrona embalada", "28.00", 90, 85, 100, 650, 900, 1500),
    ("MOV003", "Colchão de casal embalado", "25.00", 190, 140, 30, 750, 1000, 2000),
    ("MOV004", "Colchão king embalado", "45.00", 205, 195, 40, 1500, 1900, 1000),
    ("MOV005", "Guarda-roupa desmontado - kit", "110.00", 220, 60, 45, 1200, 1600, 1200),
    ("MOV006", "Mesa de jantar desmontada", "45.00", 160, 95, 25, 700, 950, 1800),
    ("MOV007", "Cadeira de escritório", "18.00", 75, 65, 65, 450, 650, 3000),
    ("MOV008", "Estante desmontada", "30.00", 190, 40, 20, 350, 500, 2500),
    ("MOV009", "Cômoda desmontada", "40.00", 110, 55, 35, 500, 700, 2000),
    ("MOV010", "Mesa de centro embalada", "15.00", 100, 60, 45, 250, 400, 2500),
    ("ESP001", "Bicicleta desmontada", "18.00", 145, 25, 80, 900, 1200, 2500),
    ("ESP002", "Esteira ergométrica dobrada", "65.00", 170, 80, 40, 2500, 3100, 800),
    ("ESP003", "Caixa organizadora grande", "2.00", 60, 40, 40, 50, 75, 12000),
    ("ESP004", "Mala de viagem grande", "5.00", 80, 55, 35, 250, 350, 6000),
    ("ESP005", "Saco de argamassa", "20.00", 50, 35, 12, 25, 35, 20000),
    ("ESP006", "Piso cerâmico - caixa", "25.00", 65, 65, 10, 65, 90, 15000),
    ("ESP007", "Tinta - caixa com lata de 18 L", "26.00", 35, 35, 45, 250, 320, 10000),
    ("ESP008", "Escada dobrável embalada", "12.00", 200, 50, 15, 250, 350, 4000),
    ("ESP009", "Tubo PVC - feixe de 10", "15.00", 300, 25, 20, 180, 250, 5000),
    ("ESP010", "Papel A4 - caixa com 10 resmas", "25.00", 45, 32, 28, 220, 280, 12000),
    ("ESP011", "Ração - saco de 15 kg", "15.00", 70, 45, 18, 120, 170, 15000),
    ("ESP012", "Bola esportiva - caixa com 12", "4.00", 70, 50, 50, 240, 330, 7000),
]


def scaled(value, scale):
    decimal = Decimal(str(value)) * scale
    if decimal != decimal.to_integral_value() or decimal <= 0:
        raise ValueError(f"Medida inválida: {value}")
    return int(decimal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplicar com backup prévio")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stock = (root / "instance" / "estoque.db").resolve(strict=True)
    loads = (root / "instance" / "cargas.db").resolve(strict=True)
    rows = [
        (code, name, scaled(weight, 1000), scaled(length, 100),
         scaled(width, 100), scaled(height, 100), scaled(cost, 100),
         scaled(value, 100), quantity)
        for code, name, weight, length, width, height, cost, value, quantity in CATALOG
    ]
    assert len(rows) == len({row[0] for row in rows}) == 60
    assert all(isinstance(row[-1], int) and 0 < row[-1] <= 1_000_000 for row in rows)
    summary = {"products": len(rows), "units": sum(row[-1] for row in rows)}
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False))
        return

    with closing(sqlite3.connect(stock, timeout=30)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("ATTACH DATABASE ? AS loads_store", (str(loads),))
        db.execute("BEGIN IMMEDIATE")
        try:
            pending = db.execute("SELECT id, name FROM loads_store.loads").fetchall()
            if any(not name.startswith("Carga demonstração") for _, name in pending):
                raise RuntimeError("Existem cargas não demonstrativas; operação cancelada.")
            old_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            users_before = db.execute("SELECT * FROM users ORDER BY id").fetchall()
            backup = root.parent / "backups" / ("estoque_antes_catalogo_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
            backup.mkdir(parents=True, exist_ok=False)
            # A transação impede novas escritas durante a cópia e a substituição.
            for path in (stock, loads):
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as src:
                    with closing(sqlite3.connect(backup / path.name)) as dest:
                        src.backup(dest)
                        assert dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            db.execute("DELETE FROM loads_store.load_positions")
            db.execute("DELETE FROM loads_store.load_items")
            db.execute("DELETE FROM loads_store.loads")
            db.execute("DELETE FROM products")
            db.executemany(
                "INSERT INTO products (code, name, weight_milli, length_centimeters, "
                "width_centimeters, height_centimeters, cost_cents, value_units, quantity) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
            )
            assert db.execute("SELECT COUNT(*), SUM(quantity) FROM products").fetchone() == (summary["products"], summary["units"])
            assert db.execute("SELECT * FROM users ORDER BY id").fetchall() == users_before
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("PRAGMA loads_store.foreign_key_check").fetchall() == []
            db.commit()
        except Exception:
            db.rollback()
            raise
    summary.update(backup=str(backup), removed_products=old_products, removed_demo_loads=len(pending))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
