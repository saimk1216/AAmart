# AAmart Full E-commerce Starter

A working Flask + SQLite e-commerce starter with:
- Customer registration/login (hashed passwords)
- Product listing, search, categories and product details
- Session cart and stock checks
- Checkout with Cash on Delivery
- Customer order history
- Owner dashboard
- Owner product CRUD and image uploads
- Order status management
- Customer list
- Store branding editor

## 1. Run on Android (Termux)

Install Python and unzip the project, then:

```bash
pkg update -y
pkg install python -y
cd AAmart_full_ecommerce
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Set owner credentials before first run:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export OWNER_USERNAME="owner"
export OWNER_PASSWORD="Use-A-Strong-Unique-Password"
python app.py
```

Open `http://127.0.0.1:5000` in your phone browser.

Owner panel: `http://127.0.0.1:5000/owner`

If you omit OWNER_PASSWORD on first run, the app creates a temporary owner password `ChangeMe123!`; change this immediately and do not deploy with it.

## 2. Deployment

Use a Python hosting service that supports Flask and persistent storage.
- Build/install command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Environment variables: `SECRET_KEY`, `OWNER_USERNAME`, `OWNER_PASSWORD`, `DATABASE_URL`
- Use a persistent disk/volume for SQLite and uploaded images, or switch to managed PostgreSQL and object storage.
- Do not commit `.env` or secrets to GitHub.

For PostgreSQL, install a PostgreSQL driver and set `DATABASE_URL` to the provider's connection string. Confirm the provider's expected URL format.

## 3. Important production work still required

This is a functional starter, not a finished large-scale marketplace. Before accepting public customers:
1. Use PostgreSQL or another managed database with backups.
2. Add email/phone verification, password reset, rate limiting and audit logs.
3. Configure HTTPS and secure cookie settings at the host.
4. Use cloud object storage for product images.
5. Integrate a payment provider (for example Razorpay) using server-side order creation, signature verification and webhooks. Never collect/store card or UPI PIN details yourself.
6. Add shipping provider integration, tax/invoice rules, refund/return workflows, privacy policy and terms.
7. Add automated tests and monitoring.
8. Change the default owner account credentials immediately.

## 4. Notes

- COD checkout is functional.
- Online payment is intentionally not enabled until a payment gateway account and server-side credentials are configured.
- Store settings currently include store name, tagline, contact details and brand color. Full drag-and-drop page builder, coupons and customer-facing reviews are not included in this first backend version.
- Product uploads accept PNG/JPG/JPEG/WEBP, max 5 MB.
