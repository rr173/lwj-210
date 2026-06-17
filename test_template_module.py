import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def test_template_module():
    print("=" * 60)
    print("信用证单据模板与自动填充模块功能测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"
        print(f"\n[✓] 找到测试信用证: {lc_number}")

        submission_id = "SUB-LC1-20240308-COMPLIANT"
        audit_record = crud.get_audit_record_by_submission(db, submission_id)
        assert audit_record is not None, f"交单 {submission_id} 不存在"
        print(f"[✓] 找到测试交单: {submission_id}")
        print(f"    结论: {audit_record.conclusion}")

        print("\n" + "-" * 40)
        print("测试1: 从成功交单创建模板")
        print("-" * 40)

        template_name = "标准交单模板-v1"
        template = crud.create_template_from_submission(db, submission_id, template_name)
        assert template is not None, "创建模板失败"
        assert template.template_name == template_name
        assert template.lc_number == lc_number
        assert template.based_on_submission_id == submission_id
        assert len(template.documents) == 5, f"模板应包含5份单据，实际为 {len(template.documents)}"
        assert template.template_number == f"{lc_number}-TPL-001"

        print(f"[✓] 模板创建成功")
        print(f"    模板编号: {template.template_number}")
        print(f"    模板名称: {template.template_name}")
        print(f"    单据数量: {len(template.documents)}")
        for doc in template.documents:
            print(f"      - {doc['document_type']}: 正本{doc['original_copies_submitted']}份, 副本{doc['copy_copies_submitted']}份")

        print("\n" + "-" * 40)
        print("测试2: 按信用证编号查询模板列表")
        print("-" * 40)

        templates = crud.get_templates_by_lc(db, lc_number)
        assert len(templates) == 1, f"应该有1个模板，实际有 {len(templates)} 个"
        assert templates[0].template_number == template.template_number

        print(f"[✓] 查询到 {len(templates)} 个模板")
        for t in templates:
            print(f"    - {t.template_number} ({t.template_name})")

        print("\n" + "-" * 40)
        print("测试3: 查询单个模板详情")
        print("-" * 40)

        template_detail = crud.get_template_by_number(db, template.template_number)
        assert template_detail is not None, "查询模板失败"
        assert template_detail.template_name == template_name
        assert len(template_detail.documents) == 5

        print(f"[✓] 模板详情查询成功")
        print(f"    模板编号: {template_detail.template_number}")
        print(f"    基于交单: {template_detail.based_on_submission_id}")
        print(f"    创建时间: {template_detail.created_at}")

        print("\n" + "-" * 40)
        print("测试4: 模板预览 - 不覆盖任何字段")
        print("-" * 40)

        preview_result = crud.preview_template(db, template.template_number, [])
        assert preview_result["template_number"] == template.template_number
        assert len(preview_result["documents"]) == 5

        invoice_doc = next(d for d in preview_result["documents"] if d["document_type"] == "invoice")
        assert invoice_doc["content"]["invoice_number"] == "INV-2024-0308-001"
        assert invoice_doc["content"]["total_amount"] == 50000.00

        print(f"[✓] 模板预览成功")
        print(f"    单据数量: {len(preview_result['documents'])}")
        print(f"    发票号: {invoice_doc['content']['invoice_number']}")
        print(f"    发票金额: {invoice_doc['content']['total_amount']}")

        print("\n" + "-" * 40)
        print("测试5: 模板预览 - 覆盖部分字段")
        print("-" * 40)

        field_overrides = [
            schemas.TemplateFieldOverride(
                document_type="invoice",
                content_overrides={
                    "invoice_number": "INV-2024-0401-002",
                    "invoice_date": "2024-04-01",
                },
                original_copies_submitted=5,
            ),
            schemas.TemplateFieldOverride(
                document_type="bill_of_lading",
                content_overrides={
                    "bl_number": "MAEU-2024-0401-9900",
                    "shipment_date": "2024-04-01",
                },
            ),
        ]

        preview_with_overrides = crud.preview_template(db, template.template_number, field_overrides)
        assert len(preview_with_overrides["documents"]) == 5

        invoice_preview = next(d for d in preview_with_overrides["documents"] if d["document_type"] == "invoice")
        assert invoice_preview["content"]["invoice_number"] == "INV-2024-0401-002"
        assert invoice_preview["content"]["invoice_date"] == "2024-04-01"
        assert invoice_preview["content"]["total_amount"] == 50000.00
        assert invoice_preview["original_copies_submitted"] == 5

        bl_preview = next(d for d in preview_with_overrides["documents"] if d["document_type"] == "bill_of_lading")
        assert bl_preview["content"]["bl_number"] == "MAEU-2024-0401-9900"
        assert bl_preview["content"]["shipment_date"] == "2024-04-01"
        assert bl_preview["content"]["port_of_loading"] == "SHANGHAI PORT"

        print(f"[✓] 带覆盖字段的预览成功")
        print(f"    新发票号: {invoice_preview['content']['invoice_number']}")
        print(f"    新发票日期: {invoice_preview['content']['invoice_date']}")
        print(f"    发票金额(未变): {invoice_preview['content']['total_amount']}")
        print(f"    正本份数(已修改): {invoice_preview['original_copies_submitted']}")
        print(f"    新提单号: {bl_preview['content']['bl_number']}")

        print("\n" + "-" * 40)
        print("测试6: 基于模板创建新交单")
        print("-" * 40)

        new_submission_id = "SUB-LC1-20240402-FROM-TEMPLATE"
        use_request = schemas.TemplateUseRequest(
            lc_number=lc_number,
            submission_id=new_submission_id,
            presentation_date=date(2024, 4, 2),
            field_overrides=[
                schemas.TemplateFieldOverride(
                    document_type="invoice",
                    content_overrides={
                        "invoice_number": "INV-2024-0402-003",
                        "invoice_date": "2024-04-02",
                    },
                ),
                schemas.TemplateFieldOverride(
                    document_type="bill_of_lading",
                    content_overrides={
                        "bl_number": "MAEU-2024-0402-1122",
                        "shipment_date": "2024-04-02",
                    },
                ),
            ],
        )

        new_audit = crud.create_submission_from_template(db, template.template_number, use_request)
        assert new_audit is not None, "基于模板创建交单失败"
        assert new_audit.submission_id == new_submission_id
        assert new_audit.lc_id == lc.id

        new_docs = crud.get_documents_by_submission(db, new_submission_id)
        assert len(new_docs) == 5, f"新交单应包含5份单据，实际为 {len(new_docs)}"

        new_invoice = next(d for d in new_docs if d.document_type == "invoice")
        assert new_invoice.content["invoice_number"] == "INV-2024-0402-003"
        assert new_invoice.content["total_amount"] == 50000.00

        new_bl = next(d for d in new_docs if d.document_type == "bill_of_lading")
        assert new_bl.content["bl_number"] == "MAEU-2024-0402-1122"
        assert new_bl.content["shipment_date"] == "2024-04-02"

        print(f"[✓] 基于模板创建交单成功")
        print(f"    新提交编号: {new_submission_id}")
        print(f"    审核结论: {new_audit.conclusion}")
        print(f"    不符点数量: {new_audit.total_discrepancies}")
        print(f"    新发票号: {new_invoice.content['invoice_number']}")
        print(f"    新提单号: {new_bl.content['bl_number']}")

        print("\n" + "-" * 40)
        print("测试7: 同一份信用证最多保存5个模板")
        print("-" * 40)

        for i in range(4):
            try:
                name = f"测试模板-{i+2}"
                crud.create_template_from_submission(db, submission_id, name)
                print(f"    创建模板 {i+2}: {name}")
            except Exception as e:
                print(f"    创建模板 {i+2} 失败: {str(e)}")

        templates_after = crud.get_templates_by_lc(db, lc_number)
        assert len(templates_after) == 5, f"应该有5个模板，实际有 {len(templates_after)} 个"
        print(f"[✓] 成功创建5个模板，达到上限")

        try:
            crud.create_template_from_submission(db, submission_id, "第6个模板")
            print("[✗] 应该拒绝创建第6个模板，但成功了")
            assert False, "同一份信用证最多只能保存5个模板"
        except ValueError as e:
            print(f"[✓] 正确拒绝了创建第6个模板")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试8: 只有compliant或minor_discrepancy的交单才能保存为模板")
        print("-" * 40)

        discrepant_submission_id = "SUB-LC2-20240420-DISCREPANT"
        discrepant_audit = crud.get_audit_record_by_submission(db, discrepant_submission_id)
        print(f"    测试交单结论: {discrepant_audit.conclusion}")

        try:
            crud.create_template_from_submission(db, discrepant_submission_id, "不符交单模板")
            print("[✗] 应该拒绝保存不符交单为模板，但成功了")
            assert False, "只有compliant或minor_discrepancy的交单才能保存为模板"
        except ValueError as e:
            print(f"[✓] 正确拒绝了保存不符交单为模板")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试9: 删除模板")
        print("-" * 40)

        templates_before_delete = crud.get_templates_by_lc(db, lc_number)
        count_before = len(templates_before_delete)

        template_to_delete = templates_before_delete[0].template_number
        crud.delete_template(db, template_to_delete)

        templates_after_delete = crud.get_templates_by_lc(db, lc_number)
        count_after = len(templates_after_delete)

        assert count_after == count_before - 1, f"删除后应该减少1个模板"
        assert crud.get_template_by_number(db, template_to_delete) is None

        print(f"[✓] 模板删除成功")
        print(f"    删除的模板: {template_to_delete}")
        print(f"    删除前模板数: {count_before}")
        print(f"    删除后模板数: {count_after}")

        print("\n" + "-" * 40)
        print("测试10: 模板不能跨信用证使用")
        print("-" * 40)

        other_lc_number = "LC-AIR-CFR-2024-002"
        other_template = crud.create_template_from_submission(
            db, "SUB-LC2-20240418-COMPLIANT", "其他信用证模板"
        )

        try:
            bad_use_request = schemas.TemplateUseRequest(
                lc_number=lc_number,
                submission_id="SUB-BAD-CROSS-LC",
                presentation_date=date(2024, 4, 3),
                field_overrides=[],
            )
            crud.create_submission_from_template(db, other_template.template_number, bad_use_request)
            print("[✗] 应该拒绝跨信用证使用模板")
            assert False, "模板不能跨信用证使用"
        except ValueError as e:
            print(f"[✓] 正确拒绝了跨信用证使用模板")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试11: 深度嵌套字段覆盖")
        print("-" * 40)

        deep_overrides = [
            schemas.TemplateFieldOverride(
                document_type="invoice",
                content_overrides={
                    "goods": [
                        {"name": "测试商品", "specification": "测试规格", "quantity": 100, "unit": "PCS", "unit_price": 100.00}
                    ],
                },
            )
        ]

        deep_preview = crud.preview_template(db, template.template_number, deep_overrides)
        deep_invoice = next(d for d in deep_preview["documents"] if d["document_type"] == "invoice")
        assert len(deep_invoice["content"]["goods"]) == 1
        assert deep_invoice["content"]["goods"][0]["name"] == "测试商品"
        assert deep_invoice["content"]["goods"][0]["quantity"] == 100

        print(f"[✓] 深度嵌套字段覆盖成功")
        print(f"    商品名称: {deep_invoice['content']['goods'][0]['name']}")
        print(f"    商品数量: {deep_invoice['content']['goods'][0]['quantity']}")

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
    test_template_module()
