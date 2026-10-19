import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "store.db"

JWT_SECRET = os.getenv("JWT_SECRET", "development-only-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 120

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5500/frontend")

stripe.api_key = STRIPE_SECRET_KEY

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="Progree Secure E-Commerce API",
    version="1.0.0",
    description="JWT authentication, persistent cart, Stripe sandbox checkout, and inventory management."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# -----------------------------
# Database
# -----------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                stripe_session_id TEXT NOT NULL UNIQUE,
                total_cents INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                unit_price_cents INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );
            """
        )

        product_count = conn.execute(
            "SELECT COUNT(*) AS total FROM products"
        ).fetchone()["total"]

        if product_count == 0:
            conn.executemany(
                """
                INSERT INTO products (name, description, price_cents, stock)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("Wireless Mouse", "Compact wireless mouse for everyday work.", 2499, 12),
                    ("Mechanical Keyboard", "Tactile keyboard for coding and productivity.", 5999, 8),
                    ("USB-C Hub", "Multi-port USB-C hub with HDMI and USB ports.", 3499, 15),
                    ("Laptop Stand", "Adjustable aluminum laptop stand.", 3999, 10),
                ],
            )

        conn.commit()


@app.on_event("startup")
def startup_event():
    init_db()


# -----------------------------
# Request models
# -----------------------------
class RegisterPayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class CartPayload(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=20)


# -----------------------------
# Authentication
# -----------------------------
def create_access_token(user_id: int):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_user_id(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_user_id(token)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(row)


# -----------------------------
# Root / health
# -----------------------------
@app.get("/")
def root():
    return {"message": "Secure E-Commerce API is running"}


# -----------------------------
# Auth routes
# -----------------------------
@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterPayload, response: Response):
    email = payload.email.lower().strip()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        password_hash = pwd_context.hash(payload.password)

        cursor = conn.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                payload.name.strip(),
                email,
                password_hash,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        user_id = cursor.lastrowid

    token = create_access_token(user_id)

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Use True over HTTPS in production
        max_age=ACCESS_TOKEN_MINUTES * 60,
    )

    return {"message": "Registration successful"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, response: Response):
    email = payload.email.lower().strip()

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not row or not pwd_context.verify(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(row["id"])

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ACCESS_TOKEN_MINUTES * 60,
    )

    return {"message": "Login successful"}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}


@app.get("/api/auth/me")
def auth_me(user=Depends(get_current_user)):
    return user


# -----------------------------
# Products
# -----------------------------
@app.get("/api/products")
def get_products():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, description, price_cents, stock
            FROM products
            ORDER BY id
            """
        ).fetchall()

    return [dict(row) for row in rows]


# -----------------------------
# Persistent cart
# -----------------------------
def build_cart(user_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                ci.product_id,
                ci.quantity,
                p.name,
                p.price_cents,
                p.stock,
                (p.price_cents * ci.quantity) AS line_total_cents
            FROM cart_items ci
            JOIN products p ON p.id = ci.product_id
            WHERE ci.user_id = ?
            ORDER BY ci.id DESC
            """,
            (user_id,),
        ).fetchall()

    items = [dict(row) for row in rows]

    return {
        "items": items,
        "count": sum(item["quantity"] for item in items),
        "total_cents": sum(item["line_total_cents"] for item in items),
    }


@app.get("/api/cart")
def get_cart(user=Depends(get_current_user)):
    return build_cart(user["id"])


@app.post("/api/cart")
def add_to_cart(payload: CartPayload, user=Depends(get_current_user)):
    with get_connection() as conn:
        product = conn.execute(
            "SELECT id, stock FROM products WHERE id = ?",
            (payload.product_id,),
        ).fetchone()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        existing = conn.execute(
            """
            SELECT quantity FROM cart_items
            WHERE user_id = ? AND product_id = ?
            """,
            (user["id"], payload.product_id),
        ).fetchone()

        existing_qty = existing["quantity"] if existing else 0
        new_qty = existing_qty + payload.quantity

        if new_qty > product["stock"]:
            raise HTTPException(
                status_code=400,
                detail="Requested quantity exceeds available stock",
            )

        if existing:
            conn.execute(
                """
                UPDATE cart_items
                SET quantity = ?
                WHERE user_id = ? AND product_id = ?
                """,
                (new_qty, user["id"], payload.product_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO cart_items (user_id, product_id, quantity)
                VALUES (?, ?, ?)
                """,
                (user["id"], payload.product_id, payload.quantity),
            )

        conn.commit()

    return build_cart(user["id"])


@app.put("/api/cart/{product_id}")
def update_cart(
    product_id: int,
    payload: CartPayload,
    user=Depends(get_current_user),
):
    if payload.product_id != product_id:
        raise HTTPException(status_code=400, detail="Product ID mismatch")

    with get_connection() as conn:
        product = conn.execute(
            "SELECT stock FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        existing = conn.execute(
            """
            SELECT id FROM cart_items
            WHERE user_id = ? AND product_id = ?
            """,
            (user["id"], product_id),
        ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Cart item not found")

        if payload.quantity > product["stock"]:
            raise HTTPException(
                status_code=400,
                detail="Requested quantity exceeds available stock",
            )

        conn.execute(
            """
            UPDATE cart_items
            SET quantity = ?
            WHERE user_id = ? AND product_id = ?
            """,
            (payload.quantity, user["id"], product_id),
        )
        conn.commit()

    return build_cart(user["id"])


@app.delete("/api/cart/{product_id}")
def remove_cart_item(product_id: int, user=Depends(get_current_user)):
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM cart_items
            WHERE user_id = ? AND product_id = ?
            """,
            (user["id"], product_id),
        )
        conn.commit()

    return build_cart(user["id"])


# -----------------------------
# Stripe sandbox checkout
# -----------------------------
@app.post("/api/checkout/session")
def create_checkout_session(user=Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe test secret key is not configured",
        )

    cart = build_cart(user["id"])

    if not cart["items"]:
        raise HTTPException(status_code=400, detail="Cart is empty")

    line_items = []

    for item in cart["items"]:
        if item["quantity"] > item["stock"]:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock for {item['name']}",
            )

        line_items.append(
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": item["name"]},
                    "unit_amount": item["price_cents"],
                },
                "quantity": item["quantity"],
            }
        )

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            success_url=(
                f"{FRONTEND_URL}/success.html"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{FRONTEND_URL}/index.html?checkout=cancelled",
            metadata={"user_id": str(user["id"])},
        )
    except stripe.error.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        raise HTTPException(status_code=502, detail=f"Stripe error: {message}")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders (
                user_id, stripe_session_id, total_cents, status, created_at
            )
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (
                user["id"],
                session.id,
                cart["total_cents"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        order_id = cursor.lastrowid

        for item in cart["items"]:
            conn.execute(
                """
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_name,
                    unit_price_cents,
                    quantity
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item["product_id"],
                    item["name"],
                    item["price_cents"],
                    item["quantity"],
                ),
            )

        conn.commit()

    return {"checkout_url": session.url, "session_id": session.id}


@app.post("/api/checkout/confirm")
def confirm_checkout(session_id: str, user=Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe test secret key is not configured",
        )

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        raise HTTPException(status_code=502, detail=f"Stripe error: {message}")

    if session.payment_status != "paid":
        raise HTTPException(status_code=400, detail="Payment is not completed")

    metadata_user_id = int(session.metadata.get("user_id", "0"))
    if metadata_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Checkout does not belong to this user")

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        order = conn.execute(
            """
            SELECT id, status, total_cents
            FROM orders
            WHERE stripe_session_id = ? AND user_id = ?
            """,
            (session_id, user["id"]),
        ).fetchone()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order["status"] == "completed":
            conn.rollback()
            return {
                "message": "Order already completed",
                "order_id": order["id"],
                "total_cents": order["total_cents"],
            }

        items = conn.execute(
            """
            SELECT product_id, product_name, quantity
            FROM order_items
            WHERE order_id = ?
            """,
            (order["id"],),
        ).fetchall()

        for item in items:
            product = conn.execute(
                "SELECT stock FROM products WHERE id = ?",
                (item["product_id"],),
            ).fetchone()

            if not product or product["stock"] < item["quantity"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Inventory conflict for {item['product_name']}",
                )

        for item in items:
            conn.execute(
                """
                UPDATE products
                SET stock = stock - ?
                WHERE id = ?
                """,
                (item["quantity"], item["product_id"]),
            )

        conn.execute(
            """
            UPDATE orders
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                order["id"],
            ),
        )

        conn.execute(
            "DELETE FROM cart_items WHERE user_id = ?",
            (user["id"],),
        )

        conn.commit()

        return {
            "message": "Payment verified and order completed",
            "order_id": order["id"],
            "total_cents": order["total_cents"],
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.get("/api/orders")
def list_orders(user=Depends(get_current_user)):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, stripe_session_id, total_cents, status, created_at, completed_at
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user["id"],),
        ).fetchall()

    return [dict(row) for row in rows]
