# Part 3: Low Stock Alerts Endpoint

## 1. Implementation

```python
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify
from sqlalchemy import func

from models import (
    Company, Warehouse, Product,
    Inventory, InventoryTransaction,
    Supplier, SupplierProduct,
    db,
)

app = Flask(__name__)


@app.get("/api/companies/<int:company_id>/alerts/low-stock")
def low_stock_alerts(company_id: int):
    company = db.session.get(Company, company_id)
    if company is None:
        return jsonify({"error": "Company not found"}), 404

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    recent_sales = (
        db.session.query(
            InventoryTransaction.product_id,
            InventoryTransaction.warehouse_id,
            func.coalesce(
                func.sum(func.abs(InventoryTransaction.quantity_delta)), 0
            ).label("total_sold"),
        )
        .filter(
            InventoryTransaction.transaction_type == "sale",
            InventoryTransaction.created_at >= thirty_days_ago,
        )
        .group_by(
            InventoryTransaction.product_id,
            InventoryTransaction.warehouse_id,
        )
        .subquery()
    )

    low_stock_items = (
        db.session.query(
            Inventory,
            Product,
            Warehouse,
            recent_sales.c.total_sold,
        )
        .join(Product, Product.id == Inventory.product_id)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .join(
            recent_sales,
            (recent_sales.c.product_id == Inventory.product_id) &
            (recent_sales.c.warehouse_id == Inventory.warehouse_id),
        )
        .filter(
            Warehouse.company_id == company_id,
            Product.is_active == True,
            Product.low_stock_threshold.isnot(None),
            Product.low_stock_threshold > 0,
            Inventory.quantity < Product.low_stock_threshold,
        )
        .all()
    )

    if not low_stock_items:
        return jsonify({"alerts": [], "total_alerts": 0}), 200

    product_ids = [row.Product.id for row in low_stock_items]

    supplier_rows = (
        db.session.query(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .filter(SupplierProduct.product_id.in_(product_ids))
        .distinct()
        .all()
    )

    supplier_map = {}
    for sp, supplier in supplier_rows:
        if sp.product_id not in supplier_map or sp.is_preferred:
            supplier_map[sp.product_id] = supplier

    alerts = []
    for row in low_stock_items:
        inventory = row.Inventory
        product = row.Product
        warehouse = row.Warehouse
        total_sold = row.total_sold or 0

        avg_daily_sales = total_sold / 30

        if avg_daily_sales > 0:
            days_until_stockout = round(inventory.quantity / avg_daily_sales, 1)
        else:
            days_until_stockout = None

        supplier = supplier_map.get(product.id)
        supplier_out = (
            {
                "id": supplier.id,
                "name": supplier.name,
                "contact_email": supplier.email,
            }
            if supplier else None
        )

        alerts.append({
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku,
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "current_stock": inventory.quantity,
            "threshold": product.low_stock_threshold,
            "days_until_stockout": days_until_stockout,
            "supplier": supplier_out,
        })

    return jsonify({"alerts": alerts, "total_alerts": len(alerts)}), 200
```

---

## 2. Edge Cases Handling

### No recent sales data

The sales subquery uses an INNER JOIN, so products with zero sales in the last 30 days are excluded entirely. This is intentional — a product that hasn't sold recently does not need a reorder alert regardless of stock level.

### avg_daily_sales = 0 / division by zero

If `total_sold` comes back as 0, `avg_daily_sales` becomes 0 and `days_until_stockout` is set to `None` instead of dividing. The alert is still returned, but the client is explicitly informed that stockout timing cannot be computed.

### No supplier found

If no supplier is linked, `supplier_map.get(product.id)` returns `None` and the response includes `"supplier": null`. The alert is still returned since missing supplier information is useful for debugging or operations.

### Multiple suppliers

All suppliers are fetched in one query. The logic prioritizes `is_preferred = True`. If multiple preferred suppliers exist, the last one wins. This is acceptable for now but could be made deterministic with ordering.

### Zero or negative stock

Database constraint `CHECK (quantity >= 0)` prevents negative values. Zero stock is valid and will trigger alerts if below threshold. `days_until_stockout` becomes `0.0` if recent sales exist.

### Missing threshold value

If `low_stock_threshold` is `NULL`, the condition evaluates to false in SQL and the product is excluded. This is mitigated in code by explicitly filtering out NULL thresholds.

---

## 3. Assumptions and Approach

### Threshold source

`low_stock_threshold` is assumed to be a column on the `products` table (`INTEGER NOT NULL DEFAULT 10`). This represents a fixed reorder point per product.

### Definition of "recent sales"

Defined as the last 30 days using UTC timestamps. This is a reasonable default and aligns with the average calculation window.

### Average daily sales calculation

Computed as:

```
total units sold in last 30 days / 30
```

This is a simple rolling average. In production, this could be replaced with a weighted or exponential moving average for better accuracy.

### Supplier selection

Preferred supplier (`is_preferred = True`) is selected if available. Otherwise, any linked supplier is returned. Supplier data is fetched in a single query to avoid N+1 issues.

### Sales quantity representation

Sales are assumed to be stored as negative `quantity_delta`. `abs()` is used during aggregation to compute total units sold.

### Overall approach

The implementation uses:

* 1 query to validate company
* 1 query to fetch low-stock items with aggregated sales
* 1 query to fetch supplier data

This keeps the logic simple, avoids N+1 queries, and maintains readability. Business logic calculations are handled in Python rather than SQL to keep queries clean and easier to debug.
