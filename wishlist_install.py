from pathlib import Path

app_path = Path("app.py")
app = app_path.read_text()

if "class WishlistItem(db.Model):" in app:
    print("Wishlist model already exists. Stopping safely.")
    raise SystemExit(0)

# 1. Wishlist database model
model = """

class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")
    product = db.relationship("Product")

    __table_args__ = (
        db.UniqueConstraint("user_id", "product_id", name="unique_wishlist_product"),
    )

"""

marker = "class Order(db.Model):"
if marker not in app:
    raise SystemExit("Order model marker missing. No changes made.")

app = app.replace(marker, model + marker, 1)

# 2. Wishlist routes
routes = """

@app.route("/wishlist")
@login_required
def wishlist():
    items = WishlistItem.query.join(Product).filter(
        WishlistItem.user_id == current_user.id,
        Product.active == True
    ).order_by(WishlistItem.created_at.desc()).all()
    return render_template("wishlist.html", items=items)


@app.route("/wishlist/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_wishlist(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()

    existing = WishlistItem.query.filter_by(
        user_id=current_user.id,
        product_id=product.id
    ).first()

    if existing:
        flash("Ye product pehle se Wishlist mein hai.", "success")
    else:
        db.session.add(WishlistItem(
            user_id=current_user.id,
            product_id=product.id
        ))
        db.session.commit()
        flash("Product Wishlist mein add ho gaya. ❤️", "success")

    return redirect(request.referrer or url_for("wishlist"))


@app.route("/wishlist/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_from_wishlist(item_id):
    item = WishlistItem.query.filter_by(
        id=item_id,
        user_id=current_user.id
    ).first_or_404()

    db.session.delete(item)
    db.session.commit()
    flash("Product Wishlist se remove ho gaya.", "success")
    return redirect(url_for("wishlist"))


@app.route("/wishlist/move/<int:item_id>", methods=["POST"])
@login_required
def move_wishlist_to_cart(item_id):
    item = WishlistItem.query.filter_by(
        id=item_id,
        user_id=current_user.id
    ).first_or_404()

    product = Product.query.filter_by(
        id=item.product_id,
        active=True
    ).first()

    if not product:
        flash("Ye product ab available nahi hai.", "error")
        return redirect(url_for("wishlist"))

    cart = session.get("cart", {})
    current_qty = int(cart.get(str(product.id), 0))

    if product.stock <= current_qty:
        flash("Is product ka required stock available nahi hai.", "error")
        return redirect(url_for("wishlist"))

    cart[str(product.id)] = current_qty + 1
    session["cart"] = cart

    db.session.delete(item)
    db.session.commit()

    flash("Product Cart mein add ho gaya.", "success")
    return redirect(url_for("wishlist"))


"""

route_marker = '@app.route("/cart")'
if route_marker not in app:
    raise SystemExit("Cart route marker missing. No changes made.")

app = app.replace(route_marker, routes + route_marker, 1)
app_path.write_text(app)

# 3. Add Wishlist link to navigation
base_path = Path("templates/base.html")
base = base_path.read_text()

cart_link = """<a href="{{ url_for('cart') }}">Cart ({{ cart_count }})</a>"""
wishlist_link = """<a href="{{ url_for('wishlist') }}">❤️ Wishlist</a>"""

if wishlist_link not in base:
    if cart_link not in base:
        raise SystemExit("Cart navigation link missing.")
    base = base.replace(cart_link, cart_link + wishlist_link, 1)

base_path.write_text(base)

# 4. Add button to product page
product_path = Path("templates/product.html")
product = product_path.read_text()

button = """
        <form method="post" action="{{ url_for('add_to_wishlist', product_id=product.id) }}" style="margin-top:12px">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn" type="submit">❤️ Add to Wishlist</button>
        </form>
"""

product_marker = """    </div>
</div>

<section id="reviews"""

if button.strip() not in product:
    if product_marker not in product:
        raise SystemExit("Product page insertion point missing.")
    product = product.replace(
        product_marker,
        button + product_marker,
        1
    )

product_path.write_text(product)

# 5. Create Wishlist page
wishlist_template = """{% extends "base.html" %}
{% block content %}

<h1>❤️ My Wishlist</h1>

{% if items %}
<div class="grid">
    {% for item in items %}
    <div class="card">
        <a href="{{ url_for('product_detail', product_id=item.product.id) }}">
            {% if item.product.image %}
            <img src="{{ url_for('static', filename='uploads/' + item.product.image) }}" alt="{{ item.product.name }}">
            {% else %}
            <div class="detailimg">📦</div>
            {% endif %}
            <h3>{{ item.product.name }}</h3>
        </a>

        <p class="price">₹{{ '%.2f'|format(item.product.price) }}</p>
        <p>{{ item.product.stock }} available</p>

        <form method="post" action="{{ url_for('move_wishlist_to_cart', item_id=item.id) }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn" type="submit">Add to Cart</button>
        </form>

        <form method="post" action="{{ url_for('remove_from_wishlist', item_id=item.id) }}" style="margin-top:8px">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button class="btn" type="submit">Remove</button>
        </form>
    </div>
    {% endfor %}
</div>
{% else %}
<p>Your Wishlist is empty.</p>
<a class="btn" href="{{ url_for('index') }}">Explore Products</a>
{% endif %}

{% endblock %}
"""

Path("templates/wishlist.html").write_text(wishlist_template)

print("Wishlist feature installed successfully!")
