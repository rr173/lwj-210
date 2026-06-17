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
    PAYMENT_STATUS_ACCEPTED,
    PAYMENT_STATUS_PAID,
    DEFAULT_PENALTY_RATE,
    OVERDUE_GRACE_WORKING_DAYS,
)
from app.crud import add_business_days, calculate_penalty_interest


def test_bugfix_verification():
    print("=" * 70)
    print("Bug修复验证测试")
    print("=" * 70)

    if os.path.exists("./data/lc_audit.db"):
        os.remove("./data/lc_audit.db")
        print("已删除旧数据库")

    init_db()
    seed_data()

    db = SessionLocal()

    today = date.today()

    try:
        lc1 = crud.get_letter_of_credit_by_number(db, "LC-SEA-CIF-2024-001")
        assert lc1 is not None

        print("\n" + "-" * 50)
        print("Bug 1 验证: 罚息宽限期生效测试")
        print("-" * 50)
        print(f"今天日期: {today}")
        print(f"宽限期: {OVERDUE_GRACE_WORKING_DAYS} 个工作日")

        maturity_1d_ago = today - timedelta(days=1)
        grace_deadline_1d = add_business_days(maturity_1d_ago, OVERDUE_GRACE_WORKING_DAYS)
        print(f"测试场景1: 到期日={maturity_1d_ago} (1天前), 宽限截止日={grace_deadline_1d}")

        test_payment_1d = models.Payment(
            payment_number=f"PAY-GRACE-1D-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-GRACE-1D-001",
            audit_record_id=0,
            payment_amount=100000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=maturity_1d_ago,
            status=PAYMENT_STATUS_MATURED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now(),
        )
        db.add(test_payment_1d)
        db.commit()
        db.refresh(test_payment_1d)

        penalty_1d = calculate_penalty_interest(db, test_payment_1d, today)
        print(f"  罚息起算日: {penalty_1d['penalty_start_date']}")
        print(f"  逾期天数: {penalty_1d['overdue_days']}")
        print(f"  当前罚息: {penalty_1d['current_penalty']}")

        assert penalty_1d["current_penalty"] == 0.0, f"Bug 1未修复: 到期才过1天就有罚息 {penalty_1d['current_penalty']}，宽限期未生效！"
        assert penalty_1d["overdue_days"] == 0, f"Bug 1未修复: 逾期天数应为0，实际为 {penalty_1d['overdue_days']}"
        print("[✓] Bug 1修复验证通过: 宽限期内罚息为0")

        print("\n测试场景2: 到期日超过宽限期，应有罚息")
        maturity_10d_ago = today - timedelta(days=10)
        grace_deadline_10d = add_business_days(maturity_10d_ago, OVERDUE_GRACE_WORKING_DAYS)
        print(f"  到期日={maturity_10d_ago} (10天前), 宽限截止日={grace_deadline_10d}")

        test_payment_10d = models.Payment(
            payment_number=f"PAY-GRACE-10D-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-GRACE-10D-001",
            audit_record_id=0,
            payment_amount=100000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=maturity_10d_ago,
            status=PAYMENT_STATUS_MATURED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now(),
        )
        db.add(test_payment_10d)
        db.commit()
        db.refresh(test_payment_10d)

        penalty_10d = calculate_penalty_interest(db, test_payment_10d, today)
        expected_overdue_days = (today - grace_deadline_10d).days
        expected_penalty = round(100000.00 * (6.0 / 100.0) / 365.0 * expected_overdue_days, 2)
        print(f"  罚息起算日: {penalty_10d['penalty_start_date']}")
        print(f"  逾期天数: {penalty_10d['overdue_days']} (预期: {expected_overdue_days})")
        print(f"  当前罚息: {penalty_10d['current_penalty']} (预期: {expected_penalty})")

        assert penalty_10d["current_penalty"] > 0, "超过宽限期应有罚息"
        assert abs(penalty_10d["current_penalty"] - expected_penalty) < 0.01, "罚息金额计算不正确"
        print("[✓] 超过宽限期后罚息计算正确")

        print("\n" + "-" * 50)
        print("Bug 3 验证: 卡在accepted状态的到期付款会被处理")
        print("-" * 50)

        maturity_old = today - timedelta(days=15)
        accepted_payment = models.Payment(
            payment_number=f"PAY-ACCEPTED-STUCK-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-ACCEPTED-STUCK-001",
            audit_record_id=0,
            payment_amount=75000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=maturity_old,
            status=PAYMENT_STATUS_ACCEPTED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=15),
        )
        db.add(accepted_payment)
        db.commit()
        db.refresh(accepted_payment)

        print(f"  测试付款: {accepted_payment.payment_number}")
        print(f"  初始状态: {accepted_payment.status}")
        print(f"  到期日: {accepted_payment.maturity_date} (15天前)")

        matured_list_before = crud.get_payments_by_status(db, PAYMENT_STATUS_MATURED)
        count_before = len([p for p in matured_list_before if p.payment_number == accepted_payment.payment_number])
        overdue_list_before = crud.get_payments_by_status(db, PAYMENT_STATUS_OVERDUE)
        overdue_before = len([p for p in overdue_list_before if p.payment_number == accepted_payment.payment_number])
        print(f"  检查前: matured列表有{count_before}个, overdue列表有{overdue_before}个")

        updated_count = crud.check_and_update_overdue_payments(db, lc1.id)
        db.refresh(accepted_payment)
        print(f"  逾期检查处理了 {updated_count} 笔付款")
        print(f"  检查后状态: {accepted_payment.status}")

        assert accepted_payment.status == PAYMENT_STATUS_OVERDUE, f"Bug 3未修复: 卡在accepted状态的付款没有被处理，状态仍为 {accepted_payment.status}"
        print("[✓] Bug 3修复验证通过: accepted状态的到期付款会先转matured再转overdue")

        print("\n" + "-" * 50)
        print("Bug 2 验证: 按状态查询与详情查询状态一致")
        print("-" * 50)

        test_payment_consistent = models.Payment(
            payment_number=f"PAY-CONSISTENCY-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-CONSISTENCY-001",
            audit_record_id=0,
            payment_amount=50000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=today - timedelta(days=12),
            status=PAYMENT_STATUS_MATURED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=12),
        )
        db.add(test_payment_consistent)
        db.commit()
        db.refresh(test_payment_consistent)

        print(f"  测试付款: {test_payment_consistent.payment_number}")
        print(f"  数据库原始状态: {test_payment_consistent.status}")

        matured_payments = crud.get_payments_by_status(db, PAYMENT_STATUS_MATURED)
        in_matured = any(p.payment_number == test_payment_consistent.payment_number for p in matured_payments)
        print(f"  查询matured列表: {'找到' if in_matured else '未找到'}该付款")

        overdue_payments = crud.get_payments_by_status(db, PAYMENT_STATUS_OVERDUE)
        in_overdue = any(p.payment_number == test_payment_consistent.payment_number for p in overdue_payments)
        print(f"  查询overdue列表: {'找到' if in_overdue else '未找到'}该付款")

        db.refresh(test_payment_consistent)
        status_after_list_query = test_payment_consistent.status
        print(f"  列表查询后状态: {status_after_list_query}")

        detail = crud.get_payment_detail(db, test_payment_consistent.payment_number)
        status_detail = detail["status"]
        print(f"  详情查询状态: {status_detail}")

        assert status_after_list_query == status_detail, f"Bug 2未修复: 列表查询状态={status_after_list_query}, 详情查询状态={status_detail}"
        assert in_overdue, "应在overdue列表中找到该付款"
        assert not in_matured, "不应在matured列表中找到该付款"
        print("[✓] Bug 2修复验证通过: 列表查询与详情查询状态一致")

        print("\n测试场景2: get_all_payments也会触发状态更新")
        test_payment_all = models.Payment(
            payment_number=f"PAY-ALL-TEST-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-ALL-TEST-001",
            audit_record_id=0,
            payment_amount=25000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=today - timedelta(days=20),
            status=PAYMENT_STATUS_ACCEPTED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=20),
        )
        db.add(test_payment_all)
        db.commit()
        db.refresh(test_payment_all)

        print(f"  付款初始状态: {test_payment_all.status}")
        all_payments = crud.get_all_payments(db)
        db.refresh(test_payment_all)
        print(f"  get_all_payments后状态: {test_payment_all.status}")
        assert test_payment_all.status == PAYMENT_STATUS_OVERDUE, "get_all_payments应触发状态更新"
        print("[✓] get_all_payments会触发状态更新")

        print("\n测试场景3: get_payments_by_lc也会触发状态更新")
        test_payment_bylc = models.Payment(
            payment_number=f"PAY-BYLC-TEST-{today.strftime('%Y%m%d%H%M%S')}",
            lc_id=lc1.id,
            submission_id="SUB-BYLC-TEST-001",
            audit_record_id=0,
            payment_amount=30000.00,
            currency="USD",
            payment_method=models.PAYMENT_METHOD_SIGHT,
            maturity_date=today - timedelta(days=25),
            status=PAYMENT_STATUS_ACCEPTED,
            total_paid_amount=0.0,
            total_penalty_paid=0.0,
            created_at=datetime.now() - timedelta(days=25),
        )
        db.add(test_payment_bylc)
        db.commit()
        db.refresh(test_payment_bylc)

        print(f"  付款初始状态: {test_payment_bylc.status}")
        lc_payments = crud.get_payments_by_lc(db, lc1.lc_number)
        db.refresh(test_payment_bylc)
        print(f"  get_payments_by_lc后状态: {test_payment_bylc.status}")
        assert test_payment_bylc.status == PAYMENT_STATUS_OVERDUE, "get_payments_by_lc应触发状态更新"
        print("[✓] get_payments_by_lc会触发状态更新")

        print("\n测试场景4: 宽限期内的matured付款不会被标记为overdue")
        maturity_2d_ago = today - timedelta(days=2)
        grace_deadline_2d = add_business_days(maturity_2d_ago, OVERDUE_GRACE_WORKING_DAYS)
        print(f"  到期日={maturity_2d_ago}, 宽限截止日={grace_deadline_2d}")
        print(f"  今天={today}, 宽限期未过: {today <= grace_deadline_2d}")

        if today <= grace_deadline_2d:
            test_payment_grace = models.Payment(
                payment_number=f"PAY-GRACE-TEST-{today.strftime('%Y%m%d%H%M%S')}",
                lc_id=lc1.id,
                submission_id="SUB-GRACE-TEST-001",
                audit_record_id=0,
                payment_amount=40000.00,
                currency="USD",
                payment_method=models.PAYMENT_METHOD_SIGHT,
                maturity_date=maturity_2d_ago,
                status=PAYMENT_STATUS_MATURED,
                total_paid_amount=0.0,
                total_penalty_paid=0.0,
                created_at=datetime.now(),
            )
            db.add(test_payment_grace)
            db.commit()
            db.refresh(test_payment_grace)

            crud.check_and_update_overdue_payments(db, lc1.id)
            db.refresh(test_payment_grace)
            print(f"  逾期检查后状态: {test_payment_grace.status}")
            assert test_payment_grace.status == PAYMENT_STATUS_MATURED, "宽限期内的付款不应被标记为overdue"
            print("[✓] 宽限期内的matured付款保持matured状态")

        print("\n" + "=" * 70)
        print("所有Bug修复验证测试通过! ✓")
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
    test_bugfix_verification()
