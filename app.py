import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from pathlib import Path
import csv
import io
import json
import socket
from datetime import datetime
import openpyxl

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-for-production")

BASE = Path(__file__).resolve().parent
UPLOADS_DIR = BASE / "static" / "uploads"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = f"sqlite:///{BASE / 'data.db'}"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Product(db.Model):
    __tablename__ = "products"
    barcode = db.Column(db.String(128), primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0.0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image = db.Column(db.String(512), nullable=True)

    def to_dict(self):
        return {
            "barcode": self.barcode,
            "name": self.name,
            "price": self.price,
            "stock": self.stock,
            "image": self.image,
        }

class Member(db.Model):
    __tablename__ = "members"
    member_id = db.Column(db.String(128), primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    discount = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            "member_id": self.member_id,
            "name": self.name,
            "discount": self.discount,
        }


def ensure_directories():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


with app.app_context():
    ensure_directories()
    db.create_all()


def load_inventory():
    return [product.to_dict() for product in Product.query.order_by(Product.barcode).all()]


def save_inventory(data):
    Product.query.delete()
    for item in data:
        try:
            product = Product(
                barcode=str(item.get("barcode", "") or "").strip(),
                name=str(item.get("name", "") or "").strip(),
                price=float(item.get("price", 0) or 0),
                stock=int(item.get("stock", 0) or 0),
                image=str(item.get("image", "") or None) if item.get("image") else None,
            )
        except (ValueError, TypeError):
            continue
        db.session.add(product)
    db.session.commit()


def load_members():
    return [member.to_dict() for member in Member.query.order_by(Member.member_id).all()]


def save_members(data):
    Member.query.delete()
    for item in data:
        try:
            member = Member(
                member_id=str(item.get("member_id", "") or "").strip(),
                name=str(item.get("name", "") or "").strip(),
                discount=int(item.get("discount", 0) or 0),
            )
        except (ValueError, TypeError):
            continue
        db.session.add(member)
    db.session.commit()


def find_product(barcode):
    return Product.query.get(barcode)


def find_member(member_id):
    return Member.query.get(member_id)


def allowed_image(filename):
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_IMAGE_EXTENSIONS


def save_image_file(file_storage, barcode):
    if not file_storage:
        return None
    filename = secure_filename(file_storage.filename)
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        return None
    ensure_directories()
    target_name = f"{barcode}{suffix}"
    target_path = UPLOADS_DIR / target_name
    file_storage.save(target_path)
    return f"uploads/{target_name}"


def update_product(product):
    existing = Product.query.get(product["barcode"])
    if existing:
        existing.name = product["name"]
        existing.price = product["price"]
        existing.stock = product["stock"]
        existing.image = product.get("image")
    else:
        existing = Product(
            barcode=product["barcode"],
            name=product["name"],
            price=product["price"],
            stock=product["stock"],
            image=product.get("image"),
        )
        db.session.add(existing)
    db.session.commit()


def update_member(member):
    existing = Member.query.get(member["member_id"])
    if existing:
        existing.name = member["name"]
        existing.discount = member["discount"]
    else:
        existing = Member(
            member_id=member["member_id"],
            name=member["name"],
            discount=member["discount"],
        )
        db.session.add(existing)
    db.session.commit()


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_cart():
    return session.get("cart", {})


def save_cart(cart):
    session["cart"] = cart


def cart_items():
    cart = get_cart()
    items = []
    total = 0.0
    for barcode, qty in cart.items():
        product = find_product(barcode)
        if not product:
            continue
        subtotal = product.price * qty
        items.append({
            "barcode": barcode,
            "name": product.name,
            "price": product.price,
            "qty": qty,
            "subtotal": subtotal,
        })
        total += subtotal
    return items, total


def parse_inventory_file(file_storage):
    filename = file_storage.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = io.TextIOWrapper(file_storage.stream, encoding="utf-8")
        reader = csv.DictReader(text)
        products = []
        for row in reader:
            if not row.get("barcode"):
                continue
            try:
                products.append({
                    "barcode": str(row.get("barcode", "")).strip(),
                    "name": str(row.get("name", "")).strip(),
                    "price": float(row.get("price", 0)),
                    "stock": int(row.get("stock", 0)),
                    "image": str(row.get("image", "")).strip() or None,
                })
            except ValueError:
                raise ValueError("CSV 文件中的价格或库存格式错误")
        return products
    elif suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        workbook = openpyxl.load_workbook(file_storage, data_only=True)
        sheet = workbook.active
        headers = [str(cell.value).strip().lower() if cell.value else "" for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        products = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            row_data = dict(zip(headers, row))
            try:
                products.append({
                    "barcode": str(row_data.get("barcode", "")).strip(),
                    "name": str(row_data.get("name", "")).strip(),
                    "price": float(row_data.get("price", 0) or 0),
                    "stock": int(row_data.get("stock", 0) or 0),
                    "image": str(row_data.get("image", "")).strip() or None,
                })
            except ValueError:
                raise ValueError("Excel 文件中的价格或库存格式错误")
        return products
    else:
        raise ValueError("仅支持 CSV 或 Excel 文件")


@app.route("/")
def index():
    return render_template("index.html", host=request.host, local_ip=get_local_ip())


@app.route("/manage")
def manage():
    inventory = load_inventory()
    return render_template("manage.html", inventory=inventory)


@app.route("/manage/add", methods=["POST"])
def manage_add():
    barcode = request.form.get("barcode", "").strip()
    name = request.form.get("name", "").strip()
    price = request.form.get("price", "").strip()
    stock = request.form.get("stock", "").strip()
    image_file = request.files.get("image")

    if not barcode or not name or not price or not stock:
        flash("请填写完整商品信息", "error")
        return redirect(url_for("manage"))
    try:
        price = float(price)
        stock = int(stock)
    except ValueError:
        flash("价格必须是数字，库存必须是整数", "error")
        return redirect(url_for("manage"))

    existing = find_product(barcode) or {}
    image_path = existing.get("image")
    uploaded_image = save_image_file(image_file, barcode)
    if uploaded_image:
        image_path = uploaded_image
    product = {
        "barcode": barcode,
        "name": name,
        "price": price,
        "stock": stock,
        "image": image_path,
    }
    update_product(product)
    flash("商品已保存", "success")
    return redirect(url_for("manage"))


@app.route("/manage/delete/<barcode>", methods=["POST"])
def manage_delete(barcode):
    product = Product.query.get(barcode)
    if product and product.image:
        image_path = BASE / "static" / product.image
        if image_path.exists():
            try:
                image_path.unlink()
            except Exception:
                pass
    if product:
        db.session.delete(product)
        db.session.commit()
    flash("商品已删除", "success")
    return redirect(url_for("manage"))


@app.route("/manage/import", methods=["POST"])
def manage_import():
    inventory_file = request.files.get("inventory_file")
    if not inventory_file or not inventory_file.filename:
        flash("请上传 CSV 或 Excel 文件", "error")
        return redirect(url_for("manage"))
    try:
        products = parse_inventory_file(inventory_file)
        for product in products:
            update_product(product)
        flash(f"已导入 {len(products)} 条商品", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("manage"))


@app.route("/manage/export/<fmt>")
def manage_export(fmt):
    inventory = load_inventory()
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["barcode", "name", "price", "stock", "image"])
        for product in inventory:
            writer.writerow([
                product.get("barcode", ""),
                product.get("name", ""),
                product.get("price", ""),
                product.get("stock", ""),
                product.get("image", ""),
            ])
        data = output.getvalue().encode("utf-8-sig")
        return send_file(
            io.BytesIO(data),
            mimetype="text/csv",
            as_attachment=True,
            download_name="inventory.csv",
        )
    elif fmt in {"xlsx", "xlsm", "xltx", "xltm"}:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["barcode", "name", "price", "stock", "image"])
        for product in inventory:
            sheet.append([
                product.get("barcode", ""),
                product.get("name", ""),
                product.get("price", ""),
                product.get("stock", ""),
                product.get("image", ""),
            ])
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="inventory.xlsx",
        )
    flash("不支持的导出格式", "error")
    return redirect(url_for("manage"))


@app.route("/members")
def members():
    members = load_members()
    return render_template("members.html", members=members)


@app.route("/members/add", methods=["POST"])
def members_add():
    member_id = request.form.get("member_id", "").strip()
    name = request.form.get("name", "").strip()
    discount = request.form.get("discount", "").strip()
    if not member_id or not name or not discount:
        flash("请填写完整会员信息", "error")
        return redirect(url_for("members"))
    try:
        discount = int(discount)
    except ValueError:
        flash("折扣必须是整数", "error")
        return redirect(url_for("members"))
    member = {"member_id": member_id, "name": name, "discount": discount}
    update_member(member)
    flash("会员已保存", "success")
    return redirect(url_for("members"))


@app.route("/members/delete/<member_id>", methods=["POST"])
def members_delete(member_id):
    member = Member.query.get(member_id)
    if member:
        db.session.delete(member)
        db.session.commit()
    flash("会员已删除", "success")
    return redirect(url_for("members"))


@app.route("/api/member/<member_id>")
def api_member(member_id):
    member = find_member(member_id)
    if member:
        return jsonify({"found": True, "member": member.to_dict()})
    return jsonify({"found": False, "error": "未找到会员"}), 404


@app.route("/cashier")
def cashier():
    items, total = cart_items()
    return render_template("cashier.html", items=items, total=total)


@app.route("/api/product/<barcode>")
def api_product(barcode):
    product = find_product(barcode)
    if product:
        return jsonify({"found": True, "product": product.to_dict()})
    return jsonify({"found": False}), 404


@app.route("/api/cashier/scan", methods=["POST"])
def api_cashier_scan():
    data = request.get_json(force=True, silent=True) or {}
    barcode = str(data.get("barcode", "")).strip()
    if not barcode:
        return jsonify({"error": "barcode required"}), 400
    product = find_product(barcode)
    if not product:
        return jsonify({"error": "未找到商品"}), 404

    cart = get_cart()
    qty = cart.get(barcode, 0) + 1
    if qty > product.stock:
        return jsonify({"error": "库存不足"}), 400

    cart[barcode] = qty
    save_cart(cart)
    items, total = cart_items()
    return jsonify({
        "product": {
            "barcode": product.barcode,
            "name": product.name,
            "price": product.price,
            "stock": product.stock,
            "qty": qty,
            "image": product.image,
        },
        "cart": {
            "items": items,
            "total": round(total, 2),
        },
    })


@app.route("/api/cashier/checkout", methods=["POST"])
def api_checkout():
    data = request.get_json(force=True, silent=True) or {}
    member_id = str(data.get("member_id", "")).strip()
    member = find_member(member_id) if member_id else None
    cart = get_cart()
    if not cart:
        return jsonify({"error": "购物车为空"}), 400
    for barcode, qty in cart.items():
        product = find_product(barcode)
        if product:
            product.stock = max(0, product.stock - qty)
    db.session.commit()
    session["cart"] = {}
    message = "结账完成，库存已更新"
    if member:
        message += f"（{member.name} 享受 {member.discount}% 折扣）"
    return jsonify({"success": True, "message": message})


@app.route("/api/cashier/cancel", methods=["POST"])
def api_cancel():
    session["cart"] = {}
    return jsonify({"success": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug)
