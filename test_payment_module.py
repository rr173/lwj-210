import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data
from app.models import (
    PAYMENT_METHOD_SIGHT,
    PAYMENT_METHOD_USANCE,
    PAYMENT_METHOD_DEFERRED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_ACCEPTED,
    PAYMENT_STATUS_MATURED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_REJECTED,
    SIGHT_PROCESSING_DAYS,
)


def test_payment_module():
    print("=" * 60)
    print("承兑与付款管理模块功能测试")
    print("=" * 60)

    if os.path.exists("./data/lc_audit.db"):
        os.remove("./data/lc_audit.db")
        print("已删除旧数据库")

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        lc1 = crud.get_letter_of_credit_by_number(db, "LC-SEA-CIF-2024-001")
        assert lc1 is not None, "信用证1不存在"
        assert lc1.payment_method == PAYMENT_METHOD_SIGHT, f"信用证1付款方式应为 sight，实际为 {lc1.payment_method}"
        print(f"\n[✓] 信用证1: {lc1.lc_number} (付款方式: {lc1.payment_method})")

        lc2 = crud.get_letter_of_credit_by_number(db, "LC-AIR-CFR-2024-002")
        assert lc2 is not None, "信用证2不存在"
        assert lc2.payment_method == PAYMENT_METHOD_USANCE, f"信用证2付款方式应为 usance，实际为 {lc2.payment_method}"
        assert lc2.usance_days == 90, f"远期天数应为 90，实际为 {lc2.usance_days}"
        assert lc2.usance_basis == "shipment_date", f"起算基准应为 shipment_date，实际为 {lc2.usance_basis}"
        print(f"[✓] 信用证2: {lc2.lc_number} (付款方式: {lc2.payment_method}, 远期: {lc2.usance_days}天, 起算: {lc2.usance_basis})")

        print("\n" + "-" * 40)
        print("测试1: 预置付款申请数据验证")
        print("-" * 40)

        payments_lc1 = crud.get_payments_by_lc(db, "LC-SEA-CIF-2024-001")
        assert len(payments_lc1) >= 1, f"信用证1应有至少1条付款记录，实际为 {len(payments_lc1)}"
        payment1 = payments_lc1[0]
        print(f"[✓] 信用证1付款申请: {payment1.payment_number}")
        print(f"    金额: {payment1.payment_amount} {payment1.currency}")
        print(f"    方式: {payment1.payment_method}")
        print(f"    到期日: {payment1.maturity_date}")
        print(f"    状态: {payment1.status}")

        payments_lc2 = crud.get_payments_by_lc(db, "LC-AIR-CFR-2024-002")
        assert len(payments_lc2) >= 1, f"信用证2应有至少1条付款记录，实际为 {len(payments_lc2)}"
        payment2 = None
        for p in payments_lc2:
            if p.payment_method == PAYMENT_METHOD_USANCE:
                payment2 = p
                break
        assert payment2 is not None, "信用证2应有远期付款记录"
        assert payment2.status == PAYMENT_STATUS_ACCEPTED, f"远期付款状态应为 accepted，实际为 {payment2.status}"
        print(f"[✓] 信用证2付款申请: {payment2.payment_number}")
        print(f"    金额: {payment2.payment_amount} {payment2.currency}")
        print(f"    方式: {payment2.payment_method}")
        print(f"    到期日: {payment2.maturity_date}")
        print(f"    状态: {payment2.status}")
        print(f"    承兑时间: {payment2.accepted_at}")

        print("\n" + "-" * 40)
        print("测试2: 工作日计算")
        print("-" * 40)

        test_date = date(2024, 3, 8)
        result = crud.add_business_days(test_date, 5)
        print(f"    2024-03-08 + 5个工作日 = {result}")
        assert crud.is_business_day(result), f"结果 {result} 应该是工作日"
        assert result.weekday() < 5, f"结果 {result} 应该是周一到周五"

        weekend_test = date(2024, 3, 9)
        assert not crud.is_business_day(weekend_test), f"2024-03-09 是周六，应该不是工作日"
        print(f"[✓] 工作日计算正确 (跳过周末)")

        print("\n" + "-" * 40)
        print("测试3: 付款申请创建 (即期)")
        print("-" * 40)

        compliant_submission = "SUB-LC1-20240308-COMPLIANT"
        try:
            payment_new = crud.create_payment_application(db, compliant_submission)
            print(f"[✗] 应该创建失败（已有付款申请），但成功了: {payment_new.payment_number}")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝重复创建付款申请")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试4: 付款详情查询")
        print("-" * 40)

        payment_detail = crud.get_payment_detail(db, payment1.payment_number)
        assert payment_detail is not None, "付款详情不应为空"
        assert "status_history" in payment_detail, "应包含状态历史"
        assert "partial_payments" in payment_detail, "应包含部分付款记录"
        assert len(payment_detail["status_history"]) >= 2, f"状态历史至少应有2条，实际为 {len(payment_detail['status_history'])}"
        print(f"[✓] 付款详情查询成功")
        print(f"    状态历史记录数: {len(payment_detail['status_history'])}")
        for h in payment_detail["status_history"]:
            print(f"      - {h.from_status or '初始'} -> {h.to_status} ({h.changed_at}, by {h.changed_by})")

        print("\n" + "-" * 40)
        print("测试5: 状态历史查询")
        print("-" * 40)

        history = crud.get_payment_status_history(db, payment2.payment_number)
        assert len(history) >= 2, f"远期付款状态历史至少应有2条，实际为 {len(history)}"
        print(f"[✓] 状态历史查询成功，共 {len(history)} 条记录")
        for h in history:
            print(f"    - {h.from_status or '初始'} -> {h.to_status}")
            print(f"      时间: {h.changed_at}")
            print(f"      操作人: {h.changed_by}")
            print(f"      备注: {h.remark}")

        print("\n" + "-" * 40)
        print("测试6: 按状态查询付款")
        print("-" * 40)

        matured_payments = crud.get_payments_by_status(db, PAYMENT_STATUS_MATURED)
        print(f"[✓] matured 状态付款数: {len(matured_payments)}")
        assert len(matured_payments) >= 1, "至少应有1条 matured 状态的付款"

        accepted_payments = crud.get_payments_by_status(db, PAYMENT_STATUS_ACCEPTED)
        print(f"[✓] accepted 状态付款数: {len(accepted_payments)}")

        try:
            crud.get_payments_by_status(db, "invalid_status")
            print("[✗] 应该拒绝无效状态查询")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝无效状态查询: {str(e)}")

        print("\n" + "-" * 40)
        print("测试7: 即期付款 - 实际付款结算")
        print("-" * 40)

        assert payment1.status == PAYMENT_STATUS_MATURED, f"付款状态应为 matured，实际为 {payment1.status}"

        settled_payment = crud.settle_payment(
            db,
            payment1.payment_number,
            payment_date=date(2024, 3, 15),
            settled_by="cashier_01",
            reference="T20240315001",
        )
        assert settled_payment.status == PAYMENT_STATUS_PAID, f"付款后状态应为 paid，实际为 {settled_payment.status}"
        assert abs(settled_payment.total_paid_amount - payment1.payment_amount) < 0.01, "全额付款后累计付款金额应等于付款金额"
        assert settled_payment.actual_payment_date == date(2024, 3, 15), "实际付款日期应正确记录"
        print(f"[✓] 即期付款结算成功")
        print(f"    状态: {settled_payment.status}")
        print(f"    已付金额: {settled_payment.total_paid_amount}")
        print(f"    实际付款日: {settled_payment.actual_payment_date}")
        print(f"    付款参考号: T20240315001")

        print("\n" + "-" * 40)
        print("测试8: 信用证付款汇总查询")
        print("-" * 40)

        summary = crud.get_lc_payment_summary(db, "LC-SEA-CIF-2024-001")
        assert summary["lc_number"] == "LC-SEA-CIF-2024-001"
        assert summary["total_payments"] >= 1
        print(f"[✓] 信用证付款汇总查询成功")
        print(f"    信用证: {summary['lc_number']}")
        print(f"    付款笔数: {summary['total_payments']}")
        print(f"    总金额: {summary['total_amount']}")
        print(f"    已付金额: {summary['paid_amount']}")
        print(f"    待付金额: {summary['pending_amount']}")

        print("\n" + "-" * 40)
        print("测试9: 远期付款 - 承兑验证")
        print("-" * 40)

        assert payment2.status == PAYMENT_STATUS_ACCEPTED
        assert payment2.accepted_at is not None
        print(f"[✓] 远期付款承兑状态正确")
        print(f"    承兑时间: {payment2.accepted_at}")

        try:
            crud.accept_payment(db, payment1.payment_number, accepted_by="teller")
            print("[✗] 即期付款不应能承兑")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝即期付款的承兑操作: {str(e)}")

        print("\n" + "-" * 40)
        print("测试9.5: 未到期付款不能结算")
        print("-" * 40)

        assert payment2.status == PAYMENT_STATUS_ACCEPTED
        assert payment2.maturity_date > date.today(), f"远期付款到期日 {payment2.maturity_date} 应在未来"
        try:
            crud.settle_payment(
                db,
                payment2.payment_number,
                payment_date=date.today(),
                settled_by="cashier_test",
            )
            print("[✗] 未到期的远期付款不应能结算")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝未到期远期付款的结算操作: {str(e)}")

        test_sight_pending_number = f"PAY-TEST-SIGHT-PENDING-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        test_sight_pending = models.Payment(
            payment_number=test_sight_pending_number,
            lc_id=lc1.id,
            submission_id="SUB-TEST-SIGHT-PENDING-001",
            audit_record_id=0,
            payment_amount=5000.00,
            currency=lc1.currency,
            payment_method=PAYMENT_METHOD_SIGHT,
            maturity_date=date.today() + timedelta(days=30),
            status=PAYMENT_STATUS_PENDING,
            total_paid_amount=0.0,
            created_at=datetime.now(),
        )
        db.add(test_sight_pending)
        db.flush()
        db.refresh(test_sight_pending)
        print(f"    创建了测试用即期待到期付款，到期日: {test_sight_pending.maturity_date}")

        try:
            crud.settle_payment(
                db,
                test_sight_pending_number,
                payment_date=date.today(),
                settled_by="cashier_test",
            )
            print("[✗] 未到期的即期付款不应能结算")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝未到期即期付款的结算操作: {str(e)}")

        print("\n" + "-" * 40)
        print("测试10: 拒付功能")
        print("-" * 40)

        pending_payment = None
        for p in payments_lc2:
            if p.status == PAYMENT_STATUS_PENDING:
                pending_payment = p
                break

        if pending_payment is None:
            test_payment_number = f"PAY-TEST-REJECT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            test_payment = models.Payment(
                payment_number=test_payment_number,
                lc_id=lc2.id,
                submission_id="SUB-TEST-REJECT-001",
                audit_record_id=0,
                payment_amount=1000.00,
                currency=lc2.currency,
                payment_method=PAYMENT_METHOD_USANCE,
                maturity_date=date(2024, 12, 31),
                status=PAYMENT_STATUS_PENDING,
                total_paid_amount=0.0,
            )
            db.add(test_payment)
            db.flush()
            db.refresh(test_payment)
            pending_payment = test_payment
            print("    创建了测试用 pending 状态付款")

        rejection_reason = "单据存在重大不符点，申请人拒绝付款"
        rejected_payment = crud.reject_payment(
            db,
            pending_payment.payment_number,
            rejection_reason=rejection_reason,
            rejected_by="bank_manager",
        )
        assert rejected_payment.status == PAYMENT_STATUS_REJECTED, f"拒付后状态应为 rejected，实际为 {rejected_payment.status}"
        assert rejected_payment.rejection_reason == rejection_reason, "拒付理由应正确记录"
        print(f"[✓] 拒付功能正常")
        print(f"    状态: {rejected_payment.status}")
        print(f"    拒付理由: {rejected_payment.rejection_reason}")

        try:
            crud.reject_payment(db, rejected_payment.payment_number, rejection_reason="again")
            print("[✗] 已拒付的付款不应能再次拒付")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝重复拒付: {str(e)}")

        print("\n" + "-" * 40)
        print("测试11: 按时间范围统计付款 (按币种分组)")
        print("-" * 40)

        stats = crud.get_payment_stats_by_time_range(
            db,
            start_date=date(2024, 1, 1),
            end_date=date(2027, 12, 31),
        )
        assert stats["total_count"] >= 2, f"总付款笔数应至少为2，实际为 {stats['total_count']}"
        assert len(stats["by_currency"]) >= 2, f"应至少有2种币种，实际为 {len(stats['by_currency'])}"
        print(f"[✓] 付款统计查询成功")
        print(f"    统计区间: {stats['start_date']} ~ {stats['end_date']}")
        print(f"    总笔数: {stats['total_count']}")
        print(f"    总金额: {stats['total_amount']}")
        print(f"    已付总额: {stats['total_paid_amount']}")
        print(f"    币种明细:")
        for c in stats["by_currency"]:
            print(f"      - {c['currency']}: {c['total_amount']} (已付: {c['paid_amount']}, 笔数: {c['count']})")

        print("\n" + "-" * 40)
        print("测试12: 到期检查 (maturity check)")
        print("-" * 40)

        matured_count = crud.check_and_update_matured_payments(db)
        print(f"[✓] 到期检查完成，本次处理 {matured_count} 笔到期付款")

        print("\n" + "-" * 40)
        print("测试13: 所有付款列表查询")
        print("-" * 40)

        all_payments = crud.get_all_payments(db, limit=50)
        print(f"[✓] 所有付款列表查询成功，共 {len(all_payments)} 条")
        for p in all_payments[:5]:
            print(f"    - {p.payment_number}: {p.payment_amount} {p.currency} ({p.status}, 到期: {p.maturity_date})")

        print("\n" + "-" * 40)
        print("测试14: 延期付款信用证创建验证")
        print("-" * 40)

        deferred_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-DEFERRED-TEST-001",
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=date(2024, 6, 30),
            latest_presentation_date=date(2024, 7, 15),
            expiry_date=date(2024, 7, 30),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="SINGAPORE",
            partial_shipment_allowed=True,
            transshipment_allowed=False,
            goods_description="测试货物",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.DEFERRED,
            deferred_payment_date=date(2024, 8, 15),
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            ]
        )
        deferred_lc = crud.create_letter_of_credit(db, deferred_lc_data)
        assert deferred_lc.payment_method == PAYMENT_METHOD_DEFERRED
        assert deferred_lc.deferred_payment_date == date(2024, 8, 15)
        print(f"[✓] 延期付款信用证创建成功")
        print(f"    信用证号: {deferred_lc.lc_number}")
        print(f"    付款方式: {deferred_lc.payment_method}")
        print(f"    延期付款日: {deferred_lc.deferred_payment_date}")

        try:
            bad_lc_data = deferred_lc_data.model_copy()
            bad_lc_data.lc_number = "LC-BAD-DEFERRED-001"
            bad_lc_data.deferred_payment_date = None
            crud.create_letter_of_credit(db, bad_lc_data)
            print("[✗] 延期付款未指定日期应该创建失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝未指定延期付款日的创建: {str(e)}")

        try:
            bad_usance_data = deferred_lc_data.model_copy()
            bad_usance_data.lc_number = "LC-BAD-USANCE-001"
            bad_usance_data.payment_method = schemas.PaymentMethod.USANCE
            bad_usance_data.usance_days = None
            bad_usance_data.deferred_payment_date = None
            crud.create_letter_of_credit(db, bad_usance_data)
            print("[✗] 远期付款未指定天数应该创建失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝未指定远期天数的创建: {str(e)}")

        print("\n" + "-" * 40)
        print("测试15: 部分付款功能")
        print("-" * 40)

        partial_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-PARTIAL-TEST-001",
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=50000.00,
            latest_shipment_date=date(2024, 6, 30),
            latest_presentation_date=date(2024, 7, 15),
            expiry_date=date(2024, 7, 30),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="ROTTERDAM",
            partial_shipment_allowed=True,
            transshipment_allowed=False,
            goods_description="分批装运货物",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            ]
        )
        partial_lc = crud.create_letter_of_credit(db, partial_lc_data)

        partial_submission_id = "SUB-PARTIAL-TEST-001"
        partial_doc = models.Document(
            lc_id=partial_lc.id,
            submission_id=partial_submission_id,
            original_submission_id=partial_submission_id,
            resubmission_round=0,
            document_type="invoice",
            original_copies_submitted=3,
            copy_copies_submitted=2,
            content={
                "invoice_number": "INV-PARTIAL-001",
                "invoice_date": "2024-05-01",
                "beneficiary": "测试受益人",
                "applicant": "测试申请人",
                "currency": "USD",
                "total_amount": 50000.00,
                "goods_description": "分批装运货物",
            }
        )
        db.add(partial_doc)
        db.flush()

        partial_audit = models.AuditRecord(
            lc_id=partial_lc.id,
            submission_id=partial_submission_id,
            original_submission_id=partial_submission_id,
            resubmission_round=0,
            conclusion="compliant",
            auto_conclusion="compliant",
            total_discrepancies=0,
            critical_count=0,
            minor_count=0,
            presentation_date=date(2024, 5, 5),
            review_status="reviewed",
        )
        db.add(partial_audit)
        db.flush()

        partial_payment = crud.create_payment_application(db, partial_submission_id)
        print(f"[✓] 分批装运信用证付款申请创建成功: {partial_payment.payment_number}")
        print(f"    总金额: {partial_payment.payment_amount} USD")

        partial_payment.maturity_date = date(2024, 5, 1)
        db.commit()
        db.refresh(partial_payment)
        crud.check_and_update_matured_payments(db, partial_lc.id)
        db.refresh(partial_payment)

        first_payment = crud.settle_payment(
            db,
            partial_payment.payment_number,
            payment_date=date(2024, 5, 2),
            amount=20000.00,
            settled_by="cashier_02",
            reference="PARTIAL-PAY-001",
        )
        assert first_payment.status != PAYMENT_STATUS_PAID, "部分付款后状态不应为 paid"
        assert abs(first_payment.total_paid_amount - 20000.00) < 0.01
        print(f"[✓] 第一次部分付款成功")
        print(f"    付款金额: 20000.00 USD")
        print(f"    累计已付: {first_payment.total_paid_amount} USD")
        print(f"    当前状态: {first_payment.status}")

        second_payment = crud.settle_payment(
            db,
            partial_payment.payment_number,
            payment_date=date(2024, 5, 10),
            amount=30000.00,
            settled_by="cashier_02",
            reference="PARTIAL-PAY-002",
        )
        assert second_payment.status == PAYMENT_STATUS_PAID, "付清后状态应为 paid"
        assert abs(second_payment.total_paid_amount - 50000.00) < 0.01
        print(f"[✓] 第二次部分付款后全额付清")
        print(f"    付款金额: 30000.00 USD")
        print(f"    累计已付: {second_payment.total_paid_amount} USD")
        print(f"    当前状态: {second_payment.status}")

        print("\n" + "-" * 40)
        print("测试16: 不允许分批装运的信用证拒绝部分付款")
        print("-" * 40)

        no_partial_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-NO-PARTIAL-TEST-001",
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=30000.00,
            latest_shipment_date=date(2024, 6, 30),
            latest_presentation_date=date(2024, 7, 15),
            expiry_date=date(2024, 7, 30),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="HAMBURG",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="整批货物",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            ]
        )
        no_partial_lc = crud.create_letter_of_credit(db, no_partial_lc_data)

        np_submission_id = "SUB-NO-PARTIAL-TEST-001"
        np_doc = models.Document(
            lc_id=no_partial_lc.id,
            submission_id=np_submission_id,
            original_submission_id=np_submission_id,
            resubmission_round=0,
            document_type="invoice",
            original_copies_submitted=3,
            copy_copies_submitted=2,
            content={
                "invoice_number": "INV-NP-001",
                "invoice_date": "2024-05-01",
                "beneficiary": "测试受益人",
                "applicant": "测试申请人",
                "currency": "USD",
                "total_amount": 30000.00,
                "goods_description": "整批货物",
            }
        )
        db.add(np_doc)
        db.flush()

        np_audit = models.AuditRecord(
            lc_id=no_partial_lc.id,
            submission_id=np_submission_id,
            original_submission_id=np_submission_id,
            resubmission_round=0,
            conclusion="compliant",
            auto_conclusion="compliant",
            total_discrepancies=0,
            critical_count=0,
            minor_count=0,
            presentation_date=date(2024, 5, 5),
            review_status="reviewed",
        )
        db.add(np_audit)
        db.flush()

        np_payment = crud.create_payment_application(db, np_submission_id)
        np_payment.maturity_date = date(2024, 5, 1)
        db.commit()
        db.refresh(np_payment)
        crud.check_and_update_matured_payments(db, no_partial_lc.id)
        db.refresh(np_payment)

        try:
            crud.settle_payment(
                db,
                np_payment.payment_number,
                payment_date=date(2024, 5, 2),
                amount=10000.00,
                settled_by="cashier_03",
            )
            print("[✗] 不允许分批装运的信用证应该拒绝部分付款")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝部分付款: {str(e)}")

        print("\n" + "=" * 60)
        print("所有测试通过! ✓")
        print("=" * 60)

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
    test_payment_module()
