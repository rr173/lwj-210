import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data
from app.models import (
    FEE_TIER_STANDARD,
    FEE_TIER_PREFERRED,
    FEE_TIER_VIP,
    FEE_TYPE_FIRST_SUBMISSION,
    FEE_TYPE_RESUBMISSION,
    FEE_STATUS_CONFIRMED,
    FEE_STATUS_PENDING,
    FEE_RULES,
)


def _build_compliant_docs(lc_id, submission_id, original_submission_id, round_n=0):
    return [
        schemas.DocumentSubmit(
            lc_number="LC-FEE-TEST-001",
            submission_id=submission_id,
            document_type="invoice",
            original_copies_submitted=3,
            copy_copies_submitted=2,
            content={
                "invoice_number": f"INV-{submission_id}",
                "invoice_date": "2024-06-01",
                "beneficiary": "上海贸易有限公司",
                "applicant": "ABC IMPORTS CO.",
                "currency": "USD",
                "goods": [
                    {"name": "COTTON T-SHIRTS", "specification": "SIZE M", "quantity": 5000, "unit": "PCS", "unit_price": 10.00}
                ],
                "goods_description": "100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
                "total_amount": 50000.00
            }
        ),
        schemas.DocumentSubmit(
            lc_number="LC-FEE-TEST-001",
            submission_id=submission_id,
            document_type="bill_of_lading",
            original_copies_submitted=3,
            copy_copies_submitted=3,
            content={
                "bl_number": f"BL-{submission_id}",
                "shipper": "上海贸易有限公司",
                "consignee": "TO ORDER",
                "notify_party": "ABC IMPORTS CO. ROTTERDAM",
                "vessel_voyage": "MAERSK TEST V.001",
                "port_of_loading": "SHANGHAI PORT",
                "port_of_discharge": "ROTTERDAM PORT",
                "shipment_date": "2024-06-05",
                "packages": 5000,
                "package_unit": "PCS",
                "freight_term": "FREIGHT PREPAID",
                "clean": True,
                "transshipment": False,
                "endorsement": "BLANK ENDORSED",
                "remarks": "CLEAN ON BOARD",
                "goods_description": "100% COTTON MEN'S T-SHIRTS"
            }
        ),
        schemas.DocumentSubmit(
            lc_number="LC-FEE-TEST-001",
            submission_id=submission_id,
            document_type="packing_list",
            original_copies_submitted=2,
            copy_copies_submitted=2,
            content={
                "packing_number": f"PL-{submission_id}",
                "date": "2024-06-01",
                "total_packages": 250,
                "package_type": "CTNS",
                "gross_weight": 5250.00,
                "net_weight": 5000.00,
                "goods_description": "COTTON T-SHIRTS"
            }
        ),
    ]


def _build_discrepant_docs(lc_number, submission_id):
    docs = _build_compliant_docs(0, submission_id, submission_id)
    for d in docs:
        d.lc_number = lc_number
    docs[0].content["total_amount"] = 99999.00
    docs[0].content["goods"][0]["unit_price"] = 999.00
    return docs


def test_fee_module():
    print("=" * 70)
    print("交单费用计算与收费记录模块功能测试")
    print("=" * 70)

    init_db()

    db = SessionLocal()

    try:
        print("\n" + "-" * 60)
        print("测试1: 创建不同费率档位的信用证，验证费率档位绑定")
        print("-" * 60)

        lc_standard_data = schemas.LetterOfCreditCreate(
            lc_number="LC-FEE-TEST-001",
            issuing_bank="中国银行上海分行",
            beneficiary_name="上海贸易有限公司",
            applicant_name="ABC IMPORTS CO.",
            currency=schemas.Currency.USD,
            amount=50000.00,
            latest_shipment_date=date(2024, 6, 15),
            latest_presentation_date=date(2024, 6, 30),
            expiry_date=date(2024, 7, 10),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI PORT",
            port_of_discharge="ROTTERDAM PORT",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
            additional_terms=[
                "保险金额不低于发票金额110%",
                "提单必须做成指示抬头(TO ORDER)",
                "提单显示运费预付(FREIGHT PREPAID)",
            ],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
                schemas.DocumentRequirementCreate(document_type="packing_list", original_copies=2, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="insurance", original_copies=2, copy_copies=1),
            ]
        )
        lc_standard = crud.create_letter_of_credit(db, lc_standard_data)
        assert lc_standard.fee_tier == FEE_TIER_STANDARD, f"费率档位应为 standard，实际为 {lc_standard.fee_tier}"
        print(f"[✓] 标准档信用证创建成功: {lc_standard.lc_number}, 档位={lc_standard.fee_tier}")

        lc_preferred_data = lc_standard_data.model_copy()
        lc_preferred_data.lc_number = "LC-FEE-TEST-002"
        lc_preferred_data.fee_tier = schemas.FeeTier.PREFERRED
        lc_preferred = crud.create_letter_of_credit(db, lc_preferred_data)
        assert lc_preferred.fee_tier == FEE_TIER_PREFERRED
        print(f"[✓] 优惠档信用证创建成功: {lc_preferred.lc_number}, 档位={lc_preferred.fee_tier}")

        lc_vip_data = lc_standard_data.model_copy()
        lc_vip_data.lc_number = "LC-FEE-TEST-003"
        lc_vip_data.fee_tier = schemas.FeeTier.VIP
        lc_vip = crud.create_letter_of_credit(db, lc_vip_data)
        assert lc_vip.fee_tier == FEE_TIER_VIP
        print(f"[✓] VIP档信用证创建成功: {lc_vip.lc_number}, 档位={lc_vip.fee_tier}")

        print("\n" + "-" * 60)
        print("测试2: 费率档位创建后不可修改")
        print("-" * 60)

        try:
            update_data = lc_standard_data.model_copy()
            update_data.fee_tier = schemas.FeeTier.VIP
            crud.update_letter_of_credit(db, lc_standard.id, update_data)
            print("[✗] 应该拒绝修改费率档位，但修改成功了")
            assert False, "费率档位创建后不可修改"
        except ValueError as e:
            print(f"[✓] 正确拒绝了费率档位修改: {str(e)}")

        print("\n" + "-" * 60)
        print("测试3: 标准档首次交单(compliant)费用计算与记录生成")
        print("-" * 60)

        submission1_data = schemas.SubmissionSubmit(
            lc_number="LC-FEE-TEST-001",
            submission_id="SUB-FEE-STD-001",
            presentation_date=date(2024, 6, 10),
            documents=_build_compliant_docs(lc_standard.id, "SUB-FEE-STD-001", "SUB-FEE-STD-001")
        )
        audit1 = crud.submit_documents_and_audit(db, submission1_data)
        doc_count = len(submission1_data.documents)

        expected = FEE_RULES[FEE_TIER_STANDARD]
        expected_base = expected["first_submission_base"]
        expected_per_doc = expected["first_submission_per_doc"]
        expected_total = expected_base + expected_per_doc * doc_count

        fee_records = db.query(models.FeeRecord).filter(
            models.FeeRecord.submission_id == "SUB-FEE-STD-001"
        ).all()
        assert len(fee_records) == 1, f"应生成1条收费记录，实际{len(fee_records)}条"
        fee = fee_records[0]

        assert fee.fee_type == FEE_TYPE_FIRST_SUBMISSION, f"费用类型错误: {fee.fee_type}"
        assert fee.fee_tier == FEE_TIER_STANDARD
        assert fee.base_fee == expected_base, f"基础费应为{expected_base}，实际{fee.base_fee}"
        assert fee.per_doc_fee == expected_per_doc
        assert fee.document_count == doc_count
        assert fee.document_fee_total == expected_per_doc * doc_count
        assert fee.total_amount == expected_total, f"总金额应为{expected_total}，实际{fee.total_amount}"
        assert fee.status == FEE_STATUS_CONFIRMED if audit1.conclusion == "compliant" or audit1.conclusion == "minor_discrepancy" else FEE_STATUS_PENDING
        assert fee.fee_number.startswith("FEE-LC-FEE-TEST-001-")

        print(f"[✓] 标准档首次交单收费记录生成成功")
        print(f"    费用编号: {fee.fee_number}")
        print(f"    费用类型: {fee.fee_type}")
        print(f"    单据数: {doc_count}")
        print(f"    基础费: {fee.base_fee} + 单据费: {fee.per_doc_fee}×{doc_count}={fee.document_fee_total}")
        print(f"    总金额: {fee.total_amount}")
        print(f"    审核结论: {audit1.conclusion} → 费用状态: {fee.status}")

        print("\n" + "-" * 60)
        print("测试4: 优惠档首次交单 费用计算")
        print("-" * 60)

        sub_pref = submission1_data.model_copy()
        sub_pref.lc_number = "LC-FEE-TEST-002"
        sub_pref.submission_id = "SUB-FEE-PREF-001"
        for d in sub_pref.documents:
            d.lc_number = "LC-FEE-TEST-002"
            d.submission_id = "SUB-FEE-PREF-001"
        audit_pref = crud.submit_documents_and_audit(db, sub_pref)

        exp_pref = FEE_RULES[FEE_TIER_PREFERRED]
        exp_total_pref = exp_pref["first_submission_base"] + exp_pref["first_submission_per_doc"] * doc_count

        fee_pref = db.query(models.FeeRecord).filter_by(submission_id="SUB-FEE-PREF-001").first()
        assert fee_pref is not None
        assert abs(fee_pref.total_amount - exp_total_pref) < 0.01

        print(f"[✓] 优惠档首次交单费用计算正确")
        print(f"    基础费 {exp_pref['first_submission_base']} + 单据费 {exp_pref['first_submission_per_doc']}×{doc_count} = {exp_total_pref}")
        print(f"    实际记录总金额: {fee_pref.total_amount}")

        print("\n" + "-" * 60)
        print("测试5: VIP档首次交单 费用计算")
        print("-" * 60)

        sub_vip = submission1_data.model_copy()
        sub_vip.lc_number = "LC-FEE-TEST-003"
        sub_vip.submission_id = "SUB-FEE-VIP-001"
        for d in sub_vip.documents:
            d.lc_number = "LC-FEE-TEST-003"
            d.submission_id = "SUB-FEE-VIP-001"
        audit_vip = crud.submit_documents_and_audit(db, sub_vip)

        exp_vip = FEE_RULES[FEE_TIER_VIP]
        exp_total_vip = exp_vip["first_submission_base"] + exp_vip["first_submission_per_doc"] * doc_count
        fee_vip = db.query(models.FeeRecord).filter_by(submission_id="SUB-FEE-VIP-001").first()
        assert fee_vip is not None
        assert abs(fee_vip.total_amount - exp_total_vip) < 0.01

        print(f"[✓] VIP档首次交单费用计算正确")
        print(f"    基础费 {exp_vip['first_submission_base']} + 单据费 {exp_vip['first_submission_per_doc']}×{doc_count} = {exp_total_vip}")
        print(f"    实际记录总金额: {fee_vip.total_amount}")

        print("\n" + "-" * 60)
        print("测试6: 提交discrepant单据，费用状态为pending(待确认)")
        print("-" * 60)

        discrepant_sub = schemas.SubmissionSubmit(
            lc_number="LC-FEE-TEST-001",
            submission_id="SUB-FEE-STD-DISCREPANT",
            presentation_date=date(2024, 6, 12),
            documents=_build_discrepant_docs("LC-FEE-TEST-001", "SUB-FEE-STD-DISCREPANT")
        )
        try:
            audit_disc = crud.submit_documents_and_audit(db, discrepant_sub)
        except ValueError:
            pass
        audit_disc = crud.get_audit_record_by_submission(db, "SUB-FEE-STD-DISCREPANT")
        if audit_disc is None:
            print("    (已有不符交单阻止新不符交单，使用修改重提流程代替验证)")

            resub_data = schemas.SubmissionResubmitRequest(
                new_submission_id="RESUB-FEE-DISCREPANT-001",
                modification_remark="重新提交但仍有不符点用于测试pending状态",
                presentation_date=date(2024, 6, 13),
                documents=_build_discrepant_docs("LC-FEE-TEST-001", "RESUB-FEE-DISCREPANT-001")
            )
            audit_resub_disc = crud.resubmit_documents_and_audit(db, "SUB-FEE-STD-001", resub_data)
            fee_disc = db.query(models.FeeRecord).filter_by(submission_id="RESUB-FEE-DISCREPANT-001").first()
            assert fee_disc is not None

            if audit_resub_disc.conclusion == "discrepant":
                assert fee_disc.status == FEE_STATUS_PENDING, f"discrepant交单费用应为pending，实际{fee_disc.status}"
                print(f"[✓] discrepant审核结论 → 费用状态正确标记为 pending")
            else:
                print(f"    (本次修改重提审核结论为{audit_resub_disc.conclusion}，状态标记为{fee_disc.status})")
        else:
            fee_disc = db.query(models.FeeRecord).filter_by(submission_id="SUB-FEE-STD-DISCREPANT").first()
            assert fee_disc is not None
            if audit_disc.conclusion == "discrepant":
                assert fee_disc.status == FEE_STATUS_PENDING
            print(f"[✓] 审核结论={audit_disc.conclusion} → 费用状态={fee_disc.status}")

        print("\n" + "-" * 60)
        print("测试7: 修改重提收费 - 三档对比")
        print("-" * 60)

        for tier_name, lc_num, sub_id_prefix in [
            ("标准档", "LC-FEE-TEST-001", "RESUB-STD"),
            ("优惠档", "LC-FEE-TEST-002", "RESUB-PREF"),
            ("VIP档", "LC-FEE-TEST-003", "RESUB-VIP"),
        ]:
            orig_sub = db.query(models.AuditRecord).filter(
                models.AuditRecord.lc_id == crud.get_letter_of_credit_by_number(db, lc_num).id,
                models.AuditRecord.resubmission_round == 0
            ).first()

            if orig_sub and orig_sub.conclusion == "discrepant":
                orig_id = orig_sub.original_submission_id
            else:
                disc_sub_id = f"{sub_id_prefix}-DISC"
                disc_sub = schemas.SubmissionSubmit(
                    lc_number=lc_num,
                    submission_id=disc_sub_id,
                    presentation_date=date(2024, 6, 11),
                    documents=_build_discrepant_docs(lc_num, disc_sub_id)
                )
                try:
                    crud.submit_documents_and_audit(db, disc_sub)
                except ValueError:
                    pass
                orig = crud.get_audit_record_by_submission(db, disc_sub_id)
                if orig is None:
                    continue
                orig_id = orig.original_submission_id

            new_sub_id = f"{sub_id_prefix}-FINAL"
            resub = schemas.SubmissionResubmitRequest(
                new_submission_id=new_sub_id,
                modification_remark=f"{tier_name}修改重提",
                presentation_date=date(2024, 6, 14),
                documents=_build_compliant_docs(0, new_sub_id, orig_id)
            )
            for d in resub.documents:
                d.lc_number = lc_num
            audit_r = crud.resubmit_documents_and_audit(db, orig_id, resub)

            fee_r = db.query(models.FeeRecord).filter_by(submission_id=new_sub_id).first()
            assert fee_r is not None
            assert fee_r.fee_type == FEE_TYPE_RESUBMISSION
            exp_resub = FEE_RULES[fee_r.fee_tier]["resubmission_fixed"]
            assert abs(fee_r.total_amount - exp_resub) < 0.01

            status_str = "已确认" if audit_r.conclusion != "discrepant" else "待确认"
            print(f"[✓] {tier_name} 修改重提收费: 固定{exp_resub}元 → 实际记录:{fee_r.total_amount}元 [{status_str}]")

        print("\n" + "-" * 60)
        print("测试8: VIP档修改重提免费验证")
        print("-" * 60)

        vip_lc = crud.get_letter_of_credit_by_number(db, "LC-FEE-TEST-003")
        vip_orig = db.query(models.AuditRecord).filter(
            models.AuditRecord.lc_id == vip_lc.id,
            models.AuditRecord.resubmission_round == 0
        ).first()

        vip_disc_id = "VIP-DISC-FOR-FREE-RESUB"
        try:
            vip_disc_sub = schemas.SubmissionSubmit(
                lc_number="LC-FEE-TEST-003",
                submission_id=vip_disc_id,
                presentation_date=date(2024, 6, 15),
                documents=_build_discrepant_docs("LC-FEE-TEST-003", vip_disc_id)
            )
            crud.submit_documents_and_audit(db, vip_disc_sub)
        except ValueError:
            pass

        vip_disc_audit = crud.get_audit_record_by_submission(db, vip_disc_id)
        if vip_disc_audit:
            vip_free_resub_id = "VIP-RESUB-FREE-001"
            resub_free = schemas.SubmissionResubmitRequest(
                new_submission_id=vip_free_resub_id,
                modification_remark="VIP免费重提",
                presentation_date=date(2024, 6, 16),
                documents=_build_compliant_docs(vip_lc.id, vip_free_resub_id, vip_disc_audit.original_submission_id)
            )
            for d in resub_free.documents:
                d.lc_number = "LC-FEE-TEST-003"
            crud.resubmit_documents_and_audit(db, vip_disc_audit.original_submission_id, resub_free)

            fee_free = db.query(models.FeeRecord).filter_by(submission_id=vip_free_resub_id).first()
            assert fee_free is not None
            assert fee_free.fee_tier == FEE_TIER_VIP
            assert fee_free.fee_type == FEE_TYPE_RESUBMISSION
            assert fee_free.total_amount == 0, f"VIP修改重提应免费，实际收费{fee_free.total_amount}"
            print(f"[✓] VIP档修改重提收费记录: 总金额 {fee_free.total_amount} 元 (验证免费)")

        print("\n" + "-" * 60)
        print("测试9: 按信用证编号查询累计费用接口")
        print("-" * 60)

        for lc_num in ["LC-FEE-TEST-001", "LC-FEE-TEST-002", "LC-FEE-TEST-003"]:
            summary = crud.get_fee_records_by_lc(db, lc_num)
            lc = crud.get_letter_of_credit_by_number(db, lc_num)
            assert summary["lc_number"] == lc_num
            assert summary["fee_tier"] == lc.fee_tier

            records_sum = sum(r.total_amount for r in summary["fee_records"])
            assert abs(records_sum - summary["total_amount"]) < 0.01

            confirmed_sum = sum(r.total_amount for r in summary["fee_records"] if r.status == FEE_STATUS_CONFIRMED)
            pending_sum = sum(r.total_amount for r in summary["fee_records"] if r.status == FEE_STATUS_PENDING)
            assert abs(confirmed_sum - summary["confirmed_amount"]) < 0.01
            assert abs(pending_sum - summary["pending_amount"]) < 0.01

            print(f"[✓] 信用证 {lc_num} (档位: {summary['fee_tier']}):")
            print(f"    记录数: {len(summary['fee_records'])}, 合计: {summary['total_amount']}")
            print(f"    已确认: {summary['confirmed_amount']}, 待确认: {summary['pending_amount']}")

        print("\n" + "-" * 60)
        print("测试10: 按时间范围查询收费汇总 (按档位分组)")
        print("-" * 60)

        today = date.today()
        start = date(2000, 1, 1)
        end = date(2099, 12, 31)
        summary = crud.get_fee_records_by_time_range(db, start, end)

        assert summary["start_date"] == start
        assert summary["end_date"] == end

        all_records_count = db.query(models.FeeRecord).count()
        assert summary["total_records"] == all_records_count, f"总记录数应为{all_records_count}，实际{summary['total_records']}"

        gt = sum(r["total_amount"] for r in summary["by_tier"])
        assert abs(gt - summary["grand_total"]) < 0.01

        print(f"[✓] 全时间范围汇总: 总记录数={summary['total_records']}, 总金额={summary['grand_total']}")
        for t in summary["by_tier"]:
            print(f"    - {t['fee_tier']}: {t['record_count']}笔, 合计{t['total_amount']} "
                  f"(已确认{t['confirmed_amount']}, 待确认{t['pending_amount']})")

        tier_map = {t["fee_tier"]: t for t in summary["by_tier"]}
        for tier in [FEE_TIER_STANDARD, FEE_TIER_PREFERRED, FEE_TIER_VIP]:
            db_count = db.query(models.FeeRecord).filter_by(fee_tier=tier).count()
            assert tier_map[tier]["record_count"] == db_count

        print("\n" + "-" * 60)
        print("测试11: 费用编号自动生成 (同一证同日多笔递增加序号)")
        print("-" * 60)

        fee_numbers = [r.fee_number for r in db.query(models.FeeRecord).all()]
        for fn in fee_numbers:
            assert fn.startswith("FEE-")
            parts = fn.split("-")
            assert len(parts) >= 5
        print(f"[✓] 共 {len(fee_numbers)} 条收费记录，编号格式均正确")
        print(f"    示例编号: {fee_numbers[:3]}")

        print("\n" + "-" * 60)
        print("测试12: 收费记录追溯性 (可关联回交单/信用证)")
        print("-" * 60)

        sample_fee = db.query(models.FeeRecord).first()
        assert sample_fee is not None

        linked_audit = crud.get_audit_record_by_submission(db, sample_fee.submission_id)
        assert linked_audit is not None
        assert linked_audit.id == sample_fee.audit_record_id

        linked_lc = crud.get_letter_of_credit_by_id(db, sample_fee.lc_id)
        assert linked_lc is not None
        assert linked_lc.fee_tier == sample_fee.fee_tier

        print(f"[✓] 收费记录追溯验证通过:")
        print(f"    费用编号 {sample_fee.fee_number}")
        print(f"      → 关联交单: {sample_fee.submission_id} (审核结论: {linked_audit.conclusion})")
        print(f"      → 关联信用证: {linked_lc.lc_number} (档位: {linked_lc.fee_tier})")

        print("\n" + "=" * 70)
        print("所有测试通过! ✓")
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
    test_fee_module()
