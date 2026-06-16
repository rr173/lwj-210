import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def test_rule_version_module():
    print("=" * 60)
    print("审核规则版本管理与灰度发布模块测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        print("\n" + "-" * 40)
        print("测试1: 创建规则版本")
        print("-" * 40)

        rv_data = schemas.RuleVersionCreate(
            version_number="v1.0",
            rules=schemas.RuleContent(
                amount_tolerance=0.01,
                date_tolerance_days=0,
                name_case_sensitive=False,
                enabled_categories=["completeness", "amount", "date", "party", "goods", "transport", "special"],
                severity_overrides={}
            ),
            description="初始版本"
        )
        rv1 = crud.create_rule_version(db, rv_data)
        assert rv1.version_number == "v1.0", f"版本号应为 v1.0，实际为 {rv1.version_number}"
        assert rv1.status == "draft", f"新建版本状态应为 draft，实际为 {rv1.status}"
        assert rv1.grayscale_percentage == 0, f"新建版本灰度比例应为 0，实际为 {rv1.grayscale_percentage}"
        print(f"[✓] 创建规则版本成功: {rv1.version_number}, 状态: {rv1.status}")

        print("\n" + "-" * 40)
        print("测试2: 版本号唯一性校验")
        print("-" * 40)

        try:
            dup_data = schemas.RuleVersionCreate(
                version_number="v1.0",
                rules=schemas.RuleContent()
            )
            crud.create_rule_version(db, dup_data)
            print("[✗] 应该拒绝重复版本号")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了重复版本号: {str(e)}")

        print("\n" + "-" * 40)
        print("测试3: 编辑 draft 版本的规则内容")
        print("-" * 40)

        update_data = schemas.RuleVersionUpdate(
            rules=schemas.RuleContent(
                amount_tolerance=0.05,
                date_tolerance_days=1,
                name_case_sensitive=True,
                enabled_categories=["completeness", "amount", "date", "party"],
                severity_overrides={
                    "amount": {"invoice_exceeds_lc": "minor"}
                }
            ),
            description="放宽金额容差，新增日期容差"
        )
        updated = crud.update_rule_version(db, "v1.0", update_data)
        assert updated.rules["amount_tolerance"] == 0.05, f"金额容差应为 0.05"
        assert updated.rules["date_tolerance_days"] == 1, f"日期容差应为 1"
        assert updated.rules["name_case_sensitive"] == True, f"名称比对应区分大小写"
        assert "transport" not in updated.rules["enabled_categories"], f"transport 类别应已被禁用"
        assert updated.rules["severity_overrides"]["amount"]["invoice_exceeds_lc"] == "minor"
        print(f"[✓] 编辑 draft 版本成功")
        print(f"    金额容差: {updated.rules['amount_tolerance']}")
        print(f"    日期容差: {updated.rules['date_tolerance_days']}")
        print(f"    区分大小写: {updated.rules['name_case_sensitive']}")
        print(f"    启用类别: {updated.rules['enabled_categories']}")
        print(f"    严重等级覆盖: {updated.rules['severity_overrides']}")

        print("\n" + "-" * 40)
        print("测试4: 非 draft 状态不允许编辑")
        print("-" * 40)

        crud.publish_rule_version_to_testing(db, "v1.0", grayscale_percentage=30)
        try:
            crud.update_rule_version(db, "v1.0", schemas.RuleVersionUpdate(
                description="尝试修改testing版本"
            ))
            print("[✗] 应该拒绝编辑 testing 状态的版本")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了编辑 testing 版本: {str(e)}")

        crud.revert_testing_to_draft(db, "v1.0")

        print("\n" + "-" * 40)
        print("测试5: 发布灰度测试")
        print("-" * 40)

        rv_testing = crud.publish_rule_version_to_testing(db, "v1.0", grayscale_percentage=30)
        assert rv_testing.status == "testing", f"状态应为 testing，实际为 {rv_testing.status}"
        assert rv_testing.grayscale_percentage == 30, f"灰度比例应为 30，实际为 {rv_testing.grayscale_percentage}"
        print(f"[✓] 发布灰度测试成功")
        print(f"    状态: {rv_testing.status}")
        print(f"    灰度比例: {rv_testing.grayscale_percentage}%")

        print("\n" + "-" * 40)
        print("测试6: 同一时间只能有一个 testing 版本")
        print("-" * 40)

        rv2_data = schemas.RuleVersionCreate(
            version_number="v2.0",
            rules=schemas.RuleContent(
                amount_tolerance=0.10,
                date_tolerance_days=2
            ),
            description="第二版"
        )
        crud.create_rule_version(db, rv2_data)
        try:
            crud.publish_rule_version_to_testing(db, "v2.0", grayscale_percentage=50)
            print("[✗] 应该拒绝第二个 testing 版本")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了第二个 testing 版本: {str(e)}")

        print("\n" + "-" * 40)
        print("测试7: testing 回退为 draft")
        print("-" * 40)

        reverted = crud.revert_testing_to_draft(db, "v1.0")
        assert reverted.status == "draft", f"回退后状态应为 draft，实际为 {reverted.status}"
        assert reverted.grayscale_percentage == 0, f"回退后灰度比例应为 0"
        print(f"[✓] testing 回退 draft 成功")

        print("\n" + "-" * 40)
        print("测试8: 发布为 active（原 active 自动归档）")
        print("-" * 40)

        crud.publish_rule_version_to_testing(db, "v1.0", grayscale_percentage=50)
        rv_active = crud.publish_rule_version_to_active(db, "v1.0")
        assert rv_active.status == "active", f"状态应为 active，实际为 {rv_active.status}"
        assert rv_active.grayscale_percentage == 100, f"active 版本灰度应为 100"
        assert rv_active.activated_at is not None, f"激活时间不应为空"
        print(f"[✓] 发布为 active 成功")
        print(f"    状态: {rv_active.status}")
        print(f"    激活时间: {rv_active.activated_at}")

        rv2_updated = crud.update_rule_version(db, "v2.0", schemas.RuleVersionUpdate(
            rules=schemas.RuleContent(
                amount_tolerance=0.10,
                date_tolerance_days=2,
                enabled_categories=["completeness", "amount", "date", "party", "goods", "transport", "special"],
                severity_overrides={"date": {"presentation_after_latest": "minor"}}
            )
        ))
        crud.publish_rule_version_to_testing(db, "v2.0", grayscale_percentage=30)
        rv2_active = crud.publish_rule_version_to_active(db, "v2.0")
        assert rv2_active.status == "active", f"v2.0 应为 active"

        rv1_refreshed = crud.get_rule_version_by_number(db, "v1.0")
        assert rv1_refreshed.status == "archived", f"v1.0 应自动归档为 archived，实际为 {rv1_refreshed.status}"
        assert rv1_refreshed.archived_at is not None, f"归档时间不应为空"
        print(f"[✓] 原 active 版本自动归档")
        print(f"    v1.0 状态: {rv1_refreshed.status}")
        print(f"    v2.0 状态: {rv2_active.status}")

        print("\n" + "-" * 40)
        print("测试9: 版本对比")
        print("-" * 40)

        diff = crud.compare_rule_versions(db, "v1.0", "v2.0")
        assert diff["version_a"] == "v1.0"
        assert diff["version_b"] == "v2.0"
        diff_fields = [d["field"] for d in diff["differences"]]
        print(f"[✓] 版本对比成功")
        print(f"    差异字段: {diff_fields}")
        for d in diff["differences"]:
            print(f"    - {d['field']}: 旧值={d['old_value']}, 新值={d['new_value']}")

        assert "amount_tolerance" in diff_fields, "金额容差应有差异"
        assert "date_tolerance_days" in diff_fields, "日期容差应有差异"
        assert "name_case_sensitive" in diff_fields, "区分大小写应有差异"

        print("\n" + "-" * 40)
        print("测试10: 审核时灰度分配与规则版本记录")
        print("-" * 40)

        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"测试信用证 {lc_number} 不存在"

        active_rv = crud.get_rule_version_by_number(db, "v2.0")
        assert active_rv.status == "active"

        rv3_data = schemas.RuleVersionCreate(
            version_number="v3.0",
            rules=schemas.RuleContent(
                amount_tolerance=0.50,
                date_tolerance_days=5,
                name_case_sensitive=False,
                enabled_categories=["completeness", "amount"],
                severity_overrides={"completeness": {"missing_document": "minor"}}
            ),
            description="灰度测试版本-大幅放宽规则"
        )
        rv3 = crud.create_rule_version(db, rv3_data)
        rv3_testing = crud.publish_rule_version_to_testing(db, "v3.0", grayscale_percentage=100)

        submission_data = schemas.SubmissionSubmit(
            lc_number=lc_number,
            submission_id="SUB-RV-TEST-001",
            presentation_date=date(2024, 3, 1),
            documents=[
                schemas.DocumentSubmit(
                    lc_number=lc_number,
                    submission_id="SUB-RV-TEST-001",
                    document_type="invoice",
                    original_copies_submitted=1,
                    copy_copies_submitted=1,
                    content={
                        "total_amount": 50000.00,
                        "currency": "USD",
                        "invoice_date": "2024-03-01",
                        "beneficiary": lc.beneficiary_name,
                        "applicant": lc.applicant_name,
                        "goods_description": lc.goods_description
                    }
                ),
                schemas.DocumentSubmit(
                    lc_number=lc_number,
                    submission_id="SUB-RV-TEST-001",
                    document_type="bill_of_lading",
                    original_copies_submitted=1,
                    copy_copies_submitted=1,
                    content={
                        "shipment_date": "2024-03-01",
                        "port_of_loading": lc.port_of_loading,
                        "port_of_discharge": lc.port_of_discharge,
                        "shipper": lc.beneficiary_name,
                        "consignee": "TO ORDER",
                        "freight_term": "FREIGHT PREPAID",
                        "clean": True
                    }
                )
            ]
        )

        audit_record = crud.submit_documents_and_audit(db, submission_data)
        assert audit_record.rule_version_id is not None, "审核记录应标记规则版本"
        rule_version_used = crud.get_rule_version_by_id(db, audit_record.rule_version_id)
        assert rule_version_used is not None
        print(f"[✓] 审核记录标记了规则版本")
        print(f"    使用的规则版本: {rule_version_used.version_number}")
        print(f"    审核结论: {audit_record.conclusion}")
        print(f"    不符点数量: {audit_record.total_discrepancies}")

        crud.revert_testing_to_draft(db, "v3.0")

        print("\n" + "-" * 40)
        print("测试11: 按版本号查询交单列表")
        print("-" * 40)

        result = crud.get_submissions_by_rule_version(db, "v2.0")
        assert "rule_version_number" in result
        assert "total_count" in result
        assert "submissions" in result
        print(f"[✓] 查询版本 v2.0 审核的交单列表")
        print(f"    交单数量: {result['total_count']}")

        print("\n" + "-" * 40)
        print("测试12: 查询所有版本列表（按状态过滤）")
        print("-" * 40)

        all_versions = crud.get_all_rule_versions(db)
        print(f"    全部版本数: {len(all_versions)}")

        active_versions = crud.get_all_rule_versions(db, status="active")
        assert len(active_versions) == 1, f"应只有1个 active 版本，实际有 {len(active_versions)}"
        print(f"    active 版本数: {len(active_versions)}")

        archived_versions = crud.get_all_rule_versions(db, status="archived")
        assert len(archived_versions) >= 1, f"应至少有1个 archived 版本"
        print(f"    archived 版本数: {len(archived_versions)}")

        draft_versions = crud.get_all_rule_versions(db, status="draft")
        print(f"    draft 版本数: {len(draft_versions)}")

        print("\n" + "-" * 40)
        print("测试13: 无效检查类别校验")
        print("-" * 40)

        try:
            bad_data = schemas.RuleVersionCreate(
                version_number="v-bad",
                rules=schemas.RuleContent(
                    enabled_categories=["completeness", "invalid_category"]
                )
            )
            crud.create_rule_version(db, bad_data)
            print("[✗] 应该拒绝无效的检查类别")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了无效检查类别: {str(e)}")

        print("\n" + "-" * 40)
        print("测试14: 规则版本影响审核结果（启用/禁用类别）")
        print("-" * 40)

        rv_restrict_data = schemas.RuleVersionCreate(
            version_number="v-restrict",
            rules=schemas.RuleContent(
                amount_tolerance=0.01,
                date_tolerance_days=0,
                name_case_sensitive=False,
                enabled_categories=["completeness"],
                severity_overrides={}
            ),
            description="仅启用完整性检查"
        )
        rv_restrict = crud.create_rule_version(db, rv_restrict_data)

        from app.audit_engine import AuditEngine
        documents = crud.get_documents_by_submission(db, audit_record.submission_id)
        engine_default = AuditEngine(lc, documents, date(2024, 3, 1))
        _, discs_default = engine_default.run_audit()

        engine_restrict = AuditEngine(lc, documents, date(2024, 3, 1), rule_version=rv_restrict)
        _, discs_restrict = engine_restrict.run_audit()

        assert len(discs_restrict) <= len(discs_default), "仅启用 completeness 时，不符点数应不多于启用全部类别"
        restrict_types = set(d["discrepancy_type"] for d in discs_restrict)
        assert all(t == "completeness" for t in restrict_types), f"仅应含 completeness 类型不符点，实际含: {restrict_types}"

        print(f"[✓] 启用/禁用类别正确影响审核结果")
        print(f"    全部类别启用时不符点数: {len(discs_default)}")
        print(f"    仅 completeness 启用时不符点数: {len(discs_restrict)}")
        print(f"    仅 completeness 启用时不符点类型: {restrict_types}")

        print("\n" + "-" * 40)
        print("测试15: 严重等级覆盖规则生效")
        print("-" * 40)

        rv_override_data = schemas.RuleVersionCreate(
            version_number="v-override",
            rules=schemas.RuleContent(
                amount_tolerance=0.01,
                date_tolerance_days=0,
                name_case_sensitive=False,
                enabled_categories=["completeness", "amount", "date", "party", "goods", "transport", "special"],
                severity_overrides={
                    "amount": {"invoice_exceeds_lc": "minor"},
                    "completeness": {"missing_document": "minor"}
                }
            ),
            description="将金额超限和缺少单据降为 minor"
        )
        rv_override = crud.create_rule_version(db, rv_override_data)

        engine_override = AuditEngine(lc, documents, date(2024, 3, 1), rule_version=rv_override)
        _, discs_override = engine_override.run_audit()

        amount_discs_override = [d for d in discs_override if d["discrepancy_type"] == "amount"]
        for d in amount_discs_override:
            if "超过信用证金额" in d["description"]:
                assert d["severity"] == "minor", f"金额超限应为 minor（被覆盖），实际为 {d['severity']}"

        print(f"[✓] 严重等级覆盖规则正确生效")

        print("\n" + "-" * 40)
        print("测试16: 无规则版本时使用默认规则")
        print("-" * 40)

        engine_no_version = AuditEngine(lc, documents, date(2024, 3, 1), rule_version=None)
        assert engine_no_version.amount_tolerance == 0.01
        assert engine_no_version.date_tolerance_days == 0
        assert engine_no_version.name_case_sensitive == False
        assert len(engine_no_version.enabled_categories) == 7
        print(f"[✓] 无规则版本时使用默认规则")

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
    test_rule_version_module()
