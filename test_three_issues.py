import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app import models, schemas, crud

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_three_issues.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def setup_module(module):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = next(override_get_db())

    lc1_data = schemas.LetterOfCreditCreate(
        lc_number="ISSUE-LC-001",
        issuing_bank="BANK OF CHINA",
        beneficiary_name="SHANGHAI TRADING CO.",
        applicant_name="ABC IMPORT CO.",
        currency=schemas.Currency.USD,
        amount=80000.00,
        latest_shipment_date=date(2024, 12, 31),
        latest_presentation_date=date(2025, 1, 15),
        expiry_date=date(2025, 1, 20),
        transport_mode=schemas.TransportMode.SEA,
        port_of_loading="SHANGHAI",
        port_of_discharge="ROTTERDAM",
        partial_shipment_allowed=False,
        transshipment_allowed=False,
        goods_description="MACHINERY EQUIPMENT",
        additional_terms=["INSURANCE 110% OF INVOICE VALUE"],
        fee_tier=schemas.FeeTier.STANDARD,
        document_requirements=[
            schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
            schemas.DocumentRequirementCreate(document_type="insurance", original_copies=2, copy_copies=1),
        ]
    )
    crud.create_letter_of_credit(db, lc1_data)
    db.close()


def teardown_module(module):
    if os.path.exists("./test_three_issues.db"):
        os.remove("./test_three_issues.db")


class TestIssue1ReviewStatus:
    """问题1: 预置数据的审核记录查出来复核状态是空的而不是待复核"""

    def test_submit_and_check_review_status(self):
        response = client.post(
            "/api/submission",
            json={
                "lc_number": "ISSUE-LC-001",
                "submission_id": "ISSUE-SUB-001",
                "presentation_date": "2024-12-20",
                "documents": [
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-001",
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-001",
                            "invoice_date": "2024-12-18",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 80000.00,
                            "goods_description": "MACHINERY EQUIPMENT"
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-001",
                        "document_type": "bill_of_lading",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 3,
                        "content": {
                            "bl_number": "BL-001",
                            "shipper": "SHANGHAI TRADING CO.",
                            "consignee": "TO ORDER",
                            "port_of_loading": "SHANGHAI",
                            "port_of_discharge": "ROTTERDAM",
                            "shipment_date": "2024-12-18",
                            "freight_term": "FREIGHT PREPAID",
                            "clean": True
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-001",
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-001",
                            "issue_date": "2024-12-17",
                            "insurance_amount": 88000.00,
                            "currency": "USD",
                            "risks": "ALL RISKS"
                        }
                    }
                ]
            }
        )
        assert response.status_code == 201
        data = response.json()
        audit_id = data["id"]

        detail_response = client.get(f"/api/audit/{audit_id}/review")
        assert detail_response.status_code == 200
        detail = detail_response.json()

        print(f"\n  审核记录 ID: {audit_id}")
        print(f"  review_status: {detail.get('review_status')}")
        print(f"  auto_conclusion: {detail.get('auto_conclusion')}")
        print(f"  final_conclusion: {detail.get('final_conclusion')}")

        assert detail["review_status"] is not None, "❌ review_status 是空值!"
        assert detail["review_status"] == "pending_review", f"❌ 状态应该是 pending_review, 实际是 {detail['review_status']}"
        assert detail["auto_conclusion"] is not None, "❌ auto_conclusion 是空值!"

        print("  ✅ 问题1验证通过: 复核状态正确为 pending_review")


class TestIssue3FeeStatus:
    """问题3: 审单员确认系统结论之后费用状态应该跟着同步更新"""

    def test_confirm_updates_fee_status(self):
        db = next(override_get_db())

        client.post(
            "/api/reviewers",
            json={"employee_id": "ISSUE-R001", "name": "问题测试员", "department": "测试部"}
        )

        audit = crud.get_audit_record_by_submission(db, "ISSUE-SUB-001")
        fee_before = db.query(models.FeeRecord).filter_by(audit_record_id=audit.id).first()
        print(f"\n  复核前费用状态: {fee_before.status if fee_before else 'None'}")
        print(f"  系统结论: {audit.conclusion}")

        client.post(f"/api/audit/{audit.id}/claim", json={"employee_id": "ISSUE-R001"})

        confirm_response = client.post(
            f"/api/audit/{audit.id}/review",
            json={"action": "confirm", "remarks": "确认无误"}
        )
        assert confirm_response.status_code == 200

        db.refresh(fee_before)
        print(f"  复核后费用状态: {fee_before.status}")

        expected_status = crud.determine_fee_status(audit.conclusion)
        assert fee_before.status == expected_status, f"❌ 费用状态应为 {expected_status}, 实际是 {fee_before.status}"
        print(f"  ✅ 问题3验证通过: 确认后费用状态正确为 {fee_before.status}")

    def test_overrule_updates_fee_status(self):
        db = next(override_get_db())

        response = client.post(
            "/api/submission",
            json={
                "lc_number": "ISSUE-LC-001",
                "submission_id": "ISSUE-SUB-002",
                "presentation_date": "2024-12-22",
                "documents": [
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-002",
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-002",
                            "invoice_date": "2024-12-20",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 85000.00,
                            "goods_description": "MACHINERY EQUIPMENT"
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-002",
                        "document_type": "bill_of_lading",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 3,
                        "content": {
                            "bl_number": "BL-002",
                            "shipper": "SHANGHAI TRADING CO.",
                            "consignee": "TO ORDER",
                            "port_of_loading": "SHANGHAI",
                            "port_of_discharge": "ROTTERDAM",
                            "shipment_date": "2024-12-20",
                            "freight_term": "FREIGHT PREPAID",
                            "clean": True
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": "ISSUE-SUB-002",
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-002",
                            "issue_date": "2024-12-19",
                            "insurance_amount": 80000.00,
                            "currency": "USD",
                            "risks": "ALL RISKS"
                        }
                    }
                ]
            }
        )
        assert response.status_code == 201

        audit = crud.get_audit_record_by_submission(db, "ISSUE-SUB-002")
        fee_before = db.query(models.FeeRecord).filter_by(audit_record_id=audit.id).first()
        print(f"\n  推翻前费用状态: {fee_before.status}")
        print(f"  系统结论: {audit.conclusion}")

        client.post(f"/api/audit/{audit.id}/claim", json={"employee_id": "ISSUE-R001"})

        overrule_response = client.post(
            f"/api/audit/{audit.id}/review",
            json={
                "action": "overrule",
                "overrule_data": {
                    "new_conclusion": "compliant",
                    "overruled_reason": "经核实可接受"
                },
                "remarks": "推翻测试"
            }
        )
        assert overrule_response.status_code == 200

        db.refresh(fee_before)
        print(f"  推翻后费用状态: {fee_before.status}")
        assert fee_before.status == "confirmed", f"❌ 费用状态应为 confirmed, 实际是 {fee_before.status}"
        print(f"  ✅ 问题3验证通过: 推翻结论后费用状态更新为 {fee_before.status}")


class TestIssue2Stats:
    """问题2: 审单员工作量统计接口返回的复核笔数和平均耗时都是空值不是数字"""

    def test_stats_are_numbers(self):
        today = date.today()
        start_date = today - timedelta(days=30)
        end_date = today + timedelta(days=1)

        response = client.get(
            f"/api/reviewer/ISSUE-R001/stats?start_date={start_date}&end_date={end_date}"
        )
        assert response.status_code == 200
        stats = response.json()

        print(f"\n  统计结果:")
        for k, v in stats.items():
            print(f"    {k}: {v} (类型: {type(v).__name__})")

        assert stats["total_reviewed"] is not None, "❌ total_reviewed 是空值!"
        assert isinstance(stats["total_reviewed"], int), f"❌ total_reviewed 不是 int 类型, 是 {type(stats['total_reviewed'])}"
        assert stats["total_reviewed"] >= 2, f"❌ total_reviewed 应该 >= 2, 实际是 {stats['total_reviewed']}"

        assert stats["avg_review_duration_seconds"] is not None, "❌ avg_review_duration_seconds 是空值!"
        assert isinstance(stats["avg_review_duration_seconds"], float), f"❌ avg_review_duration_seconds 不是 float 类型"
        assert stats["avg_review_duration_seconds"] >= 0, "❌ 平均耗时不能为负数"

        assert isinstance(stats["confirm_rate"], float), "❌ confirm_rate 不是 float 类型"
        assert isinstance(stats["total_review_duration_seconds"], int), "❌ total_review_duration_seconds 不是 int 类型"

        print("  ✅ 问题2验证通过: 所有统计字段都是数字类型且有值")


class TestIssue1SubmissionDetail:
    """问题1b: 提交详情接口也应该包含 review_status 字段"""

    def test_submission_detail_has_review_status(self):
        submission_id = "ISSUE-DETAIL-001"
        response = client.post(
            "/api/submission",
            json={
                "lc_number": "ISSUE-LC-001",
                "submission_id": submission_id,
                "presentation_date": "2024-12-20",
                "documents": [
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": submission_id,
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-DET-001",
                            "invoice_date": "2024-12-18",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 80000.00,
                            "goods_description": "MACHINERY EQUIPMENT"
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": submission_id,
                        "document_type": "bill_of_lading",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 3,
                        "content": {
                            "bl_number": "BL-DET-001",
                            "shipper": "SHANGHAI TRADING CO.",
                            "consignee": "TO ORDER",
                            "port_of_loading": "SHANGHAI",
                            "port_of_discharge": "ROTTERDAM",
                            "shipment_date": "2024-12-18",
                            "freight_term": "FREIGHT PREPAID",
                            "clean": True
                        }
                    },
                    {
                        "lc_number": "ISSUE-LC-001",
                        "submission_id": submission_id,
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-DET-001",
                            "insured_amount": 88000.00,
                            "currency": "USD",
                            "risk_coverage": "ALL RISKS",
                            "issue_date": "2024-12-18"
                        }
                    }
                ]
            }
        )
        assert response.status_code == 201

        detail_response = client.get(f"/api/submission/{submission_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()

        assert "review_status" in detail, "❌ 提交详情接口缺少 review_status 字段"
        assert detail["review_status"] == "pending_review", f"❌ 状态应该是 pending_review, 实际是 {detail['review_status']}"
        assert "auto_conclusion" in detail, "❌ 提交详情接口缺少 auto_conclusion 字段"
        assert "final_conclusion" in detail, "❌ 提交详情接口缺少 final_conclusion 字段"

        print(f"\n  提交详情接口字段验证:")
        print(f"    review_status: {detail['review_status']}")
        print(f"    auto_conclusion: {detail['auto_conclusion']}")
        print(f"    final_conclusion: {detail['final_conclusion']}")
        print("  ✅ 提交详情接口包含所有复核相关字段")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
