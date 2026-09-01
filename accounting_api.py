"""Private accounting API backed by the inventory system database.

The browser never calls this API directly. The accounting site's server proxy
adds ACCOUNTING_API_TOKEN and forwards requests over HTTPS.
"""

import hashlib
import hmac
import io
import json
import os
import uuid
import zipfile
from datetime import date, datetime

import jwt
from flask import Blueprint, Response, jsonify, request, send_file
from flask import g
from jwt import PyJWKClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy import UniqueConstraint


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_BACKUP_BYTES = 90 * 1024 * 1024
MAX_BACKUP_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_BACKUP_FILES = 2500
ACCOUNTING_ROLES = {"admin", "editor", "viewer"}
DEFAULT_BOOTSTRAP_USERS = {
    "wangyiwei0924@gmail.com": "admin",
    "moon.gallery.studio@gmail.com": "editor",
}
FIREBASE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def init_accounting_api(app, db, Sale, app_timezone):
    class AccountingEntry(db.Model):
        __tablename__ = "accounting_entries"
        id = db.Column(db.String(80), primary_key=True)
        entry_date = db.Column(db.Date, nullable=False, index=True)
        description = db.Column(db.String(500), nullable=False)
        source = db.Column(db.String(80), nullable=False, default="manual")
        debit_account = db.Column(db.String(120), nullable=False)
        credit_account = db.Column(db.String(120), nullable=False)
        amount = db.Column(db.Integer, nullable=False)
        status = db.Column(db.String(32), nullable=False, default="review")
        payment = db.Column(db.String(120), nullable=False, default="")
        import_key = db.Column(db.String(500), nullable=True, unique=True)
        import_batch_id = db.Column(db.String(120), nullable=True)
        import_file_name = db.Column(db.String(500), nullable=True)
        imported_at = db.Column(db.DateTime, nullable=True)
        version = db.Column(db.Integer, nullable=False, default=1)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        created_by = db.Column(db.String(200), nullable=False, default="system")

    class AccountingEmployee(db.Model):
        __tablename__ = "accounting_employees"
        id = db.Column(db.String(80), primary_key=True)
        name = db.Column(db.String(250), nullable=False)
        furigana = db.Column(db.String(250), nullable=False, default="")
        employee_number = db.Column(db.String(100), nullable=False, default="")
        birth_date = db.Column(db.Date, nullable=True)
        address = db.Column(db.String(700), nullable=False, default="")
        role = db.Column(db.String(40), nullable=False, default="employee")
        start_date = db.Column(db.Date, nullable=True)
        municipality = db.Column(db.String(300), nullable=False, default="")
        version = db.Column(db.Integer, nullable=False, default=1)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))

    class AccountingPayroll(db.Model):
        __tablename__ = "accounting_payroll_records"
        id = db.Column(db.String(80), primary_key=True)
        employee_id = db.Column(db.String(80), db.ForeignKey("accounting_employees.id"), nullable=False, index=True)
        month = db.Column(db.String(7), nullable=False, index=True)
        pay_date = db.Column(db.Date, nullable=False)
        gross = db.Column(db.Integer, nullable=False, default=0)
        social_insurance = db.Column(db.Integer, nullable=False, default=0)
        income_tax = db.Column(db.Integer, nullable=False, default=0)
        resident_tax = db.Column(db.Integer, nullable=False, default=0)
        other_deductions = db.Column(db.Integer, nullable=False, default=0)
        import_key = db.Column(db.String(500), nullable=True, unique=True)
        import_file_name = db.Column(db.String(500), nullable=True)
        version = db.Column(db.Integer, nullable=False, default=1)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))

    class AccountingProcedure(db.Model):
        __tablename__ = "accounting_procedure_statuses"
        item_id = db.Column(db.String(120), primary_key=True)
        completed = db.Column(db.Boolean, nullable=False, default=False)
        completed_at = db.Column(db.DateTime, nullable=True)
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))

    class AccountingDocument(db.Model):
        __tablename__ = "accounting_documents"
        id = db.Column(db.String(100), primary_key=True)
        category = db.Column(db.String(40), nullable=False, index=True)
        related_id = db.Column(db.String(120), nullable=True, index=True)
        employee_id = db.Column(db.String(80), nullable=True, index=True)
        document_type = db.Column(db.String(200), nullable=False, default="")
        file_name = db.Column(db.String(500), nullable=False)
        mime_type = db.Column(db.String(200), nullable=False)
        size = db.Column(db.Integer, nullable=False)
        sha256 = db.Column(db.String(64), nullable=False, index=True)
        content = db.Column(db.LargeBinary, nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        created_by = db.Column(db.String(200), nullable=False, default="owner")
        __table_args__ = (UniqueConstraint("category", "sha256", "related_id", name="uq_accounting_document_scope_hash"),)

    class AccountingSetting(db.Model):
        __tablename__ = "accounting_settings"
        key = db.Column(db.String(120), primary_key=True)
        value = db.Column(db.Text, nullable=False, default="")
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))

    class AccountingAuditLog(db.Model):
        __tablename__ = "accounting_audit_logs"
        id = db.Column(db.Integer, primary_key=True)
        action = db.Column(db.String(80), nullable=False, index=True)
        entity_type = db.Column(db.String(80), nullable=False, index=True)
        entity_id = db.Column(db.String(120), nullable=True, index=True)
        actor = db.Column(db.String(200), nullable=False, default="owner")
        detail = db.Column(db.Text, nullable=False, default="{}")
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None), index=True)

    class AccountingUser(db.Model):
        __tablename__ = "accounting_users"
        email = db.Column(db.String(320), primary_key=True)
        firebase_uid = db.Column(db.String(128), nullable=True, unique=True)
        display_name = db.Column(db.String(250), nullable=False, default="")
        role = db.Column(db.String(20), nullable=False, default="viewer", index=True)
        active = db.Column(db.Boolean, nullable=False, default=True)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None))
        created_by = db.Column(db.String(320), nullable=False, default="bootstrap")

    class AccountingBackup(db.Model):
        __tablename__ = "accounting_backups"
        id = db.Column(db.String(100), primary_key=True)
        daily_key = db.Column(db.String(20), nullable=True, unique=True)
        kind = db.Column(db.String(30), nullable=False, default="manual", index=True)
        file_name = db.Column(db.String(300), nullable=False)
        size = db.Column(db.Integer, nullable=False)
        sha256 = db.Column(db.String(64), nullable=False, index=True)
        summary = db.Column(db.Text, nullable=False, default="{}")
        content = db.Column(db.LargeBinary, nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(app_timezone).replace(tzinfo=None), index=True)
        created_by = db.Column(db.String(320), nullable=False, default="system")

    api = Blueprint("accounting_api", __name__, url_prefix="/api/accounting")
    firebase_jwk_client = PyJWKClient(FIREBASE_JWKS_URL, cache_keys=True, lifespan=3600)

    def now():
        return datetime.now(app_timezone).replace(tzinfo=None)

    def iso(value):
        return value.isoformat() if value else None

    def parse_date(value, required=False):
        if not value:
            if required:
                raise ValueError("date is required")
            return None
        return date.fromisoformat(str(value)[:10])

    def integer(value):
        number = int(float(value or 0))
        if number < 0:
            raise ValueError("amounts cannot be negative")
        return number

    def locked_through():
        row = db.session.get(AccountingSetting, "locked_through")
        if not row or not row.value:
            return None
        try:
            return date.fromisoformat(row.value[:10])
        except ValueError:
            return None

    def entry_values(row):
        return (
            iso(row.entry_date), row.description, row.source, row.debit_account,
            row.credit_account, row.amount, row.status, row.payment,
            row.import_key, row.import_batch_id, row.import_file_name,
        )

    def incoming_entry_values(data):
        return (
            iso(parse_date(data.get("date"), True)),
            str(data.get("description") or "").strip()[:500],
            str(data.get("source") or "manual")[:80],
            str(data.get("debit") or "").strip()[:120],
            str(data.get("credit") or "").strip()[:120],
            integer(data.get("amount")),
            str(data.get("status") or "review")[:32],
            str(data.get("payment") or "")[:120],
            str(data.get("importKey"))[:500] if data.get("importKey") else None,
            str(data.get("importBatchId"))[:120] if data.get("importBatchId") else None,
            str(data.get("importFileName"))[:500] if data.get("importFileName") else None,
        )

    def validate_entry_data(data):
        entry_date = parse_date(data.get("date"), True)
        description = str(data.get("description") or "").strip()
        debit = str(data.get("debit") or "").strip()
        credit = str(data.get("credit") or "").strip()
        amount = integer(data.get("amount"))
        if not description or not debit or not credit or amount <= 0:
            raise ValueError("entry fields are incomplete")
        if debit == credit:
            raise ValueError("debit and credit accounts must be different")
        lock_date = locked_through()
        if lock_date and entry_date <= lock_date:
            existing = db.session.get(AccountingEntry, str(data.get("id") or "")[:80])
            if not existing or incoming_entry_values(data) != entry_values(existing):
                raise PermissionError(f"period is closed through {lock_date.isoformat()}")

    def validate_payroll_data(data):
        gross = integer(data.get("gross"))
        deductions = sum(integer(data.get(key)) for key in (
            "socialInsurance", "incomeTax", "residentTax", "otherDeductions",
        ))
        if deductions > gross:
            raise ValueError("payroll deductions cannot exceed gross pay")
        row_id = str(data.get("id") or "")[:80]
        employee_id = str(data.get("employeeId") or "")[:80]
        month = str(data.get("month") or "")[:7]
        duplicate = AccountingPayroll.query.filter_by(employee_id=employee_id, month=month).first()
        if duplicate and duplicate.id != row_id:
            raise ValueError("payroll already exists for this employee and month")
        pay_date = parse_date(data.get("payDate"), True)
        lock_date = locked_through()
        if lock_date and pay_date <= lock_date:
            existing = db.session.get(AccountingPayroll, str(data.get("id") or "")[:80])
            unchanged = existing and all((
                existing.employee_id == str(data.get("employeeId") or "")[:80],
                existing.month == str(data.get("month") or "")[:7],
                existing.pay_date == pay_date,
                existing.gross == gross,
                existing.social_insurance == integer(data.get("socialInsurance")),
                existing.income_tax == integer(data.get("incomeTax")),
                existing.resident_tax == integer(data.get("residentTax")),
                existing.other_deductions == integer(data.get("otherDeductions")),
            ))
            if not unchanged:
                raise PermissionError(f"period is closed through {lock_date.isoformat()}")

    def actor():
        identity = getattr(g, "firebase_identity", None) or {}
        return (identity.get("email") or request.headers.get("X-Accounting-Actor") or "system")[:200]

    def authorized():
        expected = os.environ.get("ACCOUNTING_API_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        if not expected or not supplied.startswith("Bearer "):
            return False
        return hmac.compare_digest(supplied[7:], expected)

    def verified_firebase_identity():
        project_id = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        supplied = request.headers.get("X-Firebase-Authorization", "")
        if not project_id or not supplied.startswith("Bearer "):
            return None
        token = supplied[7:]
        try:
            signing_key = firebase_jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, signing_key.key, algorithms=["RS256"], audience=project_id,
                issuer=f"https://securetoken.google.com/{project_id}", leeway=30,
                options={"require": ["exp", "iat", "sub"]},
            )
        except (jwt.PyJWTError, jwt.exceptions.PyJWKClientError, ValueError):
            return None
        email = str(claims.get("email") or "").strip().lower()
        uid = str(claims.get("sub") or "").strip()
        auth_time = claims.get("auth_time", claims.get("iat"))
        if not isinstance(auth_time, (int, float)) or auth_time > datetime.now().timestamp() + 30:
            return None
        if not email or not uid or len(uid) > 128 or claims.get("email_verified") is not True:
            return None
        return {"email": email[:320], "uid": uid, "name": str(claims.get("name") or "")[:250]}

    def bootstrap_user_roles():
        configured = os.environ.get("ACCOUNTING_BOOTSTRAP_USERS", "").strip()
        if not configured:
            return DEFAULT_BOOTSTRAP_USERS
        roles = {}
        for item in configured.split(","):
            email, separator, role = item.strip().partition(":")
            normalized = email.strip().lower()
            selected_role = role.strip().lower() if separator else "viewer"
            if normalized and selected_role in ACCOUNTING_ROLES:
                roles[normalized] = selected_role
        return roles

    def ensure_bootstrap_users():
        changed = False
        for email, role in bootstrap_user_roles().items():
            if not db.session.get(AccountingUser, email):
                db.session.add(AccountingUser(email=email, role=role, active=True, created_by="bootstrap"))
                changed = True
        if changed:
            db.session.commit()

    @api.before_request
    def require_access():
        if not authorized():
            return jsonify({"error": "UNAUTHORIZED"}), 401
        if request.path.endswith("/health"):
            return None
        identity = verified_firebase_identity()
        if not identity:
            return jsonify({"error": "INVALID_FIREBASE_TOKEN"}), 401
        g.firebase_identity = identity
        ensure_bootstrap_users()
        user = db.session.get(AccountingUser, identity["email"])
        if not user or not user.active:
            return jsonify({"error": "ACCOUNT_NOT_ALLOWED"}), 403
        if user.firebase_uid and not hmac.compare_digest(user.firebase_uid, identity["uid"]):
            return jsonify({"error": "IDENTITY_MISMATCH"}), 403
        if not user.firebase_uid:
            user.firebase_uid = identity["uid"]
        if identity["name"] and identity["name"] != user.display_name:
            user.display_name = identity["name"]
        user.updated_at = now()
        db.session.add(user)
        db.session.commit()
        g.accounting_user = user
        admin_only = any(request.path == path or request.path.startswith(f"{path}/") for path in {
            "/api/accounting/users", "/api/accounting/sales/sync", "/api/accounting/audit",
            "/api/accounting/backup", "/api/accounting/backups", "/api/accounting/restore",
        })
        if admin_only and user.role != "admin":
            return jsonify({"error": "ADMIN_REQUIRED"}), 403
        if user.role == "viewer" and request.method not in {"GET", "HEAD"}:
            return jsonify({"error": "READ_ONLY"}), 403
        try:
            ensure_daily_backup()
        except Exception:
            db.session.rollback()
            app.logger.exception("Automatic accounting backup failed")
        return None

    def audit(action, entity_type, entity_id=None, detail=None):
        safe_detail = detail if isinstance(detail, dict) else {}
        db.session.add(AccountingAuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id)[:120] if entity_id is not None else None,
            actor=actor(),
            detail=json.dumps(safe_detail, ensure_ascii=False, separators=(",", ":")),
        ))

    def entry_dict(row, shop_sales=None):
        payload = {
            "id": row.id, "date": iso(row.entry_date), "description": row.description,
            "source": row.source, "debit": row.debit_account, "credit": row.credit_account,
            "amount": row.amount, "status": row.status, "payment": row.payment,
            "importKey": row.import_key, "importBatchId": row.import_batch_id,
            "importFileName": row.import_file_name, "importedAt": iso(row.imported_at),
            "version": row.version,
        }
        if row.source == "shop-db" and shop_sales:
            payload["details"] = shop_sales.get(iso(row.entry_date), {}).get("details", [])
        return payload

    def shop_sales_by_day():
        groups = {}
        for sale in Sale.query.order_by(Sale.created_at, Sale.id).all():
            day = sale.created_at.date().isoformat()
            group = groups.setdefault(day, {
                "amount": 0, "salesCount": 0, "itemCount": 0,
                "paymentMethods": set(), "details": [],
            })
            payable = integer(round(sale.payable or 0))
            group["amount"] += payable
            group["salesCount"] += 1
            if sale.payment_method:
                group["paymentMethods"].add(sale.payment_method)

            items = list(sale.items)
            sale_total = float(sale.total or sum(float(item.subtotal or 0) for item in items))
            allocated = [integer(round(float(item.subtotal or 0) * payable / sale_total)) if sale_total else 0 for item in items]
            if allocated:
                allocated[-1] += payable - sum(allocated)
            for item, recognized_amount in zip(items, allocated):
                quantity = integer(item.qty)
                group["itemCount"] += quantity
                group["details"].append({
                    "id": f"shop-item-{item.id}", "saleId": sale.id,
                    "soldAt": iso(sale.created_at), "name": item.name,
                    "quantity": quantity, "unitPrice": integer(round(item.price or 0)),
                    "amount": recognized_amount, "payment": sale.payment_method or "未记录",
                })
        return groups

    def employee_dict(row):
        return {
            "id": row.id, "name": row.name, "furigana": row.furigana,
            "employeeNumber": row.employee_number, "birthDate": iso(row.birth_date),
            "address": row.address, "role": row.role, "startDate": iso(row.start_date),
            "municipality": row.municipality, "version": row.version,
        }

    def payroll_dict(row):
        return {
            "id": row.id, "employeeId": row.employee_id, "month": row.month,
            "payDate": iso(row.pay_date), "gross": row.gross,
            "socialInsurance": row.social_insurance, "incomeTax": row.income_tax,
            "residentTax": row.resident_tax, "otherDeductions": row.other_deductions,
            "importKey": row.import_key, "importFileName": row.import_file_name,
            "version": row.version,
        }

    def document_dict(row):
        return {
            "id": row.id, "category": row.category, "itemId": row.related_id,
            "employeeId": row.employee_id, "documentType": row.document_type,
            "fileName": row.file_name, "mimeType": row.mime_type, "size": row.size,
            "createdAt": iso(row.created_at),
        }

    def user_dict(row):
        return {
            "email": row.email, "displayName": row.display_name,
            "role": row.role, "active": row.active,
            "createdAt": iso(row.created_at), "updatedAt": iso(row.updated_at),
        }

    def audit_dict(row):
        try:
            detail = json.loads(row.detail or "{}")
        except (TypeError, ValueError):
            detail = {}
        return {
            "id": row.id, "action": row.action, "entityType": row.entity_type,
            "entityId": row.entity_id, "actor": row.actor,
            "detail": detail, "createdAt": iso(row.created_at),
        }

    def backup_dict(row):
        try:
            summary = json.loads(row.summary or "{}")
        except (TypeError, ValueError):
            summary = {}
        return {
            "id": row.id, "kind": row.kind, "fileName": row.file_name,
            "size": row.size, "sha256": row.sha256, "summary": summary,
            "createdAt": iso(row.created_at), "createdBy": row.created_by,
        }

    def backup_retention_days():
        try:
            return min(max(int(os.environ.get("ACCOUNTING_BACKUP_RETENTION_DAYS", "14")), 7), 90)
        except ValueError:
            return 14

    def build_backup_archive():
        documents = AccountingDocument.query.order_by(AccountingDocument.created_at, AccountingDocument.id).all()
        if sum(row.size for row in documents) > MAX_BACKUP_UNCOMPRESSED_BYTES:
            raise ValueError("documents exceed the backup safety limit")
        settings = {row.key: row.value for row in AccountingSetting.query.order_by(AccountingSetting.key).all()}
        audit_rows = AccountingAuditLog.query.order_by(AccountingAuditLog.created_at, AccountingAuditLog.id).all()
        state = state_payload()
        state["entries"] = [{key: value for key, value in entry.items() if key != "details"} for entry in state["entries"]]
        summary = {
            "entries": len(state["entries"]), "employees": len(state["employees"]),
            "payrollRecords": len(state["payrollRecords"]), "documents": len(documents),
            "documentBytes": sum(row.size for row in documents), "auditEvents": len(audit_rows),
        }
        manifest_documents = []
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for index, row in enumerate(documents, start=1):
                archive_path = f"documents/{index:05d}.bin"
                archive.writestr(archive_path, row.content)
                manifest_documents.append({**document_dict(row), "archivePath": archive_path, "sha256": row.sha256, "createdBy": row.created_by})
            manifest = {
                "format": "shingetsu-ledger-backup", "version": 1,
                "exportedAt": now().isoformat(), "company": "合同会社新月芸術",
                "summary": summary, "documents": manifest_documents,
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr("state.json", json.dumps(state, ensure_ascii=False, indent=2))
            archive.writestr("settings.json", json.dumps(settings, ensure_ascii=False, indent=2))
            archive.writestr("users.json", json.dumps([user_dict(row) for row in AccountingUser.query.order_by(AccountingUser.email).all()], ensure_ascii=False, indent=2))
            archive.writestr("audit.json", json.dumps([audit_dict(row) for row in audit_rows], ensure_ascii=False, indent=2))
        content = output.getvalue()
        if len(content) > MAX_BACKUP_BYTES:
            raise ValueError("backup exceeds the 90 MB limit")
        return content, summary

    def create_snapshot(kind="manual", daily_key=None, created_by=None):
        content, summary = build_backup_archive()
        stamp = now().strftime("%Y%m%d-%H%M%S")
        row = AccountingBackup(
            id=f"backup-{uuid.uuid4()}", daily_key=daily_key, kind=kind,
            file_name=f"shingetsu-ledger-{kind}-{stamp}.zip", size=len(content),
            sha256=hashlib.sha256(content).hexdigest(), summary=json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
            content=content, created_by=(created_by or actor())[:320],
        )
        db.session.add(row)
        audit("create", "backup", row.id, {"kind": kind, **summary})
        db.session.commit()
        return row

    def ensure_daily_backup():
        daily_key = now().date().isoformat()
        if AccountingBackup.query.filter_by(daily_key=daily_key).first():
            return
        try:
            create_snapshot("automatic", daily_key=daily_key, created_by="system")
        except IntegrityError:
            db.session.rollback()
            return
        keep = backup_retention_days()
        old_rows = AccountingBackup.query.filter_by(kind="automatic").order_by(AccountingBackup.created_at.desc()).offset(keep).all()
        if old_rows:
            for row in old_rows:
                db.session.delete(row)
            db.session.commit()

    def read_backup_archive(content):
        if not content or len(content) > MAX_BACKUP_BYTES:
            raise ValueError("backup file is empty or too large")
        try:
            archive = zipfile.ZipFile(io.BytesIO(content), "r")
        except zipfile.BadZipFile as error:
            raise ValueError("backup is not a valid ZIP file") from error
        names = archive.namelist()
        if len(names) > MAX_BACKUP_FILES or sum(info.file_size for info in archive.infolist()) > MAX_BACKUP_UNCOMPRESSED_BYTES:
            archive.close()
            raise ValueError("backup expands beyond the safety limit")
        if any(name.startswith("/") or ".." in name.split("/") for name in names):
            archive.close()
            raise ValueError("backup contains an unsafe path")
        try:
            manifest = json.loads(archive.read("manifest.json"))
            state = json.loads(archive.read("state.json"))
            settings = json.loads(archive.read("settings.json")) if "settings.json" in names else {}
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
            archive.close()
            raise ValueError("backup metadata is incomplete") from error
        if manifest.get("format") != "shingetsu-ledger-backup" or manifest.get("version") != 1:
            archive.close()
            raise ValueError("backup format is not supported")
        if not isinstance(state, dict) or not isinstance(settings, dict) or not isinstance(manifest.get("documents", []), list):
            archive.close()
            raise ValueError("backup data is invalid")
        return archive, manifest, state, settings

    def restore_archive(content, source):
        archive, manifest, state, settings = read_backup_archive(content)
        document_payloads = []
        try:
            for item in manifest.get("documents", []):
                archive_path = str(item.get("archivePath") or "")
                if not archive_path.startswith("documents/"):
                    raise ValueError("document path is invalid")
                body = archive.read(archive_path)
                if len(body) > MAX_DOCUMENT_BYTES or len(body) != int(item.get("size") or -1):
                    raise ValueError("document size does not match the manifest")
                digest = hashlib.sha256(body).hexdigest()
                if not hmac.compare_digest(digest, str(item.get("sha256") or "")):
                    raise ValueError("document checksum does not match the manifest")
                document_payloads.append((item, body, digest))
        except (KeyError, TypeError, ValueError) as error:
            archive.close()
            if isinstance(error, ValueError):
                raise
            raise ValueError("backup document data is invalid") from error
        finally:
            archive.close()

        create_snapshot("before_restore", created_by=actor())
        try:
            AccountingPayroll.query.delete(synchronize_session=False)
            AccountingProcedure.query.delete(synchronize_session=False)
            AccountingDocument.query.delete(synchronize_session=False)
            AccountingEmployee.query.delete(synchronize_session=False)
            AccountingEntry.query.delete(synchronize_session=False)
            AccountingSetting.query.delete(synchronize_session=False)
            db.session.flush()

            employees = state.get("employees") if isinstance(state.get("employees"), list) else []
            entries = state.get("entries") if isinstance(state.get("entries"), list) else []
            payroll = state.get("payrollRecords") if isinstance(state.get("payrollRecords"), list) else []
            for item in employees:
                upsert_employee(item)
            for item in entries:
                upsert_entry(item)
            db.session.flush()
            for item in payroll:
                upsert_payroll(item)
            for item_id in {str(value)[:120] for value in state.get("completedProcedures", [])}:
                db.session.add(AccountingProcedure(item_id=item_id, completed=True, completed_at=now(), updated_at=now()))
            for key, value in settings.items():
                if isinstance(key, str) and len(key) <= 120 and isinstance(value, str):
                    set_setting(key, value)
            if "profile" not in settings:
                set_setting("profile", json.dumps(state.get("profile") if isinstance(state.get("profile"), dict) else {}, ensure_ascii=False, separators=(",", ":")))
            set_setting("initialized", "true")
            set_setting("updated_at", now().isoformat())
            for item, body, digest in document_payloads:
                category = str(item.get("category") or "")[:40]
                mime_type = str(item.get("mimeType") or "application/octet-stream")[:200]
                if category not in {"year_end", "schedule"} or mime_type not in ALLOWED_DOCUMENT_TYPES:
                    raise ValueError("backup contains an unsupported document")
                db.session.add(AccountingDocument(
                    id=str(item.get("id") or f"doc-{uuid.uuid4()}")[:100], category=category,
                    related_id=str(item.get("itemId") or "")[:120] or None,
                    employee_id=str(item.get("employeeId") or "")[:80] or None,
                    document_type=str(item.get("documentType") or "")[:200],
                    file_name=str(item.get("fileName") or "document")[:500], mime_type=mime_type,
                    size=len(body), sha256=digest, content=body,
                    created_at=datetime.fromisoformat(str(item.get("createdAt"))) if item.get("createdAt") else now(),
                    created_by=str(item.get("createdBy") or actor())[:200],
                ))
            audit("restore", "backup", source, {
                "entries": len(entries), "employees": len(employees), "payroll": len(payroll),
                "documents": len(document_payloads),
            })
            db.session.commit()
            return state_payload()
        except Exception:
            db.session.rollback()
            raise

    def upsert_entry(data):
        validate_entry_data(data)
        row_id = str(data.get("id") or f"e-{uuid.uuid4()}")[:80]
        row = db.session.get(AccountingEntry, row_id)
        if row and row.source == "shop-db":
            return row
        row = row or AccountingEntry(id=row_id, created_by=actor())
        row.entry_date = parse_date(data.get("date"), True)
        row.description = str(data.get("description") or "").strip()[:500]
        row.source = str(data.get("source") or "manual")[:80]
        row.debit_account = str(data.get("debit") or "").strip()[:120]
        row.credit_account = str(data.get("credit") or "").strip()[:120]
        row.amount = integer(data.get("amount"))
        row.status = str(data.get("status") or "review")[:32]
        row.payment = str(data.get("payment") or "")[:120]
        row.import_key = str(data.get("importKey"))[:500] if data.get("importKey") else None
        row.import_batch_id = str(data.get("importBatchId"))[:120] if data.get("importBatchId") else None
        row.import_file_name = str(data.get("importFileName"))[:500] if data.get("importFileName") else None
        row.imported_at = datetime.fromisoformat(str(data.get("importedAt")).replace("Z", "+00:00")).replace(tzinfo=None) if data.get("importedAt") else None
        row.updated_at = now()
        row.version = (row.version or 0) + 1
        db.session.add(row)
        return row

    def upsert_employee(data):
        row_id = str(data.get("id") or f"p-{uuid.uuid4()}")[:80]
        row = db.session.get(AccountingEmployee, row_id) or AccountingEmployee(id=row_id)
        row.name = str(data.get("name") or "").strip()[:250]
        row.furigana = str(data.get("furigana") or "")[:250]
        row.employee_number = str(data.get("employeeNumber") or "")[:100]
        row.birth_date = parse_date(data.get("birthDate"))
        row.address = str(data.get("address") or "")[:700]
        row.role = str(data.get("role") or "employee")[:40]
        row.start_date = parse_date(data.get("startDate"))
        row.municipality = str(data.get("municipality") or "")[:300]
        row.updated_at = now()
        row.version = (row.version or 0) + 1
        if not row.name:
            raise ValueError("employee name is required")
        db.session.add(row)
        return row

    def upsert_payroll(data):
        validate_payroll_data(data)
        row_id = str(data.get("id") or f"w-{uuid.uuid4()}")[:80]
        employee_id = str(data.get("employeeId") or "")[:80]
        if not db.session.get(AccountingEmployee, employee_id):
            raise ValueError("employee does not exist")
        row = db.session.get(AccountingPayroll, row_id) or AccountingPayroll(id=row_id)
        row.employee_id = employee_id
        row.month = str(data.get("month") or "")[:7]
        row.pay_date = parse_date(data.get("payDate"), True)
        row.gross = integer(data.get("gross"))
        row.social_insurance = integer(data.get("socialInsurance"))
        row.income_tax = integer(data.get("incomeTax"))
        row.resident_tax = integer(data.get("residentTax"))
        row.other_deductions = integer(data.get("otherDeductions"))
        row.import_key = str(data.get("importKey"))[:500] if data.get("importKey") else None
        row.import_file_name = str(data.get("importFileName"))[:500] if data.get("importFileName") else None
        row.updated_at = now()
        row.version = (row.version or 0) + 1
        if len(row.month) != 7:
            raise ValueError("payroll month is invalid")
        db.session.add(row)
        return row

    def state_payload():
        settings = {row.key: row.value for row in AccountingSetting.query.all()}
        shop_sales = shop_sales_by_day()
        return {
            "initialized": settings.get("initialized") == "true",
            "entries": [entry_dict(row, shop_sales) for row in AccountingEntry.query.order_by(AccountingEntry.entry_date).all()],
            "employees": [employee_dict(row) for row in AccountingEmployee.query.order_by(AccountingEmployee.created_at).all()],
            "payrollRecords": [payroll_dict(row) for row in AccountingPayroll.query.order_by(AccountingPayroll.month).all()],
            "completedProcedures": [row.item_id for row in AccountingProcedure.query.filter_by(completed=True).all()],
            "profile": json.loads(settings.get("profile", "{}")),
            "controls": {"lockedThrough": settings.get("locked_through") or None},
            "updatedAt": settings.get("updated_at"),
        }

    def correctness_payload():
        issues = []
        entries = AccountingEntry.query.order_by(AccountingEntry.entry_date, AccountingEntry.id).all()
        fingerprints = {}
        for row in entries:
            if row.debit_account == row.credit_account:
                issues.append({"severity": "error", "code": "SAME_ACCOUNT", "entityType": "entry", "entityIds": [row.id], "date": iso(row.entry_date), "label": row.description})
            if row.amount <= 0:
                issues.append({"severity": "error", "code": "INVALID_AMOUNT", "entityType": "entry", "entityIds": [row.id], "date": iso(row.entry_date), "label": row.description})
            if row.status == "review":
                issues.append({"severity": "warning", "code": "REVIEW_REQUIRED", "entityType": "entry", "entityIds": [row.id], "date": iso(row.entry_date), "label": row.description})
            if row.source != "shop-db" and not row.import_key:
                fingerprint = (row.entry_date, " ".join(row.description.lower().split()), row.debit_account, row.credit_account, row.amount)
                fingerprints.setdefault(fingerprint, []).append(row)
        for rows in fingerprints.values():
            if len(rows) > 1:
                issues.append({"severity": "warning", "code": "POSSIBLE_DUPLICATE", "entityType": "entry", "entityIds": [row.id for row in rows], "date": iso(rows[0].entry_date), "label": rows[0].description})

        payroll_groups = {}
        payroll_rows = AccountingPayroll.query.order_by(AccountingPayroll.month, AccountingPayroll.id).all()
        for row in payroll_rows:
            deductions = row.social_insurance + row.income_tax + row.resident_tax + row.other_deductions
            if deductions > row.gross:
                issues.append({"severity": "error", "code": "DEDUCTIONS_EXCEED_GROSS", "entityType": "payroll", "entityIds": [row.id], "date": iso(row.pay_date), "label": row.month})
            payroll_groups.setdefault((row.employee_id, row.month), []).append(row)
        for rows in payroll_groups.values():
            if len(rows) > 1:
                issues.append({"severity": "error", "code": "DUPLICATE_PAYROLL_MONTH", "entityType": "payroll", "entityIds": [row.id for row in rows], "date": iso(rows[0].pay_date), "label": rows[0].month})
        errors = sum(issue["severity"] == "error" for issue in issues)
        return {
            "checkedAt": now().isoformat(), "lockedThrough": iso(locked_through()),
            "summary": {"errors": errors, "warnings": len(issues) - errors, "entries": len(entries), "payroll": len(payroll_rows)},
            "issues": issues,
        }

    def set_setting(key, value):
        row = db.session.get(AccountingSetting, key) or AccountingSetting(key=key)
        row.value = value
        row.updated_at = now()
        db.session.add(row)

    @api.get("/health")
    def health():
        return jsonify({"ok": True, "database": db.engine.dialect.name, "service": "mooon-accounting"})

    @api.get("/auth/session")
    def auth_session():
        return jsonify(user_dict(g.accounting_user))

    @api.get("/users")
    def list_users():
        rows = AccountingUser.query.order_by(AccountingUser.role, AccountingUser.email).all()
        return jsonify({"users": [user_dict(row) for row in rows]})

    @api.put("/users")
    def put_user():
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()[:320]
        role = str(data.get("role") or "viewer").strip().lower()
        if not email or "@" not in email or role not in ACCOUNTING_ROLES:
            return jsonify({"error": "INVALID_USER"}), 400
        row = db.session.get(AccountingUser, email)
        active = data.get("active", True)
        if not isinstance(active, bool):
            return jsonify({"error": "INVALID_USER"}), 400
        if row and row.role == "admin" and row.active and (role != "admin" or not active):
            other_admins = AccountingUser.query.filter(AccountingUser.role == "admin", AccountingUser.active.is_(True), AccountingUser.email != email).count()
            if not other_admins:
                return jsonify({"error": "LAST_ADMIN"}), 409
        created = row is None
        row = row or AccountingUser(email=email, created_by=actor())
        row.display_name = str(data.get("displayName") or row.display_name or "")[:250]
        row.role = role
        row.active = active
        row.updated_at = now()
        db.session.add(row)
        audit("create" if created else "update", "user", email, {"role": role, "active": row.active})
        db.session.commit()
        return jsonify(user_dict(row)), 201 if created else 200

    @api.delete("/users")
    def delete_user():
        email = str(request.args.get("email") or "").strip().lower()[:320]
        row = db.session.get(AccountingUser, email) if email else None
        if not row:
            return jsonify({"error": "NOT_FOUND"}), 404
        if row.role == "admin" and row.active:
            other_admins = AccountingUser.query.filter(AccountingUser.role == "admin", AccountingUser.active.is_(True), AccountingUser.email != email).count()
            if not other_admins:
                return jsonify({"error": "LAST_ADMIN"}), 409
        db.session.delete(row)
        audit("delete", "user", email, {"role": row.role})
        db.session.commit()
        return Response(status=204)

    @api.get("/state")
    def get_state():
        return jsonify(state_payload())

    @api.get("/checks")
    def get_correctness_checks():
        return jsonify(correctness_payload())

    @api.get("/controls")
    def get_accounting_controls():
        return jsonify({"lockedThrough": iso(locked_through())})

    @api.put("/controls")
    def put_accounting_controls():
        if g.accounting_user.role != "admin":
            return jsonify({"error": "ADMIN_REQUIRED"}), 403
        data = request.get_json(silent=True) or {}
        value = data.get("lockedThrough")
        try:
            lock_date = parse_date(value) if value else None
        except ValueError:
            return jsonify({"error": "INVALID_LOCK_DATE"}), 400
        previous = locked_through()
        if previous and (lock_date is None or lock_date < previous) and data.get("confirmation") != "REOPEN":
            return jsonify({"error": "REOPEN_CONFIRMATION_REQUIRED"}), 409
        if lock_date and (not previous or lock_date > previous):
            unresolved = [issue for issue in correctness_payload()["issues"] if issue.get("date") and issue["date"] <= iso(lock_date)]
            if unresolved:
                return jsonify({"error": "UNRESOLVED_CHECKS", "count": len(unresolved)}), 409
        set_setting("locked_through", iso(lock_date) or "")
        set_setting("updated_at", now().isoformat())
        audit("update", "accounting_controls", detail={"lockedThrough": iso(lock_date), "previous": iso(previous)})
        db.session.commit()
        return jsonify({"lockedThrough": iso(lock_date)})

    @api.put("/state")
    def put_state():
        data = request.get_json(silent=True) or {}
        try:
            incoming_entries = data.get("entries") if isinstance(data.get("entries"), list) else []
            incoming_employees = data.get("employees") if isinstance(data.get("employees"), list) else []
            incoming_payroll = data.get("payrollRecords") if isinstance(data.get("payrollRecords"), list) else []
            entry_ids = {upsert_entry(item).id for item in incoming_entries}
            employee_ids = {upsert_employee(item).id for item in incoming_employees}
            payroll_ids = {upsert_payroll(item).id for item in incoming_payroll}

            lock_date = locked_through()
            for row in AccountingPayroll.query.all():
                if row.id not in payroll_ids:
                    if lock_date and row.pay_date <= lock_date:
                        raise PermissionError(f"period is closed through {lock_date.isoformat()}")
                    db.session.delete(row)
            for row in AccountingEmployee.query.all():
                if row.id not in employee_ids and not AccountingDocument.query.filter_by(employee_id=row.id).first():
                    db.session.delete(row)
            for row in AccountingEntry.query.filter(AccountingEntry.source != "shop-db").all():
                if row.id not in entry_ids:
                    if lock_date and row.entry_date <= lock_date:
                        raise PermissionError(f"period is closed through {lock_date.isoformat()}")
                    db.session.delete(row)

            completed = {str(value)[:120] for value in data.get("completedProcedures", [])}
            for row in AccountingProcedure.query.all():
                if row.item_id not in completed:
                    row.completed = False
                    row.completed_at = None
                    row.updated_at = now()
            for item_id in completed:
                row = db.session.get(AccountingProcedure, item_id) or AccountingProcedure(item_id=item_id)
                if not row.completed:
                    row.completed_at = now()
                row.completed = True
                row.updated_at = now()
                db.session.add(row)

            profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
            set_setting("profile", json.dumps(profile, ensure_ascii=False, separators=(",", ":")))
            set_setting("initialized", "true")
            set_setting("updated_at", now().isoformat())
            audit("sync", "state", detail={"entries": len(entry_ids), "employees": len(employee_ids), "payroll": len(payroll_ids)})
            db.session.commit()
            return jsonify(state_payload())
        except PermissionError as error:
            db.session.rollback()
            return jsonify({"error": "PERIOD_CLOSED", "message": str(error), "lockedThrough": iso(locked_through())}), 409
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"error": "INVALID_STATE", "message": str(error)}), 400

    @api.post("/sales/sync")
    def sync_sales():
        grouped = shop_sales_by_day()
        expected_keys = {f"mooon-shop-day:{day}" for day in grouped}
        created = updated = removed_legacy = removed_duplicates = 0
        lock_date = locked_through()

        if lock_date:
            for row in AccountingEntry.query.filter_by(source="shop-db").all():
                if row.entry_date <= lock_date and row.import_key not in expected_keys:
                    return jsonify({"error": "PERIOD_CLOSED", "lockedThrough": iso(lock_date)}), 409
            for day, sales in grouped.items():
                entry_date = date.fromisoformat(day)
                if entry_date > lock_date:
                    continue
                payments = sales["paymentMethods"]
                payment = next(iter(payments)) if len(payments) == 1 else "複数決済"
                debit = "現金" if payments and payments <= {"现金", "現金"} else "普通預金" if payments and payments <= {"银行转账", "銀行振込"} else "未収入金"
                description = f"Mooon Shop 日次売上（{sales['salesCount']}会計・{sales['itemCount']}点）"
                row = AccountingEntry.query.filter_by(import_key=f"mooon-shop-day:{day}").first()
                if not row or (row.description, row.debit_account, row.credit_account, row.amount, row.payment) != (description, debit, "売上高", sales["amount"], payment):
                    return jsonify({"error": "PERIOD_CLOSED", "lockedThrough": iso(lock_date)}), 409

        for row in AccountingEntry.query.filter_by(source="shop-db").all():
            if row.import_key not in expected_keys:
                db.session.delete(row)
                removed_legacy += 1

        for day, sales in grouped.items():
            if lock_date and date.fromisoformat(day) <= lock_date:
                continue
            import_key = f"mooon-shop-day:{day}"
            row = AccountingEntry.query.filter_by(import_key=import_key).first()
            if row:
                updated += 1
            else:
                row = AccountingEntry(id=f"shop-day-{day}", import_key=import_key, created_by="sales-sync")
                created += 1
            payments = sales["paymentMethods"]
            payment = next(iter(payments)) if len(payments) == 1 else "複数決済"
            debit = "現金" if payments and payments <= {"现金", "現金"} else "普通預金" if payments and payments <= {"银行转账", "銀行振込"} else "未収入金"
            row.entry_date = date.fromisoformat(day)
            row.description = f"Mooon Shop 日次売上（{sales['salesCount']}会計・{sales['itemCount']}点）"
            row.source = "shop-db"
            row.debit_account = debit
            row.credit_account = "売上高"
            row.amount = sales["amount"]
            row.status = "done"
            row.payment = payment
            row.import_batch_id = "shop-db"
            row.import_file_name = "Mooon Shop PostgreSQL"
            row.imported_at = now()
            row.updated_at = now()
            row.version = (row.version or 0) + 1
            db.session.add(row)

        sale_dates = set(grouped)
        imported_shop_entries = AccountingEntry.query.filter(
            AccountingEntry.source == "shop",
            AccountingEntry.credit_account == "売上高",
            AccountingEntry.import_key.isnot(None),
        ).all()
        if lock_date and any(row.entry_date <= lock_date and iso(row.entry_date) in sale_dates for row in imported_shop_entries):
            db.session.rollback()
            return jsonify({"error": "PERIOD_CLOSED", "lockedThrough": iso(lock_date)}), 409
        for row in imported_shop_entries:
            if iso(row.entry_date) in sale_dates:
                db.session.delete(row)
                removed_duplicates += 1
        set_setting("updated_at", now().isoformat())
        audit("sync", "shop_sales", detail={
            "created": created, "updated": updated, "removedLegacy": removed_legacy,
            "removedDuplicates": removed_duplicates, "days": len(grouped),
        })
        db.session.commit()
        return jsonify({
            "created": created, "updated": updated, "removedLegacy": removed_legacy,
            "removedDuplicates": removed_duplicates, "state": state_payload(),
        })

    @api.get("/documents")
    def list_documents():
        category = request.args.get("category", "")
        query = AccountingDocument.query
        if category:
            query = query.filter_by(category=category)
        return jsonify({"documents": [document_dict(row) for row in query.order_by(AccountingDocument.created_at.desc()).all()]})

    @api.post("/documents")
    def upload_document():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"error": "FILE_REQUIRED"}), 400
        content = upload.read(MAX_DOCUMENT_BYTES + 1)
        if len(content) > MAX_DOCUMENT_BYTES:
            return jsonify({"error": "FILE_TOO_LARGE"}), 413
        mime_type = upload.mimetype or "application/octet-stream"
        if mime_type not in ALLOWED_DOCUMENT_TYPES:
            return jsonify({"error": "UNSUPPORTED_FILE"}), 415
        category = str(request.form.get("category") or "")[:40]
        if category not in {"year_end", "schedule"}:
            return jsonify({"error": "INVALID_CATEGORY"}), 400
        digest = hashlib.sha256(content).hexdigest()
        related_id = str(request.form.get("itemId") or "")[:120] or None
        existing = AccountingDocument.query.filter_by(category=category, sha256=digest, related_id=related_id).first()
        if existing:
            return jsonify(document_dict(existing))
        row = AccountingDocument(
            id=str(request.form.get("id") or f"doc-{uuid.uuid4()}")[:100], category=category,
            related_id=related_id, employee_id=str(request.form.get("employeeId") or "")[:80] or None,
            document_type=str(request.form.get("documentType") or "")[:200],
            file_name=upload.filename[:500], mime_type=mime_type, size=len(content),
            sha256=digest, content=content, created_by=actor(),
        )
        db.session.add(row)
        audit("create", "document", row.id, {"category": category, "fileName": row.file_name, "size": row.size})
        db.session.commit()
        return jsonify(document_dict(row)), 201

    @api.get("/documents/<document_id>")
    def download_document(document_id):
        row = db.session.get(AccountingDocument, document_id)
        if not row:
            return jsonify({"error": "NOT_FOUND"}), 404
        return send_file(
            __import__("io").BytesIO(row.content), mimetype=row.mime_type,
            as_attachment=True, download_name=row.file_name, max_age=0,
        )

    @api.delete("/documents/<document_id>")
    def delete_document(document_id):
        row = db.session.get(AccountingDocument, document_id)
        if not row:
            return jsonify({"error": "NOT_FOUND"}), 404
        detail = {"category": row.category, "fileName": row.file_name, "size": row.size}
        db.session.delete(row)
        audit("delete", "document", document_id, detail)
        db.session.commit()
        return Response(status=204)

    @api.get("/audit")
    def audit_log():
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
        query = AccountingAuditLog.query
        if request.args.get("action"):
            query = query.filter_by(action=str(request.args["action"])[:80])
        if request.args.get("entityType"):
            query = query.filter_by(entity_type=str(request.args["entityType"])[:80])
        if request.args.get("actor"):
            query = query.filter(AccountingAuditLog.actor.ilike(f"%{str(request.args['actor'])[:120]}%"))
        rows = query.order_by(AccountingAuditLog.created_at.desc()).limit(limit).all()
        return jsonify({"events": [audit_dict(row) for row in rows]})

    @api.get("/backup")
    def backup():
        content, summary = build_backup_archive()
        audit("export", "backup", detail=summary)
        db.session.commit()
        return send_file(
            io.BytesIO(content), mimetype="application/zip", as_attachment=True,
            download_name=f"shingetsu-ledger-full-{now().strftime('%Y%m%d-%H%M%S')}.zip", max_age=0,
        )

    @api.get("/backups")
    def list_backups():
        rows = AccountingBackup.query.order_by(AccountingBackup.created_at.desc()).limit(100).all()
        return jsonify({"backups": [backup_dict(row) for row in rows], "retentionDays": backup_retention_days()})

    @api.post("/backups")
    def make_backup():
        try:
            row = create_snapshot("manual")
            return jsonify(backup_dict(row)), 201
        except ValueError as error:
            db.session.rollback()
            return jsonify({"error": "BACKUP_FAILED", "message": str(error)}), 400

    @api.get("/backups/<backup_id>")
    def download_saved_backup(backup_id):
        row = db.session.get(AccountingBackup, backup_id)
        if not row:
            return jsonify({"error": "NOT_FOUND"}), 404
        audit("download", "backup", row.id, {"kind": row.kind, "size": row.size})
        db.session.commit()
        return send_file(io.BytesIO(row.content), mimetype="application/zip", as_attachment=True, download_name=row.file_name, max_age=0)

    @api.post("/backups/<backup_id>/restore")
    def restore_saved_backup(backup_id):
        row = db.session.get(AccountingBackup, backup_id)
        if not row:
            return jsonify({"error": "NOT_FOUND"}), 404
        try:
            state = restore_archive(bytes(row.content), backup_id)
            return jsonify({"restored": True, "state": state})
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"error": "RESTORE_FAILED", "message": str(error)}), 400

    @api.post("/restore")
    def restore_uploaded_backup():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"error": "FILE_REQUIRED"}), 400
        content = upload.read(MAX_BACKUP_BYTES + 1)
        if len(content) > MAX_BACKUP_BYTES:
            return jsonify({"error": "FILE_TOO_LARGE"}), 413
        try:
            state = restore_archive(content, upload.filename[:120])
            return jsonify({"restored": True, "state": state})
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"error": "RESTORE_FAILED", "message": str(error)}), 400

    app.register_blueprint(api)
    app.extensions["accounting_models"] = {
        "entry": AccountingEntry, "employee": AccountingEmployee,
        "payroll": AccountingPayroll, "procedure": AccountingProcedure,
        "document": AccountingDocument, "setting": AccountingSetting,
        "audit": AccountingAuditLog, "user": AccountingUser, "backup": AccountingBackup,
    }
    app.extensions["accounting_firebase_jwk_client"] = firebase_jwk_client
    return app.extensions["accounting_models"]
