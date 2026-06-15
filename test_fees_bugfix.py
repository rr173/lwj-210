import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data
from app.models import (
    FEE_STATUS_CONFIRMED,
    FEE_STATUS_PENDING,
)


def test_bugfixes():
    print("=" * 70)
    print("Bug修复验证测试")
    print("=" * 70)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        print("\n" + "-" * 60)
        print("Bug修复1: 预置数据的费用记录查询验证")
        print("-" * 60)

        for lc_num in ["LC-SEA-CIF-2024-001", "LC-AIR-CFR-2024-002"]:
            summary = crud.get_fee_records_by_lc(db, lc_num)
            lc = crud.get_letter_of_credit_by_number(db, lc_num)
            fee_count = len(summary["fee_records"])
            print(f"[✓] 信用证 {lc_num} (档位: {lc.fee_tier}):")
            print(f"    费用记录数: {fee_count}, 合计金额: {summary['total_amount']}")
            assert fee_count >= 1, f"信用证 {lc_num} 应有费用记录，实际 {fee_count} 条"
            for r in summary["fee_records"]:
                print(f"      - {r.fee_number}: {r.fee_type} 总{r.total_amount}元 [{r.status}]")

        print("\n" + "-" * 60)
        print("Bug修复2: 修改费率档位应返回正确错误提示(非500)")
        print("-" * 60)

        lc = crud.get_letter_of_credit_by_number(db, "LC-SEA-CIF-2024-001")
        old_tier = lc.fee_tier

        lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-SEA-CIF-2024-001",
            issuing_bank=lc.issuing_bank,
            beneficiary_name=lc.beneficiary_name,
            applicant_name=lc.applicant_name,
            currency=schemas.Currency(lc.currency),
            amount=lc.amount,
            latest_shipment_date=lc.latest_shipment_date,
            latest_presentation_date=lc.latest_presentation_date,
            expiry_date=lc.expiry_date,
            transport_mode=schemas.TransportMode(lc.transport_mode),
            port_of_loading=lc.port_of_loading,
            port_of_discharge=lc.port_of_discharge,
            partial_shipment_allowed=lc.partial_shipment_allowed,
            transshipment_allowed=lc.transshipment_allowed,
            goods_description=lc.goods_description,
            additional_terms=lc.additional_terms,
            fee_tier=schemas.FeeTier.VIP,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type=dr.document_type,
                    original_copies=dr.original_copies,
                    copy_copies=dr.copy_copies
                ) for dr in lc.document_requirements
            ]
        )

        try:
            crud.update_letter_of_credit(db, lc.id, lc_data)
            print("[✗] 应该抛出 ValueError，但没有抛出")
            assert False
        except ValueError as e:
            print(f"[✓] 正确抛出 ValueError，错误信息: {str(e)}")
            assert "费率档位创建后不可修改" in str(e)
            db.rollback()

        db.refresh(lc)
        assert lc.fee_tier == old_tier, "费率档位不应被修改"
        print(f"[✓] 费率档位仍为: {lc.fee_tier} (未被修改)")

        print("\n" + "-" * 60)
        print("Bug修复3: Amendment接受后内部重审不重复计费，且更新费用状态")
        print("-" * 60)

        lc2 = crud.get_letter_of_credit_by_number(db, "LC-AIR-CFR-2024-002")
        audits_before = crud.get_audit_records_by_lc(db, "LC-AIR-CFR-2024-002")
        disc_audit = next((a for a in audits_before if a.conclusion == "discrepant"), None)
        assert disc_audit is not None, "应存在discrepant的审核记录"

        fee_before = db.query(models.FeeRecord).filter(
            models.FeeRecord.audit_record_id == disc_audit.id
        ).first()
        assert fee_before is not None
        assert fee_before.status == FEE_STATUS_PENDING, f"费用状态应为pending，实际{fee_before.status}"
        fee_count_before = db.query(models.FeeRecord).count()
        print(f"[i] Amendment接受前:")
        print(f"    审核结论: {disc_audit.conclusion}")
        print(f"    关联费用状态: {fee_before.status}")
        print(f"    总费用记录数: {fee_count_before}")

        amendment_data = schemas.AmendmentCreate(
            lc_number="LC-AIR-CFR-2024-002",
            field_changes=[
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value="2024-04-15",
                    new_value="2024-05-15"
                ),
            ]
        )
        amendment = crud.create_amendment(db, amendment_data)
        accepted = crud.accept_amendment(db, amendment.amendment_number)

        fee_count_after = db.query(models.FeeRecord).count()
        db.refresh(fee_before)
        db.refresh(disc_audit)

        print(f"[i] Amendment接受后:")
        print(f"    审核结论: {disc_audit.conclusion}")
        print(f"    关联费用状态: {fee_before.status}")
        print(f"    总费用记录数: {fee_count_after}")

        assert fee_count_after == fee_count_before, f"不应新增费用记录！之前{fee_count_before}，之后{fee_count_after}"
        print(f"[✓] 内部重审未新增费用记录 (总数保持 {fee_count_after})")

        if disc_audit.conclusion != "discrepant":
            assert fee_before.status == FEE_STATUS_CONFIRMED, f"结论变为{disc_audit.conclusion}，费用状态应更新为confirmed"
            print(f"[✓] 审核结论变为 {disc_audit.conclusion}，费用状态已同步更新为 confirmed")
        else:
            assert fee_before.status == FEE_STATUS_PENDING
            print(f"[i] 审核结论仍为 discrepant，费用状态保持 pending")

        print("\n" + "=" * 70)
        print("所有Bug修复验证通过! ✓")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n[✗] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    except Exception as e:
        print(f"\n[✗] 发生异常: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_bugfixes()
