from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import copy
import random

from app import models, schemas
from app.audit_engine import AuditEngine
from app.swift import LC_REQUIRED_FIELDS_FOR_CREATE
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
    RULE_VERSION_STATUS_DRAFT,
    RULE_VERSION_STATUS_TESTING,
    RULE_VERSION_STATUS_ACTIVE,
    RULE_VERSION_STATUS_ARCHIVED,
    VALID_RULE_VERSION_STATUSES,
    VALID_CHECK_CATEGORIES,
    DEFAULT_RULE_CONTENT,
)


def create_letter_of_credit(db: Session, lc_data: schemas.LetterOfCreditCreate) -> models.LetterOfCredit:
    fee_tier_value = lc_data.fee_tier.value if hasattr(lc_data.fee_tier, 'value') else lc_data.fee_tier
    if fee_tier_value not in VALID_FEE_TIERS:
        raise ValueError(f"无效的费率档位: {fee_tier_value}，允许的值: {', '.join(VALID_FEE_TIERS)}")

    payment_method = lc_data.payment_method.value if hasattr(lc_data.payment_method, 'value') else lc_data.payment_method
    if payment_method not in models.VALID_PAYMENT_METHODS:
        raise ValueError(f"无效的付款方式: {payment_method}，允许的值: {', '.join(models.VALID_PAYMENT_METHODS)}")

    usance_days = lc_data.usance_days
    usance_basis = lc_data.usance_basis.value if hasattr(lc_data.usance_basis, 'value') else lc_data.usance_basis
    deferred_payment_date = lc_data.deferred_payment_date

    if payment_method == models.PAYMENT_METHOD_USANCE:
        if usance_days is None or usance_days <= 0:
            raise ValueError("远期付款必须指定大于0的远期天数")
        if usance_basis not in models.VALID_USANCE_BASES:
            raise ValueError(f"远期付款必须指定有效的起算基准，允许的值: {', '.join(models.VALID_USANCE_BASES)}")

    if payment_method == models.PAYMENT_METHOD_DEFERRED:
        if deferred_payment_date is None:
            raise ValueError("延期付款必须指定付款日期")

    penalty_rate = lc_data.penalty_interest_rate
    if penalty_rate < 0:
        raise ValueError("罚息利率不能为负数")

    currency_value = lc_data.currency.value if hasattr(lc_data.currency, 'value') else lc_data.currency
    check_and_occupy_credit_line(
        db, lc_data.applicant_name, currency_value, lc_data.amount, lc_data.lc_number
    )

    db_lc = models.LetterOfCredit(
        lc_number=lc_data.lc_number,
        issuing_bank=lc_data.issuing_bank,
        beneficiary_name=lc_data.beneficiary_name,
        applicant_name=lc_data.applicant_name,
        currency=currency_value,
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
        fee_tier=fee_tier_value,
        payment_method=payment_method,
        usance_days=usance_days,
        usance_basis=usance_basis,
        deferred_payment_date=deferred_payment_date,
        penalty_interest_rate=penalty_rate,
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

    db.flush()

    associate_lc_parties(db, db_lc)
    dispatch_notifications(db, db_lc, models.EVENT_TYPE_LC_CREATED)

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

    new_payment_method = lc_data.payment_method.value if hasattr(lc_data.payment_method, 'value') else lc_data.payment_method
    if new_payment_method not in models.VALID_PAYMENT_METHODS:
        raise ValueError(f"无效的付款方式: {new_payment_method}")

    new_usance_days = lc_data.usance_days
    new_usance_basis = lc_data.usance_basis.value if hasattr(lc_data.usance_basis, 'value') else lc_data.usance_basis
    new_deferred_payment_date = lc_data.deferred_payment_date

    if new_payment_method == models.PAYMENT_METHOD_USANCE:
        if new_usance_days is None or new_usance_days <= 0:
            raise ValueError("远期付款必须指定大于0的远期天数")
        if new_usance_basis not in models.VALID_USANCE_BASES:
            raise ValueError(f"远期付款必须指定有效的起算基准")
    if new_payment_method == models.PAYMENT_METHOD_DEFERRED:
        if new_deferred_payment_date is None:
            raise ValueError("延期付款必须指定付款日期")

    new_penalty_rate = lc_data.penalty_interest_rate
    if new_penalty_rate < 0:
        raise ValueError("罚息利率不能为负数")

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
    db_lc.payment_method = new_payment_method
    db_lc.usance_days = new_usance_days
    db_lc.usance_basis = new_usance_basis
    db_lc.deferred_payment_date = new_deferred_payment_date
    db_lc.penalty_interest_rate = new_penalty_rate

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
        settlement_status=models.FEE_SETTLEMENT_STATUS_PENDING,
    )
    db.add(fee_record)
    db.flush()

    auto_generate_fee_split_details(db, fee_record)

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

    check_and_process_expired_alerts(db)

    freeze_reason = check_lc_frozen_for_submission(db, lc.id)
    if freeze_reason:
        raise ValueError(f"信用证已被冻结，无法提交新交单：{freeze_reason}")

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
    doc_signatures = []
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
        doc_signatures.append(doc_data.signature)

    db.flush()

    for i, sig_data in enumerate(doc_signatures):
        if sig_data is not None:
            _save_document_signature(db, documents[i].id, sig_data)

    db.flush()

    signature_results = {}
    for doc in documents:
        sig_result = verify_document_signature(db, doc)
        signature_results[doc.id] = sig_result

    rule_version = resolve_rule_version_for_audit(db)
    engine = AuditEngine(lc, documents, submission.presentation_date, rule_version=rule_version, signature_results=signature_results)
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
        review_status=REVIEW_STATUS_PENDING,
        rule_version_id=rule_version.id if rule_version else None
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

    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_SUBMISSION_CREATED, event_ref_id=submission.submission_id)

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

    check_and_process_expired_alerts(db)

    freeze_reason = check_lc_frozen_for_resubmission(db, lc.id)
    if freeze_reason:
        raise ValueError(f"信用证已被冻结，无法修改重提：{freeze_reason}")

    documents = []
    doc_signatures = []
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
        doc_signatures.append(doc_data.signature)

    db.flush()

    for i, sig_data in enumerate(doc_signatures):
        if sig_data is not None:
            _save_document_signature(db, documents[i].id, sig_data)

    db.flush()

    rule_version = resolve_rule_version_for_audit(db)
    signature_results = {}
    for doc in documents:
        sig_result = verify_document_signature(db, doc)
        signature_results[doc.id] = sig_result

    engine = AuditEngine(lc, documents, resubmit.presentation_date, rule_version=rule_version, signature_results=signature_results)
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
        review_status=REVIEW_STATUS_PENDING,
        rule_version_id=rule_version.id if rule_version else None
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

    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_SUBMISSION_CREATED, event_ref_id=resubmit.new_submission_id)

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
        "penalty_interest_rate": lc.penalty_interest_rate,
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

    check_and_process_expired_alerts(db)

    freeze_reason = check_lc_frozen_for_amendment(db, lc.id)
    if freeze_reason:
        raise ValueError(f"信用证已被冻结，无法发起修改：{freeze_reason}")

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
    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_AMENDMENT_CREATED, event_ref_id=amendment_number)

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

        engine = AuditEngine(lc, documents, record.presentation_date, rule_version=record.rule_version)
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


def handle_amendment_alert_and_freeze_cleanup(
    db: Session,
    lc_id: int,
    field_changes: List[Dict[str, Any]],
    new_lc_values: models.LetterOfCredit
) -> Dict[str, int]:
    today = date.today()

    date_field_alert_map = {
        "latest_shipment_date": (models.ALERT_TYPE_SHIPMENT, models.FREEZE_TYPE_SHIPMENT_EXPIRED),
        "latest_presentation_date": (models.ALERT_TYPE_PRESENTATION, models.FREEZE_TYPE_PRESENTATION_EXPIRED),
        "expiry_date": (models.ALERT_TYPE_EXPIRY, models.FREEZE_TYPE_EXPIRY_EXPIRED),
    }

    new_date_value_map = {
        "latest_shipment_date": new_lc_values.latest_shipment_date,
        "latest_presentation_date": new_lc_values.latest_presentation_date,
        "expiry_date": new_lc_values.expiry_date,
    }

    alerts_removed = 0
    freezes_released = 0

    for change in field_changes:
        field_name = change.get("field_name")
        if field_name not in date_field_alert_map:
            continue

        alert_type, freeze_type = date_field_alert_map[field_name]
        new_date = new_date_value_map.get(field_name)
        if new_date is None:
            continue

        alerts_to_remove = db.query(models.LCAlert).filter(
            models.LCAlert.lc_id == lc_id,
            models.LCAlert.alert_type == alert_type,
            models.LCAlert.status.in_([models.ALERT_STATUS_ACTIVE, models.ALERT_STATUS_ACKNOWLEDGED])
        ).all()

        for alert in alerts_to_remove:
            db.delete(alert)
            alerts_removed += 1

        expired_alerts_to_remove = db.query(models.LCAlert).filter(
            models.LCAlert.lc_id == lc_id,
            models.LCAlert.alert_type == alert_type,
            models.LCAlert.status == models.ALERT_STATUS_EXPIRED
        ).all()

        for alert in expired_alerts_to_remove:
            db.delete(alert)
            alerts_removed += 1

        if new_date >= today:
            freezes_to_release = db.query(models.LCFreezeRecord).filter(
                models.LCFreezeRecord.lc_id == lc_id,
                models.LCFreezeRecord.freeze_type == freeze_type,
                models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
            ).all()

            for freeze in freezes_to_release:
                freeze.status = models.FREEZE_STATUS_RELEASED
                freeze.released_at = datetime.utcnow()
                freeze.released_by = "system"
                freeze.release_reason = f"信用证修改已更新 {field_name} 为 {new_date}，自动解除冻结"
                freezes_released += 1

    if alerts_removed > 0 or freezes_released > 0:
        db.flush()

    return {
        "alerts_removed": alerts_removed,
        "freezes_released": freezes_released
    }


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

    old_amount = lc.amount
    new_amount = None
    amount_changed = False
    for change in amendment.field_changes:
        if change.get("field_name") == "amount":
            amount_changed = True
            new_amount = change.get("new_value")
            break

    if amount_changed and new_amount is not None and new_amount > old_amount:
        credit_line = get_credit_line_by_applicant_and_currency(
            db, lc.applicant_name, lc.currency
        )
        if credit_line:
            today = date.today()
            if lc.expiry_date >= today:
                used_info = calculate_used_amount(db, lc.applicant_name, lc.currency)
                current_used = used_info["used_amount"]
                available_before = credit_line.total_amount - current_used
                increase_amount = new_amount - old_amount
                if increase_amount > available_before + 0.01:
                    raise ValueError(
                        f"授信额度不足，无法增加信用证金额。申请人: {lc.applicant_name}, "
                        f"币种: {lc.currency}, 可用额度: {round(available_before, 2)}, "
                        f"需增加金额: {round(increase_amount, 2)}"
                    )

    apply_amendment_to_lc(db, lc, amendment.field_changes)

    db.flush()

    if amount_changed and new_amount is not None:
        adjust_credit_line_for_amendment(
            db, lc, old_amount, new_amount, amendment.amendment_number
        )

    check_back_to_back_conflicts(db, amendment.lc_id, amendment.field_changes)

    cleanup_result = handle_amendment_alert_and_freeze_cleanup(
        db, amendment.lc_id, amendment.field_changes, lc
    )

    snapshot_after = lc_to_snapshot_dict(lc)
    amendment.snapshot_after = snapshot_after
    amendment.status = AMENDMENT_STATUS_ACCEPTED
    amendment.acceptance_time = datetime.utcnow()

    re_audited = re_audit_pending_submissions(db, amendment.lc_id)

    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_AMENDMENT_ACCEPTED, event_ref_id=amendment_number)

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

    lc = get_letter_of_credit_by_id(db, amendment.lc_id)
    db.flush()
    if lc:
        dispatch_notifications(db, lc, models.EVENT_TYPE_AMENDMENT_REJECTED, event_ref_id=amendment_number)

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

    db.flush()
    lc = get_letter_of_credit_by_id(db, audit_record.lc_id)
    if lc:
        dispatch_notifications(db, lc, models.EVENT_TYPE_SUBMISSION_REVIEWED, event_ref_id=audit_record.submission_id)

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
        "rule_version_id": audit_record.rule_version_id,
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


def get_confirmed_transfer_amount(db: Session, lc_id: int) -> float:
    from sqlalchemy import func
    result = db.query(func.sum(models.LCTransfer.transfer_amount)).filter(
        models.LCTransfer.original_lc_id == lc_id,
        models.LCTransfer.status == models.TRANSFER_STATUS_CONFIRMED
    ).scalar()
    return float(result or 0)


def get_back_to_back_total_amount(db: Session, lc_id: int) -> float:
    from sqlalchemy import func
    result = db.query(func.sum(models.BackToBackLC.amount)).filter(
        models.BackToBackLC.original_lc_id == lc_id,
        models.BackToBackLC.status != models.BACK_TO_BACK_STATUS_REJECTED
    ).scalar()
    return float(result or 0)


def get_remaining_available_amount(db: Session, lc: models.LetterOfCredit) -> float:
    transferred = get_confirmed_transfer_amount(db, lc.id)
    back_to_back = get_back_to_back_total_amount(db, lc.id)
    return lc.amount - transferred - back_to_back


def get_next_transfer_sequence(db: Session, lc_id: int) -> int:
    from sqlalchemy import func
    max_seq = db.query(func.max(models.LCTransfer.sequence_number)).filter(
        models.LCTransfer.original_lc_id == lc_id
    ).scalar()
    return (max_seq or 0) + 1


def get_distinct_second_beneficiary_count(db: Session, lc_id: int) -> int:
    from sqlalchemy import func
    result = db.query(func.count(func.distinct(models.LCTransfer.second_beneficiary_name))).filter(
        models.LCTransfer.original_lc_id == lc_id,
        models.LCTransfer.status.in_([models.TRANSFER_STATUS_PENDING, models.TRANSFER_STATUS_CONFIRMED])
    ).scalar()
    return int(result or 0)


def create_transfer(db: Session, transfer_data: schemas.TransferCreate) -> models.LCTransfer:
    lc = get_letter_of_credit_by_number(db, transfer_data.lc_number)
    if not lc:
        raise ValueError(f"信用证 {transfer_data.lc_number} 不存在")

    transfer_type = transfer_data.transfer_type.value if hasattr(transfer_data.transfer_type, 'value') else transfer_data.transfer_type
    transfer_amount = transfer_data.transfer_amount

    if transfer_type == models.TRANSFER_TYPE_FULL:
        if abs(transfer_amount - lc.amount) > 0.01:
            raise ValueError(f"全额转让的转让金额必须等于原证金额 {lc.amount}，当前提交金额: {transfer_amount}")
    elif transfer_type == models.TRANSFER_TYPE_PARTIAL:
        max_partial = lc.amount * models.PARTIAL_TRANSFER_MAX_RATIO
        if transfer_amount > max_partial + 0.01:
            raise ValueError(f"部分转让金额不得超过原证金额的80% ({max_partial:.2f})，当前提交金额: {transfer_amount}")
        if transfer_amount <= 0:
            raise ValueError("部分转让金额必须大于0")
    else:
        raise ValueError(f"无效的转让类型: {transfer_type}")

    remaining = get_remaining_available_amount(db, lc)
    if transfer_amount > remaining + 0.01:
        raise ValueError(f"转让金额 {transfer_amount} 超过原证剩余可用金额 {remaining:.2f}")

    beneficiary_count = get_distinct_second_beneficiary_count(db, lc.id)
    existing_beneficiaries = db.query(models.LCTransfer.second_beneficiary_name).filter(
        models.LCTransfer.original_lc_id == lc.id,
        models.LCTransfer.status.in_([models.TRANSFER_STATUS_PENDING, models.TRANSFER_STATUS_CONFIRMED])
    ).all()
    existing_names = {b[0] for b in existing_beneficiaries}

    if transfer_data.second_beneficiary_name not in existing_names:
        if beneficiary_count >= models.MAX_SECOND_BENEFICIARIES:
            raise ValueError(f"同一份信用证最多允许转让给 {models.MAX_SECOND_BENEFICIARIES} 个不同的第二受益人")

    sequence_number = get_next_transfer_sequence(db, lc.id)
    transfer_number = f"{lc.lc_number}-T-{sequence_number:03d}"

    inherited_terms = {
        "port_of_loading": lc.port_of_loading,
        "port_of_discharge": lc.port_of_discharge,
        "goods_description": lc.goods_description,
        "transport_mode": lc.transport_mode,
        "additional_terms": copy.deepcopy(lc.additional_terms) if lc.additional_terms else [],
        "currency": lc.currency,
        "latest_shipment_date": lc.latest_shipment_date.isoformat() if lc.latest_shipment_date else None,
        "latest_presentation_date": lc.latest_presentation_date.isoformat() if lc.latest_presentation_date else None,
        "expiry_date": lc.expiry_date.isoformat() if lc.expiry_date else None,
        "partial_shipment_allowed": lc.partial_shipment_allowed,
        "transshipment_allowed": lc.transshipment_allowed,
    }

    doc_reqs = []
    for req in lc.document_requirements:
        doc_reqs.append({
            "document_type": req.document_type,
            "original_copies": req.original_copies,
            "copy_copies": req.copy_copies,
        })
    inherited_terms["document_requirements"] = doc_reqs

    transfer = models.LCTransfer(
        original_lc_id=lc.id,
        transfer_number=transfer_number,
        second_beneficiary_name=transfer_data.second_beneficiary_name,
        transfer_amount=transfer_amount,
        transfer_type=transfer_type,
        status=models.TRANSFER_STATUS_PENDING,
        inherited_terms=inherited_terms,
        sequence_number=sequence_number,
    )

    db.add(transfer)
    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_TRANSFER_CREATED, event_ref_id=transfer_number)

    db.commit()
    db.refresh(transfer)
    return transfer


def get_transfer_by_number(db: Session, transfer_number: str) -> Optional[models.LCTransfer]:
    return db.query(models.LCTransfer).filter(models.LCTransfer.transfer_number == transfer_number).first()


def get_transfers_by_lc(db: Session, lc_number: str) -> List[models.LCTransfer]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.LCTransfer).filter(
        models.LCTransfer.original_lc_id == lc.id
    ).order_by(models.LCTransfer.sequence_number.asc()).all()


def confirm_transfer(db: Session, transfer_number: str, action: str) -> models.LCTransfer:
    transfer = get_transfer_by_number(db, transfer_number)
    if not transfer:
        raise ValueError(f"转让证 {transfer_number} 不存在")

    if transfer.status != models.TRANSFER_STATUS_PENDING:
        raise ValueError(f"转让证 {transfer_number} 当前状态为 {transfer.status}，只有 pending 状态的转让可以确认")

    if action == "confirm":
        lc = get_letter_of_credit_by_id(db, transfer.original_lc_id)
        if not lc:
            raise ValueError("关联信用证不存在")

        remaining = get_remaining_available_amount(db, lc)
        if transfer.transfer_amount > remaining + 0.01:
            raise ValueError(f"转让金额 {transfer.transfer_amount} 超过原证剩余可用金额 {remaining:.2f}，无法确认")

        transfer.status = models.TRANSFER_STATUS_CONFIRMED
        transfer.confirmation_time = datetime.utcnow()
    elif action == "reject":
        transfer.status = models.TRANSFER_STATUS_REJECTED
        transfer.confirmation_time = datetime.utcnow()
    else:
        raise ValueError(f"无效的操作: {action}，仅支持 confirm 或 reject")

    db.commit()
    db.refresh(transfer)
    return transfer


def get_transfer_detail(db: Session, transfer_number: str) -> Optional[Dict[str, Any]]:
    transfer = get_transfer_by_number(db, transfer_number)
    if not transfer:
        return None

    lc = get_letter_of_credit_by_id(db, transfer.original_lc_id)
    return {
        "id": transfer.id,
        "original_lc_id": transfer.original_lc_id,
        "transfer_number": transfer.transfer_number,
        "second_beneficiary_name": transfer.second_beneficiary_name,
        "transfer_amount": transfer.transfer_amount,
        "transfer_type": transfer.transfer_type,
        "status": transfer.status,
        "confirmation_time": transfer.confirmation_time,
        "inherited_terms": transfer.inherited_terms,
        "sequence_number": transfer.sequence_number,
        "created_at": transfer.created_at,
        "original_lc": lc,
    }


def get_next_back_to_back_sequence(db: Session, lc_id: int) -> int:
    from sqlalchemy import func
    count = db.query(func.count(models.BackToBackLC.id)).filter(
        models.BackToBackLC.original_lc_id == lc_id
    ).scalar() or 0
    return count + 1


def create_back_to_back_lc(db: Session, btb_data: schemas.BackToBackLCCreate) -> models.BackToBackLC:
    lc = get_letter_of_credit_by_number(db, btb_data.lc_number)
    if not lc:
        raise ValueError(f"信用证 {btb_data.lc_number} 不存在")

    max_amount = lc.amount * models.BACK_TO_BACK_AMOUNT_RATIO
    if btb_data.amount > max_amount + 0.01:
        raise ValueError(f"背对背证金额不得超过原证金额的95% ({max_amount:.2f})，当前提交金额: {btb_data.amount}")

    if btb_data.amount <= 0:
        raise ValueError("背对背证金额必须大于0")

    remaining = get_remaining_available_amount(db, lc)
    if btb_data.amount > remaining + 0.01:
        raise ValueError(f"背对背证金额 {btb_data.amount} 超过原证剩余可用金额 {remaining:.2f}")

    max_shipment_date = lc.latest_shipment_date - timedelta(days=models.BACK_TO_BACK_SHIPMENT_DAYS_BEFORE)
    if btb_data.latest_shipment_date > max_shipment_date:
        raise ValueError(
            f"背对背证装运日期不晚于原证装运日期前{models.BACK_TO_BACK_SHIPMENT_DAYS_BEFORE}天，"
            f"原证装运日期: {lc.latest_shipment_date}，最迟允许: {max_shipment_date}，"
            f"提交的装运日期: {btb_data.latest_shipment_date}"
        )

    max_expiry_date = lc.expiry_date - timedelta(days=models.BACK_TO_BACK_EXPIRY_DAYS_BEFORE)
    if btb_data.expiry_date > max_expiry_date:
        raise ValueError(
            f"背对背证到期日不晚于原证到期日前{models.BACK_TO_BACK_EXPIRY_DAYS_BEFORE}天，"
            f"原证到期日: {lc.expiry_date}，最迟允许: {max_expiry_date}，"
            f"提交的到期日: {btb_data.expiry_date}"
        )

    sequence = get_next_back_to_back_sequence(db, lc.id)
    back_to_back_number = f"{lc.lc_number}-BB-{sequence:03d}"

    transport_mode_value = btb_data.transport_mode.value if hasattr(btb_data.transport_mode, 'value') else btb_data.transport_mode

    btb_lc = models.BackToBackLC(
        original_lc_id=lc.id,
        back_to_back_number=back_to_back_number,
        beneficiary_name=btb_data.beneficiary_name,
        applicant_name=btb_data.applicant_name,
        issuing_bank=btb_data.issuing_bank,
        currency=lc.currency,
        amount=btb_data.amount,
        latest_shipment_date=btb_data.latest_shipment_date,
        latest_presentation_date=btb_data.latest_presentation_date,
        expiry_date=btb_data.expiry_date,
        transport_mode=transport_mode_value,
        port_of_loading=btb_data.port_of_loading,
        port_of_discharge=btb_data.port_of_discharge,
        partial_shipment_allowed=btb_data.partial_shipment_allowed,
        transshipment_allowed=btb_data.transshipment_allowed,
        goods_description=btb_data.goods_description,
        additional_terms=btb_data.additional_terms,
        status=models.BACK_TO_BACK_STATUS_PENDING,
        conflict_status=models.CONFLICT_STATUS_NORMAL,
    )

    db.add(btb_lc)
    db.flush()

    for req in btb_data.document_requirements:
        db_req = models.BackToBackDocumentRequirement(
            back_to_back_lc_id=btb_lc.id,
            document_type=req.document_type,
            original_copies=req.original_copies,
            copy_copies=req.copy_copies,
        )
        db.add(db_req)

    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_BACK_TO_BACK_CREATED, event_ref_id=back_to_back_number)

    db.commit()
    db.refresh(btb_lc)
    return btb_lc


def get_back_to_back_by_number(db: Session, back_to_back_number: str) -> Optional[models.BackToBackLC]:
    return db.query(models.BackToBackLC).filter(
        models.BackToBackLC.back_to_back_number == back_to_back_number
    ).first()


def get_back_to_back_lcs_by_lc(db: Session, lc_number: str) -> List[models.BackToBackLC]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.BackToBackLC).filter(
        models.BackToBackLC.original_lc_id == lc.id
    ).order_by(models.BackToBackLC.created_at.desc()).all()


def get_back_to_back_detail(db: Session, back_to_back_number: str) -> Optional[Dict[str, Any]]:
    btb = get_back_to_back_by_number(db, back_to_back_number)
    if not btb:
        return None

    lc = get_letter_of_credit_by_id(db, btb.original_lc_id)
    return {
        "id": btb.id,
        "original_lc_id": btb.original_lc_id,
        "back_to_back_number": btb.back_to_back_number,
        "beneficiary_name": btb.beneficiary_name,
        "applicant_name": btb.applicant_name,
        "issuing_bank": btb.issuing_bank,
        "currency": btb.currency,
        "amount": btb.amount,
        "latest_shipment_date": btb.latest_shipment_date,
        "latest_presentation_date": btb.latest_presentation_date,
        "expiry_date": btb.expiry_date,
        "transport_mode": btb.transport_mode,
        "port_of_loading": btb.port_of_loading,
        "port_of_discharge": btb.port_of_discharge,
        "partial_shipment_allowed": btb.partial_shipment_allowed,
        "transshipment_allowed": btb.transshipment_allowed,
        "goods_description": btb.goods_description,
        "additional_terms": btb.additional_terms,
        "document_requirements": btb.document_requirements,
        "status": btb.status,
        "conflict_status": btb.conflict_status,
        "conflict_details": btb.conflict_details,
        "created_at": btb.created_at,
        "original_lc": lc,
    }


def check_back_to_back_conflicts(db: Session, lc_id: int, field_changes: List[Dict[str, Any]]) -> None:
    btb_lcs = db.query(models.BackToBackLC).filter(
        models.BackToBackLC.original_lc_id == lc_id,
        models.BackToBackLC.status != models.BACK_TO_BACK_STATUS_REJECTED
    ).all()

    if not btb_lcs:
        return

    lc = get_letter_of_credit_by_id(db, lc_id)
    if not lc:
        return

    changes_map = {}
    for change in field_changes:
        changes_map[change["field_name"]] = change["new_value"]

    for btb in btb_lcs:
        conflicts = []

        if "latest_shipment_date" in changes_map:
            new_shipment = changes_map["latest_shipment_date"]
            if isinstance(new_shipment, str):
                new_shipment = date.fromisoformat(new_shipment)
            max_allowed = new_shipment - timedelta(days=models.BACK_TO_BACK_SHIPMENT_DAYS_BEFORE)
            if btb.latest_shipment_date > max_allowed:
                conflicts.append({
                    "field": "latest_shipment_date",
                    "back_to_back_value": btb.latest_shipment_date.isoformat(),
                    "max_allowed": max_allowed.isoformat(),
                    "new_original_value": new_shipment.isoformat(),
                    "message": f"原证装运日期修改为 {new_shipment}，背对背证装运日期 {btb.latest_shipment_date} 超过新约束 (不晚于原证装运日期前{models.BACK_TO_BACK_SHIPMENT_DAYS_BEFORE}天 = {max_allowed})"
                })

        if "expiry_date" in changes_map:
            new_expiry = changes_map["expiry_date"]
            if isinstance(new_expiry, str):
                new_expiry = date.fromisoformat(new_expiry)
            max_allowed = new_expiry - timedelta(days=models.BACK_TO_BACK_EXPIRY_DAYS_BEFORE)
            if btb.expiry_date > max_allowed:
                conflicts.append({
                    "field": "expiry_date",
                    "back_to_back_value": btb.expiry_date.isoformat(),
                    "max_allowed": max_allowed.isoformat(),
                    "new_original_value": new_expiry.isoformat(),
                    "message": f"原证到期日修改为 {new_expiry}，背对背证到期日 {btb.expiry_date} 超过新约束 (不晚于原证到期日前{models.BACK_TO_BACK_EXPIRY_DAYS_BEFORE}天 = {max_allowed})"
                })

        if "amount" in changes_map:
            new_amount = float(changes_map["amount"])
            max_allowed = new_amount * models.BACK_TO_BACK_AMOUNT_RATIO
            if btb.amount > max_allowed + 0.01:
                conflicts.append({
                    "field": "amount",
                    "back_to_back_value": btb.amount,
                    "max_allowed": max_allowed,
                    "new_original_value": new_amount,
                    "message": f"原证金额修改为 {new_amount}，背对背证金额 {btb.amount} 超过新约束 (不超过原证金额的95% = {max_allowed:.2f})"
                })

        if conflicts:
            btb.conflict_status = models.CONFLICT_STATUS_CONFLICT
            existing_details = btb.conflict_details or []
            btb.conflict_details = existing_details + conflicts
        else:
            btb.conflict_status = models.CONFLICT_STATUS_NORMAL


def get_lc_available_amount(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    transferred = get_confirmed_transfer_amount(db, lc.id)
    back_to_back = get_back_to_back_total_amount(db, lc.id)
    remaining = lc.amount - transferred - back_to_back

    transfers = db.query(models.LCTransfer).filter(
        models.LCTransfer.original_lc_id == lc.id
    ).order_by(models.LCTransfer.sequence_number.asc()).all()

    btb_lcs = db.query(models.BackToBackLC).filter(
        models.BackToBackLC.original_lc_id == lc.id
    ).order_by(models.BackToBackLC.created_at.desc()).all()

    return {
        "lc_number": lc.lc_number,
        "original_amount": lc.amount,
        "total_transferred_amount": round(transferred, 2),
        "total_back_to_back_amount": round(back_to_back, 2),
        "remaining_available_amount": round(remaining, 2),
        "transfers": transfers,
        "back_to_back_lcs": btb_lcs,
    }


def get_lc_transfer_and_back_to_back_summary(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    transfers = db.query(models.LCTransfer).filter(
        models.LCTransfer.original_lc_id == lc.id
    ).order_by(models.LCTransfer.sequence_number.asc()).all()

    btb_lcs = db.query(models.BackToBackLC).filter(
        models.BackToBackLC.original_lc_id == lc.id
    ).order_by(models.BackToBackLC.created_at.desc()).all()

    return {
        "lc_number": lc.lc_number,
        "transfers": transfers,
        "back_to_back_lcs": btb_lcs,
    }


def generate_alert_number(db: Session, lc_number: str, alert_type: str) -> str:
    from sqlalchemy import func
    date_str = date.today().strftime("%Y%m%d")
    prefix = f"ALT-{lc_number}-{alert_type}-{date_str}-"
    count = db.query(func.count(models.LCAlert.id)).filter(
        models.LCAlert.alert_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def generate_freeze_number(db: Session, lc_number: str, freeze_type: str) -> str:
    from sqlalchemy import func
    date_str = date.today().strftime("%Y%m%d")
    prefix = f"FRZ-{lc_number}-{freeze_type}-{date_str}-"
    count = db.query(func.count(models.LCFreezeRecord.id)).filter(
        models.LCFreezeRecord.freeze_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def has_active_alert(db: Session, lc_id: int, alert_type: str) -> bool:
    existing = db.query(models.LCAlert).filter(
        models.LCAlert.lc_id == lc_id,
        models.LCAlert.alert_type == alert_type,
        models.LCAlert.status.in_([models.ALERT_STATUS_ACTIVE, models.ALERT_STATUS_ACKNOWLEDGED])
    ).first()
    return existing is not None


def create_alert_if_needed(
    db: Session,
    lc: models.LetterOfCredit,
    alert_type: str,
    target_date: date,
    days_before: int,
    today: date
) -> Optional[models.LCAlert]:
    remaining_days = (target_date - today).days

    if remaining_days > days_before:
        return None

    if has_active_alert(db, lc.id, alert_type):
        return None

    existing_expired = db.query(models.LCAlert).filter(
        models.LCAlert.lc_id == lc.id,
        models.LCAlert.alert_type == alert_type,
        models.LCAlert.status == models.ALERT_STATUS_EXPIRED
    ).first()
    if existing_expired:
        return None

    alert_number = generate_alert_number(db, lc.lc_number, alert_type)

    if remaining_days < 0:
        status = models.ALERT_STATUS_EXPIRED
    else:
        status = models.ALERT_STATUS_ACTIVE

    alert = models.LCAlert(
        alert_number=alert_number,
        lc_id=lc.id,
        alert_type=alert_type,
        trigger_date=today,
        target_date=target_date,
        remaining_days=remaining_days,
        status=status
    )

    db.add(alert)
    db.flush()

    if status == models.ALERT_STATUS_EXPIRED:
        freeze_type_map = {
            models.ALERT_TYPE_SHIPMENT: models.FREEZE_TYPE_SHIPMENT_EXPIRED,
            models.ALERT_TYPE_PRESENTATION: models.FREEZE_TYPE_PRESENTATION_EXPIRED,
            models.ALERT_TYPE_EXPIRY: models.FREEZE_TYPE_EXPIRY_EXPIRED,
        }
        reason_map = {
            models.ALERT_TYPE_SHIPMENT: f"最迟装运日 {target_date} 已过期，禁止新交单提交",
            models.ALERT_TYPE_PRESENTATION: f"最迟交单日 {target_date} 已过期，禁止修改重提",
            models.ALERT_TYPE_EXPIRY: f"信用证到期日 {target_date} 已过期，信用证完全冻结",
        }
        freeze_type = freeze_type_map.get(alert_type)
        reason = reason_map.get(alert_type, "")
        if freeze_type and not has_active_freeze(db, lc.id, freeze_type):
            create_freeze_record(db, lc, freeze_type, reason)

    dispatch_notifications(db, lc, models.EVENT_TYPE_ALERT_GENERATED, event_ref_id=alert_number)

    return alert


def scan_and_generate_alerts(db: Session) -> Dict[str, Any]:
    today = date.today()
    all_lcs = get_all_letter_of_credits(db)

    shipment_alerts = []
    presentation_alerts = []
    expiry_alerts = []

    for lc in all_lcs:
        shipment_alert = create_alert_if_needed(
            db, lc,
            models.ALERT_TYPE_SHIPMENT,
            lc.latest_shipment_date,
            models.ALERT_SHIPMENT_DAYS_BEFORE,
            today
        )
        if shipment_alert:
            shipment_alerts.append(shipment_alert)

        presentation_alert = create_alert_if_needed(
            db, lc,
            models.ALERT_TYPE_PRESENTATION,
            lc.latest_presentation_date,
            models.ALERT_PRESENTATION_DAYS_BEFORE,
            today
        )
        if presentation_alert:
            presentation_alerts.append(presentation_alert)

        expiry_alert = create_alert_if_needed(
            db, lc,
            models.ALERT_TYPE_EXPIRY,
            lc.expiry_date,
            models.ALERT_EXPIRY_DAYS_BEFORE,
            today
        )
        if expiry_alert:
            expiry_alerts.append(expiry_alert)

    db.commit()

    return {
        "total": len(shipment_alerts) + len(presentation_alerts) + len(expiry_alerts),
        "shipment_alerts": len(shipment_alerts),
        "presentation_alerts": len(presentation_alerts),
        "expiry_alerts": len(expiry_alerts)
    }


def get_alerts_by_lc(db: Session, lc_number: str) -> List[models.LCAlert]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")
    return db.query(models.LCAlert).filter(
        models.LCAlert.lc_id == lc.id
    ).order_by(models.LCAlert.created_at.desc()).all()


def get_active_alerts(db: Session, skip: int = 0, limit: int = 100) -> List[models.LCAlert]:
    return db.query(models.LCAlert).filter(
        models.LCAlert.status == models.ALERT_STATUS_ACTIVE
    ).order_by(models.LCAlert.target_date.asc()).offset(skip).limit(limit).all()


def get_alert_by_number(db: Session, alert_number: str) -> Optional[models.LCAlert]:
    return db.query(models.LCAlert).filter(
        models.LCAlert.alert_number == alert_number
    ).first()


def acknowledge_alert(db: Session, alert_number: str, acknowledged_by: str) -> models.LCAlert:
    alert = get_alert_by_number(db, alert_number)
    if not alert:
        raise ValueError(f"预警记录 {alert_number} 不存在")

    if alert.status == models.ALERT_STATUS_EXPIRED:
        raise ValueError(f"预警 {alert_number} 已过期，无法确认")

    if alert.status == models.ALERT_STATUS_ACKNOWLEDGED:
        return alert

    alert.status = models.ALERT_STATUS_ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = acknowledged_by

    db.commit()
    db.refresh(alert)
    return alert


def get_alert_statistics(db: Session) -> List[Dict[str, Any]]:
    from sqlalchemy import func
    results = db.query(
        models.LCAlert.alert_type,
        func.count(models.LCAlert.id).label("count")
    ).filter(
        models.LCAlert.status == models.ALERT_STATUS_ACTIVE
    ).group_by(models.LCAlert.alert_type).all()

    stats = []
    type_map = {
        models.ALERT_TYPE_SHIPMENT: "装运预警",
        models.ALERT_TYPE_PRESENTATION: "交单预警",
        models.ALERT_TYPE_EXPIRY: "到期预警"
    }
    for alert_type in models.VALID_ALERT_TYPES:
        count = 0
        for r in results:
            if r[0] == alert_type:
                count = r[1]
                break
        stats.append({
            "alert_type": alert_type,
            "alert_type_name": type_map.get(alert_type, alert_type),
            "count": count
        })
    return stats


def has_active_freeze(db: Session, lc_id: int, freeze_type: str = None) -> bool:
    query = db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.lc_id == lc_id,
        models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
    )
    if freeze_type:
        query = query.filter(models.LCFreezeRecord.freeze_type == freeze_type)
    return query.first() is not None


def get_active_freeze(db: Session, lc_id: int) -> Optional[models.LCFreezeRecord]:
    return db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.lc_id == lc_id,
        models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
    ).order_by(models.LCFreezeRecord.frozen_at.desc()).first()


def create_freeze_record(
    db: Session,
    lc: models.LetterOfCredit,
    freeze_type: str,
    reason: str
) -> models.LCFreezeRecord:
    if has_active_freeze(db, lc.id, freeze_type):
        existing = db.query(models.LCFreezeRecord).filter(
            models.LCFreezeRecord.lc_id == lc.id,
            models.LCFreezeRecord.freeze_type == freeze_type,
            models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
        ).first()
        return existing

    freeze_number = generate_freeze_number(db, lc.lc_number, freeze_type)

    freeze_record = models.LCFreezeRecord(
        freeze_number=freeze_number,
        lc_id=lc.id,
        freeze_type=freeze_type,
        reason=reason,
        status=models.FREEZE_STATUS_ACTIVE,
        frozen_at=datetime.utcnow()
    )

    db.add(freeze_record)
    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_FREEZE_CREATED, event_ref_id=freeze_number)
    return freeze_record


def check_and_process_expired_alerts(db: Session) -> Dict[str, Any]:
    today = date.today()
    active_alerts = db.query(models.LCAlert).filter(
        models.LCAlert.status.in_([models.ALERT_STATUS_ACTIVE, models.ALERT_STATUS_ACKNOWLEDGED])
    ).all()

    expired_count = 0
    freeze_count = 0

    for alert in active_alerts:
        if alert.target_date < today and alert.status != models.ALERT_STATUS_EXPIRED:
            alert.status = models.ALERT_STATUS_EXPIRED
            expired_count += 1

            lc = get_letter_of_credit_by_id(db, alert.lc_id)
            if not lc:
                continue

            if alert.alert_type == models.ALERT_TYPE_SHIPMENT:
                if not has_active_freeze(db, lc.id, models.FREEZE_TYPE_SHIPMENT_EXPIRED):
                    create_freeze_record(
                        db, lc,
                        models.FREEZE_TYPE_SHIPMENT_EXPIRED,
                        f"最迟装运日 {alert.target_date} 已过期，禁止新交单提交"
                    )
                    freeze_count += 1

            elif alert.alert_type == models.ALERT_TYPE_PRESENTATION:
                if not has_active_freeze(db, lc.id, models.FREEZE_TYPE_PRESENTATION_EXPIRED):
                    create_freeze_record(
                        db, lc,
                        models.FREEZE_TYPE_PRESENTATION_EXPIRED,
                        f"最迟交单日 {alert.target_date} 已过期，禁止修改重提"
                    )
                    freeze_count += 1

            elif alert.alert_type == models.ALERT_TYPE_EXPIRY:
                if not has_active_freeze(db, lc.id, models.FREEZE_TYPE_EXPIRY_EXPIRED):
                    create_freeze_record(
                        db, lc,
                        models.FREEZE_TYPE_EXPIRY_EXPIRED,
                        f"信用证到期日 {alert.target_date} 已过期，信用证完全冻结"
                    )
                    freeze_count += 1

    if expired_count > 0 or freeze_count > 0:
        db.commit()

    return {
        "expired_alerts": expired_count,
        "new_freezes": freeze_count
    }


def get_all_active_freezes_by_lc_id(db: Session, lc_id: int) -> List[models.LCFreezeRecord]:
    return db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.lc_id == lc_id,
        models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
    ).all()


def check_lc_frozen_for_submission(db: Session, lc_id: int) -> Optional[str]:
    active_freezes = get_all_active_freezes_by_lc_id(db, lc_id)
    if not active_freezes:
        return None

    for freeze in active_freezes:
        if freeze.freeze_type in [
            models.FREEZE_TYPE_EXPIRY_EXPIRED,
            models.FREEZE_TYPE_SHIPMENT_EXPIRED
        ]:
            return freeze.reason

    return None


def check_lc_frozen_for_resubmission(db: Session, lc_id: int) -> Optional[str]:
    active_freezes = get_all_active_freezes_by_lc_id(db, lc_id)
    if not active_freezes:
        return None

    for freeze in active_freezes:
        if freeze.freeze_type in [
            models.FREEZE_TYPE_EXPIRY_EXPIRED,
            models.FREEZE_TYPE_PRESENTATION_EXPIRED
        ]:
            return freeze.reason

    return None


def check_lc_frozen_for_amendment(db: Session, lc_id: int) -> Optional[str]:
    active_freezes = get_all_active_freezes_by_lc_id(db, lc_id)
    if not active_freezes:
        return None

    for freeze in active_freezes:
        if freeze.freeze_type == models.FREEZE_TYPE_EXPIRY_EXPIRED:
            return freeze.reason

    return None


def get_freeze_records_by_lc(db: Session, lc_number: str) -> List[models.LCFreezeRecord]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")
    return db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.lc_id == lc.id
    ).order_by(models.LCFreezeRecord.created_at.desc()).all()


def get_freeze_record_by_number(db: Session, freeze_number: str) -> Optional[models.LCFreezeRecord]:
    return db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.freeze_number == freeze_number
    ).first()


def release_freeze(
    db: Session,
    freeze_number: str,
    released_by: str,
    release_reason: str
) -> models.LCFreezeRecord:
    freeze_record = get_freeze_record_by_number(db, freeze_number)
    if not freeze_record:
        raise ValueError(f"冻结记录 {freeze_number} 不存在")

    if freeze_record.status == models.FREEZE_STATUS_RELEASED:
        raise ValueError(f"冻结记录 {freeze_number} 已被解除")

    freeze_record.status = models.FREEZE_STATUS_RELEASED
    freeze_record.released_at = datetime.utcnow()
    freeze_record.released_by = released_by
    freeze_record.release_reason = release_reason

    db.flush()
    lc = get_letter_of_credit_by_id(db, freeze_record.lc_id)
    if lc:
        dispatch_notifications(db, lc, models.EVENT_TYPE_FREEZE_RELEASED, event_ref_id=freeze_number)

    db.commit()
    db.refresh(freeze_record)
    return freeze_record


def get_all_active_freezes(db: Session, skip: int = 0, limit: int = 100) -> List[models.LCFreezeRecord]:
    return db.query(models.LCFreezeRecord).filter(
        models.LCFreezeRecord.status == models.FREEZE_STATUS_ACTIVE
    ).order_by(models.LCFreezeRecord.frozen_at.desc()).offset(skip).limit(limit).all()


def generate_swift_message_number(db: Session, lc_number: str, message_type: str) -> str:
    from sqlalchemy import func
    date_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"SWIFT-{message_type}-{lc_number}-{date_str}-"
    count = db.query(func.count(models.SwiftMessageQueue.id)).filter(
        models.SwiftMessageQueue.message_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def create_swift_message(
    db: Session,
    message_type: str,
    lc_number: str,
    raw_message: str,
    lc_id: Optional[int] = None,
) -> models.SwiftMessageQueue:
    message_number = generate_swift_message_number(db, lc_number, message_type)

    queue_item = models.SwiftMessageQueue(
        message_number=message_number,
        message_type=message_type,
        lc_number=lc_number,
        lc_id=lc_id,
        raw_message=raw_message,
        status=models.SWIFT_SEND_STATUS_PENDING,
    )
    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)
    return queue_item


def generate_and_enqueue_mt700(db: Session, lc_number: str) -> models.SwiftMessageQueue:
    from app.swift import generate_mt700

    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    raw_message = generate_mt700(lc)
    return create_swift_message(
        db,
        models.SWIFT_MSG_TYPE_MT700,
        lc_number,
        raw_message,
        lc_id=lc.id,
    )


def generate_and_enqueue_mt707(db: Session, amendment_number: str) -> models.SwiftMessageQueue:
    from app.swift import generate_mt707

    amendment = get_amendment_by_number(db, amendment_number)
    if not amendment:
        raise ValueError(f"修改编号 {amendment_number} 不存在")

    lc = get_letter_of_credit_by_id(db, amendment.lc_id)
    if not lc:
        raise ValueError("关联信用证不存在")

    raw_message = generate_mt707(amendment, lc)
    return create_swift_message(
        db,
        models.SWIFT_MSG_TYPE_MT707,
        lc.lc_number,
        raw_message,
        lc_id=lc.id,
    )


def generate_and_enqueue_mt799(db: Session, lc_number: str, narrative: str) -> models.SwiftMessageQueue:
    from app.swift import generate_mt799

    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    raw_message = generate_mt799(lc_number, narrative)
    return create_swift_message(
        db,
        models.SWIFT_MSG_TYPE_MT799,
        lc_number,
        raw_message,
        lc_id=lc.id,
    )


def get_swift_message_by_number(db: Session, message_number: str) -> Optional[models.SwiftMessageQueue]:
    return db.query(models.SwiftMessageQueue).filter(
        models.SwiftMessageQueue.message_number == message_number
    ).first()


def get_swift_messages_by_lc(
    db: Session,
    lc_number: str,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.SwiftMessageQueue]:
    query = db.query(models.SwiftMessageQueue).filter(
        models.SwiftMessageQueue.lc_number == lc_number
    )
    if status:
        query = query.filter(models.SwiftMessageQueue.status == status)
    return query.order_by(models.SwiftMessageQueue.created_at.desc()).offset(skip).limit(limit).all()


def get_swift_messages_by_time_range(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    lc_number: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.SwiftMessageQueue]:
    query = db.query(models.SwiftMessageQueue).filter(
        models.SwiftMessageQueue.created_at >= start_time,
        models.SwiftMessageQueue.created_at <= end_time,
    )
    if lc_number:
        query = query.filter(models.SwiftMessageQueue.lc_number == lc_number)
    if status:
        query = query.filter(models.SwiftMessageQueue.status == status)
    return query.order_by(models.SwiftMessageQueue.created_at.desc()).offset(skip).limit(limit).all()


def resend_swift_message(db: Session, message_number: str) -> models.SwiftMessageQueue:
    msg = get_swift_message_by_number(db, message_number)
    if not msg:
        raise ValueError(f"报文 {message_number} 不存在")
    if msg.status != models.SWIFT_SEND_STATUS_FAILED:
        raise ValueError(f"只有 failed 状态的报文可以重发，当前状态: {msg.status}")
    msg.status = models.SWIFT_SEND_STATUS_PENDING
    msg.sent_at = None
    db.commit()
    db.refresh(msg)
    return msg


def parse_and_process_swift_message(db: Session, raw_message: str) -> Dict[str, Any]:
    from app.swift import (
        parse_swift_message,
        validate_swift_message,
        map_tags_to_fields,
        extract_lc_number_from_tags,
        extract_lc_data_from_mt700,
        extract_amendment_data_from_mt707,
    )

    message_type, tags, tag_order_list = parse_swift_message(raw_message)

    errors = validate_swift_message(message_type, tags)
    if errors:
        raise ValueError(f"报文校验失败: {'; '.join(errors)}")

    fields = map_tags_to_fields(message_type, tags)
    lc_number = extract_lc_number_from_tags(message_type, tags)

    created_resource_id = None
    created_resource_type = None
    missing_fields = []

    if message_type == models.SWIFT_MSG_TYPE_MT700:
        lc_data, missing_fields = extract_lc_data_from_mt700(tags)
        existing = get_letter_of_credit_by_number(db, lc_data.get("lc_number", ""))
        if existing:
            raise ValueError(f"信用证编号 {lc_data.get('lc_number')} 已存在，无法通过MT700报文自动创建")
        lc = _create_lc_from_swift_mt700(db, lc_data, missing_fields)
        created_resource_id = lc.id
        created_resource_type = "letter_of_credit"

    elif message_type == models.SWIFT_MSG_TYPE_MT707:
        amendment_data = extract_amendment_data_from_mt707(tags)
        lc_num = amendment_data.get("lc_number", "")
        lc = get_letter_of_credit_by_number(db, lc_num)
        if not lc:
            raise ValueError(f"信用证 {lc_num} 不存在，无法通过MT707报文自动创建修改")
        amendment = _create_amendment_from_swift_mt707(db, lc, amendment_data)
        created_resource_id = amendment.id
        created_resource_type = "amendment"

    return {
        "message_type": message_type,
        "lc_number": lc_number,
        "fields": fields,
        "created_resource_id": created_resource_id,
        "created_resource_type": created_resource_type,
        "missing_fields": missing_fields,
    }


def _create_lc_from_swift_mt700(
    db: Session,
    lc_data: Dict[str, Any],
    missing_fields: List[str],
) -> models.LetterOfCredit:
    critical_missing = []
    for field in LC_REQUIRED_FIELDS_FOR_CREATE:
        if field not in lc_data:
            critical_missing.append(field)
    if critical_missing:
        raise ValueError(
            f"报文中缺少创建信用证的必要字段，无法自动创建: {', '.join(critical_missing)}。"
            f"完整缺失字段列表: {', '.join(missing_fields)}"
        )

    currency = lc_data.get("currency", "USD")
    check_and_occupy_credit_line(
        db, lc_data["applicant_name"], currency, lc_data["amount"], lc_data["lc_number"]
    )

    lc = models.LetterOfCredit(
        lc_number=lc_data["lc_number"],
        issuing_bank=lc_data.get("issuing_bank", ""),
        beneficiary_name=lc_data["beneficiary_name"],
        applicant_name=lc_data["applicant_name"],
        currency=currency,
        amount=lc_data["amount"],
        latest_shipment_date=lc_data["latest_shipment_date"],
        latest_presentation_date=lc_data["latest_presentation_date"],
        expiry_date=lc_data["expiry_date"],
        transport_mode=lc_data.get("transport_mode", "海运"),
        port_of_loading=lc_data.get("port_of_loading", ""),
        port_of_discharge=lc_data.get("port_of_discharge", ""),
        partial_shipment_allowed=lc_data.get("partial_shipment_allowed", False),
        transshipment_allowed=lc_data.get("transshipment_allowed", False),
        goods_description=lc_data.get("goods_description", ""),
        additional_terms=lc_data.get("additional_terms", []),
        fee_tier="standard",
    )
    db.add(lc)
    db.flush()

    doc_reqs = lc_data.get("document_requirements", [])
    if doc_reqs:
        for req in doc_reqs:
            db.add(models.DocumentRequirement(
                lc_id=lc.id,
                document_type=req.get("document_type", ""),
                original_copies=req.get("original_copies", 0),
                copy_copies=req.get("copy_copies", 0),
            ))
    else:
        missing_fields.append("document_requirements (标签:46A)")

    associate_lc_parties(db, lc)
    dispatch_notifications(db, lc, models.EVENT_TYPE_LC_CREATED)

    db.commit()
    db.refresh(lc)
    return lc


def _create_amendment_from_swift_mt707(
    db: Session,
    lc: models.LetterOfCredit,
    amendment_data: Dict[str, Any],
) -> models.LCAmendment:
    field_changes = amendment_data.get("field_changes", [])
    for change in field_changes:
        field_name = change.get("field_name")
        if field_name in ["amount", "latest_shipment_date", "latest_presentation_date", "expiry_date"]:
            actual = _get_field_actual_value(lc, field_name)
            change["old_value"] = _format_value(field_name, actual) if actual is not None else None

    if has_pending_amendment(db, lc.id):
        raise ValueError(f"信用证 {lc.lc_number} 已有一个待处理的修改，请先处理后再发起新修改")

    snapshot_before = lc_to_snapshot_dict(lc)
    sequence_number = get_next_amendment_sequence(db, lc.id)
    amendment_number = f"{lc.lc_number}-AMD-{sequence_number:03d}"
    expiry_time = datetime.utcnow() + timedelta(days=AMENDMENT_EXPIRY_DAYS)

    amendment = models.LCAmendment(
        lc_id=lc.id,
        amendment_number=amendment_number,
        sequence_number=sequence_number,
        status=AMENDMENT_STATUS_PENDING,
        field_changes=field_changes,
        snapshot_before=snapshot_before,
        snapshot_after=None,
        expiry_time=expiry_time,
    )
    db.add(amendment)
    db.flush()
    dispatch_notifications(db, lc, models.EVENT_TYPE_AMENDMENT_CREATED, event_ref_id=amendment_number)

    db.commit()
    db.refresh(amendment)
    return amendment


def create_party(db: Session, party_data: schemas.PartyCreate) -> models.Party:
    role_value = party_data.role.value if hasattr(party_data.role, 'value') else party_data.role
    if role_value not in models.VALID_PARTY_ROLES:
        raise ValueError(f"无效的角色类型: {role_value}，允许值: {', '.join(models.VALID_PARTY_ROLES)}")

    existing = db.query(models.Party).filter(
        models.Party.name == party_data.name,
        models.Party.role == role_value
    ).first()
    if existing:
        raise ValueError(f"同名同角色的参与方已存在: {party_data.name} ({role_value})")

    db_party = models.Party(
        name=party_data.name,
        role=role_value,
        contact=party_data.contact
    )
    db.add(db_party)
    db.flush()

    default_events = models.DEFAULT_SUBSCRIPTIONS.get(role_value, [])
    for event_type in default_events:
        db_sub = models.PartySubscription(
            party_id=db_party.id,
            event_type=event_type,
            is_active=True
        )
        db.add(db_sub)

    db.commit()
    db.refresh(db_party)
    return db_party


def get_party_by_id(db: Session, party_id: int) -> Optional[models.Party]:
    return db.query(models.Party).filter(models.Party.id == party_id).first()


def get_party_by_name_and_role(db: Session, name: str, role: str) -> Optional[models.Party]:
    return db.query(models.Party).filter(
        models.Party.name == name,
        models.Party.role == role
    ).first()


def get_all_parties(db: Session, skip: int = 0, limit: int = 100, role: Optional[str] = None) -> List[models.Party]:
    query = db.query(models.Party)
    if role:
        query = query.filter(models.Party.role == role)
    return query.order_by(models.Party.created_at.desc()).offset(skip).limit(limit).all()


def get_party_subscriptions(db: Session, party_id: int) -> List[models.PartySubscription]:
    return db.query(models.PartySubscription).filter(
        models.PartySubscription.party_id == party_id
    ).all()


def is_party_subscribed_to(db: Session, party_id: int, event_type: str) -> bool:
    subscription = db.query(models.PartySubscription).filter(
        models.PartySubscription.party_id == party_id,
        models.PartySubscription.event_type == event_type,
        models.PartySubscription.is_active == True
    ).first()
    return subscription is not None


def update_party_subscriptions(
    db: Session,
    party_id: int,
    updates: List[Dict[str, Any]]
) -> List[models.PartySubscription]:
    party = get_party_by_id(db, party_id)
    if not party:
        raise ValueError(f"参与方 {party_id} 不存在")

    existing_subs = {
        sub.event_type: sub
        for sub in get_party_subscriptions(db, party_id)
    }

    for update in updates:
        event_type_val = update["event_type"]
        event_type = event_type_val.value if hasattr(event_type_val, 'value') else event_type_val
        is_active = update["is_active"]

        if event_type not in models.VALID_EVENT_TYPES:
            raise ValueError(f"无效的事件类型: {event_type}，允许值: {', '.join(models.VALID_EVENT_TYPES)}")

        if event_type in existing_subs:
            existing_subs[event_type].is_active = is_active
        else:
            db_sub = models.PartySubscription(
                party_id=party_id,
                event_type=event_type,
                is_active=is_active
            )
            db.add(db_sub)

    db.commit()
    return get_party_subscriptions(db, party_id)


def get_lc_parties(db: Session, lc_id: int) -> List[models.LetterOfCreditParty]:
    return db.query(models.LetterOfCreditParty).filter(
        models.LetterOfCreditParty.lc_id == lc_id
    ).all()


def associate_lc_parties(db: Session, lc: models.LetterOfCredit):
    role_name_map = {
        models.PARTY_ROLE_ISSUING_BANK: lc.issuing_bank,
        models.PARTY_ROLE_BENEFICIARY: lc.beneficiary_name,
        models.PARTY_ROLE_APPLICANT: lc.applicant_name,
    }

    existing = {(lp.role, lp.party_id) for lp in get_lc_parties(db, lc.id)}

    for role, name in role_name_map.items():
        if not name:
            continue
        party = get_party_by_name_and_role(db, name, role)
        if party and (role, party.id) not in existing:
            db_lc_party = models.LetterOfCreditParty(
                lc_id=lc.id,
                party_id=party.id,
                role=role
            )
            db.add(db_lc_party)

    db.flush()


def generate_notification_number(db: Session, lc_number: str, event_type: str, party_id: int) -> str:
    import uuid
    unique_suffix = uuid.uuid4().hex[:8].upper()
    date_str = datetime.utcnow().strftime("%Y%m%d")
    return f"NTF-{lc_number}-{event_type}-{date_str}-{party_id}-{unique_suffix}"


def _build_event_summary(event_type: str, lc: models.LetterOfCredit, ref_id: Optional[str] = None) -> str:
    summaries = {
        models.EVENT_TYPE_LC_CREATED: f"信用证 {lc.lc_number} 已成功开立",
        models.EVENT_TYPE_SUBMISSION_CREATED: f"信用证 {lc.lc_number} 收到新的交单{submission_id_suffix(ref_id)}",
        models.EVENT_TYPE_SUBMISSION_REVIEWED: f"信用证 {lc.lc_number} 的交单{submission_id_suffix(ref_id)} 已完成审核",
        models.EVENT_TYPE_AMENDMENT_CREATED: f"信用证 {lc.lc_number} 收到修改请求{ref_id_suffix(ref_id)}",
        models.EVENT_TYPE_AMENDMENT_ACCEPTED: f"信用证 {lc.lc_number} 的修改{ref_id_suffix(ref_id)} 已被接受",
        models.EVENT_TYPE_AMENDMENT_REJECTED: f"信用证 {lc.lc_number} 的修改{ref_id_suffix(ref_id)} 已被拒绝",
        models.EVENT_TYPE_ALERT_GENERATED: f"信用证 {lc.lc_number} 触发了新的预警{ref_id_suffix(ref_id)}",
        models.EVENT_TYPE_FREEZE_CREATED: f"信用证 {lc.lc_number} 已被冻结{ref_id_suffix(ref_id)}",
        models.EVENT_TYPE_FREEZE_RELEASED: f"信用证 {lc.lc_number} 已解除冻结{ref_id_suffix(ref_id)}",
        models.EVENT_TYPE_TRANSFER_CREATED: f"信用证 {lc.lc_number} 创建了转让{ref_id_suffix(ref_id)}",
        models.EVENT_TYPE_BACK_TO_BACK_CREATED: f"基于信用证 {lc.lc_number} 创建了背对背证{ref_id_suffix(ref_id)}",
    }
    return summaries.get(event_type, f"信用证 {lc.lc_number} 发生事件: {event_type}")


def ref_id_suffix(ref_id: Optional[str]) -> str:
    return f" ({ref_id})" if ref_id else ""


def submission_id_suffix(submission_id: Optional[str]) -> str:
    return f" (交单编号: {submission_id})" if submission_id else ""


def has_existing_notification(
    db: Session,
    party_id: int,
    event_type: str,
    lc_id: int,
    event_ref_id: Optional[str]
) -> bool:
    query = db.query(models.Notification).filter(
        models.Notification.party_id == party_id,
        models.Notification.event_type == event_type,
        models.Notification.lc_id == lc_id,
    )
    if event_ref_id:
        query = query.filter(models.Notification.event_ref_id == event_ref_id)
    return query.first() is not None


def dispatch_notifications(
    db: Session,
    lc: models.LetterOfCredit,
    event_type: str,
    event_ref_id: Optional[str] = None,
    event_summary_override: Optional[str] = None
) -> List[models.Notification]:
    if event_type not in models.VALID_EVENT_TYPES:
        raise ValueError(f"无效的事件类型: {event_type}")

    lc_parties = get_lc_parties(db, lc.id)
    notifications = []

    for lc_party in lc_parties:
        if not is_party_subscribed_to(db, lc_party.party_id, event_type):
            continue

        if has_existing_notification(db, lc_party.party_id, event_type, lc.id, event_ref_id):
            continue

        summary = event_summary_override or _build_event_summary(event_type, lc, event_ref_id)
        notification_number = generate_notification_number(db, lc.lc_number, event_type, lc_party.party_id)

        notification = models.Notification(
            notification_number=notification_number,
            party_id=lc_party.party_id,
            event_type=event_type,
            lc_id=lc.id,
            event_summary=summary,
            event_ref_id=event_ref_id,
            status=models.NOTIFICATION_STATUS_UNREAD,
        )
        db.add(notification)
        notifications.append(notification)

    if notifications:
        db.commit()
        for n in notifications:
            db.refresh(n)

    return notifications


def get_notifications_by_party(
    db: Session,
    party_id: int,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Dict[str, Any]]:
    query = db.query(models.Notification).filter(models.Notification.party_id == party_id)

    if status:
        if status not in models.VALID_NOTIFICATION_STATUSES:
            raise ValueError(f"无效的通知状态: {status}，允许值: {', '.join(models.VALID_NOTIFICATION_STATUSES)}")
        query = query.filter(models.Notification.status == status)

    if start_time:
        query = query.filter(models.Notification.created_at >= start_time)
    if end_time:
        query = query.filter(models.Notification.created_at <= end_time)

    notifications = query.order_by(models.Notification.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for n in notifications:
        result.append(_notification_to_dict(db, n))
    return result


def _notification_to_dict(db: Session, n: models.Notification) -> Dict[str, Any]:
    party = get_party_by_id(db, n.party_id)
    lc = get_letter_of_credit_by_id(db, n.lc_id)
    return {
        "id": n.id,
        "notification_number": n.notification_number,
        "party_id": n.party_id,
        "party_name": party.name if party else None,
        "event_type": n.event_type,
        "lc_id": n.lc_id,
        "lc_number": lc.lc_number if lc else None,
        "event_summary": n.event_summary,
        "event_ref_id": n.event_ref_id,
        "status": n.status,
        "read_at": n.read_at,
        "archived_at": n.archived_at,
        "created_at": n.created_at,
    }


def mark_notifications_read(db: Session, party_id: int, notification_ids: List[int]) -> int:
    if not notification_ids:
        return 0

    notifications = db.query(models.Notification).filter(
        models.Notification.party_id == party_id,
        models.Notification.id.in_(notification_ids)
    ).all()

    count = 0
    for n in notifications:
        if n.status == models.NOTIFICATION_STATUS_UNREAD:
            n.status = models.NOTIFICATION_STATUS_READ
            n.read_at = datetime.utcnow()
            count += 1

    if count > 0:
        db.commit()
    return count


def archive_notifications(db: Session, party_id: int, notification_ids: List[int]) -> int:
    if not notification_ids:
        return 0

    notifications = db.query(models.Notification).filter(
        models.Notification.party_id == party_id,
        models.Notification.id.in_(notification_ids)
    ).all()

    count = 0
    for n in notifications:
        if n.status != models.NOTIFICATION_STATUS_ARCHIVED:
            n.status = models.NOTIFICATION_STATUS_ARCHIVED
            n.archived_at = datetime.utcnow()
            count += 1

    if count > 0:
        db.commit()
    return count


def get_lc_event_stream(
    db: Session,
    lc_id: int,
    skip: int = 0,
    limit: int = 200
) -> List[Dict[str, Any]]:
    notifications = db.query(models.Notification).filter(
        models.Notification.lc_id == lc_id
    ).order_by(models.Notification.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    seen_keys = set()
    for n in notifications:
        key = (n.event_type, n.event_ref_id, n.party_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        party = get_party_by_id(db, n.party_id)
        result.append({
            "id": n.id,
            "event_type": n.event_type,
            "event_summary": n.event_summary,
            "event_ref_id": n.event_ref_id,
            "lc_id": n.lc_id,
            "party_id": n.party_id,
            "party_name": party.name if party else None,
            "created_at": n.created_at,
        })
    return result


def create_lc_with_parties(db: Session, lc_data: schemas.LetterOfCreditCreate) -> models.LetterOfCredit:
    lc = create_letter_of_credit(db, lc_data)
    associate_lc_parties(db, lc)
    dispatch_notifications(db, lc, models.EVENT_TYPE_LC_CREATED)
    db.commit()
    db.refresh(lc)
    return lc


def create_rule_version(db: Session, data: schemas.RuleVersionCreate) -> models.RuleVersion:
    existing = db.query(models.RuleVersion).filter(
        models.RuleVersion.version_number == data.version_number
    ).first()
    if existing:
        raise ValueError(f"版本号 {data.version_number} 已存在")

    rules_dict = data.rules.model_dump()

    for cat in rules_dict.get("enabled_categories", []):
        if cat not in VALID_CHECK_CATEGORIES:
            raise ValueError(f"无效的检查类别: {cat}，允许值: {', '.join(VALID_CHECK_CATEGORIES)}")

    if rules_dict.get("amount_tolerance") is not None and rules_dict["amount_tolerance"] < 0:
        raise ValueError("金额容差阈值不能为负数")

    if rules_dict.get("date_tolerance_days") is not None and rules_dict["date_tolerance_days"] < 0:
        raise ValueError("日期容差天数不能为负数")

    rule_version = models.RuleVersion(
        version_number=data.version_number,
        status=RULE_VERSION_STATUS_DRAFT,
        rules=rules_dict,
        grayscale_percentage=0,
        description=data.description,
    )
    db.add(rule_version)
    db.commit()
    db.refresh(rule_version)
    return rule_version


def get_rule_version_by_number(db: Session, version_number: str) -> Optional[models.RuleVersion]:
    return db.query(models.RuleVersion).filter(
        models.RuleVersion.version_number == version_number
    ).first()


def get_rule_version_by_id(db: Session, version_id: int) -> Optional[models.RuleVersion]:
    return db.query(models.RuleVersion).filter(models.RuleVersion.id == version_id).first()


def get_all_rule_versions(db: Session, status: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[models.RuleVersion]:
    query = db.query(models.RuleVersion)
    if status:
        if status not in VALID_RULE_VERSION_STATUSES:
            raise ValueError(f"无效的版本状态: {status}，允许值: {', '.join(VALID_RULE_VERSION_STATUSES)}")
        query = query.filter(models.RuleVersion.status == status)
    return query.order_by(models.RuleVersion.created_at.desc()).offset(skip).limit(limit).all()


def update_rule_version(db: Session, version_number: str, data: schemas.RuleVersionUpdate) -> models.RuleVersion:
    rule_version = get_rule_version_by_number(db, version_number)
    if not rule_version:
        raise ValueError(f"版本 {version_number} 不存在")

    if rule_version.status != RULE_VERSION_STATUS_DRAFT:
        raise ValueError(f"只有 draft 状态的版本可以编辑，当前状态: {rule_version.status}")

    if data.rules is not None:
        rules_dict = data.rules.model_dump()
        for cat in rules_dict.get("enabled_categories", []):
            if cat not in VALID_CHECK_CATEGORIES:
                raise ValueError(f"无效的检查类别: {cat}")
        if rules_dict.get("amount_tolerance") is not None and rules_dict["amount_tolerance"] < 0:
            raise ValueError("金额容差阈值不能为负数")
        if rules_dict.get("date_tolerance_days") is not None and rules_dict["date_tolerance_days"] < 0:
            raise ValueError("日期容差天数不能为负数")
        rule_version.rules = rules_dict

    if data.description is not None:
        rule_version.description = data.description

    rule_version.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule_version)
    return rule_version


def publish_rule_version_to_testing(db: Session, version_number: str, grayscale_percentage: int) -> models.RuleVersion:
    rule_version = get_rule_version_by_number(db, version_number)
    if not rule_version:
        raise ValueError(f"版本 {version_number} 不存在")

    if rule_version.status != RULE_VERSION_STATUS_DRAFT:
        raise ValueError(f"只有 draft 状态的版本可以发布为 testing，当前状态: {rule_version.status}")

    if grayscale_percentage < 0 or grayscale_percentage > 100:
        raise ValueError("灰度比例必须在 0-100 之间")

    existing_testing = db.query(models.RuleVersion).filter(
        models.RuleVersion.status == RULE_VERSION_STATUS_TESTING
    ).first()
    if existing_testing:
        raise ValueError(f"已有 testing 版本: {existing_testing.version_number}，请先将其发布为 active 或回退为 draft")

    rule_version.status = RULE_VERSION_STATUS_TESTING
    rule_version.grayscale_percentage = grayscale_percentage
    rule_version.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule_version)
    return rule_version


def publish_rule_version_to_active(db: Session, version_number: str) -> models.RuleVersion:
    rule_version = get_rule_version_by_number(db, version_number)
    if not rule_version:
        raise ValueError(f"版本 {version_number} 不存在")

    if rule_version.status != RULE_VERSION_STATUS_TESTING:
        raise ValueError(f"只有 testing 状态的版本可以发布为 active，当前状态: {rule_version.status}")

    current_active = db.query(models.RuleVersion).filter(
        models.RuleVersion.status == RULE_VERSION_STATUS_ACTIVE
    ).first()
    if current_active:
        current_active.status = RULE_VERSION_STATUS_ARCHIVED
        current_active.archived_at = datetime.utcnow()
        current_active.updated_at = datetime.utcnow()

    rule_version.status = RULE_VERSION_STATUS_ACTIVE
    rule_version.grayscale_percentage = 100
    rule_version.activated_at = datetime.utcnow()
    rule_version.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(rule_version)
    return rule_version


def revert_testing_to_draft(db: Session, version_number: str) -> models.RuleVersion:
    rule_version = get_rule_version_by_number(db, version_number)
    if not rule_version:
        raise ValueError(f"版本 {version_number} 不存在")

    if rule_version.status != RULE_VERSION_STATUS_TESTING:
        raise ValueError(f"只有 testing 状态的版本可以回退为 draft，当前状态: {rule_version.status}")

    rule_version.status = RULE_VERSION_STATUS_DRAFT
    rule_version.grayscale_percentage = 0
    rule_version.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule_version)
    return rule_version


def compare_rule_versions(db: Session, version_a: str, version_b: str) -> Dict[str, Any]:
    rv_a = get_rule_version_by_number(db, version_a)
    rv_b = get_rule_version_by_number(db, version_b)
    if not rv_a:
        raise ValueError(f"版本 {version_a} 不存在")
    if not rv_b:
        raise ValueError(f"版本 {version_b} 不存在")

    differences = []
    rules_a = rv_a.rules or {}
    rules_b = rv_b.rules or {}

    simple_fields = ["amount_tolerance", "date_tolerance_days", "name_case_sensitive"]
    for field in simple_fields:
        val_a = rules_a.get(field)
        val_b = rules_b.get(field)
        if val_a != val_b:
            differences.append({
                "field": field,
                "old_value": val_a,
                "new_value": val_b,
                "path": field,
            })

    cats_a = set(rules_a.get("enabled_categories", []))
    cats_b = set(rules_b.get("enabled_categories", []))
    if cats_a != cats_b:
        differences.append({
            "field": "enabled_categories",
            "old_value": sorted(cats_a),
            "new_value": sorted(cats_b),
            "path": "enabled_categories",
        })

    overrides_a = rules_a.get("severity_overrides", {})
    overrides_b = rules_b.get("severity_overrides", {})
    all_override_keys = set(list(overrides_a.keys()) + list(overrides_b.keys()))
    override_diffs = {}
    for key in all_override_keys:
        val_a = overrides_a.get(key)
        val_b = overrides_b.get(key)
        if val_a != val_b:
            override_diffs[key] = {"old_value": val_a, "new_value": val_b}
    if override_diffs:
        differences.append({
            "field": "severity_overrides",
            "old_value": overrides_a,
            "new_value": overrides_b,
            "path": "severity_overrides",
        })

    return {
        "version_a": version_a,
        "version_b": version_b,
        "differences": differences,
    }


def get_submissions_by_rule_version(db: Session, version_number: str, skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    rule_version = get_rule_version_by_number(db, version_number)
    if not rule_version:
        raise ValueError(f"版本 {version_number} 不存在")

    audit_records = db.query(models.AuditRecord).filter(
        models.AuditRecord.rule_version_id == rule_version.id
    ).order_by(models.AuditRecord.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "rule_version_number": version_number,
        "total_count": len(audit_records),
        "submissions": audit_records,
    }


def resolve_rule_version_for_audit(db: Session) -> Optional[models.RuleVersion]:
    testing_version = db.query(models.RuleVersion).filter(
        models.RuleVersion.status == RULE_VERSION_STATUS_TESTING
    ).first()

    if testing_version and testing_version.grayscale_percentage > 0:
        if random.randint(1, 100) <= testing_version.grayscale_percentage:
            return testing_version

    active_version = db.query(models.RuleVersion).filter(
        models.RuleVersion.status == RULE_VERSION_STATUS_ACTIVE
    ).first()

    return active_version


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def add_business_days(start_date: date, days: int) -> date:
    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def generate_payment_number(db: Session, lc_number: str) -> str:
    from sqlalchemy import func
    date_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"PAY-{lc_number}-{date_str}-"
    count = db.query(func.count(models.Payment.id)).filter(
        models.Payment.payment_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def _add_payment_status_history(
    db: Session,
    payment: models.Payment,
    from_status: Optional[str],
    to_status: str,
    changed_by: Optional[str] = None,
    remark: Optional[str] = None,
) -> models.PaymentStatusHistory:
    history = models.PaymentStatusHistory(
        payment_id=payment.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        changed_at=datetime.utcnow(),
        remark=remark,
    )
    db.add(history)
    return history


def calculate_maturity_date(
    db: Session,
    lc: models.LetterOfCredit,
    audit_record: models.AuditRecord,
    application_date: Optional[date] = None,
) -> date:
    if application_date is None:
        application_date = date.today()

    payment_method = lc.payment_method or models.PAYMENT_METHOD_SIGHT

    if payment_method == models.PAYMENT_METHOD_SIGHT:
        return add_business_days(application_date, models.SIGHT_PROCESSING_DAYS)

    elif payment_method == models.PAYMENT_METHOD_USANCE:
        usance_days = lc.usance_days
        if usance_days is None or usance_days <= 0:
            raise ValueError("远期付款必须指定远期天数")

        usance_basis = lc.usance_basis
        if usance_basis not in models.VALID_USANCE_BASES:
            raise ValueError(f"无效的远期起算基准: {usance_basis}")

        if usance_basis == models.USANCE_BASIS_PRESENTATION_DATE:
            basis_date = audit_record.presentation_date
        elif usance_basis == models.USANCE_BASIS_SHIPMENT_DATE:
            basis_date = _get_shipment_date_from_docs(db, audit_record)
        elif usance_basis == models.USANCE_BASIS_BL_DATE:
            basis_date = _get_bl_date_from_docs(db, audit_record)
        else:
            basis_date = audit_record.presentation_date

        if basis_date is None:
            raise ValueError(f"无法获取{usance_basis}作为起算基准日期")

        return add_business_days(basis_date, usance_days)

    elif payment_method == models.PAYMENT_METHOD_DEFERRED:
        if lc.deferred_payment_date is None:
            raise ValueError("延期付款必须指定付款日期")
        return lc.deferred_payment_date

    else:
        raise ValueError(f"无效的付款方式: {payment_method}")


def _get_shipment_date_from_docs(db: Session, audit_record: models.AuditRecord) -> Optional[date]:
    docs = get_documents_by_submission(db, audit_record.submission_id)
    for doc in docs:
        if doc.document_type == "bill_of_lading":
            shipment_date_str = doc.content.get("shipment_date")
            if shipment_date_str:
                if isinstance(shipment_date_str, str):
                    return date.fromisoformat(shipment_date_str)
                elif isinstance(shipment_date_str, date):
                    return shipment_date_str
    return None


def _get_bl_date_from_docs(db: Session, audit_record: models.AuditRecord) -> Optional[date]:
    docs = get_documents_by_submission(db, audit_record.submission_id)
    for doc in docs:
        if doc.document_type == "bill_of_lading":
            bl_date_str = doc.content.get("bl_date") or doc.content.get("issue_date")
            if bl_date_str:
                if isinstance(bl_date_str, str):
                    return date.fromisoformat(bl_date_str)
                elif isinstance(bl_date_str, date):
                    return bl_date_str
    return None


def _get_invoice_amount_from_docs(db: Session, audit_record: models.AuditRecord) -> float:
    docs = get_documents_by_submission(db, audit_record.submission_id)
    for doc in docs:
        if doc.document_type == "invoice":
            total_amount = doc.content.get("total_amount")
            if total_amount is not None:
                return float(total_amount)
    return 0.0


def _is_audit_eligible_for_payment(audit_record: models.AuditRecord) -> bool:
    if audit_record.conclusion == "compliant":
        return True
    if audit_record.conclusion == "minor_discrepancy" and audit_record.review_status == models.REVIEW_STATUS_REVIEWED:
        return True
    return False


def create_payment_application(db: Session, submission_id: str) -> models.Payment:
    audit_record = get_audit_record_by_submission(db, submission_id)
    if not audit_record:
        raise ValueError(f"交单记录 {submission_id} 不存在")

    lc = get_letter_of_credit_by_id(db, audit_record.lc_id)
    if not lc:
        raise ValueError(f"信用证不存在")

    existing_payment = db.query(models.Payment).filter(
        models.Payment.submission_id == submission_id,
        models.Payment.status != models.PAYMENT_STATUS_REJECTED
    ).first()
    if existing_payment:
        raise ValueError(f"交单 {submission_id} 已有有效付款申请: {existing_payment.payment_number}")

    if not _is_audit_eligible_for_payment(audit_record):
        raise ValueError(
            f"交单 {submission_id} 不符合付款条件。"
            f"审核结论: {audit_record.conclusion}, 复核状态: {audit_record.review_status}。"
            f"需要 compliant 或 minor_discrepancy且复核完成(reviewed)才能发起付款。"
        )

    payment_amount = _get_invoice_amount_from_docs(db, audit_record)
    if payment_amount <= 0:
        raise ValueError("无法从发票中获取付款金额")

    application_date = date.today()
    maturity_date = calculate_maturity_date(db, lc, audit_record, application_date)

    payment_number = generate_payment_number(db, lc.lc_number)

    initial_status = models.PAYMENT_STATUS_PENDING

    payment = models.Payment(
        payment_number=payment_number,
        lc_id=lc.id,
        submission_id=submission_id,
        audit_record_id=audit_record.id,
        payment_amount=payment_amount,
        currency=lc.currency,
        payment_method=lc.payment_method or models.PAYMENT_METHOD_SIGHT,
        maturity_date=maturity_date,
        status=initial_status,
        total_paid_amount=0.0,
    )
    db.add(payment)
    db.flush()

    _add_payment_status_history(db, payment, None, initial_status, remark="付款申请创建")

    db.commit()
    db.refresh(payment)
    return payment


def accept_payment(db: Session, payment_number: str, accepted_by: Optional[str] = None) -> models.Payment:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    if payment.payment_method != models.PAYMENT_METHOD_USANCE:
        raise ValueError(f"只有远期付款(usance)需要承兑，当前付款方式: {payment.payment_method}")

    if payment.status == models.PAYMENT_STATUS_ACCEPTED:
        return payment

    if payment.status != models.PAYMENT_STATUS_PENDING:
        raise ValueError(f"只有 pending 状态的付款可以承兑，当前状态: {payment.status}")

    old_status = payment.status
    payment.status = models.PAYMENT_STATUS_ACCEPTED
    payment.accepted_at = datetime.utcnow()

    _add_payment_status_history(db, payment, old_status, models.PAYMENT_STATUS_ACCEPTED, changed_by=accepted_by, remark="银行承兑")

    db.commit()
    db.refresh(payment)
    return payment


def reject_payment(db: Session, payment_number: str, rejection_reason: str, rejected_by: Optional[str] = None) -> models.Payment:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    if payment.status != models.PAYMENT_STATUS_PENDING:
        raise ValueError(f"只有 pending 状态的付款可以拒付，当前状态: {payment.status}")

    old_status = payment.status
    payment.status = models.PAYMENT_STATUS_REJECTED
    payment.rejection_reason = rejection_reason

    _add_payment_status_history(db, payment, old_status, models.PAYMENT_STATUS_REJECTED, changed_by=rejected_by, remark=f"拒付: {rejection_reason}")

    fee_records = db.query(models.FeeRecord).filter(
        models.FeeRecord.submission_id == payment.submission_id
    ).all()
    for fee in fee_records:
        fee.status = "cancelled"

    db.commit()
    db.refresh(payment)
    return payment


def settle_payment(
    db: Session,
    payment_number: str,
    payment_date: date,
    amount: Optional[float] = None,
    penalty_amount: Optional[float] = None,
    reference: Optional[str] = None,
    settled_by: Optional[str] = None,
) -> models.Payment:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    if payment.status == models.PAYMENT_STATUS_PAID:
        raise ValueError(f"付款申请 {payment_number} 已全部付清")

    if payment.status == models.PAYMENT_STATUS_REJECTED:
        raise ValueError(f"付款申请 {payment_number} 已被拒付，无法付款")

    check_and_update_overdue_payments(db, payment.lc_id)
    db.refresh(payment)

    if payment.status not in [models.PAYMENT_STATUS_MATURED, models.PAYMENT_STATUS_OVERDUE]:
        raise ValueError(f"只有到期(matured)或逾期(overdue)的付款可以结算，当前状态: {payment.status}。请等待付款到期后再操作。")

    if amount is None:
        amount = payment.payment_amount - payment.total_paid_amount

    if amount <= 0:
        raise ValueError("付款金额必须大于0")

    remaining = payment.payment_amount - payment.total_paid_amount
    if amount > remaining + 0.001:
        raise ValueError(f"付款金额超过剩余应付本金。应付本金: {remaining}, 申请: {amount}")

    lc = get_letter_of_credit_by_id(db, payment.lc_id)
    if not lc.partial_shipment_allowed and abs(amount - remaining) > 0.001:
        raise ValueError("信用证不允许分批装运，必须一次性全额付款")

    penalty_info = calculate_penalty_interest(db, payment, payment_date)
    remaining_penalty = penalty_info["remaining_penalty"]

    if payment.status == models.PAYMENT_STATUS_OVERDUE or remaining_penalty > 0.001:
        if penalty_amount is None:
            raise ValueError(f"该付款已逾期，必须同时支付罚息。当前应付罚息: {remaining_penalty:.2f}")
        if penalty_amount < remaining_penalty - 0.001:
            raise ValueError(f"传入的罚息金额不足。应付罚息: {remaining_penalty:.2f}, 传入罚息: {penalty_amount:.2f}，允许多付不允许少付")
        if penalty_amount < 0:
            raise ValueError("罚息金额不能为负数")
    else:
        if penalty_amount is None:
            penalty_amount = 0.0
        if penalty_amount < 0:
            raise ValueError("罚息金额不能为负数")

    actual_penalty = penalty_amount

    partial_record = models.PartialPaymentRecord(
        payment_id=payment.id,
        amount=amount,
        penalty_amount=actual_penalty,
        payment_date=payment_date,
        reference=reference,
        created_by=settled_by,
    )
    db.add(partial_record)
    db.flush()

    new_total_paid = payment.total_paid_amount + amount
    new_total_penalty_paid = payment.total_penalty_paid + actual_penalty
    payment.total_paid_amount = new_total_paid
    payment.total_penalty_paid = new_total_penalty_paid
    payment.actual_payment_date = payment_date

    old_status = payment.status
    if abs(new_total_paid - payment.payment_amount) < 0.001:
        payment.status = models.PAYMENT_STATUS_PAID
        _add_payment_status_history(db, payment, old_status, models.PAYMENT_STATUS_PAID, changed_by=settled_by, remark=f"全额付款完成(本金:{amount:.2f}, 罚息:{actual_penalty:.2f})")
    else:
        _add_payment_status_history(db, payment, old_status, payment.status, changed_by=settled_by, remark=f"部分付款: 本金{amount:.2f} {payment.currency}, 罚息{actual_penalty:.2f}")

    db.commit()
    db.refresh(payment)
    return payment


def calculate_penalty_interest(
    db: Session,
    payment: models.Payment,
    calc_date: Optional[date] = None,
) -> Dict[str, Any]:
    if calc_date is None:
        calc_date = date.today()

    lc = get_letter_of_credit_by_id(db, payment.lc_id)
    if not lc:
        raise ValueError("关联信用证不存在")

    penalty_rate = lc.penalty_interest_rate if lc.penalty_interest_rate is not None else models.DEFAULT_PENALTY_RATE
    unpaid_amount = payment.payment_amount - payment.total_paid_amount

    penalty_start_date = add_business_days(payment.maturity_date, models.OVERDUE_GRACE_WORKING_DAYS)

    if payment.maturity_date >= calc_date:
        overdue_days = 0
    elif calc_date <= penalty_start_date:
        overdue_days = 0
    else:
        overdue_days = (calc_date - penalty_start_date).days

    if overdue_days <= 0 or unpaid_amount <= 0:
        current_penalty = 0.0
    else:
        current_penalty = round(unpaid_amount * (penalty_rate / 100.0) / 365.0 * overdue_days, 2)

    remaining_penalty = max(0.0, round(current_penalty - payment.total_penalty_paid, 2))

    return {
        "payment_number": payment.payment_number,
        "payment_amount": payment.payment_amount,
        "total_paid_amount": payment.total_paid_amount,
        "unpaid_amount": round(unpaid_amount, 2),
        "penalty_interest_rate": penalty_rate,
        "maturity_date": payment.maturity_date,
        "penalty_start_date": penalty_start_date,
        "calc_date": calc_date,
        "overdue_days": overdue_days,
        "current_penalty": current_penalty,
        "total_penalty_paid": payment.total_penalty_paid,
        "remaining_penalty": remaining_penalty,
    }


def get_penalty_interest(db: Session, payment_number: str, calc_date: Optional[date] = None) -> Dict[str, Any]:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    check_and_update_overdue_payments(db, payment.lc_id)
    db.refresh(payment)

    return calculate_penalty_interest(db, payment, calc_date)


def check_and_update_overdue_payments(db: Session, lc_id: Optional[int] = None, _skip_matured_check: bool = False) -> int:
    today = date.today()

    if not _skip_matured_check:
        check_and_update_matured_payments(db, lc_id, _skip_overdue_check=True)

    query = db.query(models.Payment).filter(
        models.Payment.status == models.PAYMENT_STATUS_MATURED,
    )
    if lc_id is not None:
        query = query.filter(models.Payment.lc_id == lc_id)

    payments = query.all()
    count = 0
    for p in payments:
        grace_deadline = add_business_days(p.maturity_date, models.OVERDUE_GRACE_WORKING_DAYS)
        if today > grace_deadline:
            old_status = p.status
            p.status = models.PAYMENT_STATUS_OVERDUE
            _add_payment_status_history(db, p, old_status, models.PAYMENT_STATUS_OVERDUE, remark="自动逾期(到期超过3个工作日未付款)")
            _create_auto_collection_record(db, p)
            count += 1

    if count > 0:
        db.commit()
    return count


def generate_collection_number(db: Session, payment_number: str) -> str:
    from sqlalchemy import func
    date_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"COL-{payment_number}-{date_str}-"
    count = db.query(func.count(models.CollectionRecord.id)).filter(
        models.CollectionRecord.collection_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def _create_auto_collection_record(db: Session, payment: models.Payment) -> models.CollectionRecord:
    collection_number = generate_collection_number(db, payment.payment_number)
    record = models.CollectionRecord(
        collection_number=collection_number,
        payment_id=payment.id,
        collection_type=models.COLLECTION_TYPE_SYSTEM_AUTO,
        collection_method=None,
        contact_person=None,
        collection_content="付款已逾期,请尽快安排付款",
        collection_time=datetime.utcnow(),
        created_by="system",
    )
    db.add(record)
    db.flush()
    return record


def create_manual_collection_record(
    db: Session,
    collection_data: schemas.CollectionRecordCreate,
) -> models.CollectionRecord:
    payment = get_payment_by_number(db, collection_data.payment_number)
    if not payment:
        raise ValueError(f"付款申请 {collection_data.payment_number} 不存在")

    check_and_update_overdue_payments(db, payment.lc_id)
    db.refresh(payment)

    if payment.status not in [models.PAYMENT_STATUS_OVERDUE, models.PAYMENT_STATUS_MATURED]:
        raise ValueError(f"只有到期或逾期的付款才能添加催收记录，当前状态: {payment.status}")

    method_value = collection_data.collection_method.value if hasattr(collection_data.collection_method, 'value') else collection_data.collection_method
    if method_value not in models.VALID_COLLECTION_METHODS:
        raise ValueError(f"无效的催收方式: {method_value}，允许值: {', '.join(models.VALID_COLLECTION_METHODS)}")

    collection_number = generate_collection_number(db, payment.payment_number)
    record = models.CollectionRecord(
        collection_number=collection_number,
        payment_id=payment.id,
        collection_type=models.COLLECTION_TYPE_MANUAL,
        collection_method=method_value,
        contact_person=collection_data.contact_person,
        collection_content=collection_data.collection_content,
        collection_time=datetime.utcnow(),
        created_by=collection_data.created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_collection_records_by_payment(db: Session, payment_number: str) -> List[Dict[str, Any]]:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    records = db.query(models.CollectionRecord).filter(
        models.CollectionRecord.payment_id == payment.id
    ).order_by(models.CollectionRecord.collection_time.desc()).all()

    result = []
    for r in records:
        result.append({
            "id": r.id,
            "collection_number": r.collection_number,
            "payment_id": r.payment_id,
            "payment_number": payment.payment_number,
            "collection_type": r.collection_type,
            "collection_method": r.collection_method,
            "contact_person": r.contact_person,
            "collection_content": r.collection_content,
            "collection_time": r.collection_time,
            "created_by": r.created_by,
            "created_at": r.created_at,
        })
    return result


def get_overdue_stats_by_time_range(
    db: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    if start_date > end_date:
        raise ValueError("开始日期不能大于结束日期")

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    query = db.query(models.Payment).filter(
        models.Payment.status == models.PAYMENT_STATUS_OVERDUE,
        models.Payment.created_at >= start_dt,
        models.Payment.created_at <= end_dt,
    )
    overdue_payments = query.all()

    by_currency = {}
    total_amount = 0.0
    for p in overdue_payments:
        curr = p.currency
        unpaid = p.payment_amount - p.total_paid_amount
        if curr not in by_currency:
            by_currency[curr] = {"currency": curr, "count": 0, "total_amount": 0.0, "unpaid_amount": 0.0}
        by_currency[curr]["count"] += 1
        by_currency[curr]["total_amount"] += p.payment_amount
        by_currency[curr]["unpaid_amount"] += unpaid
        total_amount += unpaid

    return {
        "start_date": start_date,
        "end_date": end_date,
        "overdue_count": len(overdue_payments),
        "overdue_total_amount": round(total_amount, 2),
        "overdue_currency_details": list(by_currency.values()),
    }


def get_payment_by_number(db: Session, payment_number: str) -> Optional[models.Payment]:
    return db.query(models.Payment).filter(models.Payment.payment_number == payment_number).first()


def get_payments_by_lc(db: Session, lc_number: str) -> List[models.Payment]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")
    check_and_update_overdue_payments(db, lc.id)
    return db.query(models.Payment).filter(
        models.Payment.lc_id == lc.id
    ).order_by(models.Payment.created_at.desc()).all()


def get_payments_by_status(db: Session, status: str, skip: int = 0, limit: int = 100) -> List[models.Payment]:
    if status not in models.VALID_PAYMENT_STATUSES:
        raise ValueError(f"无效的付款状态: {status}，允许值: {', '.join(models.VALID_PAYMENT_STATUSES)}")
    check_and_update_overdue_payments(db, None)
    return db.query(models.Payment).filter(
        models.Payment.status == status
    ).order_by(models.Payment.maturity_date.asc()).offset(skip).limit(limit).all()


def get_payment_detail(db: Session, payment_number: str) -> Dict[str, Any]:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")

    check_and_update_overdue_payments(db, payment.lc_id)
    db.refresh(payment)

    collection_records = get_collection_records_by_payment(db, payment_number)

    return {
        "id": payment.id,
        "payment_number": payment.payment_number,
        "lc_id": payment.lc_id,
        "submission_id": payment.submission_id,
        "audit_record_id": payment.audit_record_id,
        "payment_amount": payment.payment_amount,
        "currency": payment.currency,
        "payment_method": payment.payment_method,
        "maturity_date": payment.maturity_date,
        "status": payment.status,
        "accepted_at": payment.accepted_at,
        "rejection_reason": payment.rejection_reason,
        "total_paid_amount": payment.total_paid_amount,
        "total_penalty_paid": payment.total_penalty_paid,
        "actual_payment_date": payment.actual_payment_date,
        "created_at": payment.created_at,
        "status_history": payment.status_history,
        "partial_payments": payment.partial_payments,
        "collection_records": collection_records,
    }


def get_payment_status_history(db: Session, payment_number: str) -> List[models.PaymentStatusHistory]:
    payment = get_payment_by_number(db, payment_number)
    if not payment:
        raise ValueError(f"付款申请 {payment_number} 不存在")
    return payment.status_history


def get_payment_stats_by_time_range(
    db: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    if start_date > end_date:
        raise ValueError("开始日期不能大于结束日期")

    payments = db.query(models.Payment).filter(
        models.Payment.created_at >= datetime.combine(start_date, datetime.min.time()),
        models.Payment.created_at <= datetime.combine(end_date, datetime.max.time()),
    ).all()

    by_currency = {}
    for p in payments:
        curr = p.currency
        if curr not in by_currency:
            by_currency[curr] = {"currency": curr, "total_amount": 0.0, "paid_amount": 0.0, "count": 0}
        by_currency[curr]["total_amount"] += p.payment_amount
        by_currency[curr]["paid_amount"] += p.total_paid_amount
        by_currency[curr]["count"] += 1

    total_count = len(payments)
    total_amount = sum(p.payment_amount for p in payments)
    total_paid_amount = sum(p.total_paid_amount for p in payments)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "by_currency": list(by_currency.values()),
        "total_count": total_count,
        "total_amount": total_amount,
        "total_paid_amount": total_paid_amount,
    }


def check_and_update_matured_payments(db: Session, lc_id: Optional[int] = None, _skip_overdue_check: bool = False) -> int:
    today = date.today()
    query = db.query(models.Payment).filter(
        models.Payment.status.in_([models.PAYMENT_STATUS_PENDING, models.PAYMENT_STATUS_ACCEPTED]),
        models.Payment.maturity_date <= today,
    )
    if lc_id is not None:
        query = query.filter(models.Payment.lc_id == lc_id)

    payments = query.all()
    count = 0
    for p in payments:
        if p.status == models.PAYMENT_STATUS_ACCEPTED or p.payment_method == models.PAYMENT_METHOD_SIGHT:
            old_status = p.status
            p.status = models.PAYMENT_STATUS_MATURED
            _add_payment_status_history(db, p, old_status, models.PAYMENT_STATUS_MATURED, remark="自动到期")
            count += 1

    if count > 0:
        db.commit()

    if not _skip_overdue_check:
        check_and_update_overdue_payments(db, lc_id, _skip_matured_check=True)
    return count


def get_lc_payment_summary(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    check_and_update_matured_payments(db, lc.id)

    payments = get_payments_by_lc(db, lc_number)

    total_amount = sum(p.payment_amount for p in payments)
    paid_amount = sum(p.total_paid_amount for p in payments)
    pending_amount = total_amount - paid_amount

    return {
        "lc_number": lc_number,
        "total_payments": len(payments),
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "pending_amount": pending_amount,
        "payments": payments,
    }


def get_all_payments(db: Session, skip: int = 0, limit: int = 100) -> List[models.Payment]:
    check_and_update_overdue_payments(db, None)
    return db.query(models.Payment).order_by(models.Payment.created_at.desc()).offset(skip).limit(limit).all()


def generate_credit_line_transaction_number(db: Session, applicant_name: str, currency: str) -> str:
    from sqlalchemy import func
    date_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"CLT-{applicant_name[:20]}-{currency}-{date_str}-"
    count = db.query(func.count(models.CreditLineTransaction.id)).filter(
        models.CreditLineTransaction.transaction_number.like(f"{prefix}%")
    ).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def create_credit_line(db: Session, credit_line_data: schemas.CreditLineCreate) -> models.CreditLine:
    currency_value = credit_line_data.currency.value if hasattr(credit_line_data.currency, 'value') else credit_line_data.currency

    if credit_line_data.total_amount <= 0:
        raise ValueError("授信总额度必须大于0")

    existing = db.query(models.CreditLine).filter(
        models.CreditLine.applicant_name == credit_line_data.applicant_name,
        models.CreditLine.currency == currency_value
    ).first()
    if existing:
        raise ValueError(
            f"申请人 {credit_line_data.applicant_name} 在 {currency_value} 币种下已有授信额度记录，"
            f"总额度为 {existing.total_amount}"
        )

    credit_line = models.CreditLine(
        applicant_name=credit_line_data.applicant_name,
        currency=currency_value,
        total_amount=credit_line_data.total_amount,
    )
    db.add(credit_line)
    db.commit()
    db.refresh(credit_line)
    return credit_line


def get_credit_line_by_id(db: Session, credit_line_id: int) -> Optional[models.CreditLine]:
    return db.query(models.CreditLine).filter(models.CreditLine.id == credit_line_id).first()


def get_credit_line_by_applicant_and_currency(
    db: Session, applicant_name: str, currency: str
) -> Optional[models.CreditLine]:
    return db.query(models.CreditLine).filter(
        models.CreditLine.applicant_name == applicant_name,
        models.CreditLine.currency == currency
    ).first()


def get_all_credit_lines(db: Session, skip: int = 0, limit: int = 100) -> List[models.CreditLine]:
    return db.query(models.CreditLine).order_by(models.CreditLine.created_at.desc()).offset(skip).limit(limit).all()


def calculate_used_amount(db: Session, applicant_name: str, currency: str) -> Dict[str, Any]:
    today = date.today()

    active_lcs = db.query(models.LetterOfCredit).filter(
        models.LetterOfCredit.applicant_name == applicant_name,
        models.LetterOfCredit.currency == currency,
        models.LetterOfCredit.expiry_date >= today
    ).all()

    used_amount = 0.0
    occupancy_details = []
    for lc in active_lcs:
        used_amount += lc.amount
        occupancy_details.append({
            "lc_number": lc.lc_number,
            "amount": lc.amount,
            "expiry_date": lc.expiry_date,
        })

    return {
        "used_amount": used_amount,
        "occupancy_details": occupancy_details,
    }


def get_credit_line_detail(
    db: Session, applicant_name: str, currency: str
) -> Dict[str, Any]:
    credit_line = get_credit_line_by_applicant_and_currency(db, applicant_name, currency)
    if not credit_line:
        raise ValueError(f"申请人 {applicant_name} 在 {currency} 币种下没有授信额度记录")

    used_info = calculate_used_amount(db, applicant_name, currency)
    used_amount = used_info["used_amount"]
    occupancy_details = used_info["occupancy_details"]
    available_amount = credit_line.total_amount - used_amount
    if available_amount < 0:
        available_amount = 0.0

    return {
        "applicant_name": applicant_name,
        "currency": currency,
        "total_amount": credit_line.total_amount,
        "used_amount": round(used_amount, 2),
        "available_amount": round(available_amount, 2),
        "occupancy_details": occupancy_details,
    }


def _create_credit_line_transaction(
    db: Session,
    credit_line: models.CreditLine,
    transaction_type: str,
    change_amount: float,
    balance_before: float,
    balance_after: float,
    lc_number: Optional[str] = None,
    remark: Optional[str] = None,
) -> models.CreditLineTransaction:
    transaction_number = generate_credit_line_transaction_number(
        db, credit_line.applicant_name, credit_line.currency
    )

    transaction = models.CreditLineTransaction(
        credit_line_id=credit_line.id,
        transaction_number=transaction_number,
        transaction_type=transaction_type,
        change_amount=change_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        lc_number=lc_number,
        remark=remark,
    )
    db.add(transaction)
    db.flush()
    return transaction


def check_and_occupy_credit_line(
    db: Session, applicant_name: str, currency: str, amount: float, lc_number: str
) -> None:
    credit_line = get_credit_line_by_applicant_and_currency(db, applicant_name, currency)
    if not credit_line:
        return

    used_info = calculate_used_amount(db, applicant_name, currency)
    used_amount = used_info["used_amount"]
    available = credit_line.total_amount - used_amount

    if amount > available + 0.01:
        raise ValueError(
            f"授信额度不足。申请人: {applicant_name}, 币种: {currency}, "
            f"总额度: {credit_line.total_amount}, 已用额度: {round(used_amount, 2)}, "
            f"可用额度: {round(available, 2)}, 本次开证金额: {amount}"
        )

    balance_before = credit_line.total_amount - used_amount
    balance_after = balance_before - amount
    _create_credit_line_transaction(
        db,
        credit_line,
        models.CREDIT_LINE_TRANSACTION_TYPE_OCCUPY,
        amount,
        balance_before,
        balance_after,
        lc_number=lc_number,
        remark=f"开立信用证占用额度",
    )


def adjust_credit_line_for_amendment(
    db: Session,
    lc: models.LetterOfCredit,
    old_amount: float,
    new_amount: float,
    amendment_number: str,
) -> None:
    credit_line = get_credit_line_by_applicant_and_currency(
        db, lc.applicant_name, lc.currency
    )
    if not credit_line:
        return

    today = date.today()
    if lc.expiry_date < today:
        return

    amount_diff = new_amount - old_amount

    used_info = calculate_used_amount(db, lc.applicant_name, lc.currency)
    current_used_amount = used_info["used_amount"]

    used_before = current_used_amount - amount_diff
    available_before = credit_line.total_amount - used_before

    if amount_diff > 0:
        if amount_diff > available_before + 0.01:
            raise ValueError(
                f"授信额度不足，无法增加信用证金额。申请人: {lc.applicant_name}, "
                f"币种: {lc.currency}, 可用额度: {round(available_before, 2)}, "
                f"需增加金额: {round(amount_diff, 2)}"
            )

    balance_before = available_before
    balance_after = balance_before - amount_diff

    remark = f"修改{amendment_number}调整额度: 金额从{old_amount:.2f}变更为{new_amount:.2f}"

    _create_credit_line_transaction(
        db,
        credit_line,
        models.CREDIT_LINE_TRANSACTION_TYPE_ADJUST,
        amount_diff,
        balance_before,
        balance_after,
        lc_number=lc.lc_number,
        remark=remark,
    )


def get_credit_line_transactions(
    db: Session,
    applicant_name: str,
    currency: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.CreditLineTransaction]:
    credit_lines = db.query(models.CreditLine).filter(
        models.CreditLine.applicant_name == applicant_name
    )
    if currency:
        credit_lines = credit_lines.filter(models.CreditLine.currency == currency)

    credit_line_ids = [cl.id for cl in credit_lines.all()]
    if not credit_line_ids:
        return []

    return db.query(models.CreditLineTransaction).filter(
        models.CreditLineTransaction.credit_line_id.in_(credit_line_ids)
    ).order_by(
        models.CreditLineTransaction.created_at.desc()
    ).offset(skip).limit(limit).all()


def get_next_template_sequence(db: Session, lc_id: int) -> int:
    from sqlalchemy import func
    max_seq = db.query(func.max(models.DocumentTemplate.id)).filter(
        models.DocumentTemplate.lc_id == lc_id
    ).scalar()
    count = db.query(func.count(models.DocumentTemplate.id)).filter(
        models.DocumentTemplate.lc_id == lc_id
    ).scalar()
    return (count or 0) + 1


def create_template_from_submission(
    db: Session,
    submission_id: str,
    template_name: str,
) -> models.DocumentTemplate:
    audit_record = get_audit_record_by_submission(db, submission_id)
    if not audit_record:
        raise ValueError(f"交单记录 {submission_id} 不存在")

    if audit_record.conclusion not in ["compliant", "minor_discrepancy"]:
        raise ValueError(
            f"只有结论为 compliant 或 minor_discrepancy 的交单才能保存为模板，"
            f"当前交单结论为 {audit_record.conclusion}"
        )

    lc = get_letter_of_credit_by_id(db, audit_record.lc_id)
    if not lc:
        raise ValueError("关联信用证不存在")

    current_count = db.query(models.DocumentTemplate).filter(
        models.DocumentTemplate.lc_id == lc.id
    ).count()

    if current_count >= models.MAX_TEMPLATES_PER_LC:
        raise ValueError(
            f"同一份信用证最多保存 {models.MAX_TEMPLATES_PER_LC} 个模板，"
            f"当前已有 {current_count} 个模板"
        )

    documents = get_documents_by_submission(db, submission_id)
    if not documents:
        raise ValueError(f"交单 {submission_id} 没有找到单据")

    doc_snapshots = []
    for doc in documents:
        doc_snapshots.append({
            "document_type": doc.document_type,
            "original_copies_submitted": doc.original_copies_submitted,
            "copy_copies_submitted": doc.copy_copies_submitted,
            "content": copy.deepcopy(doc.content),
        })

    sequence = get_next_template_sequence(db, lc.id)
    template_number = f"{lc.lc_number}-TPL-{sequence:03d}"

    template = models.DocumentTemplate(
        template_number=template_number,
        template_name=template_name,
        lc_id=lc.id,
        lc_number=lc.lc_number,
        based_on_submission_id=submission_id,
        documents=doc_snapshots,
    )

    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def get_template_by_number(db: Session, template_number: str) -> Optional[models.DocumentTemplate]:
    return db.query(models.DocumentTemplate).filter(
        models.DocumentTemplate.template_number == template_number
    ).first()


def get_templates_by_lc(db: Session, lc_number: str) -> List[models.DocumentTemplate]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")
    return db.query(models.DocumentTemplate).filter(
        models.DocumentTemplate.lc_id == lc.id
    ).order_by(models.DocumentTemplate.created_at.desc()).all()


def delete_template(db: Session, template_number: str) -> bool:
    template = get_template_by_number(db, template_number)
    if not template:
        raise ValueError(f"模板 {template_number} 不存在")
    db.delete(template)
    db.commit()
    return True


def _deep_merge_dict(base: dict, overrides: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _apply_overrides_to_documents(
    template_docs: List[dict],
    field_overrides: List[schemas.TemplateFieldOverride],
) -> List[dict]:
    result_docs = copy.deepcopy(template_docs)

    override_map = {}
    for override in field_overrides:
        override_map[override.document_type] = override

    for doc in result_docs:
        doc_type = doc["document_type"]
        if doc_type in override_map:
            override = override_map[doc_type]
            if override.content_overrides:
                doc["content"] = _deep_merge_dict(doc["content"], override.content_overrides)
            if override.original_copies_submitted is not None:
                doc["original_copies_submitted"] = override.original_copies_submitted
            if override.copy_copies_submitted is not None:
                doc["copy_copies_submitted"] = override.copy_copies_submitted

    return result_docs


def preview_template(
    db: Session,
    template_number: str,
    field_overrides: List[schemas.TemplateFieldOverride],
) -> Dict[str, Any]:
    template = get_template_by_number(db, template_number)
    if not template:
        raise ValueError(f"模板 {template_number} 不存在")

    merged_docs = _apply_overrides_to_documents(template.documents, field_overrides)

    return {
        "template_number": template.template_number,
        "template_name": template.template_name,
        "lc_number": template.lc_number,
        "documents": merged_docs,
    }


def create_submission_from_template(
    db: Session,
    template_number: str,
    use_request: schemas.TemplateUseRequest,
) -> models.AuditRecord:
    template = get_template_by_number(db, template_number)
    if not template:
        raise ValueError(f"模板 {template_number} 不存在")

    lc = get_letter_of_credit_by_number(db, use_request.lc_number)
    if not lc:
        raise ValueError(f"信用证 {use_request.lc_number} 不存在")

    if lc.id != template.lc_id:
        raise ValueError(
            f"模板 {template_number} 属于信用证 {template.lc_number}，"
            f"不能用于信用证 {use_request.lc_number}"
        )

    merged_docs = _apply_overrides_to_documents(template.documents, use_request.field_overrides)

    documents_submit = []
    for doc_data in merged_docs:
        documents_submit.append(schemas.DocumentSubmit(
            lc_number=use_request.lc_number,
            submission_id=use_request.submission_id,
            document_type=doc_data["document_type"],
            original_copies_submitted=doc_data["original_copies_submitted"],
            copy_copies_submitted=doc_data["copy_copies_submitted"],
            content=doc_data["content"],
        ))

    submission = schemas.SubmissionSubmit(
        lc_number=use_request.lc_number,
        submission_id=use_request.submission_id,
        presentation_date=use_request.presentation_date,
        documents=documents_submit,
    )

    return submit_documents_and_audit(db, submission)


def _generate_batch_number() -> str:
    return f"BATCH-{datetime.utcnow().strftime('%Y%m%d')}"


def enqueue_submission(db: Session, queue_data: schemas.SubmissionQueueCreate) -> models.SubmissionQueue:
    lc = get_letter_of_credit_by_number(db, queue_data.lc_number)
    if not lc:
        raise ValueError(f"信用证 {queue_data.lc_number} 不存在")

    audit_record = get_audit_record_by_submission(db, queue_data.submission_id)
    if not audit_record:
        raise ValueError(f"交单 {queue_data.submission_id} 不存在（未找到对应的审核记录）")

    if audit_record.lc_id != lc.id:
        raise ValueError(
            f"交单 {queue_data.submission_id} 所属信用证为 {audit_record.lc_id}，与入队指定的 {queue_data.lc_number} 不匹配"
        )

    existing = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.submission_id == queue_data.submission_id
    ).first()
    if existing:
        raise ValueError(f"交单 {queue_data.submission_id} 已在队列中")

    priority = queue_data.priority.value if hasattr(queue_data.priority, 'value') else queue_data.priority
    if priority not in models.VALID_PRIORITIES:
        raise ValueError(f"无效的优先级: {priority}，允许值: {', '.join(models.VALID_PRIORITIES)}")

    original_submission_id = audit_record.original_submission_id

    old_entries = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.original_submission_id == original_submission_id,
        models.SubmissionQueue.submission_id != queue_data.submission_id,
        models.SubmissionQueue.queue_status.in_([
            models.QUEUE_STATUS_WAITING,
            models.QUEUE_STATUS_PROCESSING,
        ])
    ).all()
    for old_entry in old_entries:
        old_entry.queue_status = models.QUEUE_STATUS_OBSOLETE

    batch_number = _generate_batch_number()

    entry = models.SubmissionQueue(
        submission_id=queue_data.submission_id,
        original_submission_id=original_submission_id,
        lc_id=lc.id,
        batch_number=batch_number,
        priority=priority,
        deadline=queue_data.deadline,
        queue_status=models.QUEUE_STATUS_WAITING,
        timeout_release_count=0,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_next_submission(db: Session) -> Optional[models.SubmissionQueue]:
    release_timeout_submissions(db)

    priority_order_case = None
    if hasattr(models, 'PRIORITY_ORDER'):
        from sqlalchemy import case
        priority_order_case = case(
            *[(models.SubmissionQueue.priority == p, o) for p, o in models.PRIORITY_ORDER.items()],
            else_=99
        )

    query = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.queue_status == models.QUEUE_STATUS_WAITING
    )

    if priority_order_case is not None:
        query = query.order_by(priority_order_case.asc(), models.SubmissionQueue.created_at.asc())
    else:
        query = query.order_by(models.SubmissionQueue.created_at.asc())

    entry = query.first()
    if not entry:
        return None

    entry.queue_status = models.QUEUE_STATUS_PROCESSING
    entry.processing_started_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def complete_submission_in_queue(db: Session, queue_entry_id: int) -> models.SubmissionQueue:
    entry = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.id == queue_entry_id
    ).first()
    if not entry:
        raise ValueError(f"队列条目 {queue_entry_id} 不存在")

    if entry.queue_status == models.QUEUE_STATUS_OBSOLETE:
        raise ValueError(f"队列条目 {queue_entry_id} 已被标记为废弃（该交单已有新的修改重提版本入队）")

    if entry.queue_status == models.QUEUE_STATUS_COMPLETED:
        raise ValueError(f"队列条目 {queue_entry_id} 已经是完成状态")

    if entry.queue_status != models.QUEUE_STATUS_PROCESSING:
        raise ValueError(
            f"队列条目 {queue_entry_id} 当前状态为 {entry.queue_status}，只有 processing 状态的交单可以完成"
        )

    entry.queue_status = models.QUEUE_STATUS_COMPLETED
    entry.processing_completed_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def release_timeout_submissions(db: Session) -> int:
    now = datetime.utcnow()
    timeout_threshold = now - timedelta(hours=models.QUEUE_TIMEOUT_HOURS)

    timed_out = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.queue_status == models.QUEUE_STATUS_PROCESSING,
        models.SubmissionQueue.processing_started_at < timeout_threshold,
        models.SubmissionQueue.processing_completed_at.is_(None),
    ).all()

    count = 0
    for entry in timed_out:
        entry.queue_status = models.QUEUE_STATUS_WAITING
        entry.processing_started_at = None
        entry.timeout_release_count += 1
        count += 1

    if count > 0:
        db.commit()

    return count


def get_batch_submissions(db: Session, batch_number: str) -> Dict[str, Any]:
    entries = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.batch_number == batch_number
    ).order_by(models.SubmissionQueue.created_at.asc()).all()

    result_entries = []
    for entry in entries:
        lc = get_letter_of_credit_by_id(db, entry.lc_id)
        audit_record = get_audit_record_by_submission(db, entry.submission_id)
        result_entries.append({
            "id": entry.id,
            "submission_id": entry.submission_id,
            "original_submission_id": entry.original_submission_id,
            "lc_id": entry.lc_id,
            "batch_number": entry.batch_number,
            "priority": entry.priority,
            "deadline": entry.deadline,
            "queue_status": entry.queue_status,
            "processing_started_at": entry.processing_started_at,
            "processing_completed_at": entry.processing_completed_at,
            "timeout_release_count": entry.timeout_release_count,
            "created_at": entry.created_at,
            "lc_number": lc.lc_number if lc else None,
            "audit_conclusion": audit_record.conclusion if audit_record else None,
        })

    return {
        "batch_number": batch_number,
        "total_count": len(entries),
        "submissions": result_entries,
    }


def get_batch_stats(db: Session, batch_number: str) -> Dict[str, Any]:
    release_timeout_submissions(db)

    entries = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.batch_number == batch_number
    ).all()

    if not entries:
        return {
            "batch_number": batch_number,
            "total_count": 0,
            "completed_count": 0,
            "avg_processing_seconds": None,
            "timeout_release_total_count": 0,
        }

    total_count = len(entries)
    completed = [e for e in entries if e.queue_status == models.QUEUE_STATUS_COMPLETED]
    completed_count = len(completed)

    processing_times = []
    for e in completed:
        if e.processing_started_at and e.processing_completed_at:
            delta = (e.processing_completed_at - e.processing_started_at).total_seconds()
            processing_times.append(delta)

    avg_processing = None
    if processing_times:
        avg_processing = round(sum(processing_times) / len(processing_times), 2)

    timeout_release_total = sum(e.timeout_release_count for e in entries)

    return {
        "batch_number": batch_number,
        "total_count": total_count,
        "completed_count": completed_count,
        "avg_processing_seconds": avg_processing,
        "timeout_release_total_count": timeout_release_total,
    }


def get_queue_status(db: Session) -> Dict[str, Any]:
    release_timeout_submissions(db)

    waiting_entries = db.query(models.SubmissionQueue).filter(
        models.SubmissionQueue.queue_status == models.QUEUE_STATUS_WAITING
    ).all()

    priority_counts = {}
    for p in models.VALID_PRIORITIES:
        priority_counts[p] = 0

    for entry in waiting_entries:
        if entry.priority in priority_counts:
            priority_counts[entry.priority] += 1

    by_priority = [
        {"priority": p, "count": c}
        for p, c in priority_counts.items()
    ]

    return {
        "total_waiting": len(waiting_entries),
        "by_priority": by_priority,
    }


def generate_split_rule_number(db: Session, lc_number: str) -> str:
    import uuid
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:8].upper()
    return f"SPLIT-RULE-{lc_number}-{date_str}-{suffix}"


def generate_split_number(db: Session, fee_number: str) -> str:
    import uuid
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:8].upper()
    return f"SPLIT-{fee_number}-{date_str}-{suffix}"


def generate_adjustment_number(db: Session, split_number: str) -> str:
    import uuid
    date_str = datetime.utcnow().strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:8].upper()
    return f"ADJ-{split_number}-{date_str}-{suffix}"


def _validate_participating_banks(banks_data: List[Dict[str, Any]]) -> None:
    if not banks_data or len(banks_data) == 0:
        raise ValueError("至少需要指定一家参与银行")

    seen_roles = set()
    seen_banks = set()
    total_ratio = 0.0

    for bank in banks_data:
        role = bank.get("role")
        bank_name = bank.get("bank_name")
        split_ratio = bank.get("split_ratio")

        if role not in models.VALID_FEE_SPLIT_ROLES:
            raise ValueError(f"无效的银行角色: {role}，允许的值: {', '.join(models.VALID_FEE_SPLIT_ROLES)}")
        if not bank_name or not bank_name.strip():
            raise ValueError("银行名称不能为空")
        if split_ratio is None or split_ratio < 0 or split_ratio > 100:
            raise ValueError(f"分账比例必须在 0-100 之间，当前值: {split_ratio}")
        if role in seen_roles:
            raise ValueError(f"银行角色 '{role}' 重复出现")
        if bank_name.strip() in seen_banks:
            raise ValueError(f"银行名称 '{bank_name}' 重复出现")

        seen_roles.add(role)
        seen_banks.add(bank_name.strip())
        total_ratio += float(split_ratio)

    if abs(total_ratio - 100.0) > 0.01:
        raise ValueError(f"所有参与行的分账比例之和必须等于100%，当前总和: {total_ratio:.2f}%")


def create_fee_split_rule(
    db: Session,
    lc_number: str,
    participating_banks: List[Dict[str, Any]],
) -> models.FeeSplitRule:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    existing_active = db.query(models.FeeSplitRule).filter(
        models.FeeSplitRule.lc_id == lc.id,
        models.FeeSplitRule.status == models.FEE_SPLIT_RULE_STATUS_ACTIVE,
    ).first()
    if existing_active:
        raise ValueError(
            f"信用证 {lc_number} 已有一条生效的分账规则 (编号: {existing_active.rule_number})，"
            f"如需修改请先作废现有规则再重新创建"
        )

    banks_normalized = []
    for b in participating_banks:
        role = b["role"].value if hasattr(b["role"], "value") else b["role"]
        banks_normalized.append({
            "role": role,
            "bank_name": b["bank_name"].strip(),
            "split_ratio": float(b["split_ratio"]),
        })

    _validate_participating_banks(banks_normalized)

    rule_number = generate_split_rule_number(db, lc_number)

    rule = models.FeeSplitRule(
        rule_number=rule_number,
        lc_id=lc.id,
        lc_number=lc_number,
        participating_banks=banks_normalized,
        status=models.FEE_SPLIT_RULE_STATUS_ACTIVE,
    )
    db.add(rule)
    db.flush()

    existing_fees = db.query(models.FeeRecord).filter(
        models.FeeRecord.lc_id == lc.id,
    ).all()
    for fee in existing_fees:
        existing_splits = db.query(models.FeeSplitDetail).filter(
            models.FeeSplitDetail.fee_record_id == fee.id,
        ).first()
        if not existing_splits:
            auto_generate_fee_split_details_for_rule(db, fee, rule)

    db.commit()
    db.refresh(rule)
    return rule


def get_fee_split_rule_by_id(db: Session, rule_id: int) -> Optional[models.FeeSplitRule]:
    return db.query(models.FeeSplitRule).filter(models.FeeSplitRule.id == rule_id).first()


def get_fee_split_rule_by_number(db: Session, rule_number: str) -> Optional[models.FeeSplitRule]:
    return db.query(models.FeeSplitRule).filter(models.FeeSplitRule.rule_number == rule_number).first()


def get_active_fee_split_rule_by_lc(db: Session, lc_number: str) -> Optional[models.FeeSplitRule]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return None
    return db.query(models.FeeSplitRule).filter(
        models.FeeSplitRule.lc_id == lc.id,
        models.FeeSplitRule.status == models.FEE_SPLIT_RULE_STATUS_ACTIVE,
    ).first()


def get_all_fee_split_rules_by_lc(db: Session, lc_number: str) -> List[models.FeeSplitRule]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.FeeSplitRule).filter(
        models.FeeSplitRule.lc_id == lc.id,
    ).order_by(models.FeeSplitRule.created_at.desc()).all()


def void_fee_split_rule(
    db: Session,
    rule_number: str,
    void_reason: str,
    voided_by: str,
) -> models.FeeSplitRule:
    rule = get_fee_split_rule_by_number(db, rule_number)
    if not rule:
        raise ValueError(f"分账规则 {rule_number} 不存在")
    if rule.status == models.FEE_SPLIT_RULE_STATUS_VOID:
        raise ValueError(f"分账规则 {rule_number} 已经是作废状态")

    rule.status = models.FEE_SPLIT_RULE_STATUS_VOID
    rule.void_reason = void_reason
    rule.voided_at = datetime.utcnow()
    rule.voided_by = voided_by

    db.commit()
    db.refresh(rule)
    return rule


def auto_generate_fee_split_details(db: Session, fee_record: models.FeeRecord) -> None:
    rule = db.query(models.FeeSplitRule).filter(
        models.FeeSplitRule.lc_id == fee_record.lc_id,
        models.FeeSplitRule.status == models.FEE_SPLIT_RULE_STATUS_ACTIVE,
    ).first()
    if not rule:
        return

    auto_generate_fee_split_details_for_rule(db, fee_record, rule)


def auto_generate_fee_split_details_for_rule(
    db: Session,
    fee_record: models.FeeRecord,
    rule: models.FeeSplitRule,
) -> None:
    total_amount = fee_record.total_amount
    banks = rule.participating_banks

    allocated = 0.0
    split_details = []

    for i, bank in enumerate(banks):
        ratio = float(bank["split_ratio"])
        if i == len(banks) - 1:
            amount = round(total_amount - allocated, 2)
        else:
            amount = round(total_amount * ratio / 100.0, 2)
            allocated += amount

        split_number = generate_split_number(db, fee_record.fee_number)

        detail = models.FeeSplitDetail(
            split_number=split_number,
            split_rule_id=rule.id,
            fee_record_id=fee_record.id,
            fee_number=fee_record.fee_number,
            lc_id=fee_record.lc_id,
            lc_number=rule.lc_number,
            receiving_bank_name=bank["bank_name"],
            receiving_bank_role=bank["role"],
            split_ratio=ratio,
            original_amount=amount,
            current_amount=amount,
            status=models.FEE_SPLIT_DETAIL_STATUS_PENDING,
        )
        db.add(detail)
        split_details.append(detail)

    db.flush()


def get_fee_split_detail_by_number(db: Session, split_number: str) -> Optional[models.FeeSplitDetail]:
    return db.query(models.FeeSplitDetail).filter(models.FeeSplitDetail.split_number == split_number).first()


def get_fee_split_details_by_fee(db: Session, fee_record_id: int) -> List[models.FeeSplitDetail]:
    return db.query(models.FeeSplitDetail).filter(
        models.FeeSplitDetail.fee_record_id == fee_record_id,
    ).order_by(models.FeeSplitDetail.created_at.asc()).all()


def get_fee_split_details_by_lc(db: Session, lc_number: str) -> List[models.FeeSplitDetail]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        return []
    return db.query(models.FeeSplitDetail).filter(
        models.FeeSplitDetail.lc_id == lc.id,
    ).order_by(models.FeeSplitDetail.created_at.desc()).all()


def confirm_fee_split_detail(
    db: Session,
    split_number: str,
    confirmed_by: str,
) -> models.FeeSplitDetail:
    detail = get_fee_split_detail_by_number(db, split_number)
    if not detail:
        raise ValueError(f"分账明细 {split_number} 不存在")

    if detail.status == models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED:
        raise ValueError(f"分账明细 {split_number} 已经是已确认状态")
    if detail.status == models.FEE_SPLIT_DETAIL_STATUS_DISPUTED:
        raise ValueError(f"分账明细 {split_number} 处于争议状态，无法直接确认，请先处理争议")

    detail.status = models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED
    detail.confirmed_at = datetime.utcnow()
    detail.confirmed_by = confirmed_by

    db.flush()
    _check_and_update_fee_settlement(db, detail.fee_record_id)

    db.commit()
    db.refresh(detail)
    return detail


def dispute_fee_split_detail(
    db: Session,
    split_number: str,
    dispute_reason: str,
) -> models.FeeSplitDetail:
    detail = get_fee_split_detail_by_number(db, split_number)
    if not detail:
        raise ValueError(f"分账明细 {split_number} 不存在")

    if detail.status == models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED:
        raise ValueError(f"分账明细 {split_number} 已经确认，无法标记为争议")

    if not dispute_reason or not dispute_reason.strip():
        raise ValueError("争议原因不能为空")

    detail.status = models.FEE_SPLIT_DETAIL_STATUS_DISPUTED
    detail.dispute_reason = dispute_reason.strip()
    detail.disputed_at = datetime.utcnow()

    db.commit()
    db.refresh(detail)
    return detail


def adjust_fee_split_detail(
    db: Session,
    split_number: str,
    new_amount: float,
    adjustment_reason: str,
    adjusted_by: str,
) -> models.FeeSplitDetail:
    detail = get_fee_split_detail_by_number(db, split_number)
    if not detail:
        raise ValueError(f"分账明细 {split_number} 不存在")

    if detail.status != models.FEE_SPLIT_DETAIL_STATUS_DISPUTED:
        raise ValueError(
            f"只有争议状态的分账明细才能调整金额，当前状态: {detail.status}"
        )

    if new_amount is None or new_amount < 0:
        raise ValueError("调整后的金额不能为负数")

    if not adjustment_reason or not adjustment_reason.strip():
        raise ValueError("调整原因不能为空")

    amount_before = detail.current_amount
    amount_after = round(float(new_amount), 2)
    amount_diff = round(amount_after - amount_before, 2)

    adjustment_number = generate_adjustment_number(db, split_number)
    adjustment = models.FeeSplitAdjustment(
        adjustment_number=adjustment_number,
        split_detail_id=detail.id,
        split_number=split_number,
        amount_before=amount_before,
        amount_after=amount_after,
        amount_diff=amount_diff,
        adjusted_by=adjusted_by,
        adjustment_reason=adjustment_reason.strip(),
    )
    db.add(adjustment)

    detail.current_amount = amount_after
    detail.status = models.FEE_SPLIT_DETAIL_STATUS_PENDING
    detail.dispute_reason = None
    detail.disputed_at = None
    detail.confirmed_at = None
    detail.confirmed_by = None

    fee_record = db.query(models.FeeRecord).filter(models.FeeRecord.id == detail.fee_record_id).first()
    if fee_record and fee_record.settlement_status == models.FEE_SETTLEMENT_STATUS_SETTLED:
        fee_record.settlement_status = models.FEE_SETTLEMENT_STATUS_PENDING
        fee_record.settled_at = None

    db.commit()
    db.refresh(detail)
    return detail


def _check_and_update_fee_settlement(db: Session, fee_record_id: int) -> None:
    fee_record = db.query(models.FeeRecord).filter(models.FeeRecord.id == fee_record_id).first()
    if not fee_record:
        return

    split_details = get_fee_split_details_by_fee(db, fee_record_id)
    if not split_details:
        return

    all_confirmed = all(
        d.status == models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED for d in split_details
    )

    if all_confirmed and fee_record.settlement_status != models.FEE_SETTLEMENT_STATUS_SETTLED:
        fee_record.settlement_status = models.FEE_SETTLEMENT_STATUS_SETTLED
        fee_record.settled_at = datetime.utcnow()
    elif not all_confirmed and fee_record.settlement_status == models.FEE_SETTLEMENT_STATUS_SETTLED:
        fee_record.settlement_status = models.FEE_SETTLEMENT_STATUS_PENDING
        fee_record.settled_at = None


def get_lc_fee_split_summary(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证 {lc_number} 不存在")

    split_rule = get_active_fee_split_rule_by_lc(db, lc_number)

    fee_records = db.query(models.FeeRecord).filter(
        models.FeeRecord.lc_id == lc.id,
    ).order_by(models.FeeRecord.created_at.desc()).all()

    fee_records_with_splits = []
    for fee in fee_records:
        splits = get_fee_split_details_by_fee(db, fee.id)
        fee_records_with_splits.append({
            "fee_record": fee,
            "settlement_status": fee.settlement_status,
            "settled_at": fee.settled_at,
            "split_details": splits,
        })

    return {
        "lc_number": lc_number,
        "split_rule": split_rule,
        "fee_records_with_splits": fee_records_with_splits,
    }


def get_monthly_reconciliation(
    db: Session,
    year: int,
    month: int,
) -> Dict[str, Any]:
    if year < 2000 or year > 2100:
        raise ValueError(f"无效的年份: {year}")
    if month < 1 or month > 12:
        raise ValueError(f"无效的月份: {month}")

    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    all_splits = db.query(models.FeeSplitDetail).filter(
        models.FeeSplitDetail.created_at >= start_dt,
        models.FeeSplitDetail.created_at <= end_dt,
    ).all()

    total_amount = sum(d.current_amount for d in all_splits)
    total_confirmed = sum(d.current_amount for d in all_splits if d.status == models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED)
    total_disputed = sum(d.current_amount for d in all_splits if d.status == models.FEE_SPLIT_DETAIL_STATUS_DISPUTED)
    total_pending = sum(d.current_amount for d in all_splits if d.status == models.FEE_SPLIT_DETAIL_STATUS_PENDING)

    bank_agg = {}
    for d in all_splits:
        key = (d.receiving_bank_name, d.receiving_bank_role)
        if key not in bank_agg:
            bank_agg[key] = {
                "bank_name": d.receiving_bank_name,
                "bank_role": d.receiving_bank_role,
                "total_receivable": 0.0,
                "confirmed_amount": 0.0,
                "disputed_amount": 0.0,
                "pending_amount": 0.0,
                "detail_count": 0,
                "confirmed_count": 0,
                "disputed_count": 0,
                "pending_count": 0,
            }
        agg = bank_agg[key]
        agg["total_receivable"] += d.current_amount
        agg["detail_count"] += 1
        if d.status == models.FEE_SPLIT_DETAIL_STATUS_CONFIRMED:
            agg["confirmed_amount"] += d.current_amount
            agg["confirmed_count"] += 1
        elif d.status == models.FEE_SPLIT_DETAIL_STATUS_DISPUTED:
            agg["disputed_amount"] += d.current_amount
            agg["disputed_count"] += 1
        else:
            agg["pending_amount"] += d.current_amount
            agg["pending_count"] += 1

    by_bank = []
    for key in sorted(bank_agg.keys()):
        agg = bank_agg[key]
        by_bank.append({
            "bank_name": agg["bank_name"],
            "bank_role": agg["bank_role"],
            "total_receivable": round(agg["total_receivable"], 2),
            "confirmed_amount": round(agg["confirmed_amount"], 2),
            "disputed_amount": round(agg["disputed_amount"], 2),
            "pending_amount": round(agg["pending_amount"], 2),
            "detail_count": agg["detail_count"],
            "confirmed_count": agg["confirmed_count"],
            "disputed_count": agg["disputed_count"],
            "pending_count": agg["pending_count"],
        })

    year_month_str = f"{year:04d}-{month:02d}"

    return {
        "year_month": year_month_str,
        "total_split_count": len(all_splits),
        "total_amount": round(float(total_amount), 2),
        "total_confirmed_amount": round(float(total_confirmed), 2),
        "total_disputed_amount": round(float(total_disputed), 2),
        "total_pending_amount": round(float(total_pending), 2),
        "by_bank": by_bank,
    }


def get_fee_split_adjustments(db: Session, split_number: str) -> List[models.FeeSplitAdjustment]:
    detail = get_fee_split_detail_by_number(db, split_number)
    if not detail:
        raise ValueError(f"分账明细 {split_number} 不存在")
    return db.query(models.FeeSplitAdjustment).filter(
        models.FeeSplitAdjustment.split_detail_id == detail.id,
    ).order_by(models.FeeSplitAdjustment.created_at.desc()).all()


def get_fee_split_detail_with_adjustments(db: Session, split_number: str) -> Dict[str, Any]:
    detail = get_fee_split_detail_by_number(db, split_number)
    if not detail:
        raise ValueError(f"分账明细 {split_number} 不存在")
    adjustments = get_fee_split_adjustments(db, split_number)
    return {
        "id": detail.id,
        "split_number": detail.split_number,
        "split_rule_id": detail.split_rule_id,
        "fee_record_id": detail.fee_record_id,
        "fee_number": detail.fee_number,
        "lc_id": detail.lc_id,
        "lc_number": detail.lc_number,
        "receiving_bank_name": detail.receiving_bank_name,
        "receiving_bank_role": detail.receiving_bank_role,
        "split_ratio": detail.split_ratio,
        "original_amount": detail.original_amount,
        "current_amount": detail.current_amount,
        "status": detail.status,
        "dispute_reason": detail.dispute_reason,
        "disputed_at": detail.disputed_at,
        "confirmed_at": detail.confirmed_at,
        "confirmed_by": detail.confirmed_by,
        "created_at": detail.created_at,
        "adjustments": adjustments,
    }


def migrate_fee_split_tables(db: Session) -> int:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    created = 0
    try:
        conn = db.connection()
        try:
            db.execute(text("SELECT 1 FROM fee_split_rules LIMIT 1"))
        except OperationalError:
            models.FeeSplitRule.__table__.create(bind=conn)
            created += 1

        try:
            db.execute(text("SELECT 1 FROM fee_split_details LIMIT 1"))
        except OperationalError:
            models.FeeSplitDetail.__table__.create(bind=conn)
            created += 1

        try:
            db.execute(text("SELECT 1 FROM fee_split_adjustments LIMIT 1"))
        except OperationalError:
            models.FeeSplitAdjustment.__table__.create(bind=conn)
            created += 1

        columns_added_fee = False
        try:
            db.execute(text("SELECT settlement_status FROM fee_records LIMIT 1"))
        except OperationalError:
            db.execute(text("ALTER TABLE fee_records ADD COLUMN settlement_status VARCHAR(20) DEFAULT 'pending'"))
            db.execute(text("ALTER TABLE fee_records ADD COLUMN settled_at DATETIME"))
            db.commit()
            columns_added_fee = True
            created += 2

        db.commit()
    except Exception as e:
        db.rollback()
    return created


def create_signature_subject(db: Session, subject_data: schemas.SignatureSubjectCreate) -> models.SignatureSubject:
    subject_type_value = subject_data.subject_type.value if hasattr(subject_data.subject_type, 'value') else subject_data.subject_type
    if subject_type_value not in models.VALID_SIGNATURE_SUBJECT_TYPES:
        raise ValueError(f"无效的主体类型: {subject_type_value}，允许值: {', '.join(models.VALID_SIGNATURE_SUBJECT_TYPES)}")

    existing = db.query(models.SignatureSubject).filter(
        models.SignatureSubject.subject_name == subject_data.subject_name
    ).first()
    if existing:
        raise ValueError(f"签章主体名称已存在: {subject_data.subject_name}")

    db_subject = models.SignatureSubject(
        subject_name=subject_data.subject_name,
        subject_type=subject_type_value,
        public_key=subject_data.public_key,
        status=models.SIGNATURE_SUBJECT_STATUS_ACTIVE,
    )
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


def get_signature_subject_by_name(db: Session, subject_name: str) -> Optional[models.SignatureSubject]:
    return db.query(models.SignatureSubject).filter(
        models.SignatureSubject.subject_name == subject_name
    ).first()


def get_signature_subject_by_id(db: Session, subject_id: int) -> Optional[models.SignatureSubject]:
    return db.query(models.SignatureSubject).filter(
        models.SignatureSubject.id == subject_id
    ).first()


def get_all_signature_subjects(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    subject_type: Optional[str] = None,
) -> List[models.SignatureSubject]:
    query = db.query(models.SignatureSubject)
    if status:
        if status not in models.VALID_SIGNATURE_SUBJECT_STATUSES:
            raise ValueError(f"无效的状态: {status}，允许值: {', '.join(models.VALID_SIGNATURE_SUBJECT_STATUSES)}")
        query = query.filter(models.SignatureSubject.status == status)
    if subject_type:
        if subject_type not in models.VALID_SIGNATURE_SUBJECT_TYPES:
            raise ValueError(f"无效的主体类型: {subject_type}，允许值: {', '.join(models.VALID_SIGNATURE_SUBJECT_TYPES)}")
        query = query.filter(models.SignatureSubject.subject_type == subject_type)
    return query.order_by(models.SignatureSubject.created_at.desc()).offset(skip).limit(limit).all()


def revoke_signature_subject(db: Session, subject_name: str, reason: str) -> models.SignatureSubject:
    subject = get_signature_subject_by_name(db, subject_name)
    if not subject:
        raise ValueError(f"签章主体不存在: {subject_name}")
    if subject.status == models.SIGNATURE_SUBJECT_STATUS_REVOKED:
        raise ValueError(f"签章主体已被吊销: {subject_name}")

    subject.status = models.SIGNATURE_SUBJECT_STATUS_REVOKED
    subject.revoked_at = datetime.utcnow()
    subject.revoked_reason = reason
    db.commit()
    db.refresh(subject)
    return subject


def _calculate_document_signature_hash(content: Dict[str, Any]) -> str:
    import json
    import hashlib
    content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
    md5_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
    return md5_hash[:16]


def verify_document_signature(db: Session, document: models.Document) -> Dict[str, Any]:
    if not document.signature:
        return {
            "document_id": document.id,
            "document_type": document.document_type,
            "verify_status": models.SIGNATURE_VERIFY_STATUS_UNSIGNED,
            "failure_reason": None,
            "subject_name": None,
        }

    sig = document.signature
    subject = get_signature_subject_by_name(db, sig.subject_name)

    if not subject:
        return {
            "document_id": document.id,
            "document_type": document.document_type,
            "verify_status": models.SIGNATURE_VERIFY_STATUS_INVALID,
            "failure_reason": f"签章主体不存在: {sig.subject_name}",
            "subject_name": sig.subject_name,
        }

    if subject.status == models.SIGNATURE_SUBJECT_STATUS_REVOKED:
        return {
            "document_id": document.id,
            "document_type": document.document_type,
            "verify_status": models.SIGNATURE_VERIFY_STATUS_INVALID,
            "failure_reason": f"签章主体已被吊销: {sig.subject_name}",
            "subject_name": sig.subject_name,
        }

    expected_hash = _calculate_document_signature_hash(document.content)
    actual_prefix = sig.signature_value[:16]

    if expected_hash != actual_prefix:
        return {
            "document_id": document.id,
            "document_type": document.document_type,
            "verify_status": models.SIGNATURE_VERIFY_STATUS_INVALID,
            "failure_reason": "签名值与单据内容不匹配",
            "subject_name": sig.subject_name,
        }

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "verify_status": models.SIGNATURE_VERIFY_STATUS_VALID,
        "failure_reason": None,
        "subject_name": sig.subject_name,
    }


def verify_submission_signatures(db: Session, submission_id: str) -> Dict[str, Any]:
    documents = get_documents_by_submission(db, submission_id)
    if not documents:
        raise ValueError(f"交单不存在: {submission_id}")

    results = []
    for doc in documents:
        result = verify_document_signature(db, doc)
        results.append(result)

    return {
        "submission_id": submission_id,
        "results": results,
    }


def get_lc_signature_summary(db: Session, lc_number: str) -> Dict[str, Any]:
    lc = get_letter_of_credit_by_number(db, lc_number)
    if not lc:
        raise ValueError(f"信用证不存在: {lc_number}")

    audit_records = get_audit_records_by_lc(db, lc_number)
    submission_list = []

    for audit in audit_records:
        documents = get_documents_by_submission(db, audit.submission_id)
        doc_items = []
        for doc in documents:
            verify_result = verify_document_signature(db, doc)
            doc_items.append({
                "document_id": doc.id,
                "document_type": doc.document_type,
                "has_signature": doc.signature is not None,
                "verify_status": verify_result["verify_status"],
                "failure_reason": verify_result.get("failure_reason"),
                "subject_name": verify_result.get("subject_name"),
            })
        submission_list.append({
            "submission_id": audit.submission_id,
            "documents": doc_items,
        })

    return {
        "lc_number": lc_number,
        "submissions": submission_list,
    }


def _save_document_signature(
    db: Session,
    document_id: int,
    signature_data: Optional[schemas.DocumentSignatureCreate],
) -> Optional[models.DocumentSignature]:
    if not signature_data:
        return None

    db_sig = models.DocumentSignature(
        document_id=document_id,
        subject_name=signature_data.subject_name,
        signature_value=signature_data.signature_value,
        signed_at=signature_data.signed_at,
    )
    db.add(db_sig)
    db.flush()
    return db_sig


def migrate_signature_tables(db: Session) -> int:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    created = 0
    try:
        conn = db.connection()
        try:
            db.execute(text("SELECT 1 FROM signature_subjects LIMIT 1"))
        except OperationalError:
            models.SignatureSubject.__table__.create(bind=conn)
            created += 1

        try:
            db.execute(text("SELECT 1 FROM document_signatures LIMIT 1"))
        except OperationalError:
            models.DocumentSignature.__table__.create(bind=conn)
            created += 1

        db.commit()
    except Exception as e:
        db.rollback()
    return created
