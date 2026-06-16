import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import models, schemas, crud
from app.models import (
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_IN_REVIEW,
    REVIEW_STATUS_REVIEWED,
    FEE_STATUS_CONFIRMED,
    FEE_STATUS_PENDING,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./debug_test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = TestingSessionLocal()

print("=" * 60)
print("问题1: 预置数据审核记录复核状态检查")
print("=" * 60)

lc1_data = schemas.LetterOfCreditCreate(
    lc_number="DEBUG-LC-001",
    issuing_bank="BANK OF CHINA",
    beneficiary_name="SHANGHAI TRADING CO.",
    applicant_name="ABC IMPORT CO.",
    currency=schemas.Currency.USD,
    amount=50000.00,
    latest_shipment_date=date(2024, 12, 31),
    latest_presentation_date=date(2025, 1, 15),
    expiry_date=date(2025, 1, 20),
    transport_mode=schemas.TransportMode.SEA,
    port_of_loading="SHANGHAI",
    port_of_discharge="ROTTERDAM",
    partial_shipment_allowed=False,
    transshipment_allowed=False,
    goods_description="ELECTRONIC PRODUCTS",
    additional_terms=["INSURANCE 110% OF INVOICE VALUE"],
    fee_tier=schemas.FeeTier.STANDARD,
    document_requirements=[
        schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
        schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
        schemas.DocumentRequirementCreate(document_type="insurance", original_copies=2, copy_copies=1),
    ]
)
lc1 = crud.create_letter_of_credit(db, lc1_data)

submission = schemas.SubmissionSubmit(
    lc_number="DEBUG-LC-001",
    submission_id="DEBUG-SUB-001",
    presentation_date=date(2024, 12, 20),
    documents=[
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-001",
            document_type="invoice",
            original_copies_submitted=3,
            copy_copies_submitted=2,
            content={
                "invoice_number": "INV-001",
                "invoice_date": "2024-12-18",
                "beneficiary": "SHANGHAI TRADING CO.",
                "applicant": "ABC IMPORT CO.",
                "currency": "USD",
                "total_amount": 50000.00,
                "goods_description": "ELECTRONIC PRODUCTS"
            }
        ),
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-001",
            document_type="bill_of_lading",
            original_copies_submitted=3,
            copy_copies_submitted=3,
            content={
                "bl_number": "BL-001",
                "shipper": "SHANGHAI TRADING CO.",
                "consignee": "TO ORDER",
                "port_of_loading": "SHANGHAI",
                "port_of_discharge": "ROTTERDAM",
                "shipment_date": "2024-12-18",
                "freight_term": "FREIGHT PREPAID",
                "clean": True
            }
        ),
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-001",
            document_type="insurance",
            original_copies_submitted=2,
            copy_copies_submitted=1,
            content={
                "policy_number": "INS-001",
                "issue_date": "2024-12-17",
                "insurance_amount": 55000.00,
                "currency": "USD",
                "risks": "ALL RISKS"
            }
        )
    ]
)
audit_record = crud.submit_documents_and_audit(db, submission)

print(f"提交后审核记录 ID: {audit_record.id}")
print(f"  conclusion: {audit_record.conclusion}")
print(f"  auto_conclusion: {audit_record.auto_conclusion}")
print(f"  final_conclusion: {audit_record.final_conclusion}")
print(f"  review_status: {audit_record.review_status}")

if audit_record.review_status is None:
    print("  ❌ 问题: review_status 为 None")
elif audit_record.review_status == REVIEW_STATUS_PENDING:
    print("  ✅ 正确: review_status 为 pending_review")
else:
    print(f"  ⚠️  其他状态: {audit_record.review_status}")

print()
print("=" * 60)
print("问题2: 审单员注册与工作量统计检查")
print("=" * 60)

reviewer = crud.create_reviewer(db, schemas.ReviewerCreate(
    employee_id="DR001",
    name="调试员",
    department="测试部"
))
print(f"审单员 ID: {reviewer.id}, 工号: {reviewer.employee_id}")

assignment = crud.claim_review_task(db, audit_record.id, "DR001")
print(f"认领任务 ID: {assignment.id}")

review_data = schemas.ReviewCompleteRequest(
    action=schemas.ReviewAction.CONFIRM,
    remarks="确认无误"
)
result = crud.complete_review(db, audit_record.id, reviewer.id, review_data)
print(f"复核完成: final_conclusion={result['audit_record'].final_conclusion}")
print(f"  review_duration_seconds: {result['review_duration_seconds']}")

today = date.today()
start_date = today - timedelta(days=30)
end_date = today + timedelta(days=1)
stats = crud.get_reviewer_stats(db, reviewer.id, start_date, end_date)
print(f"\n统计结果:")
for k, v in stats.items():
    print(f"  {k}: {v} (类型: {type(v).__name__})")

if stats["total_reviewed"] == 0:
    print("  ❌ 问题: total_reviewed 为 0")
else:
    print(f"  ✅ total_reviewed = {stats['total_reviewed']}")

print()
print("=" * 60)
print("问题3: 费用状态更新检查")
print("=" * 60)

fee_records = db.query(models.FeeRecord).filter(
    models.FeeRecord.audit_record_id == audit_record.id
).all()
print(f"费用记录数量: {len(fee_records)}")
for fr in fee_records:
    print(f"  费用编号: {fr.fee_number}")
    print(f"  状态: {fr.status}")
    print(f"  费用类型: {fr.fee_type}")

print(f"\n当前审核结论: {audit_record.conclusion}")
print(f"预期费用状态: {crud.determine_fee_status(audit_record.conclusion)}")
if fee_records:
    actual_status = fee_records[0].status
    expected = crud.determine_fee_status(audit_record.conclusion)
    if actual_status == expected:
        print(f"  ✅ 费用状态正确: {actual_status}")
    else:
        print(f"  ❌ 费用状态不匹配: 实际={actual_status}, 预期={expected}")

print()
print("=" * 60)
print("测试: 提交一个有不符点的交单，然后推翻结论，看费用是否变化")
print("=" * 60)

submission2 = schemas.SubmissionSubmit(
    lc_number="DEBUG-LC-001",
    submission_id="DEBUG-SUB-002",
    presentation_date=date(2024, 12, 22),
    documents=[
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-002",
            document_type="invoice",
            original_copies_submitted=3,
            copy_copies_submitted=2,
            content={
                "invoice_number": "INV-002",
                "invoice_date": "2024-12-20",
                "beneficiary": "SHANGHAI TRADING CO.",
                "applicant": "ABC IMPORT CO.",
                "currency": "USD",
                "total_amount": 51000.00,
                "goods_description": "ELECTRONIC PRODUCTS"
            }
        ),
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-002",
            document_type="bill_of_lading",
            original_copies_submitted=3,
            copy_copies_submitted=3,
            content={
                "bl_number": "BL-002",
                "shipper": "SHANGHAI TRADING CO.",
                "consignee": "TO ORDER",
                "port_of_loading": "SHANGHAI",
                "port_of_discharge": "ROTTERDAM",
                "shipment_date": "2024-12-20",
                "freight_term": "FREIGHT PREPAID",
                "clean": True
            }
        ),
        schemas.DocumentSubmit(
            lc_number="DEBUG-LC-001",
            submission_id="DEBUG-SUB-002",
            document_type="insurance",
            original_copies_submitted=2,
            copy_copies_submitted=1,
            content={
                "policy_number": "INS-002",
                "issue_date": "2024-12-19",
                "insurance_amount": 50000.00,
                "currency": "USD",
                "risks": "ALL RISKS"
            }
        )
    ]
)
audit2 = crud.submit_documents_and_audit(db, submission2)
print(f"提交后结论: {audit2.conclusion}")
fee2 = db.query(models.FeeRecord).filter(models.FeeRecord.audit_record_id == audit2.id).first()
print(f"初始费用状态: {fee2.status if fee2 else 'None'}")

assignment2 = crud.claim_review_task(db, audit2.id, "DR001")
review_data2 = schemas.ReviewCompleteRequest(
    action=schemas.ReviewAction.OVERRULE,
    overrule_data=schemas.ReviewOverruleRequest(
        new_conclusion="compliant",
        overruled_reason="经核实可接受"
    ),
    remarks="推翻为相符"
)
result2 = crud.complete_review(db, audit2.id, reviewer.id, review_data2)
db.refresh(fee2)
print(f"推翻后结论: {result2['audit_record'].final_conclusion}")
print(f"推翻后费用状态: {fee2.status}")

if fee2.status == FEE_STATUS_CONFIRMED:
    print("  ✅ 费用状态已更新为 confirmed")
else:
    print(f"  ❌ 费用状态未正确更新: {fee2.status}")

db.close()
os.remove("./debug_test.db")
print("\n调试完成！")
