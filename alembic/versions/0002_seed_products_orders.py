"""seed products and orders tables for sql_lookup tool

Revision ID: 0002_seed_products_orders
Revises: 0001_initial
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_seed_products_orders"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── products table ────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
    )

    # ── orders table ──────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── Seed products (20 rows) ───────────────────────────────────────────
    products = sa.table(
        "products",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("price", sa.Float),
        sa.column("category", sa.String),
    )

    op.bulk_insert(products, [
        {"id": 1, "name": "Wireless Mouse", "price": 29.99, "category": "electronics"},
        {"id": 2, "name": "Mechanical Keyboard", "price": 89.99, "category": "electronics"},
        {"id": 3, "name": "USB-C Hub", "price": 45.00, "category": "electronics"},
        {"id": 4, "name": "Monitor Stand", "price": 34.50, "category": "accessories"},
        {"id": 5, "name": "Webcam HD", "price": 59.99, "category": "electronics"},
        {"id": 6, "name": "Desk Lamp", "price": 24.99, "category": "accessories"},
        {"id": 7, "name": "Noise-Cancelling Headphones", "price": 199.99, "category": "audio"},
        {"id": 8, "name": "Bluetooth Speaker", "price": 49.99, "category": "audio"},
        {"id": 9, "name": "External SSD 1TB", "price": 109.99, "category": "storage"},
        {"id": 10, "name": "USB Flash Drive 64GB", "price": 12.99, "category": "storage"},
        {"id": 11, "name": "Laptop Sleeve 15\"", "price": 19.99, "category": "accessories"},
        {"id": 12, "name": "HDMI Cable 2m", "price": 8.99, "category": "cables"},
        {"id": 13, "name": "Ethernet Cable Cat6", "price": 6.50, "category": "cables"},
        {"id": 14, "name": "Power Strip 6-Outlet", "price": 15.99, "category": "accessories"},
        {"id": 15, "name": "Ergonomic Chair Cushion", "price": 39.99, "category": "furniture"},
        {"id": 16, "name": "Standing Desk Mat", "price": 44.99, "category": "furniture"},
        {"id": 17, "name": "Wireless Charger", "price": 22.50, "category": "electronics"},
        {"id": 18, "name": "Screen Protector Pack", "price": 9.99, "category": "accessories"},
        {"id": 19, "name": "Cable Management Kit", "price": 14.99, "category": "accessories"},
        {"id": 20, "name": "Portable Battery Pack", "price": 35.00, "category": "electronics"},
    ])

    # ── Seed orders (20 rows) ─────────────────────────────────────────────
    orders = sa.table(
        "orders",
        sa.column("id", sa.Integer),
        sa.column("product_id", sa.Integer),
        sa.column("quantity", sa.Integer),
    )

    op.bulk_insert(orders, [
        {"id": 1, "product_id": 1, "quantity": 2},
        {"id": 2, "product_id": 3, "quantity": 1},
        {"id": 3, "product_id": 7, "quantity": 1},
        {"id": 4, "product_id": 2, "quantity": 3},
        {"id": 5, "product_id": 5, "quantity": 1},
        {"id": 6, "product_id": 9, "quantity": 2},
        {"id": 7, "product_id": 12, "quantity": 5},
        {"id": 8, "product_id": 15, "quantity": 1},
        {"id": 9, "product_id": 4, "quantity": 2},
        {"id": 10, "product_id": 8, "quantity": 1},
        {"id": 11, "product_id": 10, "quantity": 10},
        {"id": 12, "product_id": 6, "quantity": 3},
        {"id": 13, "product_id": 11, "quantity": 1},
        {"id": 14, "product_id": 14, "quantity": 2},
        {"id": 15, "product_id": 17, "quantity": 4},
        {"id": 16, "product_id": 20, "quantity": 1},
        {"id": 17, "product_id": 16, "quantity": 1},
        {"id": 18, "product_id": 13, "quantity": 8},
        {"id": 19, "product_id": 18, "quantity": 2},
        {"id": 20, "product_id": 19, "quantity": 3},
    ])


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("products")
