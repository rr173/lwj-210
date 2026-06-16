import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.database import SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def test_alert_module():
    print("=" * 60)
    print("信用证到期预警与逾期处理模块测试")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        lc_number = "LC-TEST-ALERT-001"
        existing = crud.get_letter_of_credit_by_number(db, lc_number)
        if existing:
            print(f"\n清理测试数据: {lc_number}")
            crud.delete_letter_of_credit(db, existing.id)

        today = date.today()

        print(f"\n今日日期: {today}")
        print(f"创建测试信用证 (装运日+5天, 交单日+3天, 到期日+8天)")

        lc_data = schemas.LetterOfCreditCreate(
            lc_number=lc_number,
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=today + timedelta(days=5),
            latest_presentation_date=today + timedelta(days=3),
            expiry_date=today + timedelta(days=8),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="SINGAPORE",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="测试商品",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
            ]
        )
        lc = crud.create_letter_of_credit(db, lc_data)
        print(f"  ✓ 信用证创建成功: {lc.lc_number}")

        print("\n1. 测试预警扫描生成")
        print("-" * 40)
        result = crud.scan_and_generate_alerts(db)
        print(f"  生成预警总数: {result['total']}")
        print(f"  装运预警: {result['shipment_alerts']} (预期: 1, 因为还有5天，阈值是7天，5<=7)")
        print(f"  交单预警: {result['presentation_alerts']} (预期: 1, 因为还有3天，阈值是5天，3<=5)")
        print(f"  到期预警: {result['expiry_alerts']} (预期: 1, 因为还有8天，阈值是10天，8<=10)")

        print("\n2. 测试按信用证查询预警")
        print("-" * 40)
        alerts = crud.get_alerts_by_lc(db, lc_number)
        print(f"  预警记录数: {len(alerts)}")
        for alert in alerts:
            print(f"    - {alert.alert_number}: 类型={alert.alert_type}, "
                  f"目标日期={alert.target_date}, 剩余={alert.remaining_days}天, "
                  f"状态={alert.status}")

        print("\n3. 测试活跃预警查询")
        print("-" * 40)
        active_alerts = crud.get_active_alerts(db)
        print(f"  活跃预警数: {len(active_alerts)}")

        print("\n4. 测试预警统计")
        print("-" * 40)
        stats = crud.get_alert_statistics(db)
        for s in stats:
            print(f"  {s['alert_type_name']} ({s['alert_type']}): {s['count']} 条")

        print("\n5. 测试预警确认")
        print("-" * 40)
        if alerts:
            alert = alerts[0]
            acknowledged = crud.acknowledge_alert(db, alert.alert_number, "测试用户")
            print(f"  ✓ 预警已确认: {acknowledged.alert_number}")
            print(f"    状态: {acknowledged.status}")
            print(f"    确认人: {acknowledged.acknowledged_by}")
            print(f"    确认时间: {acknowledged.acknowledged_at}")

        print("\n6. 创建一个即将到期的信用证来测试逾期和冻结")
        print("-" * 40)
        lc_number2 = "LC-TEST-EXPIRED-001"
        existing2 = crud.get_letter_of_credit_by_number(db, lc_number2)
        if existing2:
            crud.delete_letter_of_credit(db, existing2.id)

        lc_data2 = schemas.LetterOfCreditCreate(
            lc_number=lc_number2,
            issuing_bank="测试银行",
            beneficiary_name="测试受益人2",
            applicant_name="测试申请人2",
            currency=schemas.Currency.EUR,
            amount=50000.00,
            latest_shipment_date=today - timedelta(days=2),
            latest_presentation_date=today - timedelta(days=1),
            expiry_date=today + timedelta(days=5),
            transport_mode=schemas.TransportMode.AIR,
            port_of_loading="BEIJING",
            port_of_discharge="LONDON",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="电子产品",
            additional_terms=[],
            fee_tier=schemas.FeeTier.PREFERRED,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
            ]
        )
        lc2 = crud.create_letter_of_credit(db, lc_data2)
        print(f"  ✓ 信用证创建成功: {lc2.lc_number}")
        print(f"    装运日: {lc2.latest_shipment_date} (已过期2天)")
        print(f"    交单日: {lc2.latest_presentation_date} (已过期1天)")
        print(f"    到期日: {lc2.expiry_date} (还有5天)")

        print("\n7. 测试逾期处理和冻结（先扫描生成预警，再检查逾期）")
        print("-" * 40)
        scan_result = crud.scan_and_generate_alerts(db)
        print(f"  扫描新增预警: {scan_result['total']} 条")

        result = crud.check_and_process_expired_alerts(db)
        print(f"  过期预警数: {result['expired_alerts']}")
        print(f"  新增冻结数: {result['new_freezes']}")

        print("\n8. 测试冻结记录查询")
        print("-" * 40)
        freezes = crud.get_freeze_records_by_lc(db, lc_number2)
        print(f"  冻结记录数: {len(freezes)}")
        for f in freezes:
            print(f"    - {f.freeze_number}: 类型={f.freeze_type}, 状态={f.status}")
            print(f"      原因: {f.reason}")

        print("\n9. 测试冻结后提交单据（应该被拒绝）")
        print("-" * 40)
        try:
            submission = schemas.SubmissionSubmit(
                lc_number=lc_number2,
                submission_id="TEST-SUB-001",
                presentation_date=today,
                documents=[
                    schemas.DocumentSubmit(
                        lc_number=lc_number2,
                        submission_id="TEST-SUB-001",
                        document_type="invoice",
                        original_copies_submitted=2,
                        copy_copies_submitted=1,
                        content={"invoice_number": "INV-001", "total_amount": 50000}
                    )
                ]
            )
            crud.submit_documents_and_audit(db, submission)
            print("  ✗ 错误: 提交成功了，应该被拒绝")
        except ValueError as e:
            print(f"  ✓ 提交被正确拒绝: {e}")

        print("\n10. 测试解除冻结")
        print("-" * 40)
        if freezes:
            freeze = freezes[0]
            released = crud.release_freeze(
                db, freeze.freeze_number,
                "管理员", "特殊情况解除冻结"
            )
            print(f"  ✓ 冻结已解除: {released.freeze_number}")
            print(f"    状态: {released.status}")
            print(f"    解除人: {released.released_by}")
            print(f"    解除原因: {released.release_reason}")

        print("\n11. 测试所有活跃冻结")
        print("-" * 40)
        active_freezes = crud.get_all_active_freezes(db)
        print(f"  当前活跃冻结数: {len(active_freezes)}")

        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_alert_module()
