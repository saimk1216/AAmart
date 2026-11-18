from pathlib import Path

p = Path("app.py")
code = p.read_text()

def replace_once(old, new, label):
    global code
    count = code.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label} ka exact code nahi mila. Koi changes save nahi kiye.")
    code = code.replace(old, new, 1)

# 1. Import timedelta
replace_once(
    "from datetime import datetime",
    "from datetime import datetime, timedelta",
    "datetime import"
)

# 2. Order relationship
replace_once(
    '    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")',
    '    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")\n'
    '    status_updates = db.relationship("OrderStatusHistory", backref="order", '
    'cascade="all, delete-orphan", order_by="OrderStatusHistory.created_at")',
    "Order relationship"
)

# 3. History model
model_marker = "@login_manager.user_loader"
history_model = '''
class OrderStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


'''
replace_once(model_marker, history_model + model_marker, "History model")

# 4. IST filter
filter_marker = "ALLOWED_EXTENSIONS ="
ist_filter = '''
@app.template_filter("ist")
def format_ist(value):
    if not value:
        return "Time unavailable"
    return (value + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p")


'''
replace_once(filter_marker, ist_filter + filter_marker, "IST filter")

# 5. Initial Placed timestamp at checkout
replace_once(
    '''        db.session.add(order)
        db.session.flush()
        for row in rows:''',
    '''        db.session.add(order)
        db.session.flush()
        db.session.add(OrderStatusHistory(order_id=order.id, status="Placed"))
        for row in rows:''',
    "Checkout history"
)

# 6. Admin status update history
replace_once(
    '''    if status in allowed:
        order.status = status
        if status == "Delivered":''',
    '''    if status in allowed:
        if order.status != status:
            order.status = status
            db.session.add(OrderStatusHistory(order_id=order.id, status=status))
        if status == "Delivered":''',
    "Admin status history"
)

# 7. Customer cancellation history
replace_once(
    '''    order.status = "Cancelled"
    db.session.commit()''',
    '''    order.status = "Cancelled"
    db.session.add(OrderStatusHistory(order_id=order.id, status="Cancelled"))
    db.session.commit()''',
    "Cancellation history"
)

p.write_text(code)
print("Tracking timestamp code added successfully!")
