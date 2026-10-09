from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from functools import wraps

app = Flask(__name__)
import os
app.secret_key = os.environ.get("SECRET_KEY")

DB = "aamart.db"


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT,
            description TEXT
        )
    """)

    owner = conn.execute(
        "SELECT * FROM users WHERE username=?",
        ("owner",)
    ).fetchone()

    if not owner:
        conn.execute(
            "INSERT INTO users (username,password,role) VALUES (?,?,?)",
            ("owner", "owner123", "owner")
        )

    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    conn = db()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template("index.html", products=products)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/admin")

        return "Invalid username or password"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/admin")
@login_required
def admin():
    conn = db()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()

    return render_template(
        "admin.html",
        products=products,
        role=session["role"]
    )


@app.route("/add-product", methods=["POST"])
@login_required
def add_product():

    name = request.form["name"]
    price = request.form["price"]
    image = request.form["image"]
    description = request.form["description"]

    conn = db()
    conn.execute(
        "INSERT INTO products (name,price,image,description) VALUES (?,?,?,?)",
        (name, price, image, description)
    )
    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/delete-product/<int:id>")
@login_required
def delete_product(id):

    conn = db()
    conn.execute("DELETE FROM products WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/admin")


@app.route("/add-editor", methods=["POST"])
@login_required
def add_editor():

    if session["role"] != "owner":
        return "Only Owner can create Editors"

    username = request.form["username"]
    password = request.form["password"]

    conn = db()

    try:
        conn.execute(
            "INSERT INTO users (username,password,role) VALUES (?,?,?)",
            (username, password, "editor")
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "Username already exists"

    conn.close()

    return redirect("/admin")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
