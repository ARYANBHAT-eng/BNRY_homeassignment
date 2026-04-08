from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.exc import IntegrityError


app = Flask(__name__)
db = SQLAlchemy(app)



# Models (modified: price stored as integer cents; inventory uniqueness added)


class Product(db.Model):
    __tablename__ = "products"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(255), nullable=False)
    sku          = db.Column(db.String(64),  nullable=False, unique=True)
    price_cents  = db.Column(db.Integer,     nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)

    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_products_price_nonneg"),
    )


class Inventory(db.Model):
    __tablename__ = "inventories"

    id           = db.Column(db.Integer, primary_key=True)
    product_id   = db.Column(db.Integer, db.ForeignKey("products.id"),   nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False)
    quantity     = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_inventory_product_warehouse"),
        CheckConstraint("quantity >= 0",               name="ck_inventory_quantity_nonneg"),
    )



# Helpers


def _parse_price_to_cents(raw: object) -> int:
    """
    Parse a price value to integer cents.

    Accepts strings and Decimal-like values (e.g. '12.34').
    Rejects ints and floats to prevent silent precision loss.
    Raises ValueError with a user-safe message on invalid input.
    """
    if raw is None:
        raise ValueError("price is required")
    if isinstance(raw, (int, float)):
        raise ValueError("price must be a string or decimal, e.g. '12.34'")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ValueError("price must be a valid number, e.g. '12.34'")
    if value.is_nan() or value.is_infinite():
        raise ValueError("price must be a finite number")
    if value < 0:
        raise ValueError("price must be non-negative")
    if value.as_tuple().exponent < -2:
        raise ValueError("price must have at most 2 decimal places")
    return int((value * 100).to_integral_exact())



# Route


@app.post("/api/products")
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400

    required_fields = ("name", "sku", "price", "warehouse_id")
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": "Missing required fields", "missing": missing}), 400

    name = str(data["name"]).strip()
    sku  = str(data["sku"]).strip()

    if not name:
        return jsonify({"error": "name must be non-empty"}), 400
    if not sku:
        return jsonify({"error": "sku must be non-empty"}), 400

    try:
        warehouse_id = int(data["warehouse_id"])
    except (TypeError, ValueError):
        return jsonify({"error": "warehouse_id must be an integer"}), 400

    try:
        price_cents = _parse_price_to_cents(data["price"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        initial_quantity = int(data.get("initial_quantity", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "initial_quantity must be an integer"}), 400
    if initial_quantity < 0:
        return jsonify({"error": "initial_quantity must be >= 0"}), 400

    # Validate warehouse before opening a transaction.
    if db.session.get(Warehouse, warehouse_id) is None:
        return jsonify({"error": "warehouse not found"}), 404

    try:
        with db.session.begin():
            product = Product(
                name=name,
                sku=sku,
                price_cents=price_cents,
                warehouse_id=warehouse_id,
            )
            db.session.add(product)
            db.session.flush()  # Populates product.id before inventory insert.

            inventory = Inventory(
                product_id=product.id,
                warehouse_id=warehouse_id,
                quantity=initial_quantity,
            )
            db.session.add(inventory)

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "SKU already exists"}), 409

    except Exception:
        db.session.rollback()
        app.logger.exception("Unexpected error in create_product")
        return jsonify({"error": "Internal server error"}), 500

    return jsonify({"message": "Product created", "product_id": product.id}), 201