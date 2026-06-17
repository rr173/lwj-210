import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data
from app.models import (
    PAYMENT_STATUS_MATURED,
    PAYMENT_STATUS_OVERDUE,
    PAYMENT_STATUS_PAID,
    DEFAULT_PENALTY_RATE,
    COLLECTION_TYPE_SYSTEM_AUTO,
    COLLECTION_TYPE_MANUAL,
    COLLECTION_METHOD_PHONE,
    COLLECTION_METHOD_EMAIL,
)


def test_overdue_penalty_and_collection():
    print("=" * 70)
    print("逾期罚息与催收管理功能测试")
    print("=" * 70)

    if os.path.exists("./data/lc_audit.db"):
        os.remove("./data/lc_audit.db")
        print("已删除旧数据库")

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        print("\n" + "-" * 50)
        print("测试1: 信用证创建 - 罚息利率字段验证")
        print("-" * 50)

        lc1 = crud.get_letter_of_credit_by_number(db, "LC-SEA-CIF-2024-001")
        assert lc1 is not None
        assert lc1.penalty_interest_rate == DEFAULT_PENALTY_RATE, f"默认罚息利率应为 {DEFAULT_PENALTY_RATE}%，实际为 {lc1.penalty_interest_rate}%"
        print(f"[✓] 信用证默认罚息利率正确: {lc1.penalty_interest_rate}%")

        custom_rate_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-PENALTY-TEST-001",
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=date.today() + timedelta(days=30),
            latest_presentation_date=date.today() + timedelta(days=45),
            expiry_date=date.today() + timedelta(days=60),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="SINGAPORE",
            partial_shipment_allowed=True,
            transshipment_allowed=False,
            goods_description="测试货物",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            penalty_interest_rate=8.5,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            ]
        )
        custom_rate_lc = crud.create_letter_of_credit(db, custom_rate_lc_data)
        assert custom_rate_lc.penalty_interest_rate == 8.5, f"自定义罚息利率应为 8.5%，实际为 {custom_rate_lc.penalty_interest_rate}%"
        print(f"[✓] 信用证自定义罚息利率正确: {custom_rate_lc.penalty_interest_rate}%")

        try:
            bad_rate_data = custom_rate_lc_data.model_copy()
            bad_rate_data.lc_number = "LC-BAD-RATE-001"
            bad_rate_data.penalty_interest_rate = -1.0
            crud.create_letter_of_credit(db, bad_rate_data)
            print("[✗] 负罚息利率应该创建失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝负罚息利率: {str(e)}")

        print("\n" + "-" * 50)
        print("测试2: 创建测试付款 (matured状态, 刚到期)")
        print("-" * 50)

        today = date.today()
        maturity_date = today - timedelta(days=1)

        test_payment_number = f"PAY-OVERDUE-TEST-{today.strftime('%Y%m%d%H%M%S')}"
        test_payment = models.Payment(
            payment_number=test_payment_number,
            lc_id=lc1.id,
            submission_id="SUB-OVERDUE-TEST-001",
            audit_record_id=0,
            payment_amount=100000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=maturity_date,
            status=PAYMENT_STATUS_MATURED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now(),
        )
        db.add(test_payment)
        db.commit()
        db.refresh(test_payment)
        print(f"[✓] 创建测试付款: {test_payment_number}")
        print(f"    金额: {test_payment.payment_amount} {test_payment.currency}")
        print(f"    到期日: {test_payment.maturity_date} (昨天)")
        print(f"    状态: {test_payment.status}")

        print("\n" + "-" * 50)
        print("测试3: 罚息计算 - 刚到期时罚息应为0 (宽限期内)")
        print("-" * 50)

        from app.crud import add_business_days
        grace_deadline = add_business_days(test_payment.maturity_date, models.OVERDUE_GRACE_WORKING_DAYS)

        penalty_info_today = crud.calculate_penalty_interest(db, test_payment, today)
        print(f"    计算日期: {today}")
        print(f"    到期日: {test_payment.maturity_date}")
        print(f"    宽限截止日: {grace_deadline}")
        print(f"    罚息起算日: {penalty_info_today['penalty_start_date']}")
        print(f"    逾期天数: {penalty_info_today['overdue_days']}")
        print(f"    当前罚息: {penalty_info_today['current_penalty']}")
        assert penalty_info_today["overdue_days"] == 0, f"宽限期内逾期天数应为 0，实际为 {penalty_info_today['overdue_days']}"
        assert penalty_info_today["current_penalty"] == 0.0, f"宽限期内罚息应为 0，实际为 {penalty_info_today['current_penalty']}"
        print(f"[✓] 宽限期内罚息为0，正确")

        print("\n" + "-" * 50)
        print("测试4: 罚息计算 - 逾期30天 (已过宽限期)")
        print("-" * 50)

        calc_date_30 = today + timedelta(days=29)
        penalty_info_30 = crud.calculate_penalty_interest(db, test_payment, calc_date_30)
        print(f"    计算日期: {calc_date_30}")
        print(f"    罚息起算日: {penalty_info_30['penalty_start_date']}")
        print(f"    逾期天数: {penalty_info_30['overdue_days']}")
        expected_overdue_days = (calc_date_30 - grace_deadline).days
        expected_penalty_30day = round(100000.00 * (6.0 / 100.0) / 365.0 * expected_overdue_days, 2) if expected_overdue_days > 0 else 0.0
        print(f"    预期罚息(扣除宽限期): {expected_penalty_30day}")
        print(f"    实际罚息: {penalty_info_30['current_penalty']}")
        assert penalty_info_30["overdue_days"] == expected_overdue_days
        assert abs(penalty_info_30["current_penalty"] - expected_penalty_30day) < 0.01
        print(f"[✓] 罚息计算正确 (已扣除宽限期)")

        print("\n" + "-" * 50)
        print("测试5: 罚息计算API接口 (get_penalty_interest)")
        print("-" * 50)

        penalty_result = crud.get_penalty_interest(db, test_payment_number)
        assert penalty_result["payment_number"] == test_payment_number
        assert penalty_result["unpaid_amount"] == 100000.00
        assert penalty_result["penalty_interest_rate"] == 6.0
        print(f"[✓] 罚息查询接口返回正确")
        print(f"    未付金额: {penalty_result['unpaid_amount']}")
        print(f"    罚息利率: {penalty_result['penalty_interest_rate']}%")
        print(f"    当前罚息: {penalty_result['current_penalty']}")
        print(f"    剩余应付罚息: {penalty_result['remaining_penalty']}")

        print("\n" + "-" * 50)
        print("测试6: 创建已逾期超过3个工作日的付款 (验证自动逾期标记)")
        print("-" * 50)

        maturity_date_old = today - timedelta(days=10)
        overdue_payment_number = f"PAY-OVERDUE-AUTO-{today.strftime('%Y%m%d%H%M%S')}"
        overdue_payment = models.Payment(
            payment_number=overdue_payment_number,
            lc_id=lc1.id,
            submission_id="SUB-OVERDUE-AUTO-001",
            audit_record_id=0,
            payment_amount=50000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=maturity_date_old,
            status=PAYMENT_STATUS_MATURED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=10),
        )
        db.add(overdue_payment)
        db.commit()
        db.refresh(overdue_payment)

        print(f"    创建付款: {overdue_payment_number}")
        print(f"    到期日: {maturity_date_old} (10天前)")
        print(f"    当前状态: {overdue_payment.status}")

        overdue_count = crud.check_and_update_overdue_payments(db, lc1.id)
        print(f"    逾期检查处理了 {overdue_count} 笔付款")
        db.refresh(overdue_payment)

        assert overdue_payment.status == PAYMENT_STATUS_OVERDUE, f"付款应被标记为 overdue，实际为 {overdue_payment.status}"
        assert overdue_count >= 1
        print(f"[✓] 自动逾期标记功能正常，付款状态: {overdue_payment.status}")

        print("\n" + "-" * 50)
        print("测试7: 自动生成催收记录验证")
        print("-" * 50)

        collections = crud.get_collection_records_by_payment(db, overdue_payment_number)
        assert len(collections) >= 1, "应至少有1条自动生成的催收记录"
        auto_collection = collections[0]
        print(f"    催收编号: {auto_collection['collection_number']}")
        print(f"    催收类型: {auto_collection['collection_type']}")
        print(f"    催收内容: {auto_collection['collection_content']}")
        assert auto_collection["collection_type"] == COLLECTION_TYPE_SYSTEM_AUTO
        assert auto_collection["collection_content"] == "付款已逾期,请尽快安排付款"
        print(f"[✓] 自动催收记录生成正确")

        print("\n" + "-" * 50)
        print("测试8: 手动添加催收记录")
        print("-" * 50)

        manual_collection_data = schemas.CollectionRecordCreate(
            payment_number=overdue_payment_number,
            collection_method=schemas.CollectionMethod.PHONE,
            contact_person="张经理 (开证行财务)",
            collection_content="已电话联系开证行张经理，对方表示将在3个工作日内安排付款",
            created_by="bank_officer_01",
        )
        manual_record = crud.create_manual_collection_record(db, manual_collection_data)
        assert manual_record.collection_type == COLLECTION_TYPE_MANUAL
        assert manual_record.collection_method == COLLECTION_METHOD_PHONE
        assert manual_record.contact_person == "张经理 (开证行财务)"
        print(f"[✓] 手动催收记录创建成功")
        print(f"    催收编号: {manual_record.collection_number}")
        print(f"    催收方式: {manual_record.collection_method}")
        print(f"    联系人: {manual_record.contact_person}")
        print(f"    催收内容: {manual_record.collection_content}")
        print(f"    创建人: {manual_record.created_by}")

        collections_all = crud.get_collection_records_by_payment(db, overdue_payment_number)
        assert len(collections_all) == 2, f"应有2条催收记录，实际为 {len(collections_all)}"
        print(f"[✓] 该付款共有 {len(collections_all)} 条催收记录 (按时间倒序)")
        for i, c in enumerate(collections_all):
            print(f"    {i+1}. [{c['collection_type']}] {c['collection_time']} - {c['collection_content'][:30]}...")

        print("\n" + "-" * 50)
        print("测试9: 逾期付款结算 - 罚息校验 (少付罚息应被拒绝)")
        print("-" * 50)

        penalty_before = crud.calculate_penalty_interest(db, overdue_payment, today)
        remaining_penalty = penalty_before["remaining_penalty"]
        print(f"    应付本金: 50000.00 USD")
        print(f"    应付罚息: {remaining_penalty} USD")

        try:
            crud.settle_payment(
                db,
                overdue_payment_number,
                payment_date=today,
                amount=50000.00,
                penalty_amount=remaining_penalty - 100.00,
                settled_by="cashier_test",
            )
            print("[✗] 少付罚息应该结算失败")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝少付罚息: {str(e)}")

        print("\n" + "-" * 50)
        print("测试10: 逾期付款结算 - 正常支付本金+罚息 (允许多付)")
        print("-" * 50)

        extra_penalty = 50.00
        total_penalty_to_pay = remaining_penalty + extra_penalty
        settled = crud.settle_payment(
            db,
            overdue_payment_number,
            payment_date=today,
            amount=50000.00,
            penalty_amount=total_penalty_to_pay,
            settled_by="cashier_01",
            reference="OVERDUE-SETTLE-001",
        )
        assert settled.status == PAYMENT_STATUS_PAID
        assert abs(settled.total_paid_amount - 50000.00) < 0.01
        assert abs(settled.total_penalty_paid - total_penalty_to_pay) < 0.01
        print(f"[✓] 逾期付款结算成功")
        print(f"    支付本金: 50000.00 USD")
        print(f"    支付罚息: {total_penalty_to_pay} USD (应付: {remaining_penalty}, 多付: {extra_penalty})")
        print(f"    付款状态: {settled.status}")
        print(f"    实际付款日: {settled.actual_payment_date}")

        penalty_after = crud.get_penalty_interest(db, overdue_payment_number)
        print(f"    结算后剩余罚息: {penalty_after['remaining_penalty']}")

        print("\n" + "-" * 50)
        print("测试11: 部分付款后罚息计算 (基于未付本金)")
        print("-" * 50)

        partial_payment_number = f"PAY-PARTIAL-PENALTY-{today.strftime('%Y%m%d%H%M%S')}"
        partial_test_payment = models.Payment(
            payment_number=partial_payment_number,
            lc_id=custom_rate_lc.id,
            submission_id="SUB-PARTIAL-PENALTY-001",
            audit_record_id=0,
            payment_amount=200000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=today - timedelta(days=15),
            status=PAYMENT_STATUS_OVERDUE,
            total_paid_amount=80000.00,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=15),
        )
        db.add(partial_test_payment)
        db.commit()
        db.refresh(partial_test_payment)

        partial_penalty = crud.calculate_penalty_interest(db, partial_test_payment, today)
        unpaid = 200000.00 - 80000.00
        penalty_start = partial_penalty['penalty_start_date']
        actual_overdue_days = partial_penalty['overdue_days']
        expected_partial_penalty = round(unpaid * (8.5 / 100.0) / 365.0 * actual_overdue_days, 2)
        print(f"    总金额: 200000.00 USD, 已付本金: 80000.00 USD")
        print(f"    未付本金: {unpaid} USD")
        print(f"    罚息利率: 8.5%")
        print(f"    到期日: {partial_test_payment.maturity_date}, 罚息起算日: {penalty_start}")
        print(f"    实际逾期天数(扣除宽限期): {actual_overdue_days}天")
        print(f"    预期罚息: {expected_partial_penalty} USD")
        print(f"    实际罚息: {partial_penalty['current_penalty']} USD")
        assert abs(partial_penalty["current_penalty"] - expected_partial_penalty) < 0.01
        assert partial_penalty["unpaid_amount"] == unpaid
        print(f"[✓] 部分付款后罚息计算正确 (基于未付本金,已扣除宽限期)")

        print("\n" + "-" * 50)
        print("测试12: 逾期统计接口")
        print("-" * 50)

        stats_start = today - timedelta(days=30)
        stats_end = today + timedelta(days=1)
        stats = crud.get_overdue_stats_by_time_range(db, stats_start, stats_end)
        print(f"    统计区间: {stats_start} ~ {stats_end}")
        print(f"    逾期笔数: {stats['overdue_count']}")
        print(f"    逾期总金额: {stats['overdue_total_amount']}")
        print(f"    币种明细: {stats['overdue_currency_details']}")
        assert stats["overdue_count"] >= 1
        assert stats["overdue_total_amount"] > 0
        print(f"[✓] 逾期统计接口返回正确")

        print("\n" + "-" * 50)
        print("测试13: 状态流转约束验证")
        print("-" * 50)

        rejected_payment_number = f"PAY-REJECTED-TEST-{today.strftime('%Y%m%d%H%M%S')}"
        rejected_payment = models.Payment(
            payment_number=rejected_payment_number,
            lc_id=lc1.id,
            submission_id="SUB-REJECTED-TEST-001",
            audit_record_id=0,
            payment_amount=25000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=today - timedelta(days=20),
            status=models.PAYMENT_STATUS_REJECTED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=20),
        )
        db.add(rejected_payment)
        db.commit()
        db.refresh(rejected_payment)

        before_count = crud.check_and_update_overdue_payments(db, lc1.id)
        db.refresh(rejected_payment)
        assert rejected_payment.status == models.PAYMENT_STATUS_REJECTED, "rejected状态的付款不应变为overdue"
        print(f"[✓] rejected状态付款不会被标记为逾期 (状态保持: {rejected_payment.status})")

        print("\n" + "=" * 70)
        print("所有逾期罚息与催收管理功能测试通过! ✓")
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
    test_overdue_penalty_and_collection()
