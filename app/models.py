from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, Text, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta

from app.database import Base


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
    document_requirements = relationship("DocumentRequirement", back_populates="lc", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="lc", cascade="all, delete-orphan")
    audit_records = relationship("AuditRecord", back_populates="lc", cascade="all, delete-orphan")
    amendments = relationship("LCAmendment", back_populates="lc", cascade="all, delete-orphan", order_by="LCAmendment.sequence_number")
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
    total_discrepancies = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    minor_count = Column(Integer, default=0)
    presentation_date = Column(Date, nullable=False)
    discrepancies = relationship("Discrepancy", back_populates="audit_record", cascade="all, delete-orphan")
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
    audit_record = relationship("AuditRecord", back_populates="discrepancies")
