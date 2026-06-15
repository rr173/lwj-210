import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def test_amendment_module():
    print("=" * 60)
    print("信用证修改模块功能测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"
        print(f"\n[✓] 找到测试信用证: {lc_number}")
        print(f"    金额: {lc.amount} {lc.currency}")
        print(f"    最迟装运日期: {lc.latest_shipment_date}")
        print(f"    附加条款数量: {len(lc.additional_terms)}")

        print("\n" + "-" * 40)
        print("测试1: 创建修改请求")
        print("-" * 40)

        amendment_data = schemas.AmendmentCreate(
            lc_number=lc_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=50000.00,
                    new_value=55000.00
                ),
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value="2024-03-10",
                    new_value="2024-03-20"
                ),
                schemas.FieldChange(
                    field_name="additional_terms",
                    old_value=["保险金额不低于发票金额110%", "提单必须做成指示抬头(TO ORDER)", "提单显示运费预付(FREIGHT PREPAID)", "提交清洁已装船提单"],
                    new_value=["保险金额不低于发票金额110%", "提单必须做成指示抬头(TO ORDER)", "提单显示运费预付(FREIGHT PREPAID)", "提交清洁已装船提单", "所有单据须显示信用证号"]
                )
            ]
        )

        amendment = crud.create_amendment(db, amendment_data)
        assert amendment is not None, "创建修改失败"
        assert amendment.status == "pending", f"修改状态应为 pending，实际为 {amendment.status}"
        assert amendment.amendment_number == f"{lc_number}-AMD-001", f"修改编号格式错误: {amendment.amendment_number}"
        assert len(amendment.field_changes) == 3, f"字段变更数量应为 3，实际为 {len(amendment.field_changes)}"

        print(f"[✓] 修改创建成功")
        print(f"    修改编号: {amendment.amendment_number}")
        print(f"    状态: {amendment.status}")
        print(f"    修改字段数: {len(amendment.field_changes)}")
        print(f"    过期时间: {amendment.expiry_time}")

        print("\n" + "-" * 40)
        print("测试2: 同一时间只能有一个 pending 修改")
        print("-" * 40)

        try:
            amendment2_data = schemas.AmendmentCreate(
                lc_number=lc_number,
                field_changes=[
                    schemas.FieldChange(
                        field_name="expiry_date",
                        old_value="2024-04-10",
                        new_value="2024-04-20"
                    )
                ]
            )
            crud.create_amendment(db, amendment2_data)
            print("[✗] 应该拒绝创建第二个 pending 修改，但成功了")
            assert False, "同一时间应该只能有一个 pending 修改"
        except ValueError as e:
            print(f"[✓] 正确拒绝了第二个 pending 修改")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试3: 字段数量限制 (最多5个)")
        print("-" * 40)

        lc_number2 = "LC-AIR-CFR-2024-002"
        many_changes = [
            schemas.FieldChange(field_name=f"amount", old_value=35000, new_value=36000),
        ] * 6

        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number2,
                field_changes=many_changes
            )
            crud.create_amendment(db, bad_amendment)
            print("[✗] 应该拒绝超过5个字段的修改")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了超过5个字段的修改")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试4: 不允许修改的字段")
        print("-" * 40)

        try:
            bad_amendment = schemas.AmendmentCreate(
                lc_number=lc_number2,
                field_changes=[
                    schemas.FieldChange(
                        field_name="lc_number",
                        old_value="LC-AIR-CFR-2024-002",
                        new_value="LC-AIR-CFR-2024-002-NEW"
                    )
                ]
            )
            crud.create_amendment(db, bad_amendment)
            print("[✗] 应该拒绝修改不允许的字段")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了修改不允许的字段")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试5: 查询信用证修改历史")
        print("-" * 40)

        amendments = crud.get_amendments_by_lc(db, lc_number)
        assert len(amendments) == 1, f"应该有1条修改记录，实际有 {len(amendments)} 条"
        print(f"[✓] 查询到 {len(amendments)} 条修改记录")
        for a in amendments:
            print(f"    - {a.amendment_number} (状态: {a.status})")

        print("\n" + "-" * 40)
        print("测试6: 查看修改快照 (修改前)")
        print("-" * 40)

        snapshot = crud.get_amendment_snapshot(db, amendment.amendment_number)
        assert snapshot["before"] is not None, "修改前快照不应为空"
        assert snapshot["after"] is None, "pending 状态的修改不应有修改后快照"
        assert snapshot["before"]["amount"] == 50000.00, f"修改前金额应为 50000.00，实际为 {snapshot['before']['amount']}"
        print(f"[✓] 快照查询成功")
        print(f"    修改前金额: {snapshot['before']['amount']}")
        print(f"    修改后状态: {snapshot['after']} (None 表示未生效)")

        print("\n" + "-" * 40)
        print("测试7: 拒绝修改")
        print("-" * 40)

        lc_before_reject = crud.get_letter_of_credit_by_number(db, lc_number)
        amount_before = lc_before_reject.amount

        rejected_amendment = crud.reject_amendment(db, amendment.amendment_number)
        assert rejected_amendment.status == "rejected", f"状态应为 rejected，实际为 {rejected_amendment.status}"

        lc_after_reject = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc_after_reject.amount == amount_before, "拒绝修改后信用证金额不应变化"

        print(f"[✓] 修改已被拒绝")
        print(f"    状态: {rejected_amendment.status}")
        print(f"    信用证金额未变化: {lc_after_reject.amount}")

        print("\n" + "-" * 40)
        print("测试8: 接受修改并验证变更应用")
        print("-" * 40)

        amendment_data2 = schemas.AmendmentCreate(
            lc_number=lc_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=50000.00,
                    new_value=60000.00
                ),
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value="2024-03-10",
                    new_value="2024-04-10"
                ),
                schemas.FieldChange(
                    field_name="expiry_date",
                    old_value="2024-04-10",
                    new_value="2024-05-10"
                ),
                schemas.FieldChange(
                    field_name="partial_shipment_allowed",
                    old_value=False,
                    new_value=True
                )
            ]
        )

        amendment2 = crud.create_amendment(db, amendment_data2)
        print(f"[✓] 创建第二个修改: {amendment2.amendment_number}")

        accepted = crud.accept_amendment(db, amendment2.amendment_number)
        assert accepted.status == "accepted", f"状态应为 accepted，实际为 {accepted.status}"
        assert accepted.acceptance_time is not None, "应有接受时间"
        assert accepted.snapshot_after is not None, "接受后应有修改后快照"

        lc_after_accept = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc_after_accept.amount == 60000.00, f"金额应更新为 60000.00，实际为 {lc_after_accept.amount}"
        assert lc_after_accept.latest_shipment_date == date(2024, 4, 10), f"最迟装运日期应更新为 2024-04-10"
        assert lc_after_accept.expiry_date == date(2024, 5, 10), f"到期日应更新为 2024-05-10"
        assert lc_after_accept.partial_shipment_allowed == True, "分批装运应更新为允许"

        print(f"[✓] 修改已接受并生效")
        print(f"    状态: {accepted.status}")
        print(f"    新金额: {lc_after_accept.amount}")
        print(f"    新最迟装运日期: {lc_after_accept.latest_shipment_date}")
        print(f"    新到期日: {lc_after_accept.expiry_date}")
        print(f"    分批装运: {'允许' if lc_after_accept.partial_shipment_allowed else '禁止'}")

        print("\n" + "-" * 40)
        print("测试9: 查看生效后的修改快照对比")
        print("-" * 40)

        snapshot2 = crud.get_amendment_snapshot(db, amendment2.amendment_number)
        assert snapshot2["before"] is not None
        assert snapshot2["after"] is not None
        assert snapshot2["before"]["amount"] == 50000.00
        assert snapshot2["after"]["amount"] == 60000.00

        print(f"[✓] 快照对比成功")
        print(f"    修改前金额: {snapshot2['before']['amount']}")
        print(f"    修改后金额: {snapshot2['after']['amount']}")
        print(f"    修改前最迟装运日期: {snapshot2['before']['latest_shipment_date']}")
        print(f"    修改后最迟装运日期: {snapshot2['after']['latest_shipment_date']}")

        print("\n" + "-" * 40)
        print("测试10: 修改过期处理")
        print("-" * 40)

        lc2 = crud.get_letter_of_credit_by_number(db, lc_number2)
        assert lc2 is not None

        amend3_data = schemas.AmendmentCreate(
            lc_number=lc_number2,
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=35000.00,
                    new_value=38000.00
                )
            ]
        )
        amend3 = crud.create_amendment(db, amend3_data)

        from sqlalchemy.orm import Session
        amend3.expiry_time = datetime.utcnow() - timedelta(days=1)
        db.commit()

        expired_count = crud.check_and_expire_amendments(db, lc2.id)
        assert expired_count >= 1, f"应该至少有1个过期修改，实际为 {expired_count}"

        db.refresh(amend3)
        assert amend3.status == "expired", f"状态应为 expired，实际为 {amend3.status}"

        print(f"[✓] 过期处理正常工作")
        print(f"    过期修改数量: {expired_count}")
        print(f"    修改状态: {amend3.status}")

        print("\n" + "-" * 40)
        print("测试11: 过期修改不能被接受")
        print("-" * 40)

        try:
            crud.accept_amendment(db, amend3.amendment_number)
            print("[✗] 应该拒绝接受过期修改")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了接受过期修改")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试12: 审核联动 - 修改后重新审核不符单据")
        print("-" * 40)

        audit_records = crud.get_audit_records_by_lc(db, lc_number2)
        print(f"    信用证 {lc_number2} 的审核记录数: {len(audit_records)}")

        if audit_records:
            record_before = audit_records[0]
            conclusion_before = record_before.conclusion
            discrepancies_before = record_before.total_discrepancies

            print(f"    修改前结论: {conclusion_before}")
            print(f"    修改前不符点数量: {discrepancies_before}")

            amend4_data = schemas.AmendmentCreate(
                lc_number=lc_number2,
                field_changes=[
                    schemas.FieldChange(
                        field_name="latest_shipment_date",
                        old_value="2024-04-15",
                        new_value="2024-05-15"
                    ),
                    schemas.FieldChange(
                        field_name="transshipment_allowed",
                        old_value=True,
                        new_value=True
                    )
                ]
            )
            amend4 = crud.create_amendment(db, amend4_data)
            accepted4 = crud.accept_amendment(db, amend4.amendment_number)

            db.refresh(record_before)
            conclusion_after = record_before.conclusion
            discrepancies_after = record_before.total_discrepancies

            print(f"    修改后结论: {conclusion_after}")
            print(f"    修改后不符点数量: {discrepancies_after}")
            print(f"[✓] 审核联动功能已执行")

        print("\n" + "-" * 40)
        print("测试13: 查询所有 pending 修改")
        print("-" * 40)

        pending = crud.get_all_pending_amendments(db)
        print(f"[✓] 当前 pending 修改数量: {len(pending)}")

        print("\n" + "-" * 40)
        print("测试14: 批量过期检查")
        print("-" * 40)

        total_expired = crud.expire_all_overdue_amendments(db)
        print(f"[✓] 批量过期检查完成，处理了 {total_expired} 个修改")

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
    test_amendment_module()
