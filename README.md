# Progree Internship - Task 4
## Secure E-Commerce Engine with Checkout Sandbox

This project implements the Task 4 requirements using:

- FastAPI backend
- SQLite database
- JWT authentication
- HttpOnly JWT cookie
- bcrypt password hashing
- Persistent database-backed shopping cart
- Stripe Checkout in Test Mode
- Backend payment verification
- Inventory reduction after confirmed payment

## Project Structure

```text
progree-task-4-ecommerce/
│
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
└── frontend/
    ├── index.html
    ├── success.html
    ├── style.css
    └── script.js
```

`store.db` is generated automatically and is excluded from Git.

---

## Step 1 - Create the virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Step 2 - Install dependencies

```powershell
pip install -r requirements.txt
```

## Step 3 - Create `.env`

Copy `.env.example` and rename the copy to:

```text
.env
```

Generate a JWT secret locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into:

```env
JWT_SECRET=YOUR_GENERATED_VALUE
```

For Stripe, use a TEST secret key only:

```env
STRIPE_SECRET_KEY=sk_test_...
```

Never commit `.env` or your Stripe secret key to GitHub.

## Step 4 - Start the backend

```powershell
uvicorn app:app --reload --port 8000
```

Test:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
```

## Step 5 - Start frontend

Open:

```text
frontend/index.html
```

with VS Code Live Server.

Expected URL:

```text
http://127.0.0.1:5500/frontend/index.html
```

## Step 6 - Test authentication

1. Click Login / Register.
2. Choose Register.
3. Create a test account.
4. Logout.
5. Login again.

Passwords are stored as bcrypt hashes, not plain text.

## Step 7 - Test persistent cart

1. Login.
2. Add products to cart.
3. Refresh the page.
4. The cart should remain because cart items are stored in SQLite.
5. Change quantity.
6. Remove an item.

## Step 8 - Test Stripe Checkout

You need a Stripe account in TEST mode and a test secret key.

1. Add at least one product to cart.
2. Click `Secure Test Checkout`.
3. Complete the Stripe TEST checkout.
4. Stripe redirects to `success.html`.
5. The frontend sends the Checkout Session ID to the backend.
6. Backend retrieves the session directly from Stripe.
7. Backend verifies `payment_status == paid`.
8. Backend reduces product stock.
9. Backend marks the order completed.
10. Backend clears the user's cart.

No real payment should be used for this internship demo.

## Security Notes

- Passwords are bcrypt-hashed.
- JWT is stored in an HttpOnly cookie.
- Checkout success is verified server-side with Stripe.
- User ID ownership is checked before order processing.
- SQL statements are parameterized.
- `.env`, database and virtual environment are ignored by Git.

## Recommended Submission Screenshots

1. Store home page.
2. Registration/login panel.
3. Logged-in user state.
4. Persistent cart with products.
5. Stripe TEST checkout page.
6. Successful checkout page.
7. Product stock before and after payment.
8. FastAPI `/docs`.
9. GitHub repository showing `.gitignore` and source files.

## Important

This project is a learning/demo sandbox. The local cookie uses `secure=False`
because local HTTP is used. Production deployment should use HTTPS and
`secure=True`.
