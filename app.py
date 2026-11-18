import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, redirect, url_for, request, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from PIL import Image

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///aamart.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)


@app.template_filter("ist")
def format_ist(value):
    if not value:
        return "Time unavailable"
    return (value + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p")


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(100), default="General")
    price = db.Column(db.Float, nullable=False)
    mrp = db.Column(db.Float, nullable=False)
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
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(255), default="")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



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

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    payment_method = db.Column(db.String(30), default="Cash on Delivery")
    payment_status = db.Column(db.String(30), default="Pending")
    status = db.Column(db.String(40), default="Placed")
    total = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, default=0, nullable=False)
    discount = db.Column(db.Float, default=0, nullable=False)
    coupon_code = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    status_updates = db.relationship("OrderStatusHistory", backref="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.created_at")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    product_name = db.Column(db.String(180), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)


class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, default="")
    visible = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "product_id", name="unique_customer_product_review"),)

    user = db.relationship("User")
    product = db.relationship("Product")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def cart_data():
    cart = session.get("cart", {})
    rows, total, count = [], 0, 0
    for pid, qty in cart.items():
        product = db.session.get(Product, int(pid))
        if product and product.active and int(qty) > 0:
            subtotal = product.current_price * int(qty)
            rows.append({"product": product, "qty": int(qty), "subtotal": subtotal})
            total += subtotal
            count += int(qty)
    return rows, round(total, 2), count

@app.context_processor
def inject_cart():
    _, _, count = cart_data()
    return {"cart_count": count}

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    products_query = Product.query.filter_by(active=True)
    if q:
        products_query = products_query.filter(Product.name.ilike(f"%{q}%"))
    if category:
        products_query = products_query.filter_by(category=category)
    products = products_query.order_by(Product.created_at.desc()).all()
    categories = [x[0] for x in db.session.query(Product.category).filter_by(active=True).distinct().all()]
    return render_template("index.html", products=products, categories=categories, q=q, selected_category=category)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()
    reviews = Review.query.filter_by(product_id=product.id, visible=True).order_by(Review.created_at.desc()).all()
    average_rating = db.session.query(func.avg(Review.rating)).filter_by(product_id=product.id, visible=True).scalar()
    my_review = None
    can_review = False

    if current_user.is_authenticated:
        my_review = Review.query.filter_by(product_id=product.id, user_id=current_user.id).first()
        delivered_order = Order.query.join(OrderItem).filter(
            Order.user_id == current_user.id,
            Order.status == "Delivered",
            OrderItem.product_id == product.id
        ).first()
        can_review = delivered_order is not None

    return render_template(
        "product.html", product=product, reviews=reviews,
        average_rating=round(average_rating or 0, 1),
        can_review=can_review, my_review=my_review
    )


@app.route("/product/<int:product_id>/review", methods=["POST"])
@login_required
def submit_review(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()

    delivered_order = Order.query.join(OrderItem).filter(
        Order.user_id == current_user.id,
        Order.status == "Delivered",
        OrderItem.product_id == product.id
    ).first()

    if not delivered_order:
        flash("Review dene ke liye aapka order Delivered hona zaroori hai.", "error")
        return redirect(url_for("product_detail", product_id=product.id))

    try:
        rating = int(request.form.get("rating", "0"))
    except ValueError:
        rating = 0

    comment = request.form.get("comment", "").strip()

    if rating < 1 or rating > 5:
        flash("Please 1 se 5 stars ke beech rating select karein.", "error")
        return redirect(url_for("product_detail", product_id=product.id))

    if len(comment) > 1000:
        flash("Review 1000 characters se chhota rakhein.", "error")
        return redirect(url_for("product_detail", product_id=product.id))

    review = Review.query.filter_by(product_id=product.id, user_id=current_user.id).first()

    if review:
        review.rating = rating
        review.comment = comment
        review.visible = True
    else:
        review = Review(
            product_id=product.id,
            user_id=current_user.id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)

    db.session.commit()
    flash("Aapka review successfully save ho gaya!", "success")
    return redirect(url_for("product_detail", product_id=product.id) + "#reviews")



@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(username) < 3 or len(password) < 8 or "@" not in email:
            flash("Username, valid email aur minimum 8-character password enter karein.", "error")
        elif User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username ya email pehle se registered hai.", "error")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account successfully create ho gaya.", "success")
            return redirect(url_for("index"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.is_admin else "index"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        user = User.query.filter((User.username == identity) | (User.email == identity.lower())).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("admin_dashboard" if user.is_admin else "index"))
        flash("Login details sahi nahi hain.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Aap logout ho gaye.", "success")
    return redirect(url_for("index"))



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


@app.route("/cart")
def cart():
    rows, total, _ = cart_data()
    return render_template("cart.html", rows=rows, total=total)

@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()
    qty = max(1, int(request.form.get("quantity", 1)))
    cart = session.get("cart", {})
    new_qty = int(cart.get(str(product_id), 0)) + qty
    if new_qty > product.stock:
        flash("Itna stock available nahi hai.", "error")
    else:
        cart[str(product_id)] = new_qty
        session["cart"] = cart
        flash("Product cart mein add ho gaya.", "success")
    return redirect(request.referrer or url_for("cart"))

@app.route("/cart/update", methods=["POST"])
def update_cart():
    cart = session.get("cart", {})
    for pid in list(cart.keys()):
        try:
            qty = int(request.form.get(f"qty_{pid}", 0))
        except ValueError:
            qty = 0
        product = db.session.get(Product, int(pid))
        if not product or qty <= 0:
            cart.pop(pid, None)
        else:
            cart[pid] = min(qty, product.stock)
    session["cart"] = cart
    return redirect(url_for("cart"))


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
                price=product.current_price,
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

@app.route("/order/success/<order_number>")
@login_required
def order_success(order_number):
    order = Order.query.filter_by(order_number=order_number, user_id=current_user.id).first_or_404()
    return render_template("order_success.html", order=order)

@app.route("/my-orders")
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("my_orders.html", orders=orders)


@app.route("/my-orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = Order.query.filter_by(
        id=order_id,
        user_id=current_user.id
    ).first_or_404()

    if order.status not in ["Placed", "Processing"]:
        flash("Ye order ab cancel nahi kiya ja sakta.", "error")
        return redirect(url_for("my_orders"))

    for item in order.items:
        if item.product_id:
            product = db.session.get(Product, item.product_id)
            if product:
                product.stock += item.quantity

    order.status = "Cancelled"
    db.session.add(OrderStatusHistory(order_id=order.id, status="Cancelled"))
    db.session.commit()

    flash("Aapka order successfully cancel ho gaya.", "success")
    return redirect(url_for("my_orders"))


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


# OWNER PANEL
@app.route("/owner")
@admin_required
def admin_dashboard():
    stats = {
        "products": Product.query.count(),
        "orders": Order.query.count(),
        "customers": User.query.filter_by(is_admin=False).count(),
        "revenue": db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.status != "Cancelled").scalar()
    }
    recent = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    return render_template("admin_dashboard.html", stats=stats, recent=recent)

@app.route("/owner/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_products.html", products=products)

@app.route("/owner/products/new", methods=["GET", "POST"])
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

@app.route("/owner/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    product.active = False
    db.session.commit()
    flash("Product store se hide kar diya gaya.", "success")
    return redirect(url_for("admin_products"))

@app.route("/owner/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=orders)

@app.route("/owner/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    allowed = {"Placed", "Confirmed", "Processing", "Shipped", "Out for delivery", "Delivered", "Cancelled"}
    status = request.form.get("status")
    if status in allowed:
        if order.status != status:
            order.status = status
            db.session.add(OrderStatusHistory(order_id=order.id, status=status))
        if status == "Delivered":
            order.payment_status = "Paid" if order.payment_method == "Cash on Delivery" else order.payment_status
        db.session.commit()
        flash("Order status update ho gaya.", "success")
    return redirect(url_for("admin_orders"))

@app.route("/owner/customers")
@admin_required
def admin_customers():
    customers = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template("admin_customers.html", customers=customers)

@app.route("/owner/reviews")
@admin_required
def admin_reviews():
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template("admin_reviews.html", reviews=reviews)


@app.route("/owner/reviews/<int:review_id>/visibility", methods=["POST"])
@admin_required
def toggle_review_visibility(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        abort(404)
    review.visible = not review.visible
    db.session.commit()
    flash("Review visibility update ho gayi.", "success")
    return redirect(url_for("admin_reviews"))


@app.route("/owner/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def delete_review(review_id):
    review = db.session.get(Review, review_id)
    if not review:
        abort(404)
    db.session.delete(review)
    db.session.commit()
    flash("Review delete ho gaya.", "success")
    return redirect(url_for("admin_reviews"))


@app.route("/owner/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    # Lightweight editable store settings, persisted in the database.
    setting = StoreSetting.query.first()
    if request.method == "POST":
        setting.store_name = request.form.get("store_name", "AAmart").strip() or "AAmart"
        setting.tagline = request.form.get("tagline", "").strip()
        setting.contact_email = request.form.get("contact_email", "").strip()
        setting.contact_phone = request.form.get("contact_phone", "").strip()
        setting.primary_color = request.form.get("primary_color", "#2874f0")
        db.session.commit()
        flash("Store settings save ho gayi.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", setting=setting)

class StoreSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(100), default="AAmart")
    tagline = db.Column(db.String(200), default="Shopping made simple")
    contact_email = db.Column(db.String(160), default="")
    contact_phone = db.Column(db.String(30), default="")
    primary_color = db.Column(db.String(20), default="#2874f0")

@app.context_processor
def inject_store():
    setting = StoreSetting.query.first()
    return {"store": setting}

def initialize():
    with app.app_context():
        db.create_all()

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

        owner_name = os.environ.get("OWNER_USERNAME", "owner")
        owner_password = os.environ.get("OWNER_PASSWORD")
        if not User.query.filter_by(username=owner_name).first():
            if not owner_password:
                owner_password = "ChangeMe123!"
                print("WARNING: Temporary owner password is ChangeMe123! Change it immediately.")
            owner = User(username=owner_name, email="owner@aamart.local", is_admin=True)
            owner.set_password(owner_password)
            db.session.add(owner)
        if not StoreSetting.query.first():
            db.session.add(StoreSetting())
        if Product.query.count() == 0:
            samples = [
                Product(name="Wireless Earbuds", description="Compact wireless earbuds for everyday listening.", category="Electronics", price=799, mrp=1499, stock=20),
                Product(name="Casual Backpack", description="Everyday backpack with useful storage.", category="Fashion", price=599, mrp=999, stock=15),
                Product(name="LED Desk Lamp", description="Modern desk lamp for study and work.", category="Home", price=449, mrp=699, stock=12),
            ]
            db.session.add_all(samples)
        db.session.commit()

initialize()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
