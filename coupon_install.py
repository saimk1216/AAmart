import re
import os
import shutil

APP = "app.py"
CHECKOUT = "templates/checkout.html"
ADMIN_BASE = "templates/admin_base.html"

for f in [APP, CHECKOUT, ADMIN_BASE]:
    if not os.path.exists(f):
        raise SystemExit(f"Required file missing: {f}")

app = open(APP).read()
checkout = open(CHECKOUT).read()
admin_base = open(ADMIN_BASE).read()

if "class Coupon(db.Model):" in app:
    raise SystemExit("Coupon model already exists. Installer stopped safely.")

# 1. Coupon model
model = '''
class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

'''

if "class Order(db.Model):" not in app:
    raise SystemExit("Order model marker not found.")

app = app.replace("class Order(db.Model):", model + "class Order(db.Model):", 1)

# 2. Add discount fields to Order model
old = '    total = db.Column(db.Float, nullable=False)'
new = '''    total = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, default=0, nullable=False)
    discount = db.Column(db.Float, default=0, nullable=False)
    coupon_code = db.Column(db.String(40), nullable=True)'''

if old not in app:
    raise SystemExit("Order total field not found.")
app = app.replace(old, new, 1)

# 3. Replace checkout route
pattern = r'@app\.route\("/checkout", methods=\["GET", "POST"\]\)\s*@login_required\s*def checkout\(\):.*?(?=\n@app\.route\("/order/success/)'


checkout_route = '''
def calculate_coupon(code, subtotal):
    if not code:
        return None, 0, "No coupon applied."

    coupon = Coupon.query.filter_by(code=code.upper(), active=True).first()
    if not coupon:
        return None, 0, "Coupon code invalid or inactive."

    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    if coupon.expires_at and now_ist > coupon.expires_at:
        return None, 0, "This coupon has expired."

    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        return None, 0, "Coupon usage limit reached."

    if subtotal < coupon.min_order:
        return None, 0, f"Minimum order value is Rs. {coupon.min_order:.2f}."

    if coupon.discount_type == "percent":
        discount = subtotal * coupon.discount_value / 100
    else:
        discount = coupon.discount_value

    discount = min(round(discount, 2), subtotal)
    return coupon, discount, None


@app.route("/coupon/apply", methods=["POST"])
@login_required
def apply_coupon():
    _, subtotal, _ = cart_data()
    code = request.form.get("coupon_code", "").strip().upper()

    coupon, discount, error = calculate_coupon(code, subtotal)
    if error:
        session.pop("coupon_code", None)
        flash(error, "error")
    else:
        session["coupon_code"] = coupon.code
        flash(f"Coupon applied! Rs. {discount:.2f} discount.", "success")

    return redirect(url_for("checkout"))


@app.route("/coupon/remove", methods=["POST"])
@login_required
def remove_coupon():
    session.pop("coupon_code", None)
    flash("Coupon removed.", "success")
    return redirect(url_for("checkout"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    rows, subtotal, _ = cart_data()

    if not rows:
        session.pop("coupon_code", None)
        flash("Aapka cart empty hai.", "error")
        return redirect(url_for("index"))

    code = session.get("coupon_code")
    coupon, discount, coupon_error = calculate_coupon(code, subtotal)

    if coupon_error:
        session.pop("coupon_code", None)
        if code:
            flash(coupon_error, "error")
        code = None

    final_total = round(max(0, subtotal - discount), 2)

    if request.method == "POST":
        required = ["customer_name", "phone", "address", "city", "state", "pincode"]
        data = {key: request.form.get(key, "").strip() for key in required}

        if (any(not value for value in data.values())
                or not data["phone"].replace("+", "").isdigit()
                or len(data["pincode"]) != 6
                or not data["pincode"].isdigit()):
            flash("Please valid delivery details fill karein. PIN code 6 digits ka hona chahiye.", "error")
            return render_template(
                "checkout.html", rows=rows, total=final_total,
                subtotal=subtotal, discount=discount,
                coupon_code=code
            )

        for row in rows:
            if row["qty"] > row["product"].stock:
                flash(f"{row['product'].name} ka stock ab available nahi hai.", "error")
                return redirect(url_for("cart"))

        # Recheck coupon immediately before creating the order.
        coupon, discount, coupon_error = calculate_coupon(code, subtotal)
        if coupon_error:
            session.pop("coupon_code", None)
            discount = 0
            coupon = None
            flash(coupon_error, "error")

        final_total = round(max(0, subtotal - discount), 2)

        order = Order(
            order_number="AA" + uuid.uuid4().hex[:10].upper(),
            user_id=current_user.id,
            total=final_total,
            subtotal=subtotal,
            discount=discount,
            coupon_code=coupon.code if coupon else None,
            **data
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderStatusHistory(order_id=order.id, status="Placed"))

        for row in rows:
            product = row["product"]
            product.stock -= row["qty"]
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=row["qty"]
            ))

        if coupon:
            coupon.used_count += 1

        db.session.commit()
        session["cart"] = {}
        session.pop("coupon_code", None)
        return redirect(url_for("order_success", order_number=order.order_number))

    return render_template(
        "checkout.html", rows=rows, total=final_total,
        subtotal=subtotal, discount=discount,
        coupon_code=code
    )
'''

if not re.search(pattern, app, flags=re.S):
    raise SystemExit("Checkout route marker not found. No changes saved.")

app = re.sub(pattern, checkout_route, app, count=1, flags=re.S)

# 4. Admin coupon routes
admin_routes = '''
@app.route("/owner/coupons", methods=["GET", "POST"])
@admin_required
def admin_coupons():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        discount_type = request.form.get("discount_type", "")
        try:
            value = float(request.form.get("discount_value", 0))
            minimum = float(request.form.get("min_order", 0))
            max_uses_raw = request.form.get("max_uses", "").strip()
            max_uses = int(max_uses_raw) if max_uses_raw else None
            expiry_raw = request.form.get("expires_at", "").strip()
            expiry = datetime.strptime(expiry_raw, "%Y-%m-%dT%H:%M") if expiry_raw else None
        except (ValueError, TypeError):
            flash("Please valid discount, minimum order, usage limit aur expiry enter karein.", "error")
            return redirect(url_for("admin_coupons"))

        if (not code or len(code) > 40
                or discount_type not in {"percent", "fixed"}
                or value <= 0 or minimum < 0
                or (discount_type == "percent" and value > 100)
                or (max_uses is not None and max_uses < 1)):
            flash("Coupon details valid nahi hain. Percentage 100 se zyada nahi ho sakta.", "error")
            return redirect(url_for("admin_coupons"))

        if Coupon.query.filter_by(code=code).first():
            flash("Ye coupon code pehle se exist karta hai.", "error")
            return redirect(url_for("admin_coupons"))

        db.session.add(Coupon(
            code=code,
            discount_type=discount_type,
            discount_value=value,
            min_order=minimum,
            expires_at=expiry,
            max_uses=max_uses
        ))
        db.session.commit()
        flash("Coupon successfully create ho gaya.", "success")
        return redirect(url_for("admin_coupons"))

    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template("admin_coupons.html", coupons=coupons)


@app.route("/owner/coupons/<int:coupon_id>/toggle", methods=["POST"])
@admin_required
def toggle_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id) or abort(404)
    coupon.active = not coupon.active
    db.session.commit()
    flash("Coupon status update ho gaya.", "success")
    return redirect(url_for("admin_coupons"))


@app.route("/owner/coupons/<int:coupon_id>/delete", methods=["POST"])
@admin_required
def delete_coupon(coupon_id):
    coupon = db.session.get(Coupon, coupon_id) or abort(404)
    db.session.delete(coupon)
    db.session.commit()
    flash("Coupon delete ho gaya.", "success")
    return redirect(url_for("admin_coupons"))


'''

if "# OWNER PANEL" not in app:
    raise SystemExit("Admin panel marker not found.")
app = app.replace("# OWNER PANEL", admin_routes + "# OWNER PANEL", 1)

# 5. Database migration for existing Order table
migration = '''
        # Safe SQLite migration for existing orders.
        from sqlalchemy import inspect
        columns = {column["name"] for column in inspect(db.engine).get_columns("order")}
        with db.engine.begin() as connection:
            if "subtotal" not in columns:
                connection.exec_driver_sql(
                    'ALTER TABLE "order" ADD COLUMN subtotal FLOAT NOT NULL DEFAULT 0'
                )
            if "discount" not in columns:
                connection.exec_driver_sql(
                    'ALTER TABLE "order" ADD COLUMN discount FLOAT NOT NULL DEFAULT 0'
                )
            if "coupon_code" not in columns:
                connection.exec_driver_sql(
                    'ALTER TABLE "order" ADD COLUMN coupon_code VARCHAR(40)'
                )
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                'UPDATE "order" SET subtotal = total WHERE subtotal = 0 AND discount = 0'
            )
'''

marker = "        db.create_all()"
if marker not in app:
    raise SystemExit("Database initialization marker not found.")
app = app.replace(marker, marker + "\n" + migration, 1)

# 6. Checkout page
checkout_new = '''{% extends "base.html" %}
{% block content %}
<div class="formbox wide">
    <h1>Checkout</h1>

    <h3>Subtotal: ₹{{ '%.2f'|format(subtotal) }}</h3>

    <div class="card" style="margin:15px 0;padding:15px">
        <h3>🎟️ Apply Coupon</h3>
        {% if coupon_code %}
            <p>Applied coupon: <strong>{{ coupon_code }}</strong></p>
            <p>Discount: <strong>−₹{{ '%.2f'|format(discount) }}</strong></p>
            <form method="post" action="{{ url_for('remove_coupon') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button class="btn" type="submit">Remove Coupon</button>
            </form>
        {% else %}
            <form method="post" action="{{ url_for('apply_coupon') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <label>Coupon Code
                    <input name="coupon_code" placeholder="Enter coupon code" required>
                </label>
                <button class="btn" type="submit">Apply Coupon</button>
            </form>
        {% endif %}
    </div>

    <h2>Final Total: ₹{{ '%.2f'|format(total) }}</h2>

    <form method="post">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <label>Full name<input name="customer_name" required></label>
        <label>Mobile number<input name="phone" required pattern="[0-9+]{10,13}"></label>
        <label>Address<textarea name="address" required></textarea></label>
        <div class="two">
            <label>City<input name="city" required></label>
            <label>State<input name="state" required></label>
        </div>
        <label>PIN code<input name="pincode" required pattern="[0-9]{6}" maxlength="6"></label>
        <label>Payment method<select disabled><option>Cash on Delivery (currently enabled)</option></select></label>
        <button class="btn full">Place COD order</button>
    </form>
</div>
{% endblock %}
'''

# 7. Admin coupon page
admin_coupon_template = '''{% extends "admin_base.html" %}
{% block admincontent %}
<h1>Coupon Management</h1>

<div class="formbox wide">
    <h2>Create Coupon</h2>
    <form method="post">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <label>Coupon Code
            <input name="code" placeholder="WELCOME10" maxlength="40" required>
        </label>

        <div class="two">
            <label>Discount Type
                <select name="discount_type" required>
                    <option value="percent">Percentage (%)</option>
                    <option value="fixed">Fixed Amount (₹)</option>
                </select>
            </label>
            <label>Discount Value
                <input name="discount_value" type="number" min="0.01" step="0.01" required>
            </label>
        </div>

        <label>Minimum Order Value (₹)
            <input name="min_order" type="number" min="0" step="0.01" value="0" required>
        </label>

        <label>Expiry Date and Time (optional)
            <input name="expires_at" type="datetime-local">
        </label>

        <label>Maximum Usage Limit (optional)
            <input name="max_uses" type="number" min="1" placeholder="Unlimited if empty">
        </label>

        <button class="btn full" type="submit">Create Coupon</button>
    </form>
</div>

<h2>Existing Coupons</h2>
{% if coupons %}
    {% for coupon in coupons %}
    <div class="card" style="margin:12px 0;padding:15px">
        <h3>{{ coupon.code }}</h3>
        <p>Discount:
            {% if coupon.discount_type == 'percent' %}
                {{ coupon.discount_value }}%
            {% else %}
                ₹{{ coupon.discount_value }}
            {% endif %}
        </p>
        <p>Minimum order: ₹{{ coupon.min_order }}</p>
        <p>Expiry: {{ coupon.expires_at.strftime('%d %b %Y, %I:%M %p') if coupon.expires_at else 'No expiry' }}</p>
        <p>Usage: {{ coupon.used_count }} / {{ coupon.max_uses if coupon.max_uses is not none else 'Unlimited' }}</p>
        <p>Status: {{ 'Active' if coupon.active else 'Inactive' }}</p>

        <form method="post" action="{{ url_for('toggle_coupon', coupon_id=coupon.id) }}" style="display:inline">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn" type="submit">{{ 'Deactivate' if coupon.active else 'Activate' }}</button>
        </form>

        <form method="post" action="{{ url_for('delete_coupon', coupon_id=coupon.id) }}" style="display:inline">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn" type="submit" onclick="return confirm('Delete this coupon?')">Delete</button>
        </form>
    </div>
    {% endfor %}
{% else %}
    <p>No coupons created yet.</p>
{% endif %}
{% endblock %}
'''

# Add navigation
nav = "<a href=\"{{ url_for('admin_reviews') }}\">Reviews</a>"
if nav not in admin_base:
    raise SystemExit("Admin Reviews sidebar link not found.")
admin_base = admin_base.replace(
    nav,
    nav + "<a href=\"{{ url_for('admin_coupons') }}\">Coupons</a>",
    1
)

# Save only after all checks pass.
open(APP, "w").write(app)
open(CHECKOUT, "w").write(checkout_new)
open(ADMIN_BASE, "w").write(admin_base)
open("templates/admin_coupons.html", "w").write(admin_coupon_template)

print("Coupon System files installed.")
print("Existing database will be migrated when the app starts.")
