import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app import models, schemas, crud
from app.models import (
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_IN_REVIEW,
    REVIEW_STATUS_REVIEWED,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_reviewer.db"

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


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = next(override_get_db())

    lc1_data = schemas.LetterOfCreditCreate(
        lc_number="TEST-LC-001",
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

    yield

    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_reviewer.db"):
        os.remove("./test_reviewer.db")


class TestReviewerManagement:
    def test_create_reviewer(self):
        response = client.post(
            "/api/reviewers",
            json={
                "employee_id": "R001",
                "name": "张三",
                "department": "国际结算部"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["employee_id"] == "R001"
        assert data["name"] == "张三"
        assert data["department"] == "国际结算部"
        assert data["is_active"] is True

    def test_create_duplicate_reviewer(self):
        response = client.post(
            "/api/reviewers",
            json={
                "employee_id": "R001",
                "name": "李四",
                "department": "单证部"
            }
        )
        assert response.status_code == 400

    def test_create_second_reviewer(self):
        response = client.post(
            "/api/reviewers",
            json={
                "employee_id": "R002",
                "name": "李四",
                "department": "国际结算部"
            }
        )
        assert response.status_code == 201

    def test_get_reviewer_by_employee_id(self):
        response = client.get("/api/reviewers/R001")
        assert response.status_code == 200
        data = response.json()
        assert data["employee_id"] == "R001"
        assert data["name"] == "张三"

    def test_get_nonexistent_reviewer(self):
        response = client.get("/api/reviewers/R999")
        assert response.status_code == 404

    def test_list_reviewers(self):
        response = client.get("/api/reviewers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2


class TestSubmissionAndClaim:
    def submit_documents(self):
        response = client.post(
            "/api/submission",
            json={
                "lc_number": "TEST-LC-001",
                "submission_id": "TEST-SUB-001",
                "presentation_date": "2024-12-20",
                "documents": [
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-001",
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-001",
                            "invoice_date": "2024-12-18",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 50000.00,
                            "goods_description": "ELECTRONIC PRODUCTS"
                        }
                    },
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-001",
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
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-001",
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-001",
                            "issue_date": "2024-12-17",
                            "insurance_amount": 55000.00,
                            "currency": "USD",
                            "risks": "ALL RISKS"
                        }
                    }
                ]
            }
        )
        return response

    def test_submit_documents_pending_review(self):
        response = self.submit_documents()
        assert response.status_code == 201
        data = response.json()
        assert data["conclusion"] == "compliant"
        assert "review_status" not in data or data.get("review_status") is not None

    def test_get_pending_reviews(self):
        response = client.get("/api/review/pending")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_get_audit_record_with_review(self):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-001")
        assert audit is not None
        assert audit.review_status == REVIEW_STATUS_PENDING
        assert audit.auto_conclusion == "compliant"
        assert audit.final_conclusion is None

        response = client.get(f"/api/audit/{audit.id}/review")
        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == REVIEW_STATUS_PENDING
        assert data["auto_conclusion"] == "compliant"
        assert data["final_conclusion"] is None

    def test_claim_review_task(self):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-001")
        assert audit is not None

        response = client.post(
            f"/api/audit/{audit.id}/claim",
            json={"employee_id": "R001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reviewer_name"] == "张三"
        assert data["is_expired"] is False

        db.refresh(audit)
        assert audit.review_status == REVIEW_STATUS_IN_REVIEW

    def test_claim_review_task_by_another_reviewer(self):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-001")
        assert audit is not None

        response = client.post(
            f"/api/audit/{audit.id}/claim",
            json={"employee_id": "R002"}
        )
        assert response.status_code == 400
        assert "已被其他审单员认领" in response.json()["detail"]

    def test_get_reviewer_assignments(self):
        response = client.get("/api/reviewer/R001/assignments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestReviewOperations:
    def test_confirm_review(self):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-001")
        assert audit is not None

        response = client.post(
            f"/api/audit/{audit.id}/review",
            json={
                "action": "confirm",
                "remarks": "审核无误，确认系统结论"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["final_conclusion"] == "compliant"
        assert data["review_status"] == REVIEW_STATUS_REVIEWED

        db.refresh(audit)
        assert audit.final_conclusion == "compliant"
        assert audit.review_status == REVIEW_STATUS_REVIEWED
        assert len(audit.review_opinions) == 1
        assert audit.review_opinions[0].action_type == "confirm"

    def test_submit_for_overrule_test(self):
        response = client.post(
            "/api/submission",
            json={
                "lc_number": "TEST-LC-001",
                "submission_id": "TEST-SUB-002",
                "presentation_date": "2024-12-22",
                "documents": [
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-002",
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-002",
                            "invoice_date": "2024-12-20",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 51000.00,
                            "goods_description": "ELECTRONIC PRODUCTS"
                        }
                    },
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-002",
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
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-002",
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-002",
                            "issue_date": "2024-12-19",
                            "insurance_amount": 50000.00,
                            "currency": "USD",
                            "risks": "ALL RISKS"
                        }
                    }
                ]
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["conclusion"] == "discrepant"
        return data["id"]

    def test_overrule_review(self, setup_module):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-002")
        if not audit:
            self.test_submit_for_overrule_test()
            audit = crud.get_audit_record_by_submission(db, "TEST-SUB-002")

        assert audit is not None
        assert audit.auto_conclusion == "discrepant"

        response = client.post(
            f"/api/audit/{audit.id}/claim",
            json={"employee_id": "R002"}
        )
        assert response.status_code == 200

        discrepancies = [d for d in audit.discrepancies if not d.is_removed]

        response = client.post(
            f"/api/audit/{audit.id}/review",
            json={
                "action": "overrule",
                "overrule_data": {
                    "new_conclusion": "minor_discrepancy",
                    "overruled_reason": "经核实，发票金额超限为客户临时加订，已获申请人确认；保险金额不足为笔误，不影响实质"
                },
                "remarks": "与申请人沟通后确认接受此单据"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["final_conclusion"] == "minor_discrepancy"

        db.refresh(audit)
        assert audit.final_conclusion == "minor_discrepancy"
        assert len(audit.review_opinions) == 1
        opinion = audit.review_opinions[0]
        assert opinion.action_type == "overrule"
        assert opinion.overruled_reason is not None
        assert opinion.new_conclusion == "minor_discrepancy"
        assert opinion.review_duration_seconds is not None

    def test_submit_for_discrepancy_operations(self):
        response = client.post(
            "/api/submission",
            json={
                "lc_number": "TEST-LC-001",
                "submission_id": "TEST-SUB-003",
                "presentation_date": "2024-12-24",
                "documents": [
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-003",
                        "document_type": "invoice",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 2,
                        "content": {
                            "invoice_number": "INV-003",
                            "invoice_date": "2024-12-22",
                            "beneficiary": "SHANGHAI TRADING CO.",
                            "applicant": "ABC IMPORT CO.",
                            "currency": "USD",
                            "total_amount": 50000.00,
                            "goods_description": "ELECTRONIC PRODUCTS"
                        }
                    },
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-003",
                        "document_type": "bill_of_lading",
                        "original_copies_submitted": 3,
                        "copy_copies_submitted": 3,
                        "content": {
                            "bl_number": "BL-003",
                            "shipper": "SHANGHAI TRADING CO.",
                            "consignee": "TO ORDER",
                            "port_of_loading": "SHANGHAI",
                            "port_of_discharge": "ROTTERDAM",
                            "shipment_date": "2024-12-22",
                            "freight_term": "FREIGHT PREPAID",
                            "clean": True
                        }
                    },
                    {
                        "lc_number": "TEST-LC-001",
                        "submission_id": "TEST-SUB-003",
                        "document_type": "insurance",
                        "original_copies_submitted": 2,
                        "copy_copies_submitted": 1,
                        "content": {
                            "policy_number": "INS-003",
                            "issue_date": "2024-12-21",
                            "insurance_amount": 55000.00,
                            "currency": "USD",
                            "risks": "ALL RISKS"
                        }
                    }
                ]
            }
        )
        assert response.status_code == 201
        return response.json()["id"]

    def test_add_and_remove_discrepancies(self, setup_module):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-003")
        if not audit:
            self.test_submit_for_discrepancy_operations()
            audit = crud.get_audit_record_by_submission(db, "TEST-SUB-003")

        assert audit is not None

        response = client.post(
            f"/api/audit/{audit.id}/claim",
            json={"employee_id": "R001"}
        )
        assert response.status_code == 200

        db.refresh(audit)
        auto_discrepancies = [d for d in audit.discrepancies if d.source == "auto" and not d.is_removed]
        auto_disc_id = auto_discrepancies[0].id if auto_discrepancies else None

        review_data = {
            "action": "add_discrepancy",
            "add_discrepancies": [
                {
                    "discrepancy_type": "special",
                    "severity": "minor",
                    "document_type": "invoice",
                    "description": "发票未注明合同号码",
                    "lc_clause_reference": "附加条款"
                }
            ],
            "remove_discrepancies": [] if not auto_disc_id else [
                {
                    "discrepancy_id": auto_disc_id,
                    "removal_reason": "该不符点为系统误判，货物描述差异仅是格式问题"
                }
            ] if auto_disc_id else [],
            "remarks": "补充系统未检出的发票缺项"
        }
        if not auto_disc_id:
            review_data["action"] = "add_discrepancy"
            del review_data["remove_discrepancies"]

        response = client.post(
            f"/api/audit/{audit.id}/review",
            json=review_data
        )
        assert response.status_code == 200

        db.refresh(audit)
        manual_discs = [d for d in audit.discrepancies if d.source == "manual" and not d.is_removed]
        assert len(manual_discs) >= 1
        assert manual_discs[0].description == "发票未注明合同号码"

        if auto_disc_id:
            removed_disc = db.query(models.Discrepancy).filter(models.Discrepancy.id == auto_disc_id).first()
            assert removed_disc is not None
            assert removed_disc.is_removed is True
            assert removed_disc.removal_reason is not None


class TestReviewerStats:
    def test_get_reviewer_stats(self):
        today = date.today()
        start_date = today - timedelta(days=30)
        end_date = today + timedelta(days=1)

        response = client.get(
            f"/api/reviewer/R001/stats?start_date={start_date}&end_date={end_date}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["employee_id"] == "R001"
        assert data["reviewer_name"] == "张三"
        assert data["total_reviewed"] >= 1
        assert data["confirm_count"] >= 1
        assert 0 <= data["confirm_rate"] <= 1
        assert data["avg_review_duration_seconds"] >= 0
        assert data["total_review_duration_seconds"] >= 0

    def test_get_reviewer_stats_invalid_dates(self):
        today = date.today()
        response = client.get(
            f"/api/reviewer/R001/stats?start_date={today}&end_date={today - timedelta(days=1)}"
        )
        assert response.status_code == 400

    def test_get_reviewer_stats_nonexistent(self):
        today = date.today()
        response = client.get(
            f"/api/reviewer/R999/stats?start_date={today}&end_date={today}"
        )
        assert response.status_code == 404


class TestExpireAssignments:
    def test_expire_overdue_assignments(self):
        db = next(override_get_db())
        audit = crud.get_audit_record_by_submission(db, "TEST-SUB-001")
        assert audit is not None

        assignment = models.ReviewAssignment(
            audit_record_id=audit.id + 1000,
            reviewer_id=1,
            claimed_at=datetime.utcnow() - timedelta(hours=25),
            expires_at=datetime.utcnow() - timedelta(hours=1),
            is_expired=False
        )
        db.add(assignment)
        db.commit()

        response = client.post("/api/review/expire-check")
        assert response.status_code == 200
        data = response.json()
        assert data["expired_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
