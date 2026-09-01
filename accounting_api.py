"""Private accounting API backed by the inventory system database.

The browser never calls this API directly. The accounting site's server proxy
adds ACCOUNTING_API_TOKEN and forwards requests over HTTPS.
"""

import hashlib
import hmac
import json
import os
import uuid
from datetime import date, datetime

from flask import Blueprint, Response, jsonify, request, send_file
from sqlalchemy import UniqueConstraint


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
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

    api = Blueprint("accounting_api", __name__, url_prefix="/api/accounting")

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

    def actor():
        return (request.headers.get("X-Accounting-Actor") or "owner")[:200]

    def authorized():
        expected = os.environ.get("ACCOUNTING_API_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        if not expected or not supplied.startswith("Bearer "):
            return False
        return hmac.compare_digest(supplied[7:], expected)

    @api.before_request
    def require_token():
        if not authorized():
            return jsonify({"error": "UNAUTHORIZED"}), 401

    def audit(action, entity_type, entity_id=None, detail=None):
        safe_detail = detail if isinstance(detail, dict) else {}
        db.session.add(AccountingAuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id)[:120] if entity_id is not None else None,
            actor=actor(),
            detail=json.dumps(safe_detail, ensure_ascii=False, separators=(",", ":")),
        ))

    def entry_dict(row):
        return {
            "id": row.id, "date": iso(row.entry_date), "description": row.description,
            "source": row.source, "debit": row.debit_account, "credit": row.credit_account,
            "amount": row.amount, "status": row.status, "payment": row.payment,
            "importKey": row.import_key, "importBatchId": row.import_batch_id,
            "importFileName": row.import_file_name, "importedAt": iso(row.imported_at),
            "version": row.version,
        }

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

    def upsert_entry(data):
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
        if not row.description or not row.debit_account or not row.credit_account or row.amount <= 0:
            raise ValueError("entry fields are incomplete")
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
        return {
            "initialized": settings.get("initialized") == "true",
            "entries": [entry_dict(row) for row in AccountingEntry.query.order_by(AccountingEntry.entry_date).all()],
            "employees": [employee_dict(row) for row in AccountingEmployee.query.order_by(AccountingEmployee.created_at).all()],
            "payrollRecords": [payroll_dict(row) for row in AccountingPayroll.query.order_by(AccountingPayroll.month).all()],
            "completedProcedures": [row.item_id for row in AccountingProcedure.query.filter_by(completed=True).all()],
            "profile": json.loads(settings.get("profile", "{}")),
            "updatedAt": settings.get("updated_at"),
        }

    def set_setting(key, value):
        row = db.session.get(AccountingSetting, key) or AccountingSetting(key=key)
        row.value = value
        row.updated_at = now()
        db.session.add(row)

    @api.get("/health")
    def health():
        return jsonify({"ok": True, "database": db.engine.dialect.name, "service": "mooon-accounting"})

    @api.get("/state")
    def get_state():
        return jsonify(state_payload())

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

            for row in AccountingPayroll.query.all():
                if row.id not in payroll_ids:
                    db.session.delete(row)
            for row in AccountingEmployee.query.all():
                if row.id not in employee_ids and not AccountingDocument.query.filter_by(employee_id=row.id).first():
                    db.session.delete(row)
            for row in AccountingEntry.query.filter(AccountingEntry.source != "shop-db").all():
                if row.id not in entry_ids:
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
        except (ValueError, TypeError) as error:
            db.session.rollback()
            return jsonify({"error": "INVALID_STATE", "message": str(error)}), 400

    @api.post("/sales/sync")
    def sync_sales():
        created = 0
        for sale in Sale.query.order_by(Sale.id).all():
            import_key = f"mooon-shop-sale:{sale.id}"
            if AccountingEntry.query.filter_by(import_key=import_key).first():
                continue
            payment = sale.payment_method or "未记录"
            debit = "現金" if payment in {"现金", "現金"} else "普通預金" if payment in {"银行转账", "銀行振込"} else "未収入金"
            names = "、".join(item.name for item in sale.items[:3])
            if len(sale.items) > 3:
                names += f" 等{len(sale.items)}点"
            row = AccountingEntry(
                id=f"shop-sale-{sale.id}", entry_date=sale.created_at.date(),
                description=names or f"Mooon Shop 売上 #{sale.id}", source="shop-db",
                debit_account=debit, credit_account="売上高", amount=integer(sale.payable),
                status="done", payment=payment, import_key=import_key,
                import_batch_id=f"shop-db-{sale.created_at.date().isoformat()}",
                import_file_name="Mooon Shop PostgreSQL", imported_at=now(), created_by="sales-sync",
            )
            db.session.add(row)
            created += 1
        set_setting("updated_at", now().isoformat())
        audit("sync", "shop_sales", detail={"created": created})
        db.session.commit()
        return jsonify({"created": created, "state": state_payload()})

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
        rows = AccountingAuditLog.query.order_by(AccountingAuditLog.created_at.desc()).limit(limit).all()
        return jsonify({"events": [{
            "id": row.id, "action": row.action, "entityType": row.entity_type,
            "entityId": row.entity_id, "actor": row.actor,
            "detail": json.loads(row.detail or "{}"), "createdAt": iso(row.created_at),
        } for row in rows]})

    @api.get("/backup")
    def backup():
        payload = state_payload()
        payload["documents"] = [document_dict(row) for row in AccountingDocument.query.order_by(AccountingDocument.created_at).all()]
        payload["exportedAt"] = now().isoformat()
        audit("export", "backup", detail={"documents": len(payload["documents"])})
        db.session.commit()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(body, mimetype="application/json", headers={
            "Content-Disposition": f'attachment; filename="shingetsu-backup-{now().date().isoformat()}.json"'
        })

    app.register_blueprint(api)
    app.extensions["accounting_models"] = {
        "entry": AccountingEntry, "employee": AccountingEmployee,
        "payroll": AccountingPayroll, "procedure": AccountingProcedure,
        "document": AccountingDocument, "setting": AccountingSetting,
        "audit": AccountingAuditLog,
    }
    return app.extensions["accounting_models"]
