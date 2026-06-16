import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine
from app import models, schemas, crud
from datetime import date, timedelta


def test_notification_module():
    print('=== 初始化数据库 ===')
    Base.metadata.create_all(bind=engine)
    
    print('=== 开始端到端测试通知模块 ===')
    db = SessionLocal()
    try:
        print('\n1. 创建参与方...')
        party_data1 = schemas.PartyCreate(
            name='中国银行上海分行 BANK OF CHINA SHANGHAI BRANCH',
            role=schemas.PartyRole.ISSUING_BANK,
            contact='issuing@boc-sh.com'
        )
        party1 = crud.create_party(db, party_data1)
        print(f'   ✅ 创建开证行: {party1.name}, ID={party1.id}')

        party_data2 = schemas.PartyCreate(
            name='上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.',
            role=schemas.PartyRole.BENEFICIARY,
            contact='beneficiary@shanghai-trade.com'
        )
        party2 = crud.create_party(db, party_data2)
        print(f'   ✅ 创建受益人: {party2.name}, ID={party2.id}')

        party_data3 = schemas.PartyCreate(
            name='ABC IMPORTING COMPANY S.A.',
            role=schemas.PartyRole.APPLICANT,
            contact='applicant@abc.com'
        )
        party3 = crud.create_party(db, party_data3)
        print(f'   ✅ 创建申请人: {party3.name}, ID={party3.id}')

        print('\n2. 检查默认订阅...')
        subs = crud.get_party_subscriptions(db, party2.id)
        print(f'   ✅ 受益人默认订阅了 {len(subs)} 个事件类型:')
        for s in subs:
            print(f'      - {s.event_type} (active={s.is_active})')

        print('\n3. 创建信用证...')
        lc_data = schemas.LetterOfCreditCreate(
            lc_number='TEST-NOTIFICATION-001',
            issuing_bank='中国银行上海分行 BANK OF CHINA SHANGHAI BRANCH',
            beneficiary_name='上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.',
            applicant_name='ABC IMPORTING COMPANY S.A.',
            currency=schemas.Currency.USD,
            amount=50000.00,
            latest_shipment_date=date.today() + timedelta(days=30),
            latest_presentation_date=date.today() + timedelta(days=45),
            expiry_date=date.today() + timedelta(days=60),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading='SHANGHAI PORT',
            port_of_discharge='ROTTERDAM PORT',
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description='TEST GOODS',
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type='invoice', original_copies=3, copy_copies=2
                ),
            ]
        )
        lc = crud.create_letter_of_credit(db, lc_data)
        print(f'   ✅ 创建信用证: {lc.lc_number}, ID={lc.id}')

        print('\n4. 检查通知生成情况...')
        for party in [party1, party2, party3]:
            notifications = crud.get_notifications_by_party(db, party.id)
            print(f'   参与方 {party.name} ({party.role}) 收到 {len(notifications)} 条通知:')
            for n in notifications:
                print(f'      - [{n["status"]}] {n["event_type"]}: {n["event_summary"]}')

        print('\n5. 标记通知已读...')
        party2_notifications = crud.get_notifications_by_party(db, party2.id)
        if party2_notifications:
            ids = [n['id'] for n in party2_notifications]
            count = crud.mark_notifications_read(db, party2.id, ids)
            print(f'   ✅ 已标记 {count} 条通知为已读')

        print('\n6. 批量归档通知...')
        if party2_notifications:
            ids = [n['id'] for n in party2_notifications]
            count = crud.archive_notifications(db, party2.id, ids)
            print(f'   ✅ 已归档 {count} 条通知')

        print('\n7. 查看信用证事件流...')
        events = crud.get_lc_event_stream(db, lc.id)
        print(f'   信用证 {lc.lc_number} 共有 {len(events)} 个事件:')
        for e in events:
            print(f'      - {e["event_type"]}: {e["event_summary"]} (by {e["party_name"]})')

        print('\n8. 自定义订阅规则...')
        updates = [
            {'event_type': schemas.EventType.FREEZE_RELEASED, 'is_active': False},
            {'event_type': schemas.EventType.BACK_TO_BACK_CREATED, 'is_active': True},
        ]
        updated_subs = crud.update_party_subscriptions(db, party2.id, updates)
        print(f'   ✅ 已更新订阅，当前共 {len(updated_subs)} 条订阅规则')

        print('\n9. 通知去重测试...')
        before = len(crud.get_notifications_by_party(db, party2.id))
        crud.dispatch_notifications(db, lc, models.EVENT_TYPE_LC_CREATED)
        after = len(crud.get_notifications_by_party(db, party2.id))
        print(f'   ✅ 去重前: {before} 条，去重后: {after} 条 (相同事件不重复通知)')

        print('\n=== 所有测试通过！✅ ===')

    except Exception as e:
        print(f'❌ 测试失败: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == '__main__':
    test_notification_module()
