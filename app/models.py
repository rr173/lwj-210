from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, Text, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta

from app.database import Base

REVIEW_STATUS_PENDING = "pending_review"
REVIEW_STATUS_IN_REVIEW = "in_review"
REVIEW_STATUS_REVIEWED = "reviewed"
VALID_REVIEW_STATUSES = [REVIEW_STATUS_PENDING, REVIEW_STATUS_IN_REVIEW, REVIEW_STATUS_REVIEWED]

REVIEW_ACTION_CONFIRM = "confirm"
REVIEW_ACTION_OVERRULE = "overrule"
REVIEW_ACTION_ADD_DISCREPANCY = "add_discrepancy"
REVIEW_ACTION_REMOVE_DISCREPANCY = "remove_discrepancy"
VALID_REVIEW_ACTIONS = [REVIEW_ACTION_CONFIRM, REVIEW_ACTION_OVERRULE, REVIEW_ACTION_ADD_DISCREPANCY, REVIEW_ACTION_REMOVE_DISCREPANCY]

DISCREPANCY_ACTION_REMOVED = "removed"
DISCREPANCY_ACTION_MANUAL = "manual"

CLAIM_TIMEOUT_HOURS = 24


FEE_TIER_STANDARD = "standard"
FEE_TIER_PREFERRED = "preferred"
FEE_TIER_VIP = "vip"
VALID_FEE_TIERS = [FEE_TIER_STANDARD, FEE_TIER_PREFERRED, FEE_TIER_VIP]

FEE_RULES = {
    FEE_TIER_STANDARD: {
        "first_submission_base": 200,
        "first_submission_per_doc": 30,
        "resubmission_fixed": 150,
    },
    FEE_TIER_PREFERRED: {
        "first_submission_base": 150,
        "first_submission_per_doc": 20,
        "resubmission_fixed": 100,
    },
    FEE_TIER_VIP: {
        "first_submission_base": 100,
        "first_submission_per_doc": 10,
        "resubmission_fixed": 0,
    },
}

FEE_TYPE_FIRST_SUBMISSION = "first_submission"
FEE_TYPE_RESUBMISSION = "resubmission"

FEE_STATUS_CONFIRMED = "confirmed"
FEE_STATUS_PENDING = "pending"


AMENDMENT_STATUS_PENDING = "pending"
AMENDMENT_STATUS_ACCEPTED = "accepted"
AMENDMENT_STATUS_REJECTED = "rejected"
AMENDMENT_STATUS_EXPIRED = "expired"

AMENDMENT_EXPIRY_DAYS = 7

AMENDABLE_FIELDS = [
    "amount",
    "latest_shipment_date",
    "latest_presentation_date",
    "expiry_date",
    "port_of_loading",
    "port_of_discharge",
    "partial_shipment_allowed",
    "transshipment_allowed",
    "goods_description",
    "additional_terms"
]

MAX_FIELDS_PER_AMENDMENT = 5


class LetterOfCredit(Base):
    __tablename__ = "letter_of_credits"

    id = Column(Integer, primary_key=True, index=True)
    lc_number = Column(String(100), unique=True, index=True, nullable=False)
    issuing_bank = Column(String(255), nullable=False)
    beneficiary_name = Column(String(255), nullable=False)
    applicant_name = Column(String(255), nullable=False)
    currency = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    latest_shipment_date = Column(Date, nullable=False)
    latest_presentation_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    transport_mode = Column(String(50), nullable=False)
    port_of_loading = Column(String(255), nullable=False)
    port_of_discharge = Column(String(255), nullable=False)
    partial_shipment_allowed = Column(Boolean, default=False)
    transshipment_allowed = Column(Boolean, default=False)
    goods_description = Column(Text, nullable=False)
    additional_terms = Column(JSON, default=list)
    fee_tier = Column(String(20), default=FEE_TIER_STANDARD, nullable=False)
    document_requirements = relationship("DocumentRequirement", back_populates="lc", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="lc", cascade="all, delete-orphan")
    audit_records = relationship("AuditRecord", back_populates="lc", cascade="all, delete-orphan")
    amendments = relationship("LCAmendment", back_populates="lc", cascade="all, delete-orphan", order_by="LCAmendment.sequence_number")
    fee_records = relationship("FeeRecord", back_populates="lc", cascade="all, delete-orphan")
    transfers = relationship("LCTransfer", back_populates="lc", cascade="all, delete-orphan", order_by="LCTransfer.sequence_number")
    back_to_back_lcs = relationship("BackToBackLC", back_populates="original_lc", cascade="all, delete-orphan")
    created_at = Column(DateTime, default=datetime.utcnow)


class LCAmendment(Base):
    __tablename__ = "lc_amendments"

    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    amendment_number = Column(String(150), unique=True, index=True, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    status = Column(String(20), default=AMENDMENT_STATUS_PENDING, nullable=False)
    field_changes = Column(JSON, nullable=False)
    snapshot_before = Column(JSON, nullable=False)
    snapshot_after = Column(JSON, nullable=True)
    acceptance_time = Column(DateTime, nullable=True)
    expiry_time = Column(DateTime, nullable=False)
    lc = relationship("LetterOfCredit", back_populates="amendments")
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expiry_time


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"

    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    original_copies = Column(Integer, default=0)
    copy_copies = Column(Integer, default=0)
    lc = relationship("LetterOfCredit", back_populates="document_requirements")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    submission_id = Column(String(100), index=True, nullable=False)
    original_submission_id = Column(String(100), index=True, nullable=False)
    resubmission_round = Column(Integer, default=0)
    document_type = Column(String(50), nullable=False)
    original_copies_submitted = Column(Integer, default=0)
    copy_copies_submitted = Column(Integer, default=0)
    content = Column(JSON, nullable=False)
    lc = relationship("LetterOfCredit", back_populates="documents")


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    submission_id = Column(String(100), index=True, nullable=False)
    original_submission_id = Column(String(100), index=True, nullable=False)
    resubmission_round = Column(Integer, default=0)
    modification_remark = Column(Text, nullable=True)
    conclusion = Column(String(50), nullable=False)
    auto_conclusion = Column(String(50), nullable=True)
    final_conclusion = Column(String(50), nullable=True)
    total_discrepancies = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    minor_count = Column(Integer, default=0)
    presentation_date = Column(Date, nullable=False)
    review_status = Column(String(20), default=REVIEW_STATUS_PENDING, nullable=False)
    discrepancies = relationship("Discrepancy", back_populates="audit_record", cascade="all, delete-orphan")
    review_assignments = relationship("ReviewAssignment", back_populates="audit_record", cascade="all, delete-orphan")
    review_opinions = relationship("ReviewOpinion", back_populates="audit_record", cascade="all, delete-orphan")
    lc = relationship("LetterOfCredit", back_populates="audit_records")
    created_at = Column(DateTime, default=datetime.utcnow)


class Discrepancy(Base):
    __tablename__ = "discrepancies"

    id = Column(Integer, primary_key=True, index=True)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=False)
    discrepancy_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    document_type = Column(String(50))
    description = Column(Text, nullable=False)
    lc_clause_reference = Column(String(255))
    source = Column(String(20), default="auto", nullable=False)
    is_removed = Column(Boolean, default=False, nullable=False)
    removal_reason = Column(Text, nullable=True)
    audit_record = relationship("AuditRecord", back_populates="discrepancies")


class FeeRecord(Base):
    __tablename__ = "fee_records"

    id = Column(Integer, primary_key=True, index=True)
    fee_number = Column(String(100), unique=True, index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    submission_id = Column(String(100), index=True, nullable=False)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=False)
    fee_type = Column(String(30), nullable=False)
    fee_tier = Column(String(20), nullable=False)
    base_fee = Column(Float, default=0, nullable=False)
    per_doc_fee = Column(Float, default=0, nullable=False)
    document_count = Column(Integer, default=0, nullable=False)
    document_fee_total = Column(Float, default=0, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    lc = relationship("LetterOfCredit", back_populates="fee_records")
    audit_record = relationship("AuditRecord")


class Reviewer(Base):
    __tablename__ = "reviewers"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    department = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    review_assignments = relationship("ReviewAssignment", back_populates="reviewer")
    review_opinions = relationship("ReviewOpinion", back_populates="reviewer")
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"

    id = Column(Integer, primary_key=True, index=True)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"), nullable=False)
    claimed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    is_expired = Column(Boolean, default=False, nullable=False)
    audit_record = relationship("AuditRecord", back_populates="review_assignments")
    reviewer = relationship("Reviewer", back_populates="review_assignments")

    def is_still_valid(self) -> bool:
        if self.completed_at is not None or self.is_expired:
            return False
        return datetime.utcnow() <= self.expires_at


TRANSFER_TYPE_FULL = "full"
TRANSFER_TYPE_PARTIAL = "partial"
VALID_TRANSFER_TYPES = [TRANSFER_TYPE_FULL, TRANSFER_TYPE_PARTIAL]

TRANSFER_STATUS_PENDING = "pending"
TRANSFER_STATUS_CONFIRMED = "confirmed"
TRANSFER_STATUS_REJECTED = "rejected"
TRANSFER_STATUS_CANCELLED = "cancelled"
VALID_TRANSFER_STATUSES = [TRANSFER_STATUS_PENDING, TRANSFER_STATUS_CONFIRMED, TRANSFER_STATUS_REJECTED, TRANSFER_STATUS_CANCELLED]

MAX_SECOND_BENEFICIARIES = 3
PARTIAL_TRANSFER_MAX_RATIO = 0.80

BACK_TO_BACK_STATUS_PENDING = "pending_review"
BACK_TO_BACK_STATUS_IN_REVIEW = "in_review"
BACK_TO_BACK_STATUS_REVIEWED = "reviewed"
BACK_TO_BACK_STATUS_REJECTED = "rejected"
VALID_BACK_TO_BACK_STATUSES = [BACK_TO_BACK_STATUS_PENDING, BACK_TO_BACK_STATUS_IN_REVIEW, BACK_TO_BACK_STATUS_REVIEWED, BACK_TO_BACK_STATUS_REJECTED]

BACK_TO_BACK_AMOUNT_RATIO = 0.95
BACK_TO_BACK_SHIPMENT_DAYS_BEFORE = 5
BACK_TO_BACK_EXPIRY_DAYS_BEFORE = 10

CONFLICT_STATUS_NORMAL = "normal"
CONFLICT_STATUS_CONFLICT = "conflict"


class LCTransfer(Base):
    __tablename__ = "lc_transfers"

    id = Column(Integer, primary_key=True, index=True)
    original_lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    transfer_number = Column(String(200), unique=True, index=True, nullable=False)
    second_beneficiary_name = Column(String(255), nullable=False)
    transfer_amount = Column(Float, nullable=False)
    transfer_type = Column(String(20), nullable=False)
    status = Column(String(20), default=TRANSFER_STATUS_PENDING, nullable=False)
    confirmation_time = Column(DateTime, nullable=True)
    inherited_terms = Column(JSON, nullable=True)
    sequence_number = Column(Integer, nullable=False)
    lc = relationship("LetterOfCredit", back_populates="transfers")
    created_at = Column(DateTime, default=datetime.utcnow)


class BackToBackLC(Base):
    __tablename__ = "back_to_back_lcs"

    id = Column(Integer, primary_key=True, index=True)
    original_lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    back_to_back_number = Column(String(200), unique=True, index=True, nullable=False)
    beneficiary_name = Column(String(255), nullable=False)
    applicant_name = Column(String(255), nullable=False)
    issuing_bank = Column(String(255), nullable=False)
    currency = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    latest_shipment_date = Column(Date, nullable=False)
    latest_presentation_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    transport_mode = Column(String(50), nullable=False)
    port_of_loading = Column(String(255), nullable=False)
    port_of_discharge = Column(String(255), nullable=False)
    partial_shipment_allowed = Column(Boolean, default=False)
    transshipment_allowed = Column(Boolean, default=False)
    goods_description = Column(Text, nullable=False)
    additional_terms = Column(JSON, default=list)
    document_requirements = relationship("BackToBackDocumentRequirement", back_populates="back_to_back_lc", cascade="all, delete-orphan")
    status = Column(String(20), default=BACK_TO_BACK_STATUS_PENDING, nullable=False)
    conflict_status = Column(String(20), default=CONFLICT_STATUS_NORMAL, nullable=False)
    conflict_details = Column(JSON, nullable=True)
    original_lc = relationship("LetterOfCredit", back_populates="back_to_back_lcs")
    created_at = Column(DateTime, default=datetime.utcnow)


class BackToBackDocumentRequirement(Base):
    __tablename__ = "back_to_back_document_requirements"

    id = Column(Integer, primary_key=True, index=True)
    back_to_back_lc_id = Column(Integer, ForeignKey("back_to_back_lcs.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    original_copies = Column(Integer, default=0)
    copy_copies = Column(Integer, default=0)
    back_to_back_lc = relationship("BackToBackLC", back_populates="document_requirements")


class ReviewOpinion(Base):
    __tablename__ = "review_opinions"

    id = Column(Integer, primary_key=True, index=True)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("reviewers.id"), nullable=False)
    action_type = Column(String(30), nullable=False)
    overruled_reason = Column(Text, nullable=True)
    new_conclusion = Column(String(50), nullable=True)
    remarks = Column(Text, nullable=True)
    review_duration_seconds = Column(Integer, nullable=True)
    audit_record = relationship("AuditRecord", back_populates="review_opinions")
    reviewer = relationship("Reviewer", back_populates="review_opinions")
    created_at = Column(DateTime, default=datetime.utcnow)
