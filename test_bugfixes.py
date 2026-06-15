import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db


def test_old_value_validation():
    print("=" * 60)
    print("Bug修复测试1: 修改请求旧值校验")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None

        print(f"\n[测试] 提交错误的旧值应该被拒绝")
        print(f"    实际金额: {lc.amount}")
        print(f"    实际最迟装运日期: {lc.latest_shipment_date}")

        print(f"\n1. 测试金额旧值错误...")
        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="amount",
                        old_value=99999.99,
                        new_value=60000.00
                    )
                ]
            )
            crud.create_amendment(db, bad_amendment)
            print("    [✗] 应该拒绝旧值错误的修改，但成功了")
            assert False, "旧值错误应该被拒绝"
        except ValueError as e:
            print(f"    [✓] 正确拒绝了错误的旧值")
            print(f"        错误信息: {str(e)}")

        print(f"\n2. 测试日期旧值错误...")
        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="latest_shipment_date",
                        old_value="2024-12-31",
                        new_value="2024-04-10"
                    )
                ]
            )
            crud.create_amendment(db, bad_amendment)
            print("    [✗] 应该拒绝旧值错误的修改，但成功了")
            assert False, "旧值错误应该被拒绝"
        except ValueError as e:
            print(f"    [✓] 正确拒绝了错误的旧值")
            print(f"        错误信息: {str(e)}")

        print(f"\n3. 测试正确的旧值应该成功...")
        try:
            good_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="amount",
                        old_value=lc.amount,
                        new_value=70000.00
                    ),
                    schemas.FieldChange(
                        field_name="latest_shipment_date",
                        old_value=lc.latest_shipment_date.isoformat(),
                        new_value="2024-04-15"
                    )
                ]
            )
            amendment = crud.create_amendment(db, good_amendment)
            print(f"    [✓] 正确的旧值创建成功")
            print(f"        修改编号: {amendment.amendment_number}")

            crud.reject_amendment(db, amendment.amendment_number)
            print(f"        已拒绝该修改以便后续测试")
        except ValueError as e:
            print(f"    [✗] 正确的旧值应该创建成功，但失败了: {str(e)}")
            assert False

        print(f"\n4. 测试布尔值旧值错误...")
        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="partial_shipment_allowed",
                        old_value=True,
                        new_value=False
                    )
                ]
            )
            crud.create_amendment(db, bad_amendment)
            print("    [✗] 应该拒绝旧值错误的修改，但成功了")
            assert False, "旧值错误应该被拒绝"
        except ValueError as e:
            print(f"    [✓] 正确拒绝了错误的旧值")
            print(f"        错误信息: {str(e)}")

        print("\n" + "=" * 60)
        print("旧值校验修复验证通过! ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[✗] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


def test_submission_logic():
    print("\n" + "=" * 60)
    print("Bug修复测试2: 一证一审逻辑修复")
    print("=" * 60)

    db = SessionLocal()

    try:
        lc_number = "LC-AIR-CFR-2024-002"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None

        existing_audits = crud.get_audit_records_by_lc(db, lc_number)
        print(f"\n[信息] 信用证 {lc_number} 已有审核记录: {len(existing_audits)} 条")
        for audit in existing_audits:
            print(f"    - {audit.submission_id}: 结论={audit.conclusion}, 轮次={audit.resubmission_round}")

        latest = existing_audits[0]
        print(f"\n[测试1: 已有不符交单（未达重提上限）应该阻止新提交...")
        try:
            new_submission = schemas.SubmissionSubmit(
                lc_number=lc_number,
                submission_id="SUB-NEW-TEST-001",
                presentation_date=date(2024, 5, 1),
                documents=[
                    schemas.DocumentSubmit(
                        lc_number=lc_number,
                        submission_id="SUB-NEW-TEST-001",
                        document_type="invoice",
                        original_copies_submitted=3,
                        copy_copies_submitted=2,
                        content={
                            "invoice_number": "INV-TEST-001",
                            "invoice_date": "2024-04-28",
                            "beneficiary": lc.beneficiary_name,
                            "applicant": lc.applicant_name,
                            "currency": lc.currency,
                            "goods_description": lc.goods_description,
                            "total_amount": lc.amount
                        }
                    )
                ]
            )
            crud.submit_documents_and_audit(db, new_submission)
            print("    [✗] 应该阻止新提交，但成功了")
            assert False, "不符交单未达重提上限时应该阻止新提交"
        except ValueError as e:
            print(f"    [✓] 正确阻止了新提交")
            print(f"        错误信息: {str(e)}")

        print(f"\n[测试2: 通过的交单（compliant）应该允许新提交...")

        compliant_lc_number = "LC-SEA-CIF-2024-001"
        compliant_audits = crud.get_audit_records_by_lc(db, compliant_lc_number)
        compliant_lc = crud.get_letter_of_credit_by_number(db, compliant_lc_number)
        print(f"    信用证 {compliant_lc_number} 的审核结论: {compliant_audits[0].conclusion}")

        if compliant_audits[0].conclusion in ["compliant", "minor_discrepancy"]:
            try:
                new_submission2 = schemas.SubmissionSubmit(
                    lc_number=compliant_lc_number,
                    submission_id="SUB-NEW-COMPLIANT-TEST-002",
                    presentation_date=date(2024, 5, 20),
                    documents=[
                        schemas.DocumentSubmit(
                            lc_number=compliant_lc_number,
                            submission_id="SUB-NEW-COMPLIANT-TEST-002",
                            document_type="invoice",
                            original_copies_submitted=3,
                            copy_copies_submitted=2,
                            content={
                                "invoice_number": "INV-TEST-002",
                                "invoice_date": "2024-05-15",
                                "beneficiary": compliant_lc.beneficiary_name,
                                "applicant": compliant_lc.applicant_name,
                                "currency": compliant_lc.currency,
                                "goods_description": compliant_lc.goods_description,
                                "total_amount": compliant_lc.amount
                            }
                        )
                    ]
                )
                result = crud.submit_documents_and_audit(db, new_submission2)
                print(f"    [✓] 通过的交单后允许提交新交单成功")
                print(f"        新提交编号: {result.submission_id}")
                print(f"        审核结论: {result.conclusion}")
            except ValueError as e:
                print(f"    [✗] 通过的交单后应该允许新提交，但失败了: {str(e)}")
                assert False

        print(f"\n[测试3: 不符交单达到重提上限后应该允许新提交...")
        print(f"    (创建新信用证进行测试)")

        new_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-SUBMISSION-001",
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=10000.00,
            latest_shipment_date=date(2024, 12, 31),
            latest_presentation_date=date(2025, 1, 15),
            expiry_date=date(2025, 1, 31),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="LOS ANGELES",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="测试货物",
            additional_terms=[],
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=1, copy_copies=0)
            ]
        )
        new_lc = crud.create_letter_of_credit(db, new_lc_data)

        first_sub = schemas.SubmissionSubmit(
            lc_number="LC-TEST-SUBMISSION-001",
            submission_id="SUB-TEST-FIRST",
            presentation_date=date(2024, 12, 1),
            documents=[
                schemas.DocumentSubmit(
                    lc_number="LC-TEST-SUBMISSION-001",
                    submission_id="SUB-TEST-FIRST",
                    document_type="invoice",
                    original_copies_submitted=0,
                    copy_copies_submitted=0,
                    content={
                        "invoice_number": "INV-001",
                        "invoice_date": "2024-11-20",
                        "beneficiary": "测试受益人",
                        "applicant": "测试申请人",
                        "currency": "USD",
                        "goods_description": "测试货物",
                        "total_amount": 10000.00
                    }
                )
            ]
        )
        first_audit = crud.submit_documents_and_audit(db, first_sub)
        print(f"    首次交单结论: {first_audit.conclusion}, 轮次: {first_audit.resubmission_round}")

        for i in range(crud.MAX_RESUBMISSION_ROUNDS):
            resub = schemas.SubmissionResubmitRequest(
                new_submission_id=f"SUB-TEST-RESUB-{i+1}",
                modification_remark=f"第{i+1}次修改",
                presentation_date=date(2024, 12, 1),
                documents=[
                    schemas.DocumentSubmit(
                        lc_number="LC-TEST-SUBMISSION-001",
                        submission_id=f"SUB-TEST-RESUB-{i+1}",
                        document_type="invoice",
                        original_copies_submitted=0,
                        copy_copies_submitted=0,
                        content={
                            "invoice_number": f"INV-00{i+2}",
                            "invoice_date": "2024-11-20",
                            "beneficiary": "测试受益人",
                            "applicant": "测试申请人",
                            "currency": "USD",
                            "goods_description": "测试货物",
                            "total_amount": 10000.00
                        }
                    )
                ]
            )
            resub_audit = crud.resubmit_documents_and_audit(db, "SUB-TEST-FIRST", resub)
            print(f"    第{i+1}次重提: 结论={resub_audit.conclusion}, 轮次={resub_audit.resubmission_round}")

        latest_after = crud.get_latest_audit_by_lc(db, new_lc.id)
        print(f"    达到重提上限后的状态: 结论={latest_after.conclusion}, 轮次={latest_after.resubmission_round}, 上限={crud.MAX_RESUBMISSION_ROUNDS}")

        try:
            final_sub = schemas.SubmissionSubmit(
                lc_number="LC-TEST-SUBMISSION-001",
                submission_id="SUB-TEST-FINAL-NEW",
                presentation_date=date(2024, 12, 25),
                documents=[
                    schemas.DocumentSubmit(
                        lc_number="LC-TEST-SUBMISSION-001",
                        submission_id="SUB-TEST-FINAL-NEW",
                        document_type="invoice",
                        original_copies_submitted=1,
                        copy_copies_submitted=0,
                        content={
                            "invoice_number": "INV-FINAL",
                            "invoice_date": "2024-12-20",
                            "beneficiary": "测试受益人",
                            "applicant": "测试申请人",
                            "currency": "USD",
                            "goods_description": "测试货物",
                            "total_amount": 10000.00
                        }
                    )
                ]
            )
            final_audit = crud.submit_documents_and_audit(db, final_sub)
            print(f"    [✓] 达到重提上限后允许提交新交单")
            print(f"        新提交编号: {final_audit.submission_id}")
            print(f"        审核结论: {final_audit.conclusion}")
        except ValueError as e:
            print(f"    [✗] 达到重提上限后应该允许新提交，但失败了: {str(e)}")
            assert False

        print("\n" + "=" * 60)
        print("一证一审逻辑修复验证通过! ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[✗] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


def test_additional_terms_old_value():
    print("\n" + "=" * 60)
    print("Bug修复测试3: 附加条款旧值校验")
    print("=" * 60)

    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None

        print(f"\n    实际附加条款: {lc.additional_terms}")

        print(f"\n1. 测试附加条款旧值错误...")
        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="additional_terms",
                        old_value=["条款列表错误的内容"],
                        new_value=lc.additional_terms + ["新附加条款"]
                    )
                ]
            )
            crud.create_amendment(db, bad_amendment)
            print("    [✗] 应该拒绝旧值错误的修改，但成功了")
            assert False, "旧值错误应该被拒绝"
        except ValueError as e:
            print(f"    [✓] 正确拒绝了错误的旧值")
            print(f"        错误信息: {str(e)}")

        print(f"\n2. 测试正确的附加条款旧值...")
        try:
            good_amendment = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="additional_terms",
                        old_value=lc.additional_terms,
                        new_value=lc.additional_terms + ["所有单据须显示信用证号"]
                    )
                ]
            )
            amendment = crud.create_amendment(db, good_amendment)
            print(f"    [✓] 正确的旧值创建成功")
            print(f"        修改编号: {amendment.amendment_number}")

            crud.reject_amendment(db, amendment.amendment_number)
        except ValueError as e:
            print(f"    [✗] 正确的旧值应该创建成功，但失败了: {str(e)}")
            assert False

        print("\n" + "=" * 60)
        print("附加条款旧值校验验证通过! ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[✗] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_old_value_validation()
    test_submission_logic()
    test_additional_terms_old_value()
    print("\n" + "=" * 60)
    print("所有Bug修复测试全部通过! ✓")
    print("=" * 60)
