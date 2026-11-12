
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static"
)

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

DATABASE = os.path.join(BASE_DIR, "reuseloop.db")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@reuseloop.com")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


# ---------------- DATABASE CONNECTION ----------------

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ---------------- CREATE DATABASE ----------------

def create_database():

    with get_db() as connection:

        connection.executescript("""

        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            condition TEXT NOT NULL,
            age TEXT NOT NULL,
            recommendation TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        );

        CREATE TABLE IF NOT EXISTS exchanges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            old_product TEXT NOT NULL,
            desired_product TEXT NOT NULL,
            condition TEXT NOT NULL,
            estimated_value REAL NOT NULL,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS repair_shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            phone TEXT NOT NULL,
            services TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repair_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            shop_id INTEGER NOT NULL,
            device TEXT NOT NULL,
            issue TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(shop_id) REFERENCES repair_shops(id)
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT,
            status TEXT DEFAULT 'Available',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS recycling_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            waste_type TEXT NOT NULL,
            quantity TEXT NOT NULL,
            address TEXT NOT NULL,
            pickup_date TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        """)

        count = connection.execute(
            "SELECT COUNT(*) FROM repair_shops"
        ).fetchone()[0]

        if count == 0:
            connection.executemany("""
                INSERT INTO repair_shops
                (name, location, phone, services)
                VALUES (?, ?, ?, ?)
            """, [
                ("TechCare Electronics", "Karimnagar",
                 "9876543210", "Mobile, Laptop, Computer"),
                ("SmartFix Repairs", "Hyderabad",
                 "9876543211", "Mobile, Tablet, Laptop"),
                ("Digital Service Center", "Warangal",
                 "9876543212", "Computer, Printer, Electronics")
            ])


# ---------------- ORIGINAL RECOMMENDATION FUNCTION ----------------

def recommend_action(device, condition, age):

    if condition == "Working":
        return "Reuse, donate, or resell your device if it is safe to use."

    elif condition == "Repairable":
        return "Get a repair estimate. Repairing may extend its life."

    else:
        return "Send your device to an authorized e-waste collection centre."


# ---------------- HOME PAGE ----------------

@app.route("/", methods=["GET", "POST"])
def home():

    recommendation = None

    if request.method == "POST":

        device = request.form["device"]
        condition = request.form["condition"]
        age = request.form["age"]

        recommendation = recommend_action(device, condition, age)

        with get_db() as connection:
            connection.execute("""
                INSERT INTO devices
                (device, condition, age, recommendation)
                VALUES (?, ?, ?, ?)
            """, (device, condition, age, recommendation))

    with get_db() as connection:
        products = connection.execute("""
            SELECT * FROM products
            WHERE status = 'Available'
            ORDER BY id DESC LIMIT 4
        """).fetchall()

    return render_template(
        "index.html",
        recommendation=recommendation,
        products=products
    )


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 8:
            flash("Enter valid details. Password must have 8 characters.", "error")
            return redirect(url_for("register"))

        role = "admin" if email == ADMIN_EMAIL.lower() else "user"

        try:
            with get_db() as connection:
                connection.execute("""
                    INSERT INTO users (name, email, password, role)
                    VALUES (?, ?, ?, ?)
                """, (
                    name, email,
                    generate_password_hash(password), role
                ))

            flash("Registration successful!", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already registered.", "error")

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as connection:
            user = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):

            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            return redirect(url_for("home"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")

@app.route("/test")
def test():
    return "ReUseLoop Flask is working!"
# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------------- EXCHANGE ----------------

@app.route("/exchange", methods=["GET", "POST"])
def exchange():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        old_product = request.form.get("old_product", "").strip()
        desired_product = request.form.get("desired_product", "").strip()
        condition = request.form.get("condition", "")
        category = request.form.get("category", "Other")

        values = {
            "Excellent": 0.8,
            "Good": 0.6,
            "Fair": 0.35,
            "Poor": 0.15
        }

        prices = {
            "Mobile": 10000,
            "Laptop": 25000,
            "Tablet": 8000,
            "Television": 12000,
            "Other": 3000
        }

        if not old_product or not desired_product or condition not in values:
            flash("Please enter valid exchange details.", "error")
            return redirect(url_for("exchange"))

        estimated_value = prices.get(category, 3000) * values[condition]

        with get_db() as connection:
            connection.execute("""
                INSERT INTO exchanges
                (user_id, old_product, desired_product, condition, estimated_value)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                old_product,
                desired_product,
                condition,
                estimated_value
            ))

        flash("Exchange request submitted successfully!", "success")
        return redirect(url_for("my_requests"))

    return render_template("exchange.html")


# ---------------- REPAIR SHOPS ----------------

@app.route("/repair-shops")
def repair_shops():

    with get_db() as connection:
        shops = connection.execute(
            "SELECT * FROM repair_shops"
        ).fetchall()

    return render_template("repair_shops.html", shops=shops)


# ---------------- REPAIR BOOKING ----------------

@app.route("/book-repair/<int:shop_id>", methods=["POST"])
def book_repair(shop_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    device = request.form.get("device", "").strip()
    issue = request.form.get("issue", "").strip()
    booking_date = request.form.get("booking_date", "")

    if not device or not issue or not booking_date:
        flash("Complete all booking fields.", "error")
        return redirect(url_for("repair_shops"))

    try:
        selected_date = datetime.strptime(
            booking_date, "%Y-%m-%d"
        ).date()

        if selected_date < datetime.today().date():
            flash("Choose a future date.", "error")
            return redirect(url_for("repair_shops"))

    except ValueError:
        flash("Invalid booking date.", "error")
        return redirect(url_for("repair_shops"))

    with get_db() as connection:

        shop = connection.execute(
            "SELECT id FROM repair_shops WHERE id = ?",
            (shop_id,)
        ).fetchone()

        if not shop:
            abort(404)

        connection.execute("""
            INSERT INTO repair_bookings
            (user_id, shop_id, device, issue, booking_date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"], shop_id,
            device, issue, booking_date
        ))

    flash("Repair booking submitted!", "success")
    return redirect(url_for("my_requests"))


# ---------------- SELL ELECTRONICS ----------------

@app.route("/sell", methods=["GET", "POST"])
def sell():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")
        description = request.form.get("description", "").strip()

        try:
            price = float(request.form.get("price", ""))
            if price <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid price.", "error")
            return redirect(url_for("sell"))

        if not name or not description or category not in {
            "Mobile", "Laptop", "Tablet", "Computer", "Other"
        }:
            flash("Enter valid product information.", "error")
            return redirect(url_for("sell"))

        image = request.files.get("image")
        image_name = None

        if image and image.filename:

            if "." not in image.filename or image.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
                flash("Invalid image type.", "error")
                return redirect(url_for("sell"))

            filename = secure_filename(image.filename)
            image_name = datetime.now().strftime("%Y%m%d%H%M%S%f") + "_" + filename

            image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))

        with get_db() as connection:
            connection.execute("""
                INSERT INTO products
                (user_id, name, category, description, price, image)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"], name,
                category, description, price, image_name
            ))

        flash("Product listed successfully!", "success")
        return redirect(url_for("marketplace"))

    return render_template("sell.html")


# ---------------- MARKETPLACE ----------------

@app.route("/marketplace")
def marketplace():

    search = request.args.get("search", "").strip()

    with get_db() as connection:
        products = connection.execute("""
            SELECT products.*, users.name AS seller
            FROM products
            JOIN users ON products.user_id = users.id
            WHERE products.status = 'Available'
            AND (products.name LIKE ? OR products.category LIKE ?)
            ORDER BY products.id DESC
        """, (f"%{search}%", f"%{search}%")).fetchall()

    return render_template(
        "marketplace.html",
        products=products,
        search=search
    )


# ---------------- RECYCLING ----------------

@app.route("/recycling", methods=["GET", "POST"])
def recycling():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        waste_type = request.form.get("waste_type", "")
        quantity = request.form.get("quantity", "").strip()
        address = request.form.get("address", "").strip()
        pickup_date = request.form.get("pickup_date", "")

        if not all([waste_type, quantity, address, pickup_date]):
            flash("Complete all recycling fields.", "error")
            return redirect(url_for("recycling"))

        try:
            selected_date = datetime.strptime(
                pickup_date, "%Y-%m-%d"
            ).date()

            if selected_date < datetime.today().date():
                raise ValueError

        except ValueError:
            flash("Choose a valid future pickup date.", "error")
            return redirect(url_for("recycling"))

        with get_db() as connection:
            connection.execute("""
                INSERT INTO recycling_requests
                (user_id, waste_type, quantity, address, pickup_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session["user_id"], waste_type,
                quantity, address, pickup_date
            ))

        flash("Recycling request submitted!", "success")
        return redirect(url_for("my_requests"))

    return render_template("recycling.html")


# ---------------- MY REQUESTS ----------------

@app.route("/my-requests")
def my_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    uid = session["user_id"]

    with get_db() as connection:

        exchanges = connection.execute(
            "SELECT * FROM exchanges WHERE user_id = ?",
            (uid,)
        ).fetchall()

        bookings = connection.execute("""
            SELECT repair_bookings.*, repair_shops.name AS shop_name
            FROM repair_bookings
            JOIN repair_shops ON repair_bookings.shop_id = repair_shops.id
            WHERE repair_bookings.user_id = ?
        """, (uid,)).fetchall()

        recycling_requests = connection.execute(
            "SELECT * FROM recycling_requests WHERE user_id = ?",
            (uid,)
        ).fetchall()

    return render_template(
        "my_requests.html",
        exchanges=exchanges,
        bookings=bookings,
        recycling=recycling_requests
    )


# ---------------- ADMIN ----------------

@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        abort(403)

    with get_db() as connection:

        devices = connection.execute(
            "SELECT * FROM devices ORDER BY id DESC"
        ).fetchall()

        exchanges = connection.execute("""
            SELECT exchanges.*, users.name
            FROM exchanges JOIN users ON exchanges.user_id = users.id
            ORDER BY exchanges.id DESC
        """).fetchall()

        bookings = connection.execute("""
            SELECT repair_bookings.*, users.name,
            repair_shops.name AS shop_name
            FROM repair_bookings
            JOIN users ON repair_bookings.user_id = users.id
            JOIN repair_shops ON repair_bookings.shop_id = repair_shops.id
        """).fetchall()

        recycling_requests = connection.execute("""
            SELECT recycling_requests.*, users.name
            FROM recycling_requests
            JOIN users ON recycling_requests.user_id = users.id
        """).fetchall()

        products = connection.execute("""
            SELECT products.*, users.name AS seller
            FROM products JOIN users ON products.user_id = users.id
        """).fetchall()

    return render_template(
        "admin.html",
        devices=devices,
        exchanges=exchanges,
        bookings=bookings,
        recycling=recycling_requests,
        products=products
    )


# ---------------- UPDATE STATUS ----------------

@app.route("/admin/update/<table>/<int:item_id>", methods=["POST"])
def update_status(table, item_id):

    if session.get("role") != "admin":
        abort(403)

    allowed_tables = {
        "exchanges", "repair_bookings", "recycling_requests"
    }

    allowed_statuses = {
        "Pending", "Approved", "Rejected",
        "Completed", "Collected", "In Progress"
    }

    status = request.form.get("status", "")

    if table not in allowed_tables or status not in allowed_statuses:
        abort(400)

    with get_db() as connection:
        cursor = connection.execute(
            f"UPDATE {table} SET status = ? WHERE id = ?",
            (status, item_id)
        )

        if cursor.rowcount == 0:
            abort(404)

    return redirect(url_for("admin"))


# ---------------- DELETE DEVICE (ORIGINAL) ----------------

@app.route("/delete/<int:device_id>", methods=["POST"])
def delete_device(device_id):

    if session.get("role") != "admin":
        abort(403)

    with get_db() as connection:
        connection.execute(
            "DELETE FROM devices WHERE id = ?",
            (device_id,)
        )

    return redirect(url_for("admin"))


# ---------------- ERROR HANDLERS ----------------

@app.errorhandler(403)
def forbidden(error):
    return "Access denied. Admin only.", 403


@app.errorhandler(413)
def file_too_large(error):
    return "Image must be smaller than 5 MB.", 413


# ---------------- APPLICATION START ----------------

create_database()

if __name__ == "__main__":
    print("\nREGISTERED ROUTES:")
    print(app.url_map)

    app.run(debug=True, port=5000)