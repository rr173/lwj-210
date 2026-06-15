from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app import models, schemas
from app.audit_engine import AuditEngine


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
        models.AuditRecord.lc_id == lc_id
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
