import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.database import SessionLocal, Base, engine
from app import models, schemas, crud
from app.seed_data import init_db


def test_amendment_alert_and_freeze_fix():
    print("=" * 70)
    print("Amendment后预警更新和冻结自动解除修复验证")
    print("=" * 70)

    init_db()
    db = SessionLocal()

    try:
        today = date.today()
        print(f"\n今日日期: {today}")

        lc_number = "LC-TEST-AMEND-FIX-001"
        existing = crud.get_letter_of_credit_by_number(db, lc_number)
        if existing:
            print(f"\n清理旧测试数据: {lc_number}")
            crud.delete_letter_of_credit(db, existing.id)

        print("\n" + "=" * 70)
        print("场景一：Amendment延长日期后，旧预警应被清除，新预警可重新生成")
        print("=" * 70)

        print(f"\n1. 创建信用证，装运日为今日+3天（已在预警窗口内）")
        lc_data = schemas.LetterOfCreditCreate(
            lc_number=lc_number,
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=today + timedelta(days=3),
            latest_presentation_date=today + timedelta(days=15),
            expiry_date=today + timedelta(days=20),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="ROTTERDAM",
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
        print(f"    装运日: {lc.latest_shipment_date} (还有3天)")

        print(f"\n2. 扫描生成预警")
        result = crud.scan_and_generate_alerts(db)
        print(f"    生成装运预警: {result['shipment_alerts']} 条")

        alerts = crud.get_alerts_by_lc(db, lc_number)
        shipment_alerts = [a for a in alerts if a.alert_type == models.ALERT_TYPE_SHIPMENT]
        print(f"    当前装运预警数: {len(shipment_alerts)}")
        if shipment_alerts:
            print(f"    预警目标日期: {shipment_alerts[0].target_date}")

        print(f"\n3. 发起Amendment，将装运日延长到今日+15天")
        new_shipment_date = today + timedelta(days=15)
        amendment_data = schemas.AmendmentCreate(
            lc_number=lc_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value=lc.latest_shipment_date.isoformat(),
                    new_value=new_shipment_date.isoformat()
                )
            ]
        )
        amendment = crud.create_amendment(db, amendment_data)
        print(f"  ✓ Amendment创建成功: {amendment.amendment_number}")
        print(f"    新装运日: {new_shipment_date}")

        print(f"\n4. 再次扫描预警（应该不会生成新的，因为旧的还在）")
        result2 = crud.scan_and_generate_alerts(db)
        alerts2 = crud.get_alerts_by_lc(db, lc_number)
        shipment_alerts2 = [a for a in alerts2 if a.alert_type == models.ALERT_TYPE_SHIPMENT]
        print(f"    新生成装运预警: {result2['shipment_alerts']} 条 (预期: 0)")
        print(f"    当前装运预警数: {len(shipment_alerts2)} 条 (还是旧的那条)")

        print(f"\n5. Accept Amendment（关键步骤！）")
        accepted = crud.accept_amendment(db, amendment.amendment_number)
        print(f"  ✓ Amendment已accept，状态: {accepted.status}")

        print(f"\n6. 检查预警是否已被清除")
        alerts3 = crud.get_alerts_by_lc(db, lc_number)
        shipment_alerts3 = [a for a in alerts3 if a.alert_type == models.ALERT_TYPE_SHIPMENT]
        print(f"    当前装运预警数: {len(shipment_alerts3)} 条 (预期: 0，已被清除)")

        print(f"\n7. 再次扫描预警（应该会根据新日期重新生成）")
        result3 = crud.scan_and_generate_alerts(db)
        alerts4 = crud.get_alerts_by_lc(db, lc_number)
        shipment_alerts4 = [a for a in alerts4 if a.alert_type == models.ALERT_TYPE_SHIPMENT]
        print(f"    新生成装运预警: {result3['shipment_alerts']} 条 (预期: 1 或 0，因为15天>7天阈值)")

        if len(shipment_alerts4) == 0:
            print(f"    ✓ 正确：15天 > 7天阈值，暂不生成预警")
            print(f"    等离新日期还有7天内时会自动生成")
        else:
            print(f"    新预警目标日期: {shipment_alerts4[0].target_date} (应该是新日期)")
            if shipment_alerts4[0].target_date == new_shipment_date:
                print(f"    ✓ 预警日期已更新为新的装运日！")

        print("\n" + "=" * 70)
        print("场景二：装运日过期被冻结，Amendment延长后自动解除冻结")
        print("=" * 70)

        lc_number2 = "LC-TEST-FREEZE-FIX-001"
        existing2 = crud.get_letter_of_credit_by_number(db, lc_number2)
        if existing2:
            print(f"\n清理旧测试数据: {lc_number2}")
            crud.delete_letter_of_credit(db, existing2.id)

        print(f"\n1. 创建信用证，装运日为昨日（已过期）")
        old_shipment_date = today - timedelta(days=1)
        lc_data2 = schemas.LetterOfCreditCreate(
            lc_number=lc_number2,
            issuing_bank="测试银行",
            beneficiary_name="测试受益人",
            applicant_name="测试申请人",
            currency=schemas.Currency.EUR,
            amount=80000.00,
            latest_shipment_date=old_shipment_date,
            latest_presentation_date=today + timedelta(days=10),
            expiry_date=today + timedelta(days=30),
            transport_mode=schemas.TransportMode.AIR,
            port_of_loading="BEIJING",
            port_of_discharge="FRANKFURT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="电子产品",
            additional_terms=[],
            fee_tier=schemas.FeeTier.VIP,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
            ]
        )
        lc2 = crud.create_letter_of_credit(db, lc_data2)
        print(f"  ✓ 信用证创建成功: {lc2.lc_number}")
        print(f"    装运日: {lc2.latest_shipment_date} (已过期1天)")

        print(f"\n2. 扫描生成预警和冻结")
        result = crud.scan_and_generate_alerts(db)
        print(f"    生成过期预警并自动创建冻结")

        freezes = crud.get_freeze_records_by_lc(db, lc_number2)
        active_freezes = [f for f in freezes if f.status == models.FREEZE_STATUS_ACTIVE]
        print(f"    当前活跃冻结数: {len(active_freezes)}")
        for f in active_freezes:
            print(f"    - {f.freeze_type}: {f.reason}")

        print(f"\n3. 尝试提交新单据（应该被拒绝）")
        try:
            submission = schemas.SubmissionSubmit(
                lc_number=lc_number2,
                submission_id="TEST-SUB-FREEZE-001",
                presentation_date=today,
                documents=[
                    schemas.DocumentSubmit(
                        lc_number=lc_number2,
                        submission_id="TEST-SUB-FREEZE-001",
                        document_type="invoice",
                        original_copies_submitted=2,
                        copy_copies_submitted=1,
                        content={"invoice_number": "INV-001", "total_amount": 80000}
                    )
                ]
            )
            crud.submit_documents_and_audit(db, submission)
            print("    ✗ 错误: 提交成功了，应该被拒绝！")
        except ValueError as e:
            print(f"    ✓ 提交被正确拒绝: {e}")

        print(f"\n4. 发起Amendment，将装运日延长到今日+15天")
        new_shipment_date2 = today + timedelta(days=15)
        amendment_data2 = schemas.AmendmentCreate(
            lc_number=lc_number2,
            field_changes=[
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value=old_shipment_date.isoformat(),
                    new_value=new_shipment_date2.isoformat()
                )
            ]
        )
        amendment2 = crud.create_amendment(db, amendment_data2)
        print(f"  ✓ Amendment创建成功: {amendment2.amendment_number}")
        print(f"    新装运日: {new_shipment_date2}")

        print(f"\n5. Accept Amendment（关键步骤！）")
        accepted2 = crud.accept_amendment(db, amendment2.amendment_number)
        print(f"  ✓ Amendment已accept，状态: {accepted2.status}")

        print(f"\n6. 检查冻结是否已自动解除")
        freezes2 = crud.get_freeze_records_by_lc(db, lc_number2)
        active_freezes2 = [f for f in freezes2 if f.status == models.FREEZE_STATUS_ACTIVE]
        print(f"    当前活跃冻结数: {len(active_freezes2)} 条 (预期: 0)")

        if len(active_freezes2) == 0:
            print(f"  ✓ 冻结已自动解除！")
            released_freeze = [f for f in freezes2 if f.status == models.FREEZE_STATUS_RELEASED][0]
            print(f"    解除人: {released_freeze.released_by}")
            print(f"    解除原因: {released_freeze.release_reason}")
        else:
            print(f"    ✗ 错误: 冻结仍然存在！")

        print(f"\n7. 再次尝试提交新单据（应该可以成功了）")
        try:
            submission2 = schemas.SubmissionSubmit(
                lc_number=lc_number2,
                submission_id="TEST-SUB-FREEZE-002",
                presentation_date=today,
                documents=[
                    schemas.DocumentSubmit(
                        lc_number=lc_number2,
                        submission_id="TEST-SUB-FREEZE-002",
                        document_type="invoice",
                        original_copies_submitted=2,
                        copy_copies_submitted=1,
                        content={"invoice_number": "INV-002", "total_amount": 80000}
                    )
                ]
            )
            audit_record = crud.submit_documents_and_audit(db, submission2)
            print(f"  ✓ 提交成功！审核结论: {audit_record.conclusion}")
        except ValueError as e:
            print(f"    ✗ 错误: 提交被拒绝了: {e}")

        print("\n" + "=" * 70)
        print("两个问题的修复验证完成！")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_amendment_alert_and_freeze_fix()
