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
    MAX_FIELDS_PER_AMENDMENT
)


def create_letter_of_credit(db: Session, lc_data: schemas.LetterOfCreditCreate) -> models.LetterOfCredit:
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
        additional_terms=lc_data.additional_terms
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


def has_active_audit(db: Session, lc_id: int) -> bool:
    active = db.query(models.AuditRecord).filter(
        models.AuditRecord.lc_id == lc_id,
        models.AuditRecord.resubmission_round == 0
    ).first()
    return active is not None


def submit_documents_and_audit(db: Session, submission: schemas.SubmissionSubmit):
    lc = get_letter_of_credit_by_number(db, submission.lc_number)
    if not lc:
        raise ValueError(f"信用证 {submission.lc_number} 不存在")

    existing_submission = db.query(models.AuditRecord).filter(
        models.AuditRecord.submission_id == submission.submission_id
    ).first()
    if existing_submission:
        raise ValueError(f"提交编号 {submission.submission_id} 已存在")

    existing_audit = db.query(models.AuditRecord).filter(
        models.AuditRecord.lc_id == lc.id
    ).first()
    if existing_audit:
        raise ValueError(
            f"信用证 {submission.lc_number} 已有一次交单记录 (提交编号: {existing_audit.submission_id})，"
            f"同一份信用证同一时间只允许一次有效的交单在审核中"
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
        total_discrepancies=len(discrepancies),
        critical_count=critical_count,
        minor_count=minor_count,
        presentation_date=submission.presentation_date
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
        total_discrepancies=len(discrepancies),
        critical_count=critical_count,
        minor_count=minor_count,
        presentation_date=resubmit.presentation_date
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
