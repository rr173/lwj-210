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


PAYMENT_METHOD_SIGHT = "sight"
PAYMENT_METHOD_USANCE = "usance"
PAYMENT_METHOD_DEFERRED = "deferred"
VALID_PAYMENT_METHODS = [PAYMENT_METHOD_SIGHT, PAYMENT_METHOD_USANCE, PAYMENT_METHOD_DEFERRED]

USANCE_BASIS_SHIPMENT_DATE = "shipment_date"
USANCE_BASIS_PRESENTATION_DATE = "presentation_date"
USANCE_BASIS_BL_DATE = "bl_date"
VALID_USANCE_BASES = [USANCE_BASIS_SHIPMENT_DATE, USANCE_BASIS_PRESENTATION_DATE, USANCE_BASIS_BL_DATE]

PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_ACCEPTED = "accepted"
PAYMENT_STATUS_MATURED = "matured"
PAYMENT_STATUS_OVERDUE = "overdue"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_REJECTED = "rejected"
VALID_PAYMENT_STATUSES = [PAYMENT_STATUS_PENDING, PAYMENT_STATUS_ACCEPTED, PAYMENT_STATUS_MATURED, PAYMENT_STATUS_OVERDUE, PAYMENT_STATUS_PAID, PAYMENT_STATUS_REJECTED]

SIGHT_PROCESSING_DAYS = 5
DEFAULT_PENALTY_RATE = 6.0
OVERDUE_GRACE_WORKING_DAYS = 3

COLLECTION_TYPE_SYSTEM_AUTO = "system_auto"
COLLECTION_TYPE_MANUAL = "manual"
VALID_COLLECTION_TYPES = [COLLECTION_TYPE_SYSTEM_AUTO, COLLECTION_TYPE_MANUAL]

COLLECTION_METHOD_PHONE = "phone"
COLLECTION_METHOD_EMAIL = "email"
COLLECTION_METHOD_LETTER = "letter"
VALID_COLLECTION_METHODS = [COLLECTION_METHOD_PHONE, COLLECTION_METHOD_EMAIL, COLLECTION_METHOD_LETTER]


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
    payment_method = Column(String(20), default=PAYMENT_METHOD_SIGHT, nullable=False)
    usance_days = Column(Integer, nullable=True)
    usance_basis = Column(String(30), nullable=True)
    deferred_payment_date = Column(Date, nullable=True)
    penalty_interest_rate = Column(Float, default=DEFAULT_PENALTY_RATE, nullable=False)
    document_requirements = relationship("DocumentRequirement", back_populates="lc", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="lc", cascade="all, delete-orphan")
    audit_records = relationship("AuditRecord", back_populates="lc", cascade="all, delete-orphan")
    amendments = relationship("LCAmendment", back_populates="lc", cascade="all, delete-orphan", order_by="LCAmendment.sequence_number")
    fee_records = relationship("FeeRecord", back_populates="lc", cascade="all, delete-orphan")
    transfers = relationship("LCTransfer", back_populates="lc", cascade="all, delete-orphan", order_by="LCTransfer.sequence_number")
    back_to_back_lcs = relationship("BackToBackLC", back_populates="original_lc", cascade="all, delete-orphan")
    alerts = relationship("LCAlert", back_populates="lc", cascade="all, delete-orphan", order_by="LCAlert.created_at.desc()")
    freeze_records = relationship("LCFreezeRecord", back_populates="lc", cascade="all, delete-orphan", order_by="LCFreezeRecord.created_at.desc()")
    payments = relationship("Payment", back_populates="lc", cascade="all, delete-orphan", order_by="Payment.created_at.desc()")
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


RULE_VERSION_STATUS_DRAFT = "draft"
RULE_VERSION_STATUS_TESTING = "testing"
RULE_VERSION_STATUS_ACTIVE = "active"
RULE_VERSION_STATUS_ARCHIVED = "archived"
VALID_RULE_VERSION_STATUSES = [
    RULE_VERSION_STATUS_DRAFT,
    RULE_VERSION_STATUS_TESTING,
    RULE_VERSION_STATUS_ACTIVE,
    RULE_VERSION_STATUS_ARCHIVED,
]

VALID_CHECK_CATEGORIES = [
    "completeness", "amount", "date", "party", "goods", "transport", "special"
]

DEFAULT_RULE_CONTENT = {
    "amount_tolerance": 0.01,
    "date_tolerance_days": 0,
    "name_case_sensitive": False,
    "enabled_categories": [
        "completeness", "amount", "date", "party", "goods", "transport", "special"
    ],
    "severity_overrides": {}
}


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id = Column(Integer, primary_key=True, index=True)
    version_number = Column(String(50), unique=True, index=True, nullable=False)
    status = Column(String(20), default=RULE_VERSION_STATUS_DRAFT, nullable=False)
    rules = Column(JSON, nullable=False)
    grayscale_percentage = Column(Integer, default=0, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)


EPSILON = 0.01


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
    rule_version_id = Column(Integer, ForeignKey("rule_versions.id"), nullable=True)
    discrepancies = relationship("Discrepancy", back_populates="audit_record", cascade="all, delete-orphan")
    review_assignments = relationship("ReviewAssignment", back_populates="audit_record", cascade="all, delete-orphan")
    review_opinions = relationship("ReviewOpinion", back_populates="audit_record", cascade="all, delete-orphan")
    rule_version = relationship("RuleVersion")
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


ALERT_TYPE_SHIPMENT = "shipment"
ALERT_TYPE_PRESENTATION = "presentation"
ALERT_TYPE_EXPIRY = "expiry"
VALID_ALERT_TYPES = [ALERT_TYPE_SHIPMENT, ALERT_TYPE_PRESENTATION, ALERT_TYPE_EXPIRY]

ALERT_STATUS_ACTIVE = "active"
ALERT_STATUS_ACKNOWLEDGED = "acknowledged"
ALERT_STATUS_EXPIRED = "expired"
VALID_ALERT_STATUSES = [ALERT_STATUS_ACTIVE, ALERT_STATUS_ACKNOWLEDGED, ALERT_STATUS_EXPIRED]

ALERT_SHIPMENT_DAYS_BEFORE = 7
ALERT_PRESENTATION_DAYS_BEFORE = 5
ALERT_EXPIRY_DAYS_BEFORE = 10


class LCAlert(Base):
    __tablename__ = "lc_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_number = Column(String(150), unique=True, index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)
    trigger_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False)
    remaining_days = Column(Integer, nullable=False)
    status = Column(String(20), default=ALERT_STATUS_ACTIVE, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    lc = relationship("LetterOfCredit", back_populates="alerts")
    created_at = Column(DateTime, default=datetime.utcnow)


FREEZE_TYPE_SHIPMENT_EXPIRED = "shipment_expired"
FREEZE_TYPE_PRESENTATION_EXPIRED = "presentation_expired"
FREEZE_TYPE_EXPIRY_EXPIRED = "expiry_expired"
FREEZE_TYPE_MANUAL = "manual"
VALID_FREEZE_TYPES = [
    FREEZE_TYPE_SHIPMENT_EXPIRED,
    FREEZE_TYPE_PRESENTATION_EXPIRED,
    FREEZE_TYPE_EXPIRY_EXPIRED,
    FREEZE_TYPE_MANUAL
]

FREEZE_STATUS_ACTIVE = "active"
FREEZE_STATUS_RELEASED = "released"
VALID_FREEZE_STATUSES = [FREEZE_STATUS_ACTIVE, FREEZE_STATUS_RELEASED]


SWIFT_MSG_TYPE_MT700 = "MT700"
SWIFT_MSG_TYPE_MT707 = "MT707"
SWIFT_MSG_TYPE_MT799 = "MT799"
VALID_SWIFT_MSG_TYPES = [SWIFT_MSG_TYPE_MT700, SWIFT_MSG_TYPE_MT707, SWIFT_MSG_TYPE_MT799]

SWIFT_SEND_STATUS_PENDING = "pending"
SWIFT_SEND_STATUS_SENT = "sent"
SWIFT_SEND_STATUS_FAILED = "failed"
VALID_SWIFT_SEND_STATUSES = [SWIFT_SEND_STATUS_PENDING, SWIFT_SEND_STATUS_SENT, SWIFT_SEND_STATUS_FAILED]


class SwiftMessageQueue(Base):
    __tablename__ = "swift_message_queue"

    id = Column(Integer, primary_key=True, index=True)
    message_number = Column(String(150), unique=True, index=True, nullable=False)
    message_type = Column(String(10), nullable=False)
    lc_number = Column(String(100), index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=True)
    raw_message = Column(Text, nullable=False)
    status = Column(String(20), default=SWIFT_SEND_STATUS_PENDING, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    lc = relationship("LetterOfCredit")
    created_at = Column(DateTime, default=datetime.utcnow)


class LCFreezeRecord(Base):
    __tablename__ = "lc_freeze_records"

    id = Column(Integer, primary_key=True, index=True)
    freeze_number = Column(String(150), unique=True, index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    freeze_type = Column(String(30), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default=FREEZE_STATUS_ACTIVE, nullable=False)
    frozen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(String(100), nullable=True)
    release_reason = Column(Text, nullable=True)
    lc = relationship("LetterOfCredit", back_populates="freeze_records")
    created_at = Column(DateTime, default=datetime.utcnow)


PARTY_ROLE_ISSUING_BANK = "issuing_bank"
PARTY_ROLE_ADVISING_BANK = "advising_bank"
PARTY_ROLE_BENEFICIARY = "beneficiary"
PARTY_ROLE_APPLICANT = "applicant"
VALID_PARTY_ROLES = [
    PARTY_ROLE_ISSUING_BANK,
    PARTY_ROLE_ADVISING_BANK,
    PARTY_ROLE_BENEFICIARY,
    PARTY_ROLE_APPLICANT,
]

EVENT_TYPE_LC_CREATED = "lc_created"
EVENT_TYPE_SUBMISSION_CREATED = "submission_created"
EVENT_TYPE_SUBMISSION_REVIEWED = "submission_reviewed"
EVENT_TYPE_AMENDMENT_CREATED = "amendment_created"
EVENT_TYPE_AMENDMENT_ACCEPTED = "amendment_accepted"
EVENT_TYPE_AMENDMENT_REJECTED = "amendment_rejected"
EVENT_TYPE_ALERT_GENERATED = "alert_generated"
EVENT_TYPE_FREEZE_CREATED = "freeze_created"
EVENT_TYPE_FREEZE_RELEASED = "freeze_released"
EVENT_TYPE_TRANSFER_CREATED = "transfer_created"
EVENT_TYPE_BACK_TO_BACK_CREATED = "back_to_back_created"
VALID_EVENT_TYPES = [
    EVENT_TYPE_LC_CREATED,
    EVENT_TYPE_SUBMISSION_CREATED,
    EVENT_TYPE_SUBMISSION_REVIEWED,
    EVENT_TYPE_AMENDMENT_CREATED,
    EVENT_TYPE_AMENDMENT_ACCEPTED,
    EVENT_TYPE_AMENDMENT_REJECTED,
    EVENT_TYPE_ALERT_GENERATED,
    EVENT_TYPE_FREEZE_CREATED,
    EVENT_TYPE_FREEZE_RELEASED,
    EVENT_TYPE_TRANSFER_CREATED,
    EVENT_TYPE_BACK_TO_BACK_CREATED,
]

DEFAULT_SUBSCRIPTIONS = {
    PARTY_ROLE_BENEFICIARY: [
        EVENT_TYPE_AMENDMENT_CREATED,
        EVENT_TYPE_SUBMISSION_REVIEWED,
        EVENT_TYPE_ALERT_GENERATED,
        EVENT_TYPE_FREEZE_CREATED,
        EVENT_TYPE_LC_CREATED,
        EVENT_TYPE_SUBMISSION_CREATED,
        EVENT_TYPE_FREEZE_RELEASED,
    ],
    PARTY_ROLE_ISSUING_BANK: [
        EVENT_TYPE_SUBMISSION_CREATED,
        EVENT_TYPE_AMENDMENT_ACCEPTED,
        EVENT_TYPE_LC_CREATED,
        EVENT_TYPE_SUBMISSION_REVIEWED,
        EVENT_TYPE_FREEZE_CREATED,
        EVENT_TYPE_FREEZE_RELEASED,
        EVENT_TYPE_ALERT_GENERATED,
    ],
    PARTY_ROLE_ADVISING_BANK: [
        EVENT_TYPE_LC_CREATED,
        EVENT_TYPE_AMENDMENT_CREATED,
        EVENT_TYPE_AMENDMENT_ACCEPTED,
        EVENT_TYPE_ALERT_GENERATED,
    ],
    PARTY_ROLE_APPLICANT: [
        EVENT_TYPE_LC_CREATED,
        EVENT_TYPE_SUBMISSION_CREATED,
        EVENT_TYPE_SUBMISSION_REVIEWED,
        EVENT_TYPE_AMENDMENT_CREATED,
        EVENT_TYPE_AMENDMENT_ACCEPTED,
        EVENT_TYPE_ALERT_GENERATED,
    ],
}

NOTIFICATION_STATUS_UNREAD = "unread"
NOTIFICATION_STATUS_READ = "read"
NOTIFICATION_STATUS_ARCHIVED = "archived"
VALID_NOTIFICATION_STATUSES = [
    NOTIFICATION_STATUS_UNREAD,
    NOTIFICATION_STATUS_READ,
    NOTIFICATION_STATUS_ARCHIVED,
]


class Party(Base):
    __tablename__ = "parties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)
    contact = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("PartySubscription", back_populates="party", cascade="all, delete-orphan")
    lc_parties = relationship("LetterOfCreditParty", back_populates="party", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="party", cascade="all, delete-orphan")


class PartySubscription(Base):
    __tablename__ = "party_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    party = relationship("Party", back_populates="subscriptions")


class LetterOfCreditParty(Base):
    __tablename__ = "letter_of_credit_parties"

    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    role = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    lc = relationship("LetterOfCredit")
    party = relationship("Party", back_populates="lc_parties")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    notification_number = Column(String(150), unique=True, index=True, nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    event_summary = Column(String(500), nullable=False)
    event_ref_id = Column(String(100), nullable=True)
    status = Column(String(20), default=NOTIFICATION_STATUS_UNREAD, nullable=False)
    read_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    party = relationship("Party", back_populates="notifications")
    lc = relationship("LetterOfCredit")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_number = Column(String(150), unique=True, index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    submission_id = Column(String(100), index=True, nullable=False)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=False)
    payment_amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    payment_method = Column(String(20), nullable=False)
    maturity_date = Column(Date, nullable=False)
    status = Column(String(20), default=PAYMENT_STATUS_PENDING, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    total_paid_amount = Column(Float, default=0.0, nullable=False)
    total_penalty_paid = Column(Float, default=0.0, nullable=False)
    actual_payment_date = Column(Date, nullable=True)
    lc = relationship("LetterOfCredit", back_populates="payments")
    audit_record = relationship("AuditRecord")
    status_history = relationship("PaymentStatusHistory", back_populates="payment", cascade="all, delete-orphan", order_by="PaymentStatusHistory.changed_at.asc()")
    partial_payments = relationship("PartialPaymentRecord", back_populates="payment", cascade="all, delete-orphan", order_by="PartialPaymentRecord.created_at.asc()")
    collection_records = relationship("CollectionRecord", back_populates="payment", cascade="all, delete-orphan", order_by="CollectionRecord.created_at.desc()")
    created_at = Column(DateTime, default=datetime.utcnow)


class PaymentStatusHistory(Base):
    __tablename__ = "payment_status_history"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    changed_by = Column(String(100), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    remark = Column(Text, nullable=True)
    payment = relationship("Payment", back_populates="status_history")


class PartialPaymentRecord(Base):
    __tablename__ = "partial_payment_records"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    amount = Column(Float, nullable=False)
    penalty_amount = Column(Float, default=0.0, nullable=False)
    payment_date = Column(Date, nullable=False)
    reference = Column(String(200), nullable=True)
    created_by = Column(String(100), nullable=True)
    payment = relationship("Payment", back_populates="partial_payments")
    created_at = Column(DateTime, default=datetime.utcnow)


class CollectionRecord(Base):
    __tablename__ = "collection_records"

    id = Column(Integer, primary_key=True, index=True)
    collection_number = Column(String(150), unique=True, index=True, nullable=False)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    collection_type = Column(String(30), nullable=False)
    collection_method = Column(String(30), nullable=True)
    contact_person = Column(String(200), nullable=True)
    collection_content = Column(Text, nullable=False)
    collection_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100), nullable=True)
    payment = relationship("Payment", back_populates="collection_records")
    created_at = Column(DateTime, default=datetime.utcnow)


CREDIT_LINE_TRANSACTION_TYPE_OCCUPY = "occupy"
CREDIT_LINE_TRANSACTION_TYPE_RELEASE = "release"
CREDIT_LINE_TRANSACTION_TYPE_ADJUST = "adjust"
VALID_CREDIT_LINE_TRANSACTION_TYPES = [
    CREDIT_LINE_TRANSACTION_TYPE_OCCUPY,
    CREDIT_LINE_TRANSACTION_TYPE_RELEASE,
    CREDIT_LINE_TRANSACTION_TYPE_ADJUST,
]


class CreditLine(Base):
    __tablename__ = "credit_lines"

    id = Column(Integer, primary_key=True, index=True)
    applicant_name = Column(String(255), nullable=False, index=True)
    currency = Column(String(10), nullable=False, index=True)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("CreditLineTransaction", back_populates="credit_line", cascade="all, delete-orphan")


class CreditLineTransaction(Base):
    __tablename__ = "credit_line_transactions"

    id = Column(Integer, primary_key=True, index=True)
    credit_line_id = Column(Integer, ForeignKey("credit_lines.id"), nullable=False)
    transaction_number = Column(String(150), unique=True, index=True, nullable=False)
    transaction_type = Column(String(20), nullable=False)
    change_amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    lc_number = Column(String(100), nullable=True, index=True)
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    credit_line = relationship("CreditLine", back_populates="transactions")
