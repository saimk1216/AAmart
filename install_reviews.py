from pathlib import Path

app_path = Path("app.py")
app = app_path.read_text()

if "class Review(db.Model):" in app:
    print("Reviews model already exists. Installation stopped safely.")
    raise SystemExit(0)

model = '''

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
'''

marker = '\n\n@login_manager.user_loader'
if marker not in app:
    raise SystemExit("Could not find model insertion point. No changes made.")

app = app.replace(marker, model + marker, 1)

old_detail = '''@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, active=True).first_or_404()
    return render_template("product.html", product=product)
'''

new_detail = '''@app.route("/product/<int:product_id>")
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


'''

if old_detail not in app:
    raise SystemExit("Product detail route did not match. No changes made.")

app = app.replace(old_detail, new_detail, 1)

admin_routes = '''@app.route("/owner/reviews")
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


'''

admin_marker = '@app.route("/owner/settings", methods=["GET", "POST"])'
if admin_marker not in app:
    raise SystemExit("Admin insertion point not found. No changes made.")

app = app.replace(admin_marker, admin_routes + admin_marker, 1)

app_path.write_text(app)

nav_path = Path("templates/admin_base.html")
nav = nav_path.read_text()
old_nav = """<a href="{{ url_for('admin_customers') }}">Customers</a>"""
new_nav = old_nav + """<a href="{{ url_for('admin_reviews') }}">Reviews</a>"""

if old_nav not in nav:
    raise SystemExit("Admin navigation link not found. app.py was updated; restore admin_base.html from backup if needed.")

nav_path.write_text(nav.replace(old_nav, new_nav, 1))

product_template = r'''{% extends "base.html" %}
{% block content %}
<div class="detail">
    <div class="detailimg">
        {% if product.image %}
        <img src="{{ url_for('static',filename='uploads/'+product.image) }}">
        {% else %}📦{% endif %}
    </div>
    <div>
        <span class="pill">{{ product.category }}</span>
        <h1>{{ product.name }}</h1>
        <p class="price big">₹{{ '%.2f'|format(product.price) }}
            <del>₹{{ '%.2f'|format(product.mrp) }}</del>
        </p>
        <p>{{ product.description }}</p>
        <p>{{ product.stock }} available</p>
        <form method="post" action="{{ url_for('add_to_cart',product_id=product.id) }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <label>Quantity
                <input type="number" name="quantity" min="1" max="{{ product.stock }}" value="1">
            </label>
            <button class="btn">Add to cart</button>
        </form>
    </div>
</div>

<section id="reviews" style="margin-top:35px;padding:20px;border:1px solid #ddd;border-radius:12px">
    <h2>Customer Reviews ⭐</h2>
    <h3>{{ average_rating }} / 5 ⭐</h3>
    <p>{{ reviews|length }} customer review(s)</p>

    {% if current_user.is_authenticated and can_review %}
    <form method="post" action="{{ url_for('submit_review', product_id=product.id) }}" style="margin:20px 0">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <h3>{% if my_review %}Edit your review{% else %}Write a review{% endif %}</h3>
        <label>Rating</label>
        <select name="rating" required>
            <option value="">Select stars</option>
            {% for n in range(5, 0, -1) %}
            <option value="{{ n }}" {% if my_review and my_review.rating == n %}selected{% endif %}>{{ n }} Star{% if n != 1 %}s{% endif %}</option>
            {% endfor %}
        </select>
        <br><br>
        <textarea name="comment" maxlength="1000" rows="4" placeholder="Write your experience...">{{ my_review.comment if my_review else '' }}</textarea>
        <br><br>
        <button class="btn" type="submit">Submit Review</button>
    </form>
    {% elif current_user.is_authenticated %}
    <p>Review dene ke liye is product ka order Delivered hona zaroori hai.</p>
    {% else %}
    <p><a href="{{ url_for('login') }}">Login</a> karke review eligibility check karein. Review sirf Delivered order ke baad allowed hai.</p>
    {% endif %}

    <hr>
    {% for review in reviews %}
    <article style="padding:15px 0;border-bottom:1px solid #ddd">
        <strong>{{ review.user.username }}</strong>
        <p style="color:#d18b00;font-size:20px">{{ '★' * review.rating }}{{ '☆' * (5-review.rating) }}</p>
        <p>{{ review.comment }}</p>
        <small>{{ review.created_at|ist }}</small>
    </article>
    {% else %}
    <p>Abhi tak koi review nahi hai. Delivered order ke baad pehla review likhein!</p>
    {% endfor %}
</section>
{% endblock %}
'''

Path("templates/product.html").write_text(product_template)

admin_template = r'''{% extends "admin_base.html" %}
{% block admincontent %}
<h1>Customer Reviews</h1>
<p>Yahan se customer reviews hide ya delete kar sakte hain.</p>

{% for review in reviews %}
<div style="padding:15px;margin:12px 0;border:1px solid #ddd;border-radius:10px">
    <h3>{{ review.product.name }}</h3>
    <p><b>Customer:</b> {{ review.user.username }}</p>
    <p style="color:#d18b00;font-size:20px">{{ '★' * review.rating }}{{ '☆' * (5-review.rating) }}</p>
    <p>{{ review.comment }}</p>
    <small>{{ review.created_at|ist }}</small>
    <p><b>Status:</b> {{ "Visible" if review.visible else "Hidden" }}</p>

    <form method="post" action="{{ url_for('toggle_review_visibility', review_id=review.id) }}" style="display:inline">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button class="btn" type="submit">{{ "Hide" if review.visible else "Show" }}</button>
    </form>

    <form method="post" action="{{ url_for('delete_review', review_id=review.id) }}" style="display:inline" onsubmit="return confirm('Delete this review?')">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button class="btn" type="submit">Delete</button>
    </form>
</div>
{% else %}
<p>No reviews yet.</p>
{% endfor %}
{% endblock %}
'''

Path("templates/admin_reviews.html").write_text(admin_template)

print("Reviews & Ratings files installed successfully.")
