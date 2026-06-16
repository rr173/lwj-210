import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime, date, timedelta

Base = declarative_base()


class LetterOfCredit(Base):
    __tablename__ = "letter_of_credits"
    id = Column(Integer, primary_key=True, index=True)
    lc_number = Column(String(50), unique=True, index=True, nullable=False)
    issuing_bank = Column(String(200), nullable=False)
    beneficiary_name = Column(String(200), nullable=False)
    applicant_name = Column(String(200), nullable=False)
    currency = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    latest_shipment_date = Column(Date, nullable=False)
    latest_presentation_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    transport_mode = Column(String(20), nullable=False)
    port_of_loading = Column(String(100), nullable=False)
    port_of_discharge = Column(String(100), nullable=False)
    partial_shipment_allowed = Column(Boolean, default=False)
    transshipment_allowed = Column(Boolean, default=False)
    goods_description = Column(Text, nullable=False)
    additional_terms = Column(Text)
    fee_tier = Column(String(20), default="standard")
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"
    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    original_copies = Column(Integer, default=1)
    copy_copies = Column(Integer, default=0)


class SubmittedDocument(Base):
    __tablename__ = "submitted_documents"
    id = Column(Integer, primary_key=True, index=True)
    lc_number = Column(String(50), nullable=False)
    submission_id = Column(String(100), index=True, nullable=False)
    document_type = Column(String(50), nullable=False)
    original_copies_submitted = Column(Integer, default=0)
    copy_copies_submitted = Column(Integer, default=0)
    content = Column(Text)
    submitted_at = Column(DateTime, default=datetime.utcnow)


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


class AmendmentRecord(Base):
    __tablename__ = "amendment_records"
    id = Column(Integer, primary_key=True, index=True)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    amendment_number = Column(String(50), nullable=False)
    original_lc_snapshot = Column(Text, nullable=False)
    changes = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    applicant_response = Column(Text)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeeRecord(Base):
    __tablename__ = "fee_records"
    id = Column(Integer, primary_key=True, index=True)
    fee_number = Column(String(50), unique=True, index=True, nullable=False)
    lc_id = Column(Integer, ForeignKey("letter_of_credits.id"), nullable=False)
    audit_record_id = Column(Integer, ForeignKey("audit_records.id"), nullable=True)
    fee_type = Column(String(30), nullable=False)
    currency = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    fee_tier = Column(String(20), default="standard")
    created_at = Column(DateTime, default=datetime.utcnow)


DB_PATH = "./old_test.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

import json

lc = LetterOfCredit(
    lc_number="OLD-LC-001",
    issuing_bank="BANK OF CHINA",
    beneficiary_name="SHANGHAI TRADING CO.",
    applicant_name="ABC IMPORT CO.",
    currency="USD",
    amount=50000.00,
    latest_shipment_date=date(2024, 12, 31),
    latest_presentation_date=date(2025, 1, 15),
    expiry_date=date(2025, 1, 20),
    transport_mode="sea",
    port_of_loading="SHANGHAI",
    port_of_discharge="ROTTERDAM",
    partial_shipment_allowed=False,
    transshipment_allowed=False,
    goods_description="ELECTRONIC PRODUCTS",
    additional_terms=json.dumps(["INSURANCE 110% OF INVOICE VALUE"]),
    fee_tier="standard"
)
db.add(lc)
db.flush()

doc_req1 = DocumentRequirement(lc_id=lc.id, document_type="invoice", original_copies=3, copy_copies=2)
doc_req2 = DocumentRequirement(lc_id=lc.id, document_type="bill_of_lading", original_copies=3, copy_copies=3)
doc_req3 = DocumentRequirement(lc_id=lc.id, document_type="insurance", original_copies=2, copy_copies=1)
db.add_all([doc_req1, doc_req2, doc_req3])

audit = AuditRecord(
    lc_id=lc.id,
    submission_id="OLD-SUB-001",
    original_submission_id="OLD-SUB-001",
    resubmission_round=0,
    conclusion="compliant",
    total_discrepancies=0,
    critical_count=0,
    minor_count=0,
    presentation_date=date(2024, 12, 20)
)
db.add(audit)
db.flush()

sub_doc1 = SubmittedDocument(
    lc_number="OLD-LC-001",
    submission_id="OLD-SUB-001",
    document_type="invoice",
    original_copies_submitted=3,
    copy_copies_submitted=2,
    content=json.dumps({"invoice_number": "INV-001", "total_amount": 50000.00})
)
sub_doc2 = SubmittedDocument(
    lc_number="OLD-LC-001",
    submission_id="OLD-SUB-001",
    document_type="bill_of_lading",
    original_copies_submitted=3,
    copy_copies_submitted=3,
    content=json.dumps({"bl_number": "BL-001"})
)
sub_doc3 = SubmittedDocument(
    lc_number="OLD-LC-001",
    submission_id="OLD-SUB-001",
    document_type="insurance",
    original_copies_submitted=2,
    copy_copies_submitted=1,
    content=json.dumps({"policy_number": "INS-001", "insurance_amount": 55000.00})
)
db.add_all([sub_doc1, sub_doc2, sub_doc3])

fee = FeeRecord(
    fee_number="FEE-OLD-001",
    lc_id=lc.id,
    audit_record_id=audit.id,
    fee_type="first_submission",
    currency="USD",
    amount=100.00,
    status="confirmed",
    fee_tier="standard"
)
db.add(fee)

audit2 = AuditRecord(
    lc_id=lc.id,
    submission_id="OLD-SUB-002",
    original_submission_id="OLD-SUB-002",
    resubmission_round=0,
    conclusion="discrepant",
    total_discrepancies=2,
    critical_count=1,
    minor_count=1,
    presentation_date=date(2024, 12, 22)
)
db.add(audit2)
db.flush()

disc1 = Discrepancy(
    audit_record_id=audit2.id,
    discrepancy_type="amount",
    severity="critical",
    document_type="invoice",
    description="发票金额超过信用证金额",
    lc_clause_reference="第3条"
)
disc2 = Discrepancy(
    audit_record_id=audit2.id,
    discrepancy_type="insurance",
    severity="minor",
    document_type="insurance",
    description="保险金额不足",
    lc_clause_reference="第7条"
)
db.add_all([disc1, disc2])

fee2 = FeeRecord(
    fee_number="FEE-OLD-002",
    lc_id=lc.id,
    audit_record_id=audit2.id,
    fee_type="first_submission",
    currency="USD",
    amount=150.00,
    status="pending",
    fee_tier="standard"
)
db.add(fee2)

db.commit()
db.close()

print(f"旧数据库已创建: {DB_PATH}")
print("包含:")
print("  - 1 个信用证")
print("  - 2 条审核记录 (没有 review_status, auto_conclusion, final_conclusion 字段)")
print("  - 2 条不符点 (没有 source, is_removed, removal_reason 字段)")
print("  - 没有 reviewers, review_assignments, review_opinions 表")
