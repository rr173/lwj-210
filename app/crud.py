from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import copy

from app import models, schemas
from app.audit_engine import AuditEngine
from app.models import (
    AMENDMENT_STATUS_PENDING,
    AMENDMENT_STATUS_ACCEPTED,
    AMENDMENT_STATUS_REJECTED,
    AMENDMENT_STATUS_EXPIRED,
    AMENDMENT_EXPIRY_DAYS,
    AMENDABLE_FIELDS,
    MAX_FIELDS_PER_AMENDMENT,
    FEE_RULES,
    FEE_TYPE_FIRST_SUBMISSION,
    FEE_TYPE_RESUBMISSION,
    FEE_STATUS_CONFIRMED,
    FEE_STATUS_PENDING,
    VALID_FEE_TIERS,
    FEE_TIER_STANDARD,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_IN_REVIEW,
    REVIEW_STATUS_REVIEWED,
    REVIEW_ACTION_CONFIRM,
    REVIEW_ACTION_OVERRULE,
    REVIEW_ACTION_ADD_DISCREPANCY,
    REVIEW_ACTION_REMOVE_DISCREPANCY,
    DISCREPANCY_ACTION_MANUAL,
    CLAIM_TIMEOUT_HOURS,
)


def create_letter_of_credit(db: Session, lc_data: schemas.LetterOfCreditCreate) -> models.LetterOfCredit:
    fee_tier_value = lc_data.fee_tier.value if hasattr(lc_data.fee_tier, 'value') else lc_data.fee_tier
    if fee_tier_value not in VALID_FEE_TIERS:
        raise ValueError(f"无效的费率档位: {fee_tier_value}，允许的值: {', '.join(VALID_FEE_TIERS)}")

    db_lc = models.LetterOfCredit(
        lc_number=lc_data.lc_number,
        issuing_bank=lc_data.issuing_bank,
        beneficiary_name=lc_data.beneficiary_name,
        applicant_name=lc_data.applicant_name,
        currency=lc_data.currency.value,
        amount=lc_data.amount,
        latest_shipment_date=lc_data.latest_shipment_date,
        latest_presentation_date=lc_data.latest_presentation_date,
        expiry_date=lc_data.expiry_date,
        transport_mode=lc_data.transport_mode.value,
        port_of_loading=lc_data.port_of_loading,
        port_of_discharge=lc_data.port_of_discharge,
        partial_shipment_allowed=lc_data.partial_shipment_allowed,
        transshipment_allowed=lc_data.transshipment_allowed,
        goods_description=lc_data.goods_description,
        additional_terms=lc_data.additional_terms,
        fee_tier=fee_tier_value
    )
    db.add(db_lc)
    db.flush()

    for req in lc_data.document_requirements:
        db_req = models.DocumentRequirement(
            lc_id=db_lc.id,
            document_type=req.document_type,
            original_copies=req.original_copies,
            copy_copies=req.copy_copies
        )
        db.add(db_req)

    db.commit()
    db.refresh(db_lc)
    return db_lc


def get_letter_of_credit_by_number(db: Session, lc_number: str) -> Optional[models.LetterOfCredit]:
    return db.query(models.LetterOfCredit).filter(models.LetterOfCredit.lc_number == lc_number).first()


def get_letter_of_credit_by_id(db: Session, lc_id: int) -> Optional[models.LetterOfCredit]:
    return db.query(models.LetterOfCredit).filter(models.LetterOfCredit.id == lc_id).first()


def get_all_letter_of_credits(db: Session, skip: int = 0, limit: int = 100) -> List[models.LetterOfCredit]:
    return db.query(models.LetterOfCredit).offset(skip).limit(limit).all()


def update_letter_of_credit(db: Session, lc_id: int, lc_data: schemas.LetterOfCreditCreate) -> Optional[models.LetterOfCredit]:
    db_lc = get_letter_of_credit_by_id(db, lc_id)
    if not db_lc:
        return None

    new_fee_tier = lc_data.fee_tier.value if hasattr(lc_data.fee_tier, 'value') else lc_data.fee_tier
    if new_fee_tier != db_lc.fee_tier:
        raise ValueError(f"费率档位创建后不可修改，当前档位: {db_lc.fee_tier}，提交的档位: {new_fee_tier}")

    db_lc.lc_number = lc_data.lc_number
    db_lc.issuing_bank = lc_data.issuing_bank
    db_lc.beneficiary_name = lc_data.beneficiary_name
    db_lc.applicant_name = lc_data.applicant_name
    db_lc.currency = lc_data.currency.value
    db_lc.amount = lc_data.amount
    db_lc.latest_shipment_date = lc_data.latest_shipment_date
    db_lc.latest_presentation_date = lc_data.latest_presentation_date
    db_lc.expiry_date = lc_data.expiry_date
    db_lc.transport_mode = lc_data.transport_mode.value
    db_lc.port_of_loading = lc_data.port_of_loading
    db_lc.port_of_discharge = lc_data.port_of_discharge
    db_lc.partial_shipment_allowed = lc_data.partial_shipment_allowed
    db_lc.transshipment_allowed = lc_data.transshipment_allowed
    db_lc.goods_description = lc_data.goods_description
    db_lc.additional_terms = lc_data.additional_terms

    db.query(models.DocumentRequirement).filter(models.DocumentRequirement.lc_id == lc_id).delete()
    for req in lc_data.document_requirements:
        db_req = models.DocumentRequirement(
            lc_id=db_lc.id,
            document_type=req.document_type,
            original_copies=req.original_copies,
            copy_copies=req.copy_copies
        )
        db.add(db_req)

    db.commit()
    db.refresh(db_lc)
    return db_lc


def delete_letter_of_credit(db: Session, lc_id: int) -> bool:
    db_lc = get_letter_of_credit_by_id(db, lc_id)
    if not db_lc:
        return False
    db.delete(db_lc)
    db.commit()
    return True


def get_latest_audit_by_lc(db: Session, lc_id: int) -> Optional[models.AuditRecord]:
    return db.query(models.AuditRecord).filter(
        models.AuditRecord.lc_id == lc_id
    ).order_by(models.AuditRecord.created_at.desc()).first()


def generate_fee_number(db: Session, lc_number: str) -> str:
    from sqlalchemy import func
    date_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"FEE-{lc_number}-{date_str}-"
    count = db.query(func.count(models.FeeRecord.id)).filter(
        models.FeeRecord.fee_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def calculate_fee(fee_tier: str, fee_type: str, document_count: int) -> Dict[str, Any]:
    if fee_tier not in FEE_RULES:
        raise ValueError(f"无效的费率档位: {fee_tier}")
    rules = FEE_RULES[fee_tier]

    if fee_type == FEE_TYPE_FIRST_SUBMISSION:
        base_fee = rules["first_submission_base"]
        per_doc_fee = rules["first_submission_per_doc"]
        document_fee_total = per_doc_fee * document_count
        total_amount = base_fee + document_fee_total
    elif fee_type == FEE_TYPE_RESUBMISSION:
        base_fee = rules["resubmission_fixed"]
        per_doc_fee = 0
        document_fee_total = 0
        total_amount = base_fee
    else:
        raise ValueError(f"无效的费用类型: {fee_type}")

    return {
        "base_fee": float(base_fee),
        "per_doc_fee": float(per_doc_fee),
        "document_count": document_count,
        "document_fee_total": float(document_fee_total),
        "total_amount": float(total_amount),
    }


def determine_fee_status(conclusion: str) -> str:
    if conclusion == "compliant" or conclusion == "minor_discrepancy":
        return FEE_STATUS_CONFIRMED
    else:
        return FEE_STATUS_PENDING


def create_fee_record(
    db: Session,
    lc: models.LetterOfCredit,
    audit_record: models.AuditRecord,
    fee_type: str,
    document_count: int,
) -> models.FeeRecord:
    fee_details = calculate_fee(lc.fee_tier, fee_type, document_count)
    fee_status = determine_fee_status(audit_record.conclusion)
    fee_number = generate_fee_number(db, lc.lc_number)

    fee_record = models.FeeRecord(
        fee_number=fee_number,
        lc_id=lc.id,
        submission_id=audit_record.submission_id,
        audit_record_id=audit_record.id,
        fee_type=fee_type,
        fee_tier=lc.fee_tier,
        base_fee=fee_details["base_fee"],
        per_doc_fee=fee_details["per_doc_fee"],
        document_count=fee_details["document_count"],
        document_fee_total=fee_details["document_fee_total"],
        total_amount=fee_details["total_amount"],
        status=fee_status,
    )
    db.add(fee_record)
    db.flush()
    return fee_record


def migrate_existing_audit_records(db: Session) -> int:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    migrated = 0
    try:
        columns_added_audit = False
        try:
            db.execute(text("SELECT review_status FROM audit_records LIMIT 1"))
        except OperationalError:
            db.execute(text("ALTER TABLE audit_records ADD COLUMN review_status VARCHAR(20)"))
            db.execute(text("ALTER TABLE audit_records ADD COLUMN auto_conclusion VARCHAR(50)"))
            db.execute(text("ALTER TABLE audit_records ADD COLUMN final_conclusion VARCHAR(50)"))
            db.commit()
            migrated += 3
            columns_added_audit = True

        columns_added_disc = False
        try:
            db.execute(text("SELECT source FROM discrepancies LIMIT 1"))
        except OperationalError:
            db.execute(text("ALTER TABLE discrepancies ADD COLUMN source VARCHAR(20)"))
            db.execute(text("ALTER TABLE discrepancies ADD COLUMN is_removed BOOLEAN"))
            db.execute(text("ALTER TABLE discrepancies ADD COLUMN removal_reason TEXT"))
            db.commit()
            migrated += 3
            columns_added_disc = True

        tables_created = False
        try:
            db.execute(text("SELECT 1 FROM reviewers LIMIT 1"))
        except OperationalError:
            conn = db.connection()
            models.Reviewer.__table__.create(bind=conn)
            models.ReviewAssignment.__table__.create(bind=conn)
            models.ReviewOpinion.__table__.create(bind=conn)
            db.commit()
            migrated += 3
            tables_created = True

        needs_update = False
        all_audits = db.query(models.AuditRecord).all()
        for record in all_audits:
            updated = False
            if not record.review_status:
                record.review_status = REVIEW_STATUS_PENDING
                updated = True
            if not record.auto_conclusion:
                record.auto_conclusion = record.conclusion
                updated = True
            if updated:
                migrated += 1
                needs_update = True

        all_discs = db.query(models.Discrepancy).all()
        for disc in all_discs:
            updated = False
            if not disc.source:
                disc.source = "auto"
                updated = True
            if disc.is_removed is None:
                disc.is_removed = False
                updated = True
            if updated:
                migrated += 1
                needs_update = True

        if needs_update:
            db.commit()
    except Exception as e:
        db.rollback()
    return migrated


def submit_documents_and_audit(db: Session, submission: schemas.SubmissionSubmit):
    lc = get_letter_of_credit_by_number(db, submission.lc_number)
    if not lc:
        raise ValueError(f"信用证 {submission.lc_number} 不存在")

    existing_submission = db.query(models.AuditRecord).filter(
        models.AuditRecord.submission_id == submission.submission_id
    ).first()
    if existing_submission:
        raise ValueError(f"提交编号 {submission.submission_id} 已存在")

    latest_audit = get_latest_audit_by_lc(db, lc.id)
    if latest_audit:
        if latest_audit.conclusion == "discrepant" and latest_audit.resubmission_round < MAX_RESUBMISSION_ROUNDS:
            raise ValueError(
                f"信用证 {submission.lc_number} 已有一笔不符交单 (提交编号: {latest_audit.submission_id}) 等待修改，"
                f"请使用修改重提接口 /api/submission/{latest_audit.submission_id}/resubmit 提交修改后的单据，"
                f"或先完成当前交单的全部修改后再提交新交单"
            )

    documents = []
    for doc_data in submission.documents:
        db_doc = models.Document(
            lc_id=lc.id,
            submission_id=submission.submission_id,
            original_submission_id=submission.submission_id,
            resubmission_round=0,
            document_type=doc_data.document_type,
            original_copies_submitted=doc_data.original_copies_submitted,
            copy_copies_submitted=doc_data.copy_copies_submitted,
            content=doc_data.content
        )
        db.add(db_doc)
        documents.append(db_doc)

    db.flush()

    engine = AuditEngine(lc, documents, submission.presentation_date)
    conclusion, discrepancies = engine.run_audit()

    critical_count = sum(1 for d in discrepancies if d["severity"] == "critical")
    minor_count = sum(1 for d in discrepancies if d["severity"] == "minor")

    audit_record = models.AuditRecord(
        lc_id=lc.id,
        submission_id=submission.submission_id,
        original_submission_id=submission.submission_id,
        resubmission_round=0,
        modification_remark=None,
        conclusion=conclusion,
        auto_conclusion=conclusion,
        final_conclusion=None,
        total_discrepancies=len(discrepancies),
        critical_count=critical_count,
        minor_count=minor_count,
        presentation_date=submission.presentation_date,
        review_status=REVIEW_STATUS_PENDING
    )
    db.add(audit_record)
    db.flush()

    for disc in discrepancies:
        db_disc = models.Discrepancy(
            audit_record_id=audit_record.id,
            discrepancy_type=disc["discrepancy_type"],
            severity=disc["severity"],
            document_type=disc["document_type"],
            description=disc["description"],
            lc_clause_reference=disc["lc_clause_reference"]
        )
        db.add(db_disc)

    create_fee_record(db, lc, audit_record, FEE_TYPE_FIRST_SUBMISSION, len(documents))

    db.commit()
    db.refresh(audit_record)
    return audit_record


def get_audit_records_by_lc(db: Session, lc_number: str) -> List[models.AuditRecord]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.AuditRecord).filter(models.AuditRecord.lc_id == lc.id).order_by(models.AuditRecord.created_at.desc()).all()


def get_audit_record_by_submission(db: Session, submission_id: str) -> Optional[models.AuditRecord]:
    return db.query(models.AuditRecord).filter(models.AuditRecord.submission_id == submission_id).first()


def get_documents_by_submission(db: Session, submission_id: str) -> List[models.Document]:
    return db.query(models.Document).filter(models.Document.submission_id == submission_id).all()


def get_audit_records_by_original_submission(db: Session, original_submission_id: str) -> List[models.AuditRecord]:
    return db.query(models.AuditRecord).filter(
        models.AuditRecord.original_submission_id == original_submission_id
    ).order_by(models.AuditRecord.resubmission_round.asc()).all()


def get_latest_audit_record_by_original_submission(db: Session, original_submission_id: str) -> Optional[models.AuditRecord]:
    return db.query(models.AuditRecord).filter(
        models.AuditRecord.original_submission_id == original_submission_id
    ).order_by(models.AuditRecord.resubmission_round.desc()).first()


MAX_RESUBMISSION_ROUNDS = 3


def resubmit_documents_and_audit(db: Session, original_submission_id: str, resubmit: schemas.SubmissionResubmitRequest):
    latest_record = get_latest_audit_record_by_original_submission(db, original_submission_id)
    if not latest_record:
        raise ValueError(f"交单编号 {original_submission_id} 不存在")

    if latest_record.conclusion != "discrepant":
        raise ValueError(
            f"当前交单结论为 '{latest_record.conclusion}'，只有结论为 discrepant 的交单才允许修改重提"
        )

    if latest_record.resubmission_round >= MAX_RESUBMISSION_ROUNDS:
        raise ValueError(
            f"交单 {original_submission_id} 已修改重提 {MAX_RESUBMISSION_ROUNDS} 次，达到上限，不再允许修改"
        )

    new_round = latest_record.resubmission_round + 1

    existing_new_submission = db.query(models.AuditRecord).filter(
        models.AuditRecord.submission_id == resubmit.new_submission_id
    ).first()
    if existing_new_submission:
        raise ValueError(f"提交编号 {resubmit.new_submission_id} 已存在")

    lc = get_letter_of_credit_by_id(db, latest_record.lc_id)
    if not lc:
        raise ValueError("关联信用证不存在")

    documents = []
    for doc_data in resubmit.documents:
        db_doc = models.Document(
            lc_id=lc.id,
            submission_id=resubmit.new_submission_id,
            original_submission_id=original_submission_id,
            resubmission_round=new_round,
            document_type=doc_data.document_type,
            original_copies_submitted=doc_data.original_copies_submitted,
            copy_copies_submitted=doc_data.copy_copies_submitted,
            content=doc_data.content
        )
        db.add(db_doc)
        documents.append(db_doc)

    db.flush()

    engine = AuditEngine(lc, documents, resubmit.presentation_date)
    conclusion, discrepancies = engine.run_audit()

    critical_count = sum(1 for d in discrepancies if d["severity"] == "critical")
    minor_count = sum(1 for d in discrepancies if d["severity"] == "minor")

    audit_record = models.AuditRecord(
        lc_id=lc.id,
        submission_id=resubmit.new_submission_id,
        original_submission_id=original_submission_id,
        resubmission_round=new_round,
        modification_remark=resubmit.modification_remark,
        conclusion=conclusion,
        auto_conclusion=conclusion,
        final_conclusion=None,
        total_discrepancies=len(discrepancies),
        critical_count=critical_count,
        minor_count=minor_count,
        presentation_date=resubmit.presentation_date,
        review_status=REVIEW_STATUS_PENDING
    )
    db.add(audit_record)
    db.flush()

    for disc in discrepancies:
        db_disc = models.Discrepancy(
            audit_record_id=audit_record.id,
            discrepancy_type=disc["discrepancy_type"],
            severity=disc["severity"],
            document_type=disc["document_type"],
            description=disc["description"],
            lc_clause_reference=disc["lc_clause_reference"]
        )
        db.add(db_disc)

    create_fee_record(db, lc, audit_record, FEE_TYPE_RESUBMISSION, len(documents))

    db.commit()
    db.refresh(audit_record)
    return audit_record


def get_discrepancy_statistics(db: Session) -> List[dict]:
    from sqlalchemy import func
    results = db.query(
        models.Discrepancy.discrepancy_type,
        func.count(models.Discrepancy.id).label("count")
    ).group_by(models.Discrepancy.discrepancy_type).all()
    return [{"discrepancy_type": r[0], "count": r[1]} for r in results]


def get_beneficiary_discrepancy_rate(db: Session, beneficiary_name: str) -> dict:
    from sqlalchemy import func
    lc_ids = db.query(models.LetterOfCredit.id).filter(
        models.LetterOfCredit.beneficiary_name == beneficiary_name
    ).all()
    lc_ids = [id[0] for id in lc_ids]

    if not lc_ids:
        return {
            "beneficiary_name": beneficiary_name,
            "total_audits": 0,
            "total_discrepancies": 0,
            "discrepancy_rate": 0.0
        }

    total_audits = db.query(func.count(models.AuditRecord.id)).filter(
        models.AuditRecord.lc_id.in_(lc_ids)
    ).scalar()

    audit_ids = db.query(models.AuditRecord.id).filter(
        models.AuditRecord.lc_id.in_(lc_ids)
    ).all()
    audit_ids = [id[0] for id in audit_ids]

    total_discrepancies = db.query(func.count(models.Discrepancy.id)).filter(
        models.Discrepancy.audit_record_id.in_(audit_ids)
    ).scalar() if audit_ids else 0

    rate = (total_discrepancies / total_audits) if total_audits > 0 else 0.0

    return {
        "beneficiary_name": beneficiary_name,
        "total_audits": total_audits,
        "total_discrepancies": total_discrepancies,
        "discrepancy_rate": round(rate, 4)
    }


def get_all_audit_records(db: Session, skip: int = 0, limit: int = 100) -> List[models.AuditRecord]:
    return db.query(models.AuditRecord).order_by(models.AuditRecord.created_at.desc()).offset(skip).limit(limit).all()


def lc_to_snapshot_dict(lc: models.LetterOfCredit) -> Dict[str, Any]:
    return {
        "id": lc.id,
        "lc_number": lc.lc_number,
        "issuing_bank": lc.issuing_bank,
        "beneficiary_name": lc.beneficiary_name,
        "applicant_name": lc.applicant_name,
        "currency": lc.currency,
        "amount": lc.amount,
        "latest_shipment_date": lc.latest_shipment_date.isoformat() if lc.latest_shipment_date else None,
        "latest_presentation_date": lc.latest_presentation_date.isoformat() if lc.latest_presentation_date else None,
        "expiry_date": lc.expiry_date.isoformat() if lc.expiry_date else None,
        "transport_mode": lc.transport_mode,
        "port_of_loading": lc.port_of_loading,
        "port_of_discharge": lc.port_of_discharge,
        "partial_shipment_allowed": lc.partial_shipment_allowed,
        "transshipment_allowed": lc.transshipment_allowed,
        "goods_description": lc.goods_description,
        "additional_terms": copy.deepcopy(lc.additional_terms) if lc.additional_terms else [],
        "created_at": lc.created_at.isoformat() if lc.created_at else None
    }


def has_pending_amendment(db: Session, lc_id: int) -> bool:
    pending = db.query(models.LCAmendment).filter(
        models.LCAmendment.lc_id == lc_id,
        models.LCAmendment.status == AMENDMENT_STATUS_PENDING
    ).first()
    return pending is not None


def get_next_amendment_sequence(db: Session, lc_id: int) -> int:
    from sqlalchemy import func
    max_seq = db.query(func.max(models.LCAmendment.sequence_number)).filter(
        models.LCAmendment.lc_id == lc_id
    ).scalar()
    return (max_seq or 0) + 1


def _get_field_actual_value(lc: models.LetterOfCredit, field_name: str) -> Any:
    if field_name == "amount":
        return lc.amount
    elif field_name == "latest_shipment_date":
        return lc.latest_shipment_date
    elif field_name == "latest_presentation_date":
        return lc.latest_presentation_date
    elif field_name == "expiry_date":
        return lc.expiry_date
    elif field_name == "port_of_loading":
        return lc.port_of_loading
    elif field_name == "port_of_discharge":
        return lc.port_of_discharge
    elif field_name == "partial_shipment_allowed":
        return lc.partial_shipment_allowed
    elif field_name == "transshipment_allowed":
        return lc.transshipment_allowed
    elif field_name == "goods_description":
        return lc.goods_description
    elif field_name == "additional_terms":
        return lc.additional_terms
    return None


def _values_match(field_name: str, submitted_old: Any, actual: Any) -> bool:
    if submitted_old is None:
        return False

    if field_name in ["latest_shipment_date", "latest_presentation_date", "expiry_date"]:
        if isinstance(submitted_old, str) and isinstance(actual, date):
            try:
                submitted_date = date.fromisoformat(submitted_old)
                return submitted_date == actual
            except (ValueError, TypeError):
                return False
        return submitted_old == actual

    if field_name == "amount":
        try:
            return abs(float(submitted_old) - float(actual)) < 0.01
        except (ValueError, TypeError):
            return False

    if field_name == "additional_terms":
        if isinstance(submitted_old, list) and isinstance(actual, list):
            return submitted_old == actual
        return False

    if field_name in ["partial_shipment_allowed", "transshipment_allowed"]:
        return bool(submitted_old) == bool(actual)

    return str(submitted_old).strip() == str(actual).strip()


def _format_value(field_name: str, value: Any) -> str:
    if field_name in ["latest_shipment_date", "latest_presentation_date", "expiry_date"]:
        if isinstance(value, date):
            return value.isoformat()
        return str(value)
    if field_name == "amount":
        return f"{value:.2f}"
    if field_name == "additional_terms":
        return str(value)
    return str(value)


def validate_field_changes(field_changes: List[Dict[str, Any]], lc: models.LetterOfCredit) -> None:
    if len(field_changes) > MAX_FIELDS_PER_AMENDMENT:
        raise ValueError(f"每次修改最多允许修改 {MAX_FIELDS_PER_AMENDMENT} 个字段，当前提交了 {len(field_changes)} 个")

    if len(field_changes) == 0:
        raise ValueError("修改内容不能为空")

    field_names = set()
    for change in field_changes:
        field_name = change.get("field_name")
        if not field_name:
            raise ValueError("每个字段变更必须指定 field_name")
        if field_name not in AMENDABLE_FIELDS:
            raise ValueError(f"字段 '{field_name}' 不允许修改，允许修改的字段: {', '.join(AMENDABLE_FIELDS)}")
        if field_name in field_names:
            raise ValueError(f"字段 '{field_name}' 在修改列表中重复出现")
        field_names.add(field_name)

        old_value = change.get("old_value")
        new_value = change.get("new_value")

        if old_value is None:
            raise ValueError(f"字段 '{field_name}' 必须提供旧值 old_value")

        actual_value = _get_field_actual_value(lc, field_name)
        if not _values_match(field_name, old_value, actual_value):
            raise ValueError(
                f"字段 '{field_name}' 的旧值与实际值不匹配。"
                f"提交的旧值: {_format_value(field_name, old_value)}，"
                f"实际值: {_format_value(field_name, actual_value)}"
            )

        if field_name == "amount":
            if not isinstance(new_value, (int, float)):
                raise ValueError(f"字段 'amount' 的新值必须是数字类型")
            if float(new_value) <= 0:
                raise ValueError(f"字段 'amount' 的值必须大于 0")

        if field_name in ["latest_shipment_date", "latest_presentation_date", "expiry_date"]:
            if not new_value:
                raise ValueError(f"字段 '{field_name}' 的新值不能为空")
            try:
                if isinstance(new_value, str):
                    date.fromisoformat(new_value)
                elif not isinstance(new_value, date):
                    raise ValueError("日期格式不正确")
            except (ValueError, TypeError):
                raise ValueError(f"字段 '{field_name}' 的日期格式不正确，应为 YYYY-MM-DD 格式")


def create_amendment(db: Session, amendment_data: schemas.AmendmentCreate) -> models.LCAmendment:
    lc = get_letter_of_credit_by_number(db, amendment_data.lc_number)
    if not lc:
        raise ValueError(f"信用证 {amendment_data.lc_number} 不存在")

    check_and_expire_amendments(db, lc.id)

    if has_pending_amendment(db, lc.id):
        raise ValueError(f"信用证 {amendment_data.lc_number} 已有一个待处理的修改，请先处理后再发起新修改")

    field_changes_dict = [change.model_dump() for change in amendment_data.field_changes]
    validate_field_changes(field_changes_dict, lc)

    snapshot_before = lc_to_snapshot_dict(lc)

    sequence_number = get_next_amendment_sequence(db, lc.id)
    amendment_number = f"{lc.lc_number}-AMD-{sequence_number:03d}"

    expiry_time = datetime.utcnow() + timedelta(days=AMENDMENT_EXPIRY_DAYS)

    amendment = models.LCAmendment(
        lc_id=lc.id,
        amendment_number=amendment_number,
        sequence_number=sequence_number,
        status=AMENDMENT_STATUS_PENDING,
        field_changes=field_changes_dict,
        snapshot_before=snapshot_before,
        snapshot_after=None,
        expiry_time=expiry_time
    )

    db.add(amendment)
    db.commit()
    db.refresh(amendment)
    return amendment


def get_amendment_by_number(db: Session, amendment_number: str) -> Optional[models.LCAmendment]:
    return db.query(models.LCAmendment).filter(models.LCAmendment.amendment_number == amendment_number).first()


def get_amendments_by_lc(db: Session, lc_number: str) -> List[models.LCAmendment]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.LCAmendment).filter(
        models.LCAmendment.lc_id == lc.id
    ).order_by(models.LCAmendment.sequence_number.desc()).all()


def apply_amendment_to_lc(db: Session, lc: models.LetterOfCredit, field_changes: List[Dict[str, Any]]) -> None:
    for change in field_changes:
        field_name = change["field_name"]
        new_value = change["new_value"]

        if field_name == "amount":
            lc.amount = float(new_value)
        elif field_name == "latest_shipment_date":
            if isinstance(new_value, str):
                lc.latest_shipment_date = date.fromisoformat(new_value)
            else:
                lc.latest_shipment_date = new_value
        elif field_name == "latest_presentation_date":
            if isinstance(new_value, str):
                lc.latest_presentation_date = date.fromisoformat(new_value)
            else:
                lc.latest_presentation_date = new_value
        elif field_name == "expiry_date":
            if isinstance(new_value, str):
                lc.expiry_date = date.fromisoformat(new_value)
            else:
                lc.expiry_date = new_value
        elif field_name == "port_of_loading":
            lc.port_of_loading = str(new_value)
        elif field_name == "port_of_discharge":
            lc.port_of_discharge = str(new_value)
        elif field_name == "partial_shipment_allowed":
            lc.partial_shipment_allowed = bool(new_value)
        elif field_name == "transshipment_allowed":
            lc.transshipment_allowed = bool(new_value)
        elif field_name == "goods_description":
            lc.goods_description = str(new_value)
        elif field_name == "additional_terms":
            lc.additional_terms = list(new_value) if new_value else []


def re_audit_pending_submissions(db: Session, lc_id: int) -> List[models.AuditRecord]:
    audit_records = db.query(models.AuditRecord).filter(
        models.AuditRecord.lc_id == lc_id,
        models.AuditRecord.conclusion == "discrepant"
    ).all()

    re_audited = []
    for record in audit_records:
        documents = get_documents_by_submission(db, record.submission_id)
        if not documents:
            continue

        lc = get_letter_of_credit_by_id(db, lc_id)
        if not lc:
            continue

        engine = AuditEngine(lc, documents, record.presentation_date)
        conclusion, discrepancies = engine.run_audit()

        critical_count = sum(1 for d in discrepancies if d["severity"] == "critical")
        minor_count = sum(1 for d in discrepancies if d["severity"] == "minor")

        record.conclusion = conclusion
        record.total_discrepancies = len(discrepancies)
        record.critical_count = critical_count
        record.minor_count = minor_count

        db.query(models.Discrepancy).filter(
            models.Discrepancy.audit_record_id == record.id
        ).delete()

        for disc in discrepancies:
            db_disc = models.Discrepancy(
                audit_record_id=record.id,
                discrepancy_type=disc["discrepancy_type"],
                severity=disc["severity"],
                document_type=disc["document_type"],
                description=disc["description"],
                lc_clause_reference=disc["lc_clause_reference"]
            )
            db.add(db_disc)

        fee_record = db.query(models.FeeRecord).filter(
            models.FeeRecord.audit_record_id == record.id
        ).first()
        if fee_record:
            new_status = determine_fee_status(conclusion)
            if fee_record.status != new_status:
                fee_record.status = new_status

        re_audited.append(record)

    return re_audited


def accept_amendment(db: Session, amendment_number: str) -> models.LCAmendment:
    amendment = get_amendment_by_number(db, amendment_number)
    if not amendment:
        raise ValueError(f"修改编号 {amendment_number} 不存在")

    check_and_expire_amendments(db, amendment.lc_id)

    if amendment.status == AMENDMENT_STATUS_EXPIRED:
        raise ValueError(f"修改 {amendment_number} 已过期，无法接受")

    if amendment.status != AMENDMENT_STATUS_PENDING:
        raise ValueError(f"修改 {amendment_number} 当前状态为 {amendment.status}，只有 pending 状态的修改可以接受")

    lc = get_letter_of_credit_by_id(db, amendment.lc_id)
    if not lc:
        raise ValueError("关联信用证不存在")

    apply_amendment_to_lc(db, lc, amendment.field_changes)

    snapshot_after = lc_to_snapshot_dict(lc)
    amendment.snapshot_after = snapshot_after
    amendment.status = AMENDMENT_STATUS_ACCEPTED
    amendment.acceptance_time = datetime.utcnow()

    re_audited = re_audit_pending_submissions(db, amendment.lc_id)

    db.commit()
    db.refresh(amendment)
    return amendment


def reject_amendment(db: Session, amendment_number: str) -> models.LCAmendment:
    amendment = get_amendment_by_number(db, amendment_number)
    if not amendment:
        raise ValueError(f"修改编号 {amendment_number} 不存在")

    check_and_expire_amendments(db, amendment.lc_id)

    if amendment.status == AMENDMENT_STATUS_EXPIRED:
        raise ValueError(f"修改 {amendment_number} 已过期，无需拒绝")

    if amendment.status != AMENDMENT_STATUS_PENDING:
        raise ValueError(f"修改 {amendment_number} 当前状态为 {amendment.status}，只有 pending 状态的修改可以拒绝")

    amendment.status = AMENDMENT_STATUS_REJECTED
    amendment.acceptance_time = datetime.utcnow()

    db.commit()
    db.refresh(amendment)
    return amendment


def check_and_expire_amendments(db: Session, lc_id: int) -> int:
    now = datetime.utcnow()
    expired_count = 0

    pending_amendments = db.query(models.LCAmendment).filter(
        models.LCAmendment.lc_id == lc_id,
        models.LCAmendment.status == AMENDMENT_STATUS_PENDING
    ).all()

    for amendment in pending_amendments:
        if amendment.expiry_time < now:
            amendment.status = AMENDMENT_STATUS_EXPIRED
            expired_count += 1

    if expired_count > 0:
        db.commit()

    return expired_count


def get_amendment_snapshot(db: Session, amendment_number: str) -> Dict[str, Any]:
    amendment = get_amendment_by_number(db, amendment_number)
    if not amendment:
        raise ValueError(f"修改编号 {amendment_number} 不存在")

    check_and_expire_amendments(db, amendment.lc_id)
    db.refresh(amendment)

    return {
        "amendment_number": amendment.amendment_number,
        "status": amendment.status,
        "before": amendment.snapshot_before,
        "after": amendment.snapshot_after
    }


def get_all_pending_amendments(db: Session) -> List[models.LCAmendment]:
    return db.query(models.LCAmendment).filter(
        models.LCAmendment.status == AMENDMENT_STATUS_PENDING
    ).all()


def expire_all_overdue_amendments(db: Session) -> int:
    total_expired = 0
    pending = get_all_pending_amendments(db)
    for amendment in pending:
        if amendment.is_expired():
            amendment.status = AMENDMENT_STATUS_EXPIRED
            total_expired += 1
    if total_expired > 0:
        db.commit()
    return total_expired


def get_fee_records_by_lc(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    fee_records = db.query(models.FeeRecord).filter(
        models.FeeRecord.lc_id == lc.id
    ).order_by(models.FeeRecord.created_at.desc()).all()

    total_amount = sum(r.total_amount for r in fee_records)
    confirmed_amount = sum(r.total_amount for r in fee_records if r.status == FEE_STATUS_CONFIRMED)
    pending_amount = sum(r.total_amount for r in fee_records if r.status == FEE_STATUS_PENDING)

    return {
        "lc_number": lc.lc_number,
        "fee_tier": lc.fee_tier,
        "fee_records": fee_records,
        "total_amount": round(float(total_amount), 2),
        "confirmed_amount": round(float(confirmed_amount), 2),
        "pending_amount": round(float(pending_amount), 2),
    }


def get_fee_records_by_time_range(
    db: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    from sqlalchemy import func

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    query = db.query(models.FeeRecord).filter(
        models.FeeRecord.created_at >= start_dt,
        models.FeeRecord.created_at <= end_dt,
    )
    all_records = query.order_by(models.FeeRecord.created_at.desc()).all()

    grand_total = sum(r.total_amount for r in all_records)

    tier_stats = db.query(
        models.FeeRecord.fee_tier,
        models.FeeRecord.status,
        func.count(models.FeeRecord.id).label("count"),
        func.sum(models.FeeRecord.total_amount).label("total"),
    ).filter(
        models.FeeRecord.created_at >= start_dt,
        models.FeeRecord.created_at <= end_dt,
    ).group_by(models.FeeRecord.fee_tier, models.FeeRecord.status).all()

    tier_agg = {}
    for tier in VALID_FEE_TIERS:
        tier_agg[tier] = {
            "record_count": 0,
            "total_amount": 0.0,
            "confirmed_amount": 0.0,
            "pending_amount": 0.0,
        }

    for tier, status, count, total in tier_stats:
        if tier not in tier_agg:
            continue
        total = float(total or 0)
        count = int(count or 0)
        tier_agg[tier]["record_count"] += count
        tier_agg[tier]["total_amount"] += total
        if status == FEE_STATUS_CONFIRMED:
            tier_agg[tier]["confirmed_amount"] += total
        elif status == FEE_STATUS_PENDING:
            tier_agg[tier]["pending_amount"] += total

    by_tier = []
    for tier in VALID_FEE_TIERS:
        data = tier_agg[tier]
        by_tier.append({
            "fee_tier": tier,
            "record_count": data["record_count"],
            "total_amount": round(data["total_amount"], 2),
            "confirmed_amount": round(data["confirmed_amount"], 2),
            "pending_amount": round(data["pending_amount"], 2),
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(all_records),
        "grand_total": round(float(grand_total), 2),
        "by_tier": by_tier,
    }


def get_all_fee_records(db: Session, skip: int = 0, limit: int = 100) -> List[models.FeeRecord]:
    return db.query(models.FeeRecord).order_by(models.FeeRecord.created_at.desc()).offset(skip).limit(limit).all()


def create_reviewer(db: Session, reviewer_data: schemas.ReviewerCreate) -> models.Reviewer:
    existing = db.query(models.Reviewer).filter(
        models.Reviewer.employee_id == reviewer_data.employee_id
    ).first()
    if existing:
        raise ValueError(f"工号 {reviewer_data.employee_id} 已存在")

    db_reviewer = models.Reviewer(
        employee_id=reviewer_data.employee_id,
        name=reviewer_data.name,
        department=reviewer_data.department,
        is_active=True
    )
    db.add(db_reviewer)
    db.commit()
    db.refresh(db_reviewer)
    return db_reviewer


def get_reviewer_by_employee_id(db: Session, employee_id: str) -> Optional[models.Reviewer]:
    return db.query(models.Reviewer).filter(
        models.Reviewer.employee_id == employee_id
    ).first()


def get_reviewer_by_id(db: Session, reviewer_id: int) -> Optional[models.Reviewer]:
    return db.query(models.Reviewer).filter(models.Reviewer.id == reviewer_id).first()


def get_all_reviewers(db: Session, skip: int = 0, limit: int = 100, active_only: bool = True) -> List[models.Reviewer]:
    query = db.query(models.Reviewer)
    if active_only:
        query = query.filter(models.Reviewer.is_active == True)
    return query.order_by(models.Reviewer.created_at.desc()).offset(skip).limit(limit).all()


def expire_overdue_assignments(db: Session) -> int:
    now = datetime.utcnow()
    expired = db.query(models.ReviewAssignment).filter(
        models.ReviewAssignment.completed_at.is_(None),
        models.ReviewAssignment.is_expired == False,
        models.ReviewAssignment.expires_at < now
    ).all()

    count = 0
    for assignment in expired:
        assignment.is_expired = True
        audit_record = db.query(models.AuditRecord).filter(
            models.AuditRecord.id == assignment.audit_record_id
        ).first()
        if audit_record and audit_record.review_status == REVIEW_STATUS_IN_REVIEW:
            audit_record.review_status = REVIEW_STATUS_PENDING
        count += 1

    if count > 0:
        db.commit()
    return count


def get_pending_review_audits(db: Session, skip: int = 0, limit: int = 100) -> List[models.AuditRecord]:
    expire_overdue_assignments(db)
    return db.query(models.AuditRecord).filter(
        models.AuditRecord.review_status == REVIEW_STATUS_PENDING
    ).order_by(models.AuditRecord.created_at.asc()).offset(skip).limit(limit).all()


def get_active_assignment_for_audit(db: Session, audit_record_id: int) -> Optional[models.ReviewAssignment]:
    return db.query(models.ReviewAssignment).filter(
        models.ReviewAssignment.audit_record_id == audit_record_id,
        models.ReviewAssignment.completed_at.is_(None),
        models.ReviewAssignment.is_expired == False
    ).first()


def claim_review_task(db: Session, audit_record_id: int, employee_id: str) -> models.ReviewAssignment:
    expire_overdue_assignments(db)

    reviewer = get_reviewer_by_employee_id(db, employee_id)
    if not reviewer:
        raise ValueError(f"审单员工号 {employee_id} 不存在")
    if not reviewer.is_active:
        raise ValueError(f"审单员 {reviewer.name} 已停用")

    audit_record = db.query(models.AuditRecord).filter(
        models.AuditRecord.id == audit_record_id
    ).first()
    if not audit_record:
        raise ValueError(f"审核记录 {audit_record_id} 不存在")

    if audit_record.review_status == REVIEW_STATUS_REVIEWED:
        raise ValueError("该交单已完成复核，无法认领")

    active_assignment = get_active_assignment_for_audit(db, audit_record_id)
    if active_assignment:
        if active_assignment.reviewer_id == reviewer.id:
            return active_assignment
        raise ValueError("该交单已被其他审单员认领")

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=CLAIM_TIMEOUT_HOURS)

    assignment = models.ReviewAssignment(
        audit_record_id=audit_record_id,
        reviewer_id=reviewer.id,
        claimed_at=now,
        expires_at=expires_at,
        is_expired=False
    )
    db.add(assignment)

    audit_record.review_status = REVIEW_STATUS_IN_REVIEW

    db.commit()
    db.refresh(assignment)
    return assignment


def get_reviewer_active_assignments(db: Session, reviewer_id: int) -> List[models.ReviewAssignment]:
    expire_overdue_assignments(db)
    return db.query(models.ReviewAssignment).filter(
        models.ReviewAssignment.reviewer_id == reviewer_id,
        models.ReviewAssignment.completed_at.is_(None),
        models.ReviewAssignment.is_expired == False
    ).order_by(models.ReviewAssignment.claimed_at.asc()).all()


def _recalculate_discrepancy_counts(db: Session, audit_record_id: int) -> None:
    audit_record = db.query(models.AuditRecord).filter(
        models.AuditRecord.id == audit_record_id
    ).first()
    if not audit_record:
        return

    active_discrepancies = [
        d for d in audit_record.discrepancies
        if not d.is_removed
    ]
    audit_record.total_discrepancies = len(active_discrepancies)
    audit_record.critical_count = sum(1 for d in active_discrepancies if d.severity == "critical")
    audit_record.minor_count = sum(1 for d in active_discrepancies if d.severity == "minor")


def _determine_conclusion_from_discrepancies(audit_record: models.AuditRecord) -> str:
    active_discrepancies = [
        d for d in audit_record.discrepancies
        if not d.is_removed
    ]
    total = len(active_discrepancies)
    critical_count = sum(1 for d in active_discrepancies if d.severity == "critical")
    minor_count = sum(1 for d in active_discrepancies if d.severity == "minor")

    if total == 0:
        return "compliant"
    elif critical_count == 0 and minor_count <= 2:
        return "minor_discrepancy"
    else:
        return "discrepant"


def add_manual_discrepancy(
    db: Session,
    audit_record_id: int,
    reviewer_id: int,
    disc_data: schemas.DiscrepancyCreateRequest
) -> models.Discrepancy:
    db_disc = models.Discrepancy(
        audit_record_id=audit_record_id,
        discrepancy_type=disc_data.discrepancy_type,
        severity=disc_data.severity,
        document_type=disc_data.document_type,
        description=disc_data.description,
        lc_clause_reference=disc_data.lc_clause_reference,
        source=DISCREPANCY_ACTION_MANUAL,
        is_removed=False
    )
    db.add(db_disc)
    db.flush()
    _recalculate_discrepancy_counts(db, audit_record_id)
    return db_disc


def remove_discrepancy(
    db: Session,
    discrepancy_id: int,
    removal_reason: str
) -> Optional[models.Discrepancy]:
    discrepancy = db.query(models.Discrepancy).filter(
        models.Discrepancy.id == discrepancy_id
    ).first()
    if not discrepancy:
        raise ValueError(f"不符点 {discrepancy_id} 不存在")
    if discrepancy.is_removed:
        raise ValueError("该不符点已被标记为误判")

    discrepancy.is_removed = True
    discrepancy.removal_reason = removal_reason
    _recalculate_discrepancy_counts(db, discrepancy.audit_record_id)
    return discrepancy


def complete_review(
    db: Session,
    audit_record_id: int,
    reviewer_id: int,
    review_data: schemas.ReviewCompleteRequest
) -> Dict[str, Any]:
    expire_overdue_assignments(db)

    audit_record = db.query(models.AuditRecord).filter(
        models.AuditRecord.id == audit_record_id
    ).first()
    if not audit_record:
        raise ValueError(f"审核记录 {audit_record_id} 不存在")

    if audit_record.review_status == REVIEW_STATUS_REVIEWED:
        raise ValueError("该交单已完成复核")

    active_assignment = get_active_assignment_for_audit(db, audit_record_id)
    if not active_assignment:
        raise ValueError("该交单未被认领或认领已过期")
    if active_assignment.reviewer_id != reviewer_id:
        raise ValueError("该交单由其他审单员认领，您无权操作")

    action = review_data.action.value if hasattr(review_data.action, 'value') else review_data.action

    if action == REVIEW_ACTION_CONFIRM:
        audit_record.final_conclusion = audit_record.auto_conclusion
        audit_record.conclusion = audit_record.auto_conclusion

    elif action == REVIEW_ACTION_OVERRULE:
        if not review_data.overrule_data:
            raise ValueError("推翻结论时必须提供 overrule_data")
        valid_conclusions = ["compliant", "minor_discrepancy", "discrepant"]
        if review_data.overrule_data.new_conclusion not in valid_conclusions:
            raise ValueError(f"无效的结论值，允许的值: {', '.join(valid_conclusions)}")
        audit_record.final_conclusion = review_data.overrule_data.new_conclusion
        audit_record.conclusion = review_data.overrule_data.new_conclusion

    elif action in [REVIEW_ACTION_ADD_DISCREPANCY, REVIEW_ACTION_REMOVE_DISCREPANCY]:
        pass
    else:
        raise ValueError(f"无效的操作类型: {action}")

    if review_data.remove_discrepancies:
        for remove_req in review_data.remove_discrepancies:
            remove_discrepancy(db, remove_req.discrepancy_id, remove_req.removal_reason)

    if review_data.add_discrepancies:
        for add_req in review_data.add_discrepancies:
            add_manual_discrepancy(db, audit_record_id, reviewer_id, add_req)

    if action == REVIEW_ACTION_ADD_DISCREPANCY or action == REVIEW_ACTION_REMOVE_DISCREPANCY:
        new_conclusion = _determine_conclusion_from_discrepancies(audit_record)
        audit_record.final_conclusion = new_conclusion
        audit_record.conclusion = new_conclusion

    fee_record = db.query(models.FeeRecord).filter(
        models.FeeRecord.audit_record_id == audit_record_id
    ).first()
    if fee_record:
        fee_record.status = determine_fee_status(audit_record.conclusion)

    now = datetime.utcnow()
    review_duration = int((now - active_assignment.claimed_at).total_seconds())

    opinion = models.ReviewOpinion(
        audit_record_id=audit_record_id,
        reviewer_id=reviewer_id,
        action_type=action,
        overruled_reason=review_data.overrule_data.overruled_reason if review_data.overrule_data else None,
        new_conclusion=audit_record.final_conclusion,
        remarks=review_data.remarks,
        review_duration_seconds=review_duration
    )
    db.add(opinion)

    active_assignment.completed_at = now
    audit_record.review_status = REVIEW_STATUS_REVIEWED

    db.commit()
    db.refresh(audit_record)
    db.refresh(opinion)

    return {
        "audit_record": audit_record,
        "review_opinion": opinion,
        "review_duration_seconds": review_duration
    }


def get_audit_record_with_review(db: Session, audit_record_id: int) -> Dict[str, Any]:
    audit_record = db.query(models.AuditRecord).filter(
        models.AuditRecord.id == audit_record_id
    ).first()
    if not audit_record:
        return None

    expire_overdue_assignments(db)
    db.refresh(audit_record)

    active_assignment = get_active_assignment_for_audit(db, audit_record_id)
    assignment_dict = None
    if active_assignment:
        reviewer = get_reviewer_by_id(db, active_assignment.reviewer_id)
        assignment_dict = {
            "id": active_assignment.id,
            "audit_record_id": active_assignment.audit_record_id,
            "reviewer_id": active_assignment.reviewer_id,
            "reviewer_name": reviewer.name if reviewer else None,
            "claimed_at": active_assignment.claimed_at,
            "expires_at": active_assignment.expires_at,
            "completed_at": active_assignment.completed_at,
            "is_expired": active_assignment.is_expired
        }

    opinions = []
    for opinion in audit_record.review_opinions:
        reviewer = get_reviewer_by_id(db, opinion.reviewer_id)
        opinions.append({
            "id": opinion.id,
            "audit_record_id": opinion.audit_record_id,
            "reviewer_id": opinion.reviewer_id,
            "reviewer_name": reviewer.name if reviewer else None,
            "action_type": opinion.action_type,
            "overruled_reason": opinion.overruled_reason,
            "new_conclusion": opinion.new_conclusion,
            "remarks": opinion.remarks,
            "review_duration_seconds": opinion.review_duration_seconds,
            "created_at": opinion.created_at
        })

    lc = get_letter_of_credit_by_id(db, audit_record.lc_id)
    documents = get_documents_by_submission(db, audit_record.submission_id)

    return {
        "id": audit_record.id,
        "lc_id": audit_record.lc_id,
        "submission_id": audit_record.submission_id,
        "original_submission_id": audit_record.original_submission_id,
        "resubmission_round": audit_record.resubmission_round,
        "modification_remark": audit_record.modification_remark,
        "conclusion": audit_record.conclusion,
        "auto_conclusion": audit_record.auto_conclusion,
        "final_conclusion": audit_record.final_conclusion,
        "total_discrepancies": audit_record.total_discrepancies,
        "critical_count": audit_record.critical_count,
        "minor_count": audit_record.minor_count,
        "presentation_date": audit_record.presentation_date,
        "review_status": audit_record.review_status,
        "discrepancies": audit_record.discrepancies,
        "created_at": audit_record.created_at,
        "lc": lc,
        "documents": documents,
        "active_assignment": assignment_dict,
        "review_opinions": opinions
    }


def get_reviewer_stats(
    db: Session,
    reviewer_id: int,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    from sqlalchemy import func

    reviewer = get_reviewer_by_id(db, reviewer_id)
    if not reviewer:
        raise ValueError(f"审单员ID {reviewer_id} 不存在")

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    opinions_query = db.query(models.ReviewOpinion).filter(
        models.ReviewOpinion.reviewer_id == reviewer_id,
        models.ReviewOpinion.created_at >= start_dt,
        models.ReviewOpinion.created_at <= end_dt
    )
    opinions = opinions_query.all()

    total_reviewed = len(opinions)
    confirm_count = sum(1 for o in opinions if o.action_type == REVIEW_ACTION_CONFIRM)
    overrule_count = sum(1 for o in opinions if o.action_type == REVIEW_ACTION_OVERRULE)
    total_duration = sum(o.review_duration_seconds or 0 for o in opinions)
    avg_duration = (total_duration / total_reviewed) if total_reviewed > 0 else 0.0
    confirm_rate = (confirm_count / total_reviewed) if total_reviewed > 0 else 0.0

    return {
        "reviewer_id": reviewer.id,
        "reviewer_name": reviewer.name,
        "employee_id": reviewer.employee_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_reviewed": total_reviewed,
        "confirm_count": confirm_count,
        "confirm_rate": round(confirm_rate, 4),
        "overrule_count": overrule_count,
        "avg_review_duration_seconds": round(avg_duration, 2),
        "total_review_duration_seconds": total_duration
    }
