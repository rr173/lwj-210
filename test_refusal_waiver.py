import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def _create_discrepant_audit(db, lc, submission_id):
    existing = db.query(models.AuditRecord).filter(
        models.AuditRecord.submission_id == submission_id
    ).first()
    if existing:
        return existing

    audit = models.AuditRecord(
        lc_id=lc.id,
        submission_id=submission_id,
        original_submission_id=submission_id,
        resubmission_round=0,
        conclusion="discrepant",
        critical_count=1,
        minor_count=1,
        total_discrepancies=2,
        presentation_date=date(2024, 3, 1),
    )
    db.add(audit)
    db.flush()

    disc1 = models.Discrepancy(
        audit_record_id=audit.id,
        discrepancy_type="amount",
        severity="critical",
        document_type="invoice",
        description="发票金额超出信用证金额10%容差",
        lc_clause_reference="UCP600 Art.18",
        source="auto",
        is_removed=False,
    )
    disc2 = models.Discrepancy(
        audit_record_id=audit.id,
        discrepancy_type="date",
        severity="minor",
        document_type="bill_of_lading",
        description="提单装运日期晚于最迟装运日",
        lc_clause_reference="UCP600 Art.20",
        source="auto",
        is_removed=False,
    )
    db.add(disc1)
    db.add(disc2)
    db.commit()
    db.refresh(audit)
    return audit


def test_refusal_waiver_module():
    print("=" * 60)
    print("拒付通知与不符点豁免处置模块功能测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"
        print(f"\n[✓] 找到测试信用证: {lc_number}")

        print("\n" + "-" * 40)
        print("测试1: discrepant审核记录自动生成处置单")
        print("-" * 40)

        audit1 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-001")
        disposition1 = crud.auto_create_refusal_disposition(db, audit1, lc)

        assert disposition1 is not None, "处置单应为自动创建"
        assert disposition1.status == models.REFUSAL_STATUS_PENDING_APPLICANT, f"状态应为 pending_applicant_action，实际为 {disposition1.status}"
        assert disposition1.lc_number == lc_number, f"信用证号应为 {lc_number}"
        assert disposition1.submission_id == audit1.submission_id, "交单编号应匹配"
        assert disposition1.applicant_name == lc.applicant_name, "申请人应匹配"
        assert len(disposition1.discrepancy_snapshot) > 0, "不符点快照不应为空"
        assert disposition1.notice_deadline > datetime.utcnow(), "通知截止时间应在未来"
        assert len(disposition1.waiver_items) > 0, "应有豁免项"

        print(f"[✓] 处置单自动创建成功")
        print(f"    处置编号: {disposition1.disposition_number}")
        print(f"    状态: {disposition1.status}")
        print(f"    关联信用证: {disposition1.lc_number}")
        print(f"    关联交单: {disposition1.submission_id}")
        print(f"    申请人: {disposition1.applicant_name}")
        print(f"    通知截止时间: {disposition1.notice_deadline}")
        print(f"    不符点快照数量: {len(disposition1.discrepancy_snapshot)}")
        print(f"    豁免项数量: {len(disposition1.waiver_items)}")

        for item in disposition1.waiver_items:
            print(f"      - [{item.severity}] {item.description} (豁免状态: {item.waiver_status})")

        d1_number = disposition1.disposition_number

        print("\n" + "-" * 40)
        print("测试2: 重复创建处置单应返回已有记录")
        print("-" * 40)

        existing = crud.auto_create_refusal_disposition(db, audit1, lc)
        assert existing.disposition_number == d1_number, "应返回同一处置单"
        print(f"[✓] 重复创建返回已有处置单: {existing.disposition_number}")

        print("\n" + "-" * 40)
        print("测试3: 申请人接受全部不符点 (accept_all)")
        print("-" * 40)

        accepted = crud.applicant_accept_all(db, d1_number, accepted_by="张三")
        assert accepted.status == models.REFUSAL_STATUS_ACCEPT_ALL, f"状态应为 accept_all，实际为 {accepted.status}"
        assert accepted.applicant_action_at is not None, "应有申请人操作时间"

        for item in accepted.waiver_items:
            assert item.waiver_status == models.WAIVER_STATUS_WAIVED, f"所有不符点应已豁免，但 {item.description} 状态为 {item.waiver_status}"
            assert item.waived_by == "张三", "操作人应为张三"

        print(f"[✓] 申请人接受全部不符点成功")
        print(f"    状态: {accepted.status}")
        print(f"    操作时间: {accepted.applicant_action_at}")

        print("\n" + "-" * 40)
        print("测试4: 银行登记最终结果为 waived_accept")
        print("-" * 40)

        finalized = crud.bank_register_final_result(db, d1_number, models.REFUSAL_STATUS_WAIVED_ACCEPT, confirmed_by="银行经理李四")
        assert finalized.status == models.REFUSAL_STATUS_WAIVED_ACCEPT, f"状态应为 waived_accept，实际为 {finalized.status}"
        assert finalized.bank_final_result_at is not None, "应有银行最终处置时间"
        assert finalized.is_final(), "应为终态"
        print(f"[✓] 银行登记最终结果成功")
        print(f"    最终状态: {finalized.status}")
        print(f"    最终处置时间: {finalized.bank_final_result_at}")

        print("\n" + "-" * 40)
        print("测试5: 终态不可逆转")
        print("-" * 40)

        try:
            crud.applicant_accept_all(db, d1_number)
            print("[✗] 终态应不可变更，但操作成功了")
            assert False, "终态应不可变更"
        except ValueError as e:
            print(f"[✓] 正确拒绝了终态变更")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试6: 申请人拒绝全部不符点 (reject_all)")
        print("-" * 40)

        audit2 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-002")
        disposition2 = crud.auto_create_refusal_disposition(db, audit2, lc)
        assert disposition2 is not None, "第二笔处置单应创建成功"
        d2_number = disposition2.disposition_number
        print(f"[✓] 第二笔处置单创建: {d2_number}")

        rejected = crud.applicant_reject_all(db, d2_number, rejected_by="王五")
        assert rejected.status == models.REFUSAL_STATUS_REJECT_ALL, f"状态应为 reject_all，实际为 {rejected.status}"
        for item in rejected.waiver_items:
            assert item.waiver_status == models.WAIVER_STATUS_NOT_WAIVED, "所有不符点应标记为不豁免"
        print(f"[✓] 申请人拒绝全部不符点成功")
        print(f"    状态: {rejected.status}")

        print("\n" + "-" * 40)
        print("测试7: 银行登记最终结果为 refusal")
        print("-" * 40)

        refusal_result = crud.bank_register_final_result(db, d2_number, models.REFUSAL_STATUS_REFUSAL, confirmed_by="银行经理")
        assert refusal_result.status == models.REFUSAL_STATUS_REFUSAL, f"状态应为 refusal，实际为 {refusal_result.status}"
        assert refusal_result.is_final(), "应为终态"
        print(f"[✓] 银行登记拒付成功")
        print(f"    最终状态: {refusal_result.status}")

        print("\n" + "-" * 40)
        print("测试8: 申请人部分豁免 (partial_waiver)")
        print("-" * 40)

        audit3 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-003")
        disposition3 = crud.auto_create_refusal_disposition(db, audit3, lc)
        assert disposition3 is not None, "第三笔处置单应创建成功"
        d3_number = disposition3.disposition_number

        waiver_items = disposition3.waiver_items
        assert len(waiver_items) >= 2, f"应有至少2个豁免项，实际有 {len(waiver_items)} 个"

        minor_items = [item for item in waiver_items if not item.is_critical]
        critical_items = [item for item in waiver_items if item.is_critical]

        if minor_items:
            waived_item_ids = [minor_items[0].id]
            partial = crud.applicant_partial_waiver(db, d3_number, waived_item_ids, waived_by="赵六")
            assert partial.status == models.REFUSAL_STATUS_PARTIAL_WAIVER, f"状态应为 partial_waiver，实际为 {partial.status}"

            for item in partial.waiver_items:
                if item.id in waived_item_ids:
                    assert item.waiver_status == models.WAIVER_STATUS_WAIVED, "指定不符点应已豁免"
                elif item.id in [i.id for i in critical_items]:
                    assert item.waiver_status == models.WAIVER_STATUS_PENDING, f"未指定豁免的critical应仍为pending，实际为 {item.waiver_status}"

            print(f"[✓] 申请人部分豁免(minor)成功")
            print(f"    状态: {partial.status}")
            for item in partial.waiver_items:
                print(f"      - [{item.severity}] {item.description}: {item.waiver_status}")
        else:
            print("[!] 没有minor不符点可测试部分豁免，跳过")

        print("\n" + "-" * 40)
        print("测试9: 分批豁免 - 继续豁免剩余critical不符点")
        print("-" * 40)

        if minor_items and critical_items:
            critical_ids = [item.id for item in critical_items]
            partial2 = crud.applicant_partial_waiver(db, d3_number, critical_ids, waived_by="赵六")

            all_waived = all(item.waiver_status == models.WAIVER_STATUS_WAIVED for item in partial2.waiver_items)
            assert all_waived, "分批豁免后应全部豁免完成"
            assert partial2.status == models.REFUSAL_STATUS_ACCEPT_ALL, f"全部豁免后状态应为 accept_all，实际为 {partial2.status}"

            print(f"[✓] 分批豁免(critical)成功，全部豁免后自动转为 accept_all")
            print(f"    状态: {partial2.status}")
            for item in partial2.waiver_items:
                print(f"      - [{item.severity}] {item.description}: {item.waiver_status}")

            audit6 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-BATCH-002")
            disposition6 = crud.auto_create_refusal_disposition(db, audit6, lc)
            d6_number = disposition6.disposition_number
            waiver_items_6 = disposition6.waiver_items
            minors6 = [item for item in waiver_items_6 if not item.is_critical]
            if minors6:
                batch2 = crud.applicant_partial_waiver(db, d6_number, [minors6[0].id], waived_by="测试用户")
                assert batch2.status == models.REFUSAL_STATUS_PARTIAL_WAIVER
                batch_all = crud.applicant_accept_all(db, d6_number, accepted_by="测试用户")
                assert batch_all.status == models.REFUSAL_STATUS_ACCEPT_ALL, f"partial_waiver 后 accept_all 应成功，实际为 {batch_all.status}"
                print(f"[✓] partial_waiver 后 accept_all 成功")
        else:
            print("[!] 没有critical不符点可测试分批豁免，跳过")

        print("\n" + "-" * 40)
        print("测试10: 关键不符点未豁免时不能waived_accept")
        print("-" * 40)

        audit7 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-CHECK-003")
        disposition7 = crud.auto_create_refusal_disposition(db, audit7, lc)
        d7_number = disposition7.disposition_number
        waiver_items_7 = disposition7.waiver_items
        minors7 = [item for item in waiver_items_7 if not item.is_critical]

        if minors7:
            crud.applicant_partial_waiver(db, d7_number, [minors7[0].id], waived_by="测试用户")
            try:
                crud.bank_register_final_result(db, d7_number, models.REFUSAL_STATUS_WAIVED_ACCEPT, confirmed_by="银行经理")
                print("[✗] 关键不符点未豁免时应拒绝waived_accept")
                assert False, "关键不符点未豁免时不应允许waived_accept"
            except ValueError as e:
                print(f"[✓] 正确拒绝了关键不符点未豁免时的waived_accept")
                print(f"    错误信息: {str(e)}")
        else:
            print("[!] 没有minor不符点可测试，跳过")

        print("\n" + "-" * 40)
        print("测试11: 超时处置 - 超过5自然日自动冻结")
        print("-" * 40)

        audit4 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-004")
        disposition4 = crud.auto_create_refusal_disposition(db, audit4, lc)
        assert disposition4 is not None, "超时测试处置单应创建成功"
        d4_number = disposition4.disposition_number

        disposition4.notice_deadline = datetime.utcnow() - timedelta(days=1)
        db.commit()
        db.refresh(disposition4)

        overdue_result = crud.check_and_process_overdue_dispositions(db)
        assert overdue_result["processed_count"] >= 1, f"应至少处理1笔超时，实际为 {overdue_result['processed_count']}"

        db.refresh(disposition4)
        assert disposition4.status == models.REFUSAL_STATUS_OVERDUE_NOTICE, f"状态应为 overdue_notice，实际为 {disposition4.status}"

        has_refusal_freeze = crud.has_active_freeze(db, lc.id, models.FREEZE_TYPE_REFUSAL_OVERDUE)
        assert has_refusal_freeze, "应有refusal_overdue冻结记录"

        print(f"[✓] 超时处置正确触发")
        print(f"    状态: {disposition4.status}")
        print(f"    处理数: {overdue_result['processed_count']}")
        print(f"    新增冻结数: {overdue_result['frozen_count']}")
        print(f"    冻结记录存在: {has_refusal_freeze}")

        print("\n" + "-" * 40)
        print("测试12: 超时冻结后付款被阻断")
        print("-" * 40)

        block_reason = crud.check_disposition_blocks_payment(db, lc.id)
        assert block_reason is not None, "超时冻结后应阻断付款"
        print(f"[✓] 付款被正确阻断")
        print(f"    阻断原因: {block_reason}")

        print("\n" + "-" * 40)
        print("测试13: 超时处置后银行直接确认豁免接受，冻结自动解除")
        print("-" * 40)

        unfreezed = crud.bank_register_final_result(db, d4_number, models.REFUSAL_STATUS_WAIVED_ACCEPT, confirmed_by="银行经理")

        assert unfreezed.status == models.REFUSAL_STATUS_WAIVED_ACCEPT, f"状态应为 waived_accept，实际为 {unfreezed.status}"

        still_frozen = crud.has_active_freeze(db, lc.id, models.FREEZE_TYPE_REFUSAL_OVERDUE)
        assert not still_frozen, "豁免接受后冻结应自动解除"

        block_reason_after = crud.check_disposition_blocks_payment(db, lc.id)
        assert block_reason_after is None, "冻结解除后付款应可进行"

        print(f"[✓] 豁免接受后冻结自动解除")
        print(f"    最终状态: {unfreezed.status}")
        print(f"    冻结已解除: {not still_frozen}")
        print(f"    付款不再被阻断: {block_reason_after is None}")

        print("\n" + "-" * 40)
        print("测试14: 按信用证查看拒付处置历史")
        print("-" * 40)

        history = crud.get_refusal_history_by_lc(db, lc_number)
        assert history["lc_number"] == lc_number, "信用证号应匹配"
        assert history["total_dispositions"] >= 3, f"应至少有3笔处置记录，实际有 {history['total_dispositions']}"
        print(f"[✓] 查询拒付处置历史成功")
        print(f"    信用证: {history['lc_number']}")
        print(f"    总处置笔数: {history['total_dispositions']}")
        for d in history["dispositions"]:
            print(f"    - {d.disposition_number}: {d.status} (交单: {d.submission_id})")

        print("\n" + "-" * 40)
        print("测试15: 按申请人统计豁免率和拒付率")
        print("-" * 40)

        stats = crud.get_applicant_waiver_stats(db, lc.applicant_name)
        assert stats["applicant_name"] == lc.applicant_name, "申请人应匹配"
        assert stats["total_dispositions"] >= 3, f"应至少有3笔处置，实际为 {stats['total_dispositions']}"
        assert 0 <= stats["waiver_rate"] <= 1, f"豁免率应在0-1之间，实际为 {stats['waiver_rate']}"
        assert 0 <= stats["rejection_rate"] <= 1, f"拒付率应在0-1之间，实际为 {stats['rejection_rate']}"
        print(f"[✓] 申请人豁免统计成功")
        print(f"    申请人: {stats['applicant_name']}")
        print(f"    总处置笔数: {stats['total_dispositions']}")
        print(f"    全部接受笔数: {stats['accept_all_count']}")
        print(f"    全部拒绝笔数: {stats['reject_all_count']}")
        print(f"    部分豁免笔数: {stats['partial_waiver_count']}")
        print(f"    豁免率: {stats['waiver_rate']:.2%}")
        print(f"    拒付率: {stats['rejection_rate']:.2%}")

        print("\n" + "-" * 40)
        print("测试16: 超时处置统计")
        print("-" * 40)

        overdue_stats = crud.get_overdue_disposition_stats(db)
        assert "total_overdue_count" in overdue_stats, "应返回total_overdue_count"
        print(f"[✓] 超时处置统计查询成功")
        print(f"    总超时笔数: {overdue_stats['total_overdue_count']}")
        print(f"    仍冻结笔数: {overdue_stats['active_overdue_count']}")
        print(f"    已解除笔数: {overdue_stats['released_overdue_count']}")

        print("\n" + "-" * 40)
        print("测试17: 银行登记return_documents")
        print("-" * 40)

        audit5 = _create_discrepant_audit(db, lc, "SUB-REFUSAL-005")
        disposition5 = crud.auto_create_refusal_disposition(db, audit5, lc)
        d5_number = disposition5.disposition_number

        crud.applicant_reject_all(db, d5_number, rejected_by="申请人")
        return_docs = crud.bank_register_final_result(db, d5_number, models.REFUSAL_STATUS_RETURN_DOCUMENTS, confirmed_by="银行经理")
        assert return_docs.status == models.REFUSAL_STATUS_RETURN_DOCUMENTS, f"状态应为 return_documents"
        assert return_docs.is_final(), "应为终态"
        print(f"[✓] 银行登记退单成功")
        print(f"    最终状态: {return_docs.status}")

        print("\n" + "-" * 40)
        print("测试18: 状态流转单向不可逆验证")
        print("-" * 40)

        try:
            crud._validate_status_transition(models.REFUSAL_STATUS_WAIVED_ACCEPT, models.REFUSAL_STATUS_PENDING_APPLICANT)
            print("[✗] 终态不应允许回退到pending")
            assert False
        except ValueError:
            print("[✓] 终态不可回退到pending")

        try:
            crud._validate_status_transition(models.REFUSAL_STATUS_REFUSAL, models.REFUSAL_STATUS_ACCEPT_ALL)
            print("[✗] refusal终态不应允许转到accept_all")
            assert False
        except ValueError:
            print("[✓] refusal终态不可转为accept_all")

        try:
            crud._validate_status_transition(models.REFUSAL_STATUS_PENDING_APPLICANT, models.REFUSAL_STATUS_WAIVED_ACCEPT)
            print("[✗] pending不应允许直接跳到waived_accept")
            assert False
        except ValueError:
            print("[✓] pending不可直接跳到waived_accept")

        print("\n" + "-" * 40)
        print("测试19: 数据库迁移功能")
        print("-" * 40)

        migrated = crud.migrate_refusal_disposition_tables(db)
        print(f"[✓] 数据库迁移完成，新建表数: {migrated}")

        print("\n" + "-" * 40)
        print("测试20: 超时检查重复调用不重复处理")
        print("-" * 40)

        result_dup = crud.check_and_process_overdue_dispositions(db)
        assert result_dup["processed_count"] == 0, "已处理的超时处置不应重复处理"
        print(f"[✓] 重复超时检查正确返回0笔处理")

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
    test_refusal_waiver_module()
