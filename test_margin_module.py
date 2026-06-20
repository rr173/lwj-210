import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app import models, schemas, crud


def setup_test_db():
    test_db_path = "./data/test_margin.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    test_db_url = f"sqlite:///{test_db_path}"
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    crud.migrate_margin_tables(db)
    return db


def build_lc_data(applicant_name, lc_number, amount, expiry_offset=90, payment_method=None):
    pm = payment_method if payment_method is not None else schemas.PaymentMethod.SIGHT
    create_data = schemas.LetterOfCreditCreate(
        lc_number=lc_number,
        issuing_bank="TEST BANK",
        beneficiary_name="TEST BENEFICIARY",
        applicant_name=applicant_name,
        currency=schemas.Currency.USD,
        amount=amount,
        latest_shipment_date=date.today() + timedelta(days=30),
        latest_presentation_date=date.today() + timedelta(days=60),
        expiry_date=date.today() + timedelta(days=expiry_offset),
        transport_mode=schemas.TransportMode.SEA,
        port_of_loading="SHANGHAI",
        port_of_discharge="LOS ANGELES",
        partial_shipment_allowed=True,
        transshipment_allowed=False,
        goods_description="TEST GOODS",
        fee_tier=schemas.FeeTier.STANDARD,
        payment_method=pm,
        document_requirements=[
            schemas.DocumentRequirementCreate(
                document_type="invoice", original_copies=3, copy_copies=2
            ),
            schemas.DocumentRequirementCreate(
                document_type="bill_of_lading", original_copies=3, copy_copies=3
            ),
        ],
    )
    if pm == schemas.PaymentMethod.USANCE:
        create_data.usance_days = 90
        create_data.usance_basis = schemas.UsanceBasis.BL_DATE
    return create_data


def test_margin_module():
    print("=" * 80)
    print("信用证保证金质押与释放管理模块 - 完整功能测试")
    print("=" * 80)

    db = setup_test_db()

    try:
        applicant_a = "APPLICANT_A (A级信用)"
        applicant_b = "APPLICANT_B (B级信用)"
        applicant_c = "APPLICANT_C (C级信用)"

        print("\n" + "-" * 80)
        print("测试1: 创建不同信用等级的授信额度")
        print("-" * 80)

        ratings = [
            (applicant_a, schemas.CreditRating.A, 0.20, 500000),
            (applicant_b, schemas.CreditRating.B, 0.50, 300000),
            (applicant_c, schemas.CreditRating.C, 1.00, 200000),
        ]

        credit_lines = {}
        for name, rating, expected_ratio, cl_amount in ratings:
            cl = crud.create_credit_line(db, schemas.CreditLineCreate(
                applicant_name=name,
                total_amount=cl_amount,
                currency=schemas.Currency.USD,
                credit_rating=rating,
            ))
            credit_lines[name] = cl
            print(f"[✓] {name}: 信用等级={cl.credit_rating}, 额度={cl.total_amount} USD")
            assert cl.credit_rating == rating.value
            expected_margin = models.MARGIN_RATIO_BY_RATING[rating.value]
            assert expected_margin == expected_ratio
            print(f"    对应保证金比例: {expected_ratio * 100:.0f}%")

        print("\n" + "-" * 80)
        print("测试2: 创建信用证时自动生成保证金记录")
        print("-" * 80)

        lcs = {}
        lc_amount = 100000
        for idx, (name, rating, expected_ratio, _) in enumerate(ratings):
            lc_number = f"LC-MGN-TEST-{idx + 1:03d}"
            lc_data = build_lc_data(name, lc_number, lc_amount)
            lc = crud.create_letter_of_credit(db, lc_data)
            lcs[name] = lc

            initial_margin = crud.get_initial_margin_record_by_lc(db, lc.id)
            assert initial_margin is not None
            expected_required = round(lc_amount * expected_ratio, 2)

            print(f"[✓] 信用证 {lc_number} ({name})")
            print(f"    信用证金额: {lc.amount} USD")
            print(f"    保证金编号: {initial_margin.margin_number}")
            print(f"    信用等级: {initial_margin.credit_rating} (比例 {initial_margin.margin_ratio * 100:.0f}%)")
            print(f"    应缴保证金: {initial_margin.required_amount} USD (预期: {expected_required})")
            print(f"    状态: {initial_margin.status}")

            assert initial_margin.credit_rating == rating.value
            assert initial_margin.margin_ratio == expected_ratio
            assert initial_margin.required_amount == expected_required
            assert initial_margin.status == models.MARGIN_STATUS_PENDING_PAYMENT
            assert initial_margin.record_type == models.MARGIN_RECORD_TYPE_INITIAL

        print("\n" + "-" * 80)
        print("测试3: 修改信用等级 - 不追溯已开信用证")
        print("-" * 80)

        lc_a = lcs[applicant_a]
        old_margin = crud.get_initial_margin_record_by_lc(db, lc_a.id)
        old_rating = old_margin.credit_rating

        updated_cl = crud.update_credit_rating(db, applicant_a, "USD", models.CREDIT_RATING_C)
        assert updated_cl.credit_rating == models.CREDIT_RATING_C
        print(f"[✓] 已将申请人 {applicant_a} 信用等级从 {old_rating} 改为 {updated_cl.credit_rating}")

        db.refresh(old_margin)
        assert old_margin.credit_rating == old_rating
        print(f"[✓] 已开立信用证保证金等级不变: {old_margin.credit_rating} (应缴 {old_margin.required_amount})")

        new_lc_number = "LC-MGN-TEST-NEW-A"
        new_lc_data = build_lc_data(applicant_a, new_lc_number, 50000)
        new_lc = crud.create_letter_of_credit(db, new_lc_data)
        new_margin = crud.get_initial_margin_record_by_lc(db, new_lc.id)
        assert new_margin.credit_rating == models.CREDIT_RATING_C
        assert new_margin.required_amount == 50000 * 1.00
        print(f"[✓] 新开信用证使用新等级 C级: 应缴保证金 {new_margin.required_amount} USD (100% 比例)")

        crud.update_credit_rating(db, applicant_a, "USD", models.CREDIT_RATING_A)
        print("[✓] 已恢复 A 级信用等级")

        print("\n" + "-" * 80)
        print("测试4: 保证金缴纳 - 金额不足应被拦截")
        print("-" * 80)

        margin_b = crud.get_initial_margin_record_by_lc(db, lcs[applicant_b].id)
        short_amount = margin_b.required_amount - 100
        try:
            crud.pay_margin(db, margin_b.margin_number, short_amount, "tester")
            print("[✗] 金额不足时应该失败，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拦截了不足额缴纳: 应缴 {margin_b.required_amount}, 实缴 {short_amount}")
            print(f"    错误信息: {e}")

        print("\n" + "-" * 80)
        print("测试5: 保证金正常缴纳 - 状态流转正确")
        print("-" * 80)

        margin_records_to_pay = []
        for name, lc in lcs.items():
            margin = crud.get_initial_margin_record_by_lc(db, lc.id)
            pay_amount = margin.required_amount
            paid = crud.pay_margin(db, margin.margin_number, pay_amount, f"cashier_{name}")
            margin_records_to_pay.append(paid)
            assert paid.status == models.MARGIN_STATUS_PAID
            assert paid.actual_paid_amount == pay_amount
            assert paid.paid_by == f"cashier_{name}"
            assert paid.paid_at is not None
            print(f"[✓] {name} 保证金缴纳成功")
            print(f"    编号: {paid.margin_number}, 应缴: {paid.required_amount}, 实缴: {paid.actual_paid_amount}")
            print(f"    状态: {paid.status}, 操作人: {paid.paid_by}")

        new_margin_pay = crud.get_initial_margin_record_by_lc(db, new_lc.id)
        crud.pay_margin(db, new_margin_pay.margin_number, new_margin_pay.required_amount, "cashier_A")
        print("[✓] 新信用证保证金也已缴纳")

        print("\n" + "-" * 80)
        print("测试6: 保证金未缴状态下交单/amendment被拦截")
        print("-" * 80)

        unfree_name = "APPLICANT_UNFREE"
        crud.create_credit_line(db, schemas.CreditLineCreate(
            applicant_name=unfree_name,
            total_amount=500000,
            currency=schemas.Currency.USD,
            credit_rating=schemas.CreditRating.A,
        ))
        unfree_lc_number = "LC-MGN-UNFREE-001"
        unfree_lc_data = build_lc_data(unfree_name, unfree_lc_number, 80000)
        unfree_lc = crud.create_letter_of_credit(db, unfree_lc_data)

        submission = schemas.SubmissionSubmit(
            lc_number=unfree_lc_number,
            submission_id="SUB-UNFREE-001",
            presentation_date=date.today(),
            documents=[
                schemas.DocumentSubmit(
                    lc_number=unfree_lc_number,
                    submission_id="SUB-UNFREE-001",
                    document_type="invoice",
                    original_copies_submitted=3,
                    copy_copies_submitted=2,
                    content={
                        "invoice_number": "INV-001",
                        "invoice_date": str(date.today()),
                        "amount": 80000,
                        "currency": "USD",
                        "beneficiary_name": "TEST BENEFICIARY",
                        "applicant_name": unfree_name,
                        "lc_number": unfree_lc_number,
                        "goods_description": "TEST GOODS",
                        "total_amount": 80000,
                    },
                ),
                schemas.DocumentSubmit(
                    lc_number=unfree_lc_number,
                    submission_id="SUB-UNFREE-001",
                    document_type="bill_of_lading",
                    original_copies_submitted=3,
                    copy_copies_submitted=3,
                    content={
                        "bl_number": "BL-001",
                        "port_of_loading": "SHANGHAI",
                        "port_of_discharge": "LOS ANGELES",
                        "on_board_date": str(date.today() - timedelta(days=5)),
                        "goods_description": "TEST GOODS",
                        "lc_number": unfree_lc_number,
                    },
                ),
            ],
        )

        try:
            crud.submit_documents_and_audit(db, submission)
            print("[✗] 保证金未缴状态下交单应该被拦截，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 交单操作被正确拦截")
            if "保证金" in str(e):
                print(f"    拦截原因(含保证金关键字): ✓")
            else:
                print(f"    拦截信息: {e}")

        try:
            amendment_data = schemas.AmendmentCreate(
                lc_number=unfree_lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="latest_shipment_date",
                        old_value=str(date.today() + timedelta(days=30)),
                        new_value=str(date.today() + timedelta(days=45)),
                    ),
                ],
            )
            crud.create_amendment(db, amendment_data)
            print("[✗] 保证金未缴状态下amendment应该被拦截，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] Amendment操作被正确拦截")
            if "保证金" in str(e):
                print(f"    拦截原因(含保证金关键字): ✓")
            else:
                print(f"    拦截信息: {e}")

        print("\n" + "-" * 80)
        print("测试7: 缴纳保证金后可以正常交单")
        print("-" * 80)

        unfree_margin = crud.get_initial_margin_record_by_lc(db, unfree_lc.id)
        crud.pay_margin(db, unfree_margin.margin_number, unfree_margin.required_amount, "cashier")
        print(f"[✓] 已缴纳保证金 {unfree_margin.required_amount} USD")

        result = crud.submit_documents_and_audit(db, submission)
        audit_record = result["audit_record"]
        print(f"[✓] 保证金缴清后交单成功, 审核结论: {audit_record.conclusion}")

        print("\n" + "-" * 80)
        print("测试8: Amendment 增额时自动生成补缴记录")
        print("-" * 80)

        lc_b = lcs[applicant_b]
        old_b_amount = lc_b.amount
        increase_amount = 40000
        new_b_amount = old_b_amount + increase_amount

        amendment_data = schemas.AmendmentCreate(
            lc_number=lc_b.lc_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=old_b_amount,
                    new_value=new_b_amount,
                ),
            ],
        )
        amendment = crud.create_amendment(db, amendment_data)
        accepted = crud.accept_amendment(db, amendment.amendment_number)

        db.refresh(lc_b)
        all_margins_b = crud.get_all_margin_records_by_lc(db, lc_b.id)
        initial_b = crud.get_initial_margin_record_by_lc(db, lc_b.id)
        supplements = [m for m in all_margins_b if m.record_type == models.MARGIN_RECORD_TYPE_SUPPLEMENT]

        print(f"[✓] Amendment 已接受，信用证金额从 {old_b_amount} 增至 {lc_b.amount}")
        print(f"[✓] 信用证当前总保证金记录数: {len(all_margins_b)} (1初始 + {len(supplements)}补缴)")
        assert len(supplements) == 1
        supplement = supplements[0]

        expected_supplement = round(increase_amount * initial_b.margin_ratio, 2)
        print(f"    初始保证金: {initial_b.margin_number}, 应缴 {initial_b.required_amount}")
        print(f"    补缴保证金: {supplement.margin_number}, 应缴 {supplement.required_amount} (预期 {expected_supplement})")
        print(f"    补缴关联父记录ID: {supplement.related_margin_id} = {initial_b.id}")
        print(f"    补缴状态: {supplement.status}")

        assert supplement.required_amount == expected_supplement
        assert supplement.related_margin_id == initial_b.id
        assert supplement.status == models.MARGIN_STATUS_PENDING_PAYMENT
        assert supplement.record_type == models.MARGIN_RECORD_TYPE_SUPPLEMENT

        print("\n" + "-" * 80)
        print("测试9: 补缴记录未缴清时，后续交单/amendment被拦截")
        print("-" * 80)

        try:
            sub2 = schemas.SubmissionSubmit(
                lc_number=lc_b.lc_number,
                submission_id="SUB-BLOCKED-002",
                presentation_date=date.today(),
                documents=[
                    schemas.DocumentSubmit(
                        lc_number=lc_b.lc_number,
                        submission_id="SUB-BLOCKED-002",
                        document_type="invoice",
                        original_copies_submitted=3,
                        copy_copies_submitted=2,
                        content={
                            "invoice_number": "INV-002",
                            "invoice_date": str(date.today()),
                            "amount": new_b_amount,
                            "currency": "USD",
                            "beneficiary_name": "TEST BENEFICIARY",
                            "applicant_name": applicant_b,
                            "lc_number": lc_b.lc_number,
                            "goods_description": "TEST GOODS",
                            "total_amount": new_b_amount,
                        },
                    ),
                ],
            )
            crud.submit_documents_and_audit(db, sub2)
            print("[✗] 补缴未缴清时交单应被拦截，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 补缴未缴清时，新交单被正确拦截")

        crud.pay_margin(db, supplement.margin_number, supplement.required_amount, "cashier_B")
        print(f"[✓] 已缴纳补缴保证金 {supplement.required_amount} USD")

        print("\n" + "-" * 80)
        print("测试10: Amendment减额时不退还保证金")
        print("-" * 80)

        lc_c = lcs[applicant_c]
        initial_c = crud.get_initial_margin_record_by_lc(db, lc_c.id)
        paid_initial = initial_c.actual_paid_amount
        old_c_amount = lc_c.amount
        new_c_amount = old_c_amount - 20000

        amendment_c_data = schemas.AmendmentCreate(
            lc_number=lc_c.lc_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=old_c_amount,
                    new_value=new_c_amount,
                ),
            ],
        )
        amendment_c = crud.create_amendment(db, amendment_c_data)
        crud.accept_amendment(db, amendment_c.amendment_number)

        db.refresh(initial_c)
        margins_c = crud.get_all_margin_records_by_lc(db, lc_c.id)
        supplement_count_c = len([m for m in margins_c if m.record_type == models.MARGIN_RECORD_TYPE_SUPPLEMENT])

        print(f"[✓] 信用证 {lc_c.lc_number} 金额从 {old_c_amount} 减至 {new_c_amount}")
        print(f"    初始保证金实缴不变: {initial_c.actual_paid_amount} (原 {paid_initial})")
        print(f"    未生成补缴记录 (数量: {supplement_count_c})")
        assert supplement_count_c == 0
        assert initial_c.actual_paid_amount == paid_initial

        print("\n" + "-" * 80)
        print("测试11: 付款全部结清后，保证金自动变为可释放状态")
        print("-" * 80)

        applicant_release = "APPLICANT_RELEASE"
        crud.create_credit_line(db, schemas.CreditLineCreate(
            applicant_name=applicant_release,
            total_amount=500000,
            currency=schemas.Currency.USD,
            credit_rating=schemas.CreditRating.A,
        ))
        release_lc_number = "LC-MGN-RELEASE-001"
        release_lc_data = build_lc_data(applicant_release, release_lc_number, 50000,
                                        expiry_offset=365, payment_method=schemas.PaymentMethod.USANCE)
        release_lc = crud.create_letter_of_credit(db, release_lc_data)

        release_margin = crud.get_initial_margin_record_by_lc(db, release_lc.id)
        crud.pay_margin(db, release_margin.margin_number, release_margin.required_amount, "cashier")
        print(f"[✓] 信用证 {release_lc_number} 开证并缴纳保证金 {release_margin.required_amount} USD")

        release_sub = schemas.SubmissionSubmit(
            lc_number=release_lc_number,
            submission_id="SUB-RELEASE-001",
            presentation_date=date.today(),
            documents=[
                schemas.DocumentSubmit(
                    lc_number=release_lc_number,
                    submission_id="SUB-RELEASE-001",
                    document_type="invoice",
                    original_copies_submitted=3,
                    copy_copies_submitted=2,
                    content={
                        "invoice_number": "INV-RELEASE",
                        "invoice_date": str(date.today()),
                        "amount": 50000,
                        "currency": "USD",
                        "beneficiary_name": "TEST BENEFICIARY",
                        "applicant_name": applicant_release,
                        "lc_number": release_lc_number,
                        "goods_description": "TEST GOODS",
                        "total_amount": 50000,
                    },
                ),
                schemas.DocumentSubmit(
                    lc_number=release_lc_number,
                    submission_id="SUB-RELEASE-001",
                    document_type="bill_of_lading",
                    original_copies_submitted=3,
                    copy_copies_submitted=3,
                    content={
                        "bl_number": "BL-RELEASE",
                        "bl_date": str(date.today() - timedelta(days=5)),
                        "port_of_loading": "SHANGHAI",
                        "port_of_discharge": "LOS ANGELES",
                        "on_board_date": str(date.today() - timedelta(days=5)),
                        "goods_description": "TEST GOODS",
                        "lc_number": release_lc_number,
                    },
                ),
            ],
        )
        release_result = crud.submit_documents_and_audit(db, release_sub)
        release_ar = release_result["audit_record"]
        release_ar.conclusion = "compliant"
        release_ar.auto_conclusion = "compliant"
        release_ar.final_conclusion = "compliant"
        release_ar.total_discrepancies = 0
        release_ar.critical_count = 0
        db.commit()
        db.refresh(release_ar)
        print(f"[✓] 完成交单审核，结论: {release_ar.conclusion}")

        payment = crud.create_payment_application(db, release_ar.submission_id)
        print(f"[✓] 创建付款申请: {payment.payment_number}, 金额 {payment.payment_amount}")

        payment = crud.accept_payment(db, payment.payment_number, "manager")
        payment.status = models.PAYMENT_STATUS_MATURED
        db.commit()
        db.refresh(payment)
        print(f"[✓] 付款已承兑并标记到期")

        settlement = crud.settle_payment(
            db,
            payment.payment_number,
            date.today(),
            payment.payment_amount,
            0.0,
            "BANK-TRF-001",
            "settlement_officer",
        )
        print(f"[✓] 付款完成结算，状态: {settlement.status}")

        db.refresh(release_margin)
        print(f"    付款完成后保证金状态: {release_margin.status}")
        assert release_margin.status == models.MARGIN_STATUS_RELEASABLE
        print(f"[✓] 保证金已自动变更为 releasable 状态")

        print("\n" + "-" * 80)
        print("测试12: 手动释放保证金 - 需要操作人和备注")
        print("-" * 80)

        try:
            crud.release_margin(db, release_margin.margin_number, "", "无操作人")
            print("[✗] 未指定操作人应失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确校验了操作人必填: {e}")

        try:
            crud.release_margin(db, release_margin.margin_number, "officer", "")
            print("[✗] 未填写备注应失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确校验了备注必填: {e}")

        released = crud.release_margin(
            db, release_margin.margin_number, "margin_officer_01",
            "信用证付款全部结清，保证金退还申请人"
        )
        print(f"[✓] 保证金成功释放")
        print(f"    状态: {released.status}")
        print(f"    释放人: {released.released_by}")
        print(f"    释放时间: {released.released_at}")
        print(f"    释放备注: {released.release_remark}")
        print(f"    实际释放金额 = 实缴总额: {released.actual_paid_amount} USD")
        assert released.status == models.MARGIN_STATUS_RELEASED

        print("\n" + "-" * 80)
        print("测试13: 信用证到期日已过且存在未结清付款 - 保证金变待扣罚")
        print("-" * 80)

        applicant_penalty = "APPLICANT_PENALTY"
        crud.create_credit_line(db, schemas.CreditLineCreate(
            applicant_name=applicant_penalty,
            total_amount=200000,
            currency=schemas.Currency.USD,
            credit_rating=schemas.CreditRating.B,
        ))
        penalty_lc_number = "LC-MGN-PENALTY-001"
        penalty_lc_data = build_lc_data(applicant_penalty, penalty_lc_number, 60000,
                                        expiry_offset=5, payment_method=schemas.PaymentMethod.USANCE)
        penalty_lc = crud.create_letter_of_credit(db, penalty_lc_data)

        penalty_margin = crud.get_initial_margin_record_by_lc(db, penalty_lc.id)
        crud.pay_margin(db, penalty_margin.margin_number, penalty_margin.required_amount, "cashier")
        print(f"[✓] 开证 {penalty_lc_number} 到期日 {penalty_lc.expiry_date}, 保证金已缴 {penalty_margin.required_amount}")

        penalty_lc.expiry_date = date.today() - timedelta(days=3)
        db.commit()
        db.refresh(penalty_lc)

        penalty_sub = schemas.SubmissionSubmit(
            lc_number=penalty_lc_number,
            submission_id="SUB-PENALTY-001",
            presentation_date=date.today() - timedelta(days=10),
            documents=[
                schemas.DocumentSubmit(
                    lc_number=penalty_lc_number,
                    submission_id="SUB-PENALTY-001",
                    document_type="invoice",
                    original_copies_submitted=3,
                    copy_copies_submitted=2,
                    content={
                        "invoice_number": "INV-PENALTY",
                        "invoice_date": str(date.today() - timedelta(days=10)),
                        "amount": 60000,
                        "currency": "USD",
                        "beneficiary_name": "TEST BENEFICIARY",
                        "applicant_name": applicant_penalty,
                        "lc_number": penalty_lc_number,
                        "goods_description": "TEST GOODS",
                        "total_amount": 60000,
                    },
                ),
                schemas.DocumentSubmit(
                    lc_number=penalty_lc_number,
                    submission_id="SUB-PENALTY-001",
                    document_type="bill_of_lading",
                    original_copies_submitted=3,
                    copy_copies_submitted=3,
                    content={
                        "bl_number": "BL-PENALTY",
                        "bl_date": str(date.today() - timedelta(days=12)),
                        "port_of_loading": "SHANGHAI",
                        "port_of_discharge": "LOS ANGELES",
                        "on_board_date": str(date.today() - timedelta(days=12)),
                        "goods_description": "TEST GOODS",
                        "lc_number": penalty_lc_number,
                    },
                ),
            ],
        )
        penalty_result = crud.submit_documents_and_audit(db, penalty_sub)
        penalty_ar = penalty_result["audit_record"]
        penalty_ar.conclusion = "compliant"
        penalty_ar.auto_conclusion = "compliant"
        penalty_ar.final_conclusion = "compliant"
        penalty_ar.total_discrepancies = 0
        penalty_ar.critical_count = 0
        db.commit()
        db.refresh(penalty_ar)
        print(f"[✓] 逾期交单审核，结论: {penalty_ar.conclusion}")

        pen_payment = crud.create_payment_application(db, penalty_ar.submission_id)
        pen_payment = crud.accept_payment(db, pen_payment.payment_number, "manager")
        pen_payment.status = models.PAYMENT_STATUS_OVERDUE
        db.commit()
        print(f"[✓] 创建逾期付款，状态: {pen_payment.status}")

        expire_result = crud.check_and_process_expired_lc_margins(db)
        print(f"[✓] 执行到期检查，处理了 {expire_result['processed_count']} 条记录")
        assert expire_result["processed_count"] >= 1

        db.refresh(penalty_margin)
        print(f"    保证金状态: {penalty_margin.status}")
        assert penalty_margin.status == models.MARGIN_STATUS_PENALTY_PENDING
        print(f"[✓] 保证金正确变更为 penalty_pending 待扣罚状态")

        print("\n" + "-" * 80)
        print("测试14: 扣罚保证金 - 可用于抵扣逾期罚息，剩余部分可释放")
        print("-" * 80)

        try:
            crud.penalize_margin(db, penalty_margin.margin_number, 0, "零扣罚")
            print("[✗] 扣罚金额应为正数")
            assert False
        except ValueError as e:
            print(f"[✓] 正确校验了扣罚金额必须大于0: {e}")

        penalty_amount = 5000
        penalized = crud.penalize_margin(
            db, penalty_margin.margin_number, penalty_amount,
            "抵扣逾期付款罚息第1期", "collection_officer"
        )
        print(f"[✓] 扣罚成功: 扣罚 {penalized.penalized_amount} USD / 原实缴 {penalized.actual_paid_amount} USD")
        print(f"    剩余可释放: {round(penalized.actual_paid_amount - penalized.penalized_amount, 2)} USD")
        print(f"    状态: {penalized.status}")
        assert penalized.penalized_amount == penalty_amount

        remaining_before = penalized.actual_paid_amount - penalized.penalized_amount
        second_penalty = 3000
        penalized_2 = crud.penalize_margin(
            db, penalty_margin.margin_number, second_penalty,
            "抵扣逾期付款罚息第2期", "collection_officer"
        )
        total_penalized = penalized_2.penalized_amount
        print(f"[✓] 再次扣罚 {second_penalty}, 累计扣罚 {total_penalized} USD")

        released_remaining = crud.release_margin(
            db, penalty_margin.margin_number, "margin_officer_02",
            "扣罚完成后释放剩余保证金"
        )
        print(f"[✓] 扣罚后成功释放剩余部分")
        print(f"    实缴总额: {released_remaining.actual_paid_amount} USD")
        print(f"    累计扣罚: {released_remaining.penalized_amount} USD")
        print(f"    状态: {released_remaining.status}")
        assert released_remaining.status == models.MARGIN_STATUS_RELEASED

        print("\n" + "-" * 80)
        print("测试15: 查询接口 - 按申请人查询所有保证金")
        print("-" * 80)

        for name in [applicant_a, applicant_b]:
            result = crud.get_margin_records_by_applicant(db, name)
            print(f"\n[申请人: {name}]")
            print(f"    总记录数: {result['total_records']}")
            print(f"    累计实缴: {result['total_paid_amount']} USD")
            print(f"    在押净额: {result['total_held_amount']} USD")
            print(f"    累计扣罚: {result['total_penalized_amount']} USD")
            print(f"    记录明细:")
            for r in result["records"]:
                print(f"      - {r['margin_number']} | {r['record_type']} | "
                      f"等级{r['credit_rating']}({r['margin_ratio'] * 100:.0f}%) | "
                      f"应缴{r['required_amount']} | 实缴{r['actual_paid_amount']} | {r['status']}")
                for sup in r.get("supplements", []):
                    print(f"        └─补缴: {sup['margin_number']} | "
                          f"应缴{sup['required_amount']} | 实缴{sup['actual_paid_amount']} | {sup['status']}")

        print("\n" + "-" * 80)
        print("测试16: 查询接口 - 按信用证查询保证金明细（含补缴关联）")
        print("-" * 80)

        detail_b = crud.get_margin_detail_by_lc(db, lc_b.lc_number)
        print(f"[信用证: {detail_b['lc_number']}]")
        print(f"    申请人: {detail_b['applicant_name']}")
        print(f"    信用等级: {detail_b['credit_rating']}")
        print(f"    当前证金额: {detail_b['lc_current_amount']} {detail_b['currency']}")
        print(f"    累计应缴: {detail_b['total_required_amount']}")
        print(f"    累计实缴: {detail_b['total_actual_paid_amount']}")
        print(f"    累计扣罚: {detail_b['total_penalized_amount']}")
        print(f"    在押净额: {detail_b['net_held_amount']}")
        print(f"    综合状态: {detail_b['overall_status']}")
        print(f"    明细记录数: {len(detail_b['records'])} (初始+补缴树)")
        for rec in detail_b["records"]:
            print(f"      初始: {rec['margin_number']} 应缴{rec['required_amount']} 实缴{rec['actual_paid_amount']} 状态{rec['status']}")
            for sup in rec["supplements"]:
                print(f"        └─补缴: {sup.margin_number} 应缴{sup.required_amount} 实缴{sup.actual_paid_amount} 状态{sup.status}")
        assert len(detail_b["records"]) == 1
        assert len(detail_b["records"][0]["supplements"]) == 1

        print("\n" + "-" * 80)
        print("测试17: 查询接口 - 统计当前在押保证金总额（按信用等级分组）")
        print("-" * 80)

        stats = crud.get_margin_overall_stats(db)
        print(f"全局统计:")
        print(f"  在押总记录数: {stats['total_records']}")
        print(f"  累计应缴总额: {stats['total_required_amount']} USD")
        print(f"  累计实缴总额: {stats['total_actual_paid_amount']} USD")
        print(f"  累计扣罚总额: {stats['total_penalized_amount']} USD")
        print(f"  净在押总额:   {stats['total_net_held_amount']} USD")
        print(f"按信用等级分组:")
        for item in stats["by_rating"]:
            print(f"  [{item['credit_rating']}级] 记录{item['record_count']}条 "
                  f"(初始{item['initial_count']} + 补缴{item['supplement_count']}) "
                  f"实缴{item['total_actual_paid_amount']} 扣罚{item['total_penalized_amount']} "
                  f"净在押{item['net_held_amount']} USD")
        assert len(stats["by_rating"]) == 3
        for rating in models.VALID_CREDIT_RATINGS:
            assert any(r["credit_rating"] == rating for r in stats["by_rating"])

        print("\n" + "=" * 80)
        print("所有测试通过! ✓ 信用证保证金质押与释放管理模块功能完整")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    test_margin_module()
