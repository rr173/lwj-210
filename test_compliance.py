import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def _create_test_lc(db, lc_number="LC-COMPLIANCE-TEST-001", applicant_name="ABC IMPORTS CO.", beneficiary_name="上海贸易有限公司"):
    existing = crud.get_letter_of_credit_by_number(db, lc_number)
    if existing:
        crud.delete_letter_of_credit(db, existing.id)
    lc_data = schemas.LetterOfCreditCreate(
        lc_number=lc_number,
        issuing_bank="中国银行上海分行",
        beneficiary_name=beneficiary_name,
        applicant_name=applicant_name,
        currency=schemas.Currency.USD,
        amount=50000.00,
        latest_shipment_date=date(2024, 6, 30),
        latest_presentation_date=date(2024, 7, 15),
        expiry_date=date(2024, 7, 20),
        transport_mode=schemas.TransportMode.SEA,
        port_of_loading="SHANGHAI PORT",
        port_of_discharge="ROTTERDAM PORT",
        partial_shipment_allowed=False,
        transshipment_allowed=False,
        goods_description="100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
        additional_terms=[],
        fee_tier=schemas.FeeTier.STANDARD,
        payment_method=schemas.PaymentMethod.SIGHT,
        document_requirements=[
            schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
            schemas.DocumentRequirementCreate(document_type="packing_list", original_copies=2, copy_copies=2),
        ],
    )
    return crud.create_letter_of_credit(db, lc_data)


def test_blacklist_crud():
    print("\n=== 测试黑名单CRUD ===")
    db = SessionLocal()
    try:
        entry_data = schemas.BlacklistEntryCreate(
            name="ABC Corp",
            name_aliases=["ABC Corporation", "ABC Group"],
            blacklist_type=schemas.BlacklistType.SANCTIONS,
            source_organization="OFAC",
            effective_date=date(2024, 1, 1),
            expiry_date=None,
            is_active=True,
            remarks="制裁名单",
        )

        entry = crud.create_blacklist_entry(db, entry_data)
        print(f"✓ 创建黑名单: {entry.blacklist_number} - {entry.name}")

        fetched = crud.get_blacklist_entry_by_number(db, entry.blacklist_number)
        assert fetched is not None
        assert fetched.name == "ABC Corp"
        assert fetched.blacklist_type == "sanctions"
        print(f"✓ 查询黑名单: {fetched.name}")

        update_data = schemas.BlacklistEntryUpdate(
            name="ABC Corp Updated",
            name_aliases=["ABC Corporation", "ABC Group", "ABC Inc"],
            blacklist_type=schemas.BlacklistType.PEP,
            source_organization="OFAC Updated",
            effective_date=date(2024, 2, 1),
            expiry_date=date(2025, 12, 31),
            is_active=False,
            remarks="更新备注",
        )
        updated = crud.update_blacklist_entry(db, entry.blacklist_number, update_data)
        assert updated.name == "ABC Corp Updated"
        assert updated.blacklist_type == "pep"
        assert updated.is_active is False
        print(f"✓ 更新黑名单: {updated.name}")

        entries = crud.list_blacklist_entries(db, blacklist_type=schemas.BlacklistType.PEP)
        assert len(entries) >= 1
        print(f"✓ 查询黑名单列表，筛选PEP类型: {len(entries)} 条")

        crud.delete_blacklist_entry(db, entry.blacklist_number)
        deleted = crud.get_blacklist_entry_by_number(db, entry.blacklist_number)
        assert deleted is None
        print(f"✓ 删除黑名单成功")

        print("✓ 黑名单CRUD测试通过")
    finally:
        db.close()


def test_blacklist_batch_import():
    print("\n=== 测试黑名单批量导入 ===")
    db = SessionLocal()
    try:
        import_req = schemas.BlacklistBatchImportRequest(
            entries=[
                schemas.BlacklistBatchImportItem(
                    name="Bad Company 1",
                    name_aliases=["BC1"],
                    blacklist_type=schemas.BlacklistType.SANCTIONS,
                    source_organization="OFAC",
                    effective_date=date(2024, 1, 1),
                ),
                schemas.BlacklistBatchImportItem(
                    name="Bad Company 2",
                    name_aliases=["BC2"],
                    blacklist_type=schemas.BlacklistType.ADVERSE_MEDIA,
                    source_organization="UN",
                    effective_date=date(2024, 1, 1),
                    expiry_date=date(2024, 12, 31),
                ),
                schemas.BlacklistBatchImportItem(
                    name="",
                    name_aliases=[],
                    blacklist_type=schemas.BlacklistType.SANCTIONS,
                    source_organization="",
                    effective_date=date(2024, 1, 1),
                ),
            ]
        )

        result = crud.batch_import_blacklist(db, import_req)
        print(f"✓ 批量导入结果: 成功={result['success_count']}, 失败={result['failed_count']}")
        assert result["success_count"] == 2
        assert result["failed_count"] == 1
        assert len(result["success_numbers"]) == 2
        assert len(result["failures"]) == 1
        print(f"✓ 成功编号: {result['success_numbers']}")
        print(f"✓ 失败原因: {result['failures'][0]['error']}")

        print("✓ 黑名单批量导入测试通过")
    finally:
        db.close()


def test_fuzzy_matching():
    print("\n=== 测试模糊匹配 ===")
    db = SessionLocal()
    try:
        entry = crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="ABC Corp",
                name_aliases=["ABC Group"],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(2024, 1, 1),
            ),
        )

        test_cases = [
            ("ABC Corp", True, "exact_name_match"),
            ("ABC Corp International", True, "exact_name_match"),
            ("The ABC Corp", True, "exact_name_match"),
            ("abc corp", True, "exact_name_match"),
            ("ABC Group", True, "alias_match"),
            ("ABC Group Ltd", True, "alias_match"),
            ("XYZ Corp", False, None),
            ("AB Corp", False, None),
        ]

        for party_name, should_hit, expected_match_type in test_cases:
            result = crud.screen_party_against_blacklist(
                db,
                party_name=party_name,
                party_role="applicant",
                screening_scene=models.SCREENING_SCENE_LC_CREATION,
            )
            if should_hit:
                assert result["screening_result"] == models.SCREENING_RESULT_HIT
                actual_match_type = result["hit_details"][0]["match_type"]
                assert actual_match_type == expected_match_type, f"期望匹配类型 '{expected_match_type}', 实际 '{actual_match_type}', 详情: {result['hit_details'][0]}"
                print(f"  ✓ '{party_name}' 命中 (匹配类型: {expected_match_type})")
            else:
                assert result["screening_result"] == models.SCREENING_RESULT_CLEAR
                print(f"  ✓ '{party_name}' 未命中")

        print("✓ 模糊匹配测试通过")
    finally:
        db.close()


def test_lc_creation_screening():
    print("\n=== 测试创建信用证时的合规筛查 ===")
    db = SessionLocal()
    try:
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Sanctioned Entity",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(2024, 1, 1),
            ),
        )

        try:
            _create_test_lc(
                db,
                lc_number="LC-COMPLIANCE-TEST-BLOCK",
                applicant_name="Sanctioned Entity International",
                beneficiary_name="正常公司",
            )
            print("  ✗ 应该拒绝创建但没有拒绝")
            assert False, "应该抛出异常"
        except ValueError as e:
            print(f"  ✓ 创建信用证被拒绝，原因: {str(e)[:80]}...")

        lc = _create_test_lc(
            db,
            lc_number="LC-COMPLIANCE-TEST-PASS",
            applicant_name="Normal Company",
            beneficiary_name="Another Normal Company",
        )
        print(f"  ✓ 创建信用证成功: {lc.lc_number}")

        screening_records = crud.get_screening_records_by_lc_number(db, lc.lc_number)
        print(f"  ✓ 生成筛查记录: {len(screening_records)} 条")
        for rec in screening_records:
            print(f"    - {rec.screening_number} | {rec.party_role} | {rec.screening_result}")
        assert len(screening_records) >= 2

        print("✓ 创建信用证合规筛查测试通过")
    finally:
        db.close()


def test_submission_screening():
    print("\n=== 测试交单时的合规筛查 ===")
    db = SessionLocal()
    try:
        lc = _create_test_lc(
            db,
            lc_number="LC-COMPLIANCE-TEST-SUBMISSION",
            applicant_name="Normal Applicant",
            beneficiary_name="Normal Beneficiary",
        )

        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Risky Exporter",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.ADVERSE_MEDIA,
                source_organization="Local News",
                effective_date=date(2024, 1, 1),
            ),
        )

        submission = schemas.SubmissionSubmit(
            lc_number=lc.lc_number,
            submission_id="SUB-COMPLIANCE-TEST-001",
            presentation_date=date(2024, 6, 10),
            documents=[
                schemas.DocumentSubmit(
                    lc_number=lc.lc_number,
                    submission_id="SUB-COMPLIANCE-TEST-001",
                    document_type="invoice",
                    original_copies_submitted=3,
                    copy_copies_submitted=2,
                    content={
                        "invoice_number": "INV-001",
                        "invoice_date": "2024-06-01",
                        "beneficiary": "Risky Exporter International",
                        "applicant": "Normal Applicant",
                        "currency": "USD",
                        "goods_description": "100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
                        "total_amount": 50000.00,
                    },
                ),
                schemas.DocumentSubmit(
                    lc_number=lc.lc_number,
                    submission_id="SUB-COMPLIANCE-TEST-001",
                    document_type="bill_of_lading",
                    original_copies_submitted=3,
                    copy_copies_submitted=3,
                    content={
                        "bl_number": "BL-001",
                        "shipper": "Risky Exporter International",
                        "consignee": "TO ORDER",
                        "notify_party": "Normal Applicant",
                        "vessel_voyage": "MAERSK V.001",
                        "port_of_loading": "SHANGHAI PORT",
                        "port_of_discharge": "ROTTERDAM PORT",
                        "shipment_date": "2024-06-05",
                        "packages": 5000,
                        "package_unit": "PCS",
                        "freight_term": "FREIGHT PREPAID",
                    },
                ),
                schemas.DocumentSubmit(
                    lc_number=lc.lc_number,
                    submission_id="SUB-COMPLIANCE-TEST-001",
                    document_type="packing_list",
                    original_copies_submitted=2,
                    copy_copies_submitted=2,
                    content={
                        "invoice_number": "INV-001",
                        "date": "2024-06-01",
                        "packages": 5000,
                        "package_unit": "PCS",
                        "goods_description": "100% COTTON MEN'S T-SHIRTS",
                    },
                ),
            ],
        )

        result = crud.submit_documents_and_audit(db, submission)
        audit_record = result["audit_record"]
        compliance_alerts = result["compliance_alerts"]

        print(f"  ✓ 交单成功，审核结论: {audit_record.conclusion}")
        print(f"  ✓ 合规告警数量: {len(compliance_alerts)}")
        assert len(compliance_alerts) == 1
        assert compliance_alerts[0]["party_name"] == "Risky Exporter International"
        assert compliance_alerts[0]["party_role"] == "invoice_beneficiary"
        print(f"  ✓ 合规告警详情: {compliance_alerts[0]['party_name']} - {compliance_alerts[0]['party_role']}")

        screening_records = crud.get_screening_records_by_lc_number(db, lc.lc_number)
        print(f"  ✓ 该信用证总筛查记录: {len(screening_records)} 条")

        print("✓ 交单合规筛查测试通过")
    finally:
        db.close()


def test_screening_record_query():
    print("\n=== 测试筛查记录查询 ===")
    db = SessionLocal()
    try:
        lc = _create_test_lc(
            db,
            lc_number="LC-COMPLIANCE-TEST-QUERY",
            applicant_name="Test Applicant",
            beneficiary_name="Test Beneficiary",
        )

        records = crud.get_screening_records_by_lc_number(db, lc.lc_number)
        assert len(records) == 2

        for record in records:
            print(f"  ✓ {record.screening_number} | {record.party_role} | {record.party_name} | {record.screening_result}")
            fetched = crud.get_screening_record_by_number(db, record.screening_number)
            assert fetched is not None
            assert fetched.screening_number == record.screening_number

        print("✓ 筛查记录查询测试通过")
    finally:
        db.close()


def test_compliance_events():
    print("\n=== 测试合规事件 ===")
    db = SessionLocal()
    try:
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Event Test Company",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(2024, 1, 1),
            ),
        )

        try:
            _create_test_lc(
                db,
                lc_number="LC-COMPLIANCE-TEST-EVENT",
                applicant_name="Event Test Company",
                beneficiary_name="Normal Company",
            )
        except ValueError:
            pass

        events = crud.list_compliance_events(db, status=schemas.ComplianceEventStatus.OPEN)
        assert len(events) >= 1
        print(f"  ✓ 查询到未处理合规事件: {len(events)} 件")

        event = events[0]
        print(f"  ✓ 合规事件: {event.event_number} | {event.party_name} | {event.blacklist_type}")

        updated = crud.update_compliance_event_status(
            db,
            event.event_number,
            schemas.ComplianceEventStatus.INVESTIGATING,
            "正在调查中",
        )
        assert updated.status == "investigating"
        print(f"  ✓ 更新事件状态为: {updated.status}")

        print("✓ 合规事件测试通过")
    finally:
        db.close()


def test_hit_statistics():
    print("\n=== 测试命中统计 ===")
    db = SessionLocal()
    try:
        current_year = date.today().year
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Stats Test Sanctions",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(current_year, 1, 1),
            ),
        )
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Stats Test PEP",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.PEP,
                source_organization="World Bank",
                effective_date=date(current_year, 1, 1),
            ),
        )

        for party_name in ["Stats Test Sanctions Co", "Stats Test PEP Ltd", "Stats Test Sanctions Inc"]:
            crud.screen_party_against_blacklist(
                db,
                party_name=party_name,
                party_role="applicant",
                screening_scene=models.SCREENING_SCENE_LC_CREATION,
            )

        stats = crud.get_blacklist_hit_statistics(
            db,
            start_date=date(current_year, 1, 1),
            end_date=date(current_year, 12, 31),
            group_by_type=True,
        )

        print(f"  ✓ 总命中次数: {stats['total_hit_count']}")
        assert stats["total_hit_count"] >= 3

        for by_type in stats["by_type"]:
            print(f"    - {by_type['blacklist_type']}: {by_type['hit_count']} 次")

        assert len(stats["by_type"]) >= 2

        print("✓ 命中统计测试通过")
    finally:
        db.close()


def test_expired_blacklist():
    print("\n=== 测试过期黑名单不参与筛查 ===")
    db = SessionLocal()
    try:
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Expired Company",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(2023, 1, 1),
                expiry_date=date(2023, 12, 31),
            ),
        )

        result = crud.screen_party_against_blacklist(
            db,
            party_name="Expired Company",
            party_role="applicant",
            screening_scene=models.SCREENING_SCENE_LC_CREATION,
        )

        assert result["screening_result"] == models.SCREENING_RESULT_CLEAR
        print(f"  ✓ 过期黑名单未命中: {result['screening_result']}")

        print("✓ 过期黑名单测试通过")
    finally:
        db.close()


def test_inactive_blacklist():
    print("\n=== 测试未激活黑名单不参与筛查 ===")
    db = SessionLocal()
    try:
        crud.create_blacklist_entry(
            db,
            schemas.BlacklistEntryCreate(
                name="Inactive Company",
                name_aliases=[],
                blacklist_type=schemas.BlacklistType.SANCTIONS,
                source_organization="OFAC",
                effective_date=date(2024, 1, 1),
                is_active=False,
            ),
        )

        result = crud.screen_party_against_blacklist(
            db,
            party_name="Inactive Company",
            party_role="applicant",
            screening_scene=models.SCREENING_SCENE_LC_CREATION,
        )

        assert result["screening_result"] == models.SCREENING_RESULT_CLEAR
        print(f"  ✓ 未激活黑名单未命中: {result['screening_result']}")

        print("✓ 未激活黑名单测试通过")
    finally:
        db.close()


def _cleanup_test_data(db):
    from sqlalchemy import text
    try:
        db.query(models.ComplianceEvent).delete()
        db.query(models.ComplianceScreeningRecord).delete()
        db.query(models.BlacklistEntry).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"清理旧数据时出错: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("信用证合规检查与黑名单筛查模块测试")
    print("=" * 60)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        init_db()
        crud.migrate_compliance_tables(db)
        _cleanup_test_data(db)
        seed_data()
    finally:
        db.close()

    try:
        test_blacklist_crud()
        test_blacklist_batch_import()
        test_fuzzy_matching()
        test_lc_creation_screening()
        test_submission_screening()
        test_screening_record_query()
        test_compliance_events()
        test_hit_statistics()
        test_expired_blacklist()
        test_inactive_blacklist()

        print("\n" + "=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
