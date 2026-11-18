import os
import re
import shutil

APP = "app.py"
FORM = "templates/admin_product_form.html"
INDEX = "templates/index.html"
PRODUCT = "templates/product.html"
CART = "templates/cart.html"

files = [APP, FORM, INDEX, PRODUCT, CART]

for f in files:
    if not os.path.exists(f):
        raise SystemExit("File missing: " + f)

for f in files:
    shutil.copy2(f, f + ".before-flash-sale.bak")

app = open(APP, encoding="utf-8").read()

def replace_once(old, new, label):
    global app
    count = app.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    app = app.replace(old, new, 1)

# 1. Product model fields
replace_once(
    '    mrp = db.Column(db.Float, nullable=False)\n',
    '''    mrp = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=True)
    sale_start = db.Column(db.DateTime, nullable=True)
    sale_end = db.Column(db.DateTime, nullable=True)

    @property
    def is_sale_active(self):
        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
        return (
            self.sale_price is not None
            and 0 < self.sale_price < self.price
            and (self.sale_start is None or self.sale_start <= now_ist)
            and (self.sale_end is None or self.sale_end >= now_ist)
        )

    @property
    def current_price(self):
        return self.sale_price if self.is_sale_active else self.price
''',
    "Product model"
)

# 2. Cart calculation
replace_once(
    '            subtotal = product.price * int(qty)\n',
    '            subtotal = product.current_price * int(qty)\n',
    "Cart calculation"
)

# 3. Order item price snapshot
replace_once(
    '                price=product.price,\n',
    '                price=product.current_price,\n',
    "Order item price"
)

# 4. Safe database migration
migration = '''
        product_columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("product")
        }
        with db.engine.begin() as connection:
            if "sale_price" not in product_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE product ADD COLUMN sale_price FLOAT"
                )
            if "sale_start" not in product_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE product ADD COLUMN sale_start DATETIME"
                )
            if "sale_end" not in product_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE product ADD COLUMN sale_end DATETIME"
                )

'''
marker = '        owner_name = os.environ.get("OWNER_USERNAME", "owner")'
if app.count(marker) != 1:
    raise RuntimeError("Database migration location not found")
app = app.replace(marker, migration + marker, 1)

# 5. Replace product form route
start = app.index('@app.route("/owner/products/new"')
end = app.index(
    '@app.route("/owner/products/<int:product_id>/delete"',
    start
)

new_route = '''@app.route("/owner/products/new", methods=["GET", "POST"])
@app.route("/owner/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_form(product_id=None):
    product = db.session.get(Product, product_id) if product_id else None
    if product_id and not product:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        try:
            price = float(request.form.get("price", 0))
            mrp = float(request.form.get("mrp", 0))
            stock = int(request.form.get("stock", 0))

            sale_raw = request.form.get("sale_price", "").strip()
            sale_price = float(sale_raw) if sale_raw else None

            start_raw = request.form.get("sale_start", "").strip()
            end_raw = request.form.get("sale_end", "").strip()

            sale_start = (
                datetime.strptime(start_raw, "%Y-%m-%dT%H:%M")
                if start_raw else None
            )
            sale_end = (
                datetime.strptime(end_raw, "%Y-%m-%dT%H:%M")
                if end_raw else None
            )
        except (ValueError, TypeError):
            flash("Price, stock ya sale date valid nahi hai.", "error")
            return render_template("admin_product_form.html", product=product)

        if not name or price <= 0 or mrp < price or stock < 0:
            flash("Product name, price, MRP aur stock check karein.", "error")
            return render_template("admin_product_form.html", product=product)

        if sale_price is not None and not (0 < sale_price < price):
            flash("Sale price normal selling price se kam aur zero se zyada honi chahiye.", "error")
            return render_template("admin_product_form.html", product=product)

        if sale_start and sale_end and sale_end <= sale_start:
            flash("Sale end time, start time ke baad honi chahiye.", "error")
            return render_template("admin_product_form.html", product=product)

        if not product:
            product = Product(name=name, price=price, mrp=mrp, stock=stock)
            db.session.add(product)

        product.name = name
        product.price = price
        product.mrp = mrp
        product.stock = stock
        product.sale_price = sale_price
        product.sale_start = sale_start if sale_price else None
        product.sale_end = sale_end if sale_price else None
        product.description = request.form.get("description", "").strip()
        product.category = request.form.get("category", "General").strip() or "General"
        product.active = request.form.get("active") == "on"

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            ext = image_file.filename.rsplit(".", 1)[-1].lower()

            if ext not in ALLOWED_EXTENSIONS:
                flash("Image PNG, JPG, JPEG ya WEBP honi chahiye.", "error")
                return render_template("admin_product_form.html", product=product)

            filename = secure_filename(uuid.uuid4().hex + "." + ext)
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(path)

            try:
                with Image.open(path) as im:
                    im.verify()
            except Exception:
                os.remove(path)
                flash("Uploaded file valid image nahi hai.", "error")
                return render_template("admin_product_form.html", product=product)

            product.image = filename

        db.session.commit()
        flash("Product save ho gaya.", "success")
        return redirect(url_for("admin_products"))

    return render_template("admin_product_form.html", product=product)

'''
app = app[:start] + new_route + app[end:]

# 6. Save app
open(APP, "w", encoding="utf-8").write(app)

# 7. Admin product form
form = '''{% extends "admin_base.html" %}
{% block admincontent %}
<div class="formbox wide">
<h1>{{ 'Edit' if product else 'Add' }} product</h1>

<form method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

<label>Product name
<input name="name" required value="{{ product.name if product else '' }}">
</label>

<label>Description
<textarea name="description">{{ product.description if product else '' }}</textarea>
</label>

<label>Category
<input name="category" value="{{ product.category if product else 'General' }}">
</label>

<div class="two">
<label>Selling price (₹)
<input type="number" step="0.01" min="0.01" name="price" required value="{{ product.price if product else '' }}">
</label>

<label>MRP (₹)
<input type="number" step="0.01" min="0.01" name="mrp" required value="{{ product.mrp if product else '' }}">
</label>
</div>

<hr>
<h2>⚡ Flash Sale Settings</h2>
<p>Sale price normal selling price se kam rakhein.</p>

<label>Flash Sale Price (₹)
<input type="number" step="0.01" min="0.01" name="sale_price"
value="{{ product.sale_price if product and product.sale_price else '' }}">
</label>

<label>Sale Start (IST)
<input type="datetime-local" name="sale_start"
value="{{ product.sale_start.strftime('%Y-%m-%dT%H:%M') if product and product.sale_start else '' }}">
</label>

<label>Sale End (IST)
<input type="datetime-local" name="sale_end"
value="{{ product.sale_end.strftime('%Y-%m-%dT%H:%M') if product and product.sale_end else '' }}">
</label>

<p>Start aur end time blank chhodne par sale turant active rahegi aur manually band karne tak chalegi.</p>
<hr>

<label>Stock
<input type="number" min="0" name="stock" required value="{{ product.stock if product else 0 }}">
</label>

<label>Product image
<input type="file" name="image" accept="image/png,image/jpeg,image/webp">
</label>

<label class="check">
<input type="checkbox" name="active" {% if not product or product.active %}checked{% endif %}>
Visible in store
</label>

<button class="btn full">Save product</button>
</form>
</div>
{% endblock %}
'''
open(FORM, "w", encoding="utf-8").write(form)

# 8. Homepage sale price
index = open(INDEX, encoding="utf-8").read()
old = """<p class="price">₹{{ '%.2f'|format(p.price) }} <del>₹{{ '%.2f'|format(p.mrp) }}</del></p>"""
new = """{% if p.is_sale_active %}<span class="pill">⚡ FLASH SALE</span>{% endif %}
<p class="price">₹{{ '%.2f'|format(p.current_price) }}
{% if p.is_sale_active %}<del>₹{{ '%.2f'|format(p.price) }}</del>{% else %}<del>₹{{ '%.2f'|format(p.mrp) }}</del>{% endif %}
</p>"""
if index.count(old) != 1:
    raise RuntimeError("Homepage price section not found")
index = index.replace(old, new, 1)
open(INDEX, "w", encoding="utf-8").write(index)

# 9. Product detail sale price
product = open(PRODUCT, encoding="utf-8").read()
old = """<p class="price big">₹{{ '%.2f'|format(product.price) }}
            <del>₹{{ '%.2f'|format(product.mrp) }}</del>
        </p>"""
new = """{% if product.is_sale_active %}<span class="pill">⚡ FLASH SALE</span>{% endif %}
        <p class="price big">₹{{ '%.2f'|format(product.current_price) }}
            {% if product.is_sale_active %}<del>₹{{ '%.2f'|format(product.price) }}</del>{% else %}<del>₹{{ '%.2f'|format(product.mrp) }}</del>{% endif %}
        </p>"""
if product.count(old) != 1:
    raise RuntimeError("Product detail price section not found")
product = product.replace(old, new, 1)
open(PRODUCT, "w", encoding="utf-8").write(product)

# 10. Cart price display
cart = open(CART, encoding="utf-8").read()
old = """{{ '%.2f'|format(r.product.price) }}"""
new = """{{ '%.2f'|format(r.product.current_price) }}"""
if cart.count(old) != 1:
    raise RuntimeError("Cart price section not found")
cart = cart.replace(old, new, 1)
open(CART, "w", encoding="utf-8").write(cart)

# 11. Syntax validation
import py_compile
try:
    py_compile.compile(APP, doraise=True)
except Exception:
    for f in files:
        backup = f + ".before-flash-sale.bak"
        if os.path.exists(backup):
            shutil.copy2(backup, f)
    raise

print("Flash Sale System installed successfully.")
print("Existing database and products preserved.")
print("Backups created for all changed files.")
