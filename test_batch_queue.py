import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def _get_audit_ids_for_lc(db, lc_id, count):
    records = (
        db.query(models.AuditRecord)
        .filter(models.AuditRecord.lc_id == lc_id)
        .limit(count + 10)
        .all()
    )
    return [r.submission_id for r in records]


def _make_fake_audit(db, lc_id, submission_id, original_submission_id=None):
    existing = crud.get_audit_record_by_submission(db, submission_id)
    if existing:
        return existing
    if original_submission_id is None:
        original_submission_id = submission_id
    rec = models.AuditRecord(
        lc_id=lc_id,
        submission_id=submission_id,
        original_submission_id=original_submission_id,
        resubmission_round=0,
        conclusion="compliant",
        total_discrepancies=0,
        presentation_date=date.today(),
        review_status="pending",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_batch_queue_module():
    print("=" * 60)
    print("交单批次管理与优先级调度模块功能测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        db.query(models.SubmissionQueue).delete()
        db.commit()

        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"

        existing_ids = _get_audit_ids_for_lc(db, lc.id, 10)
        sub_q = []
        for i in range(1, 11):
            sid = f"SUB-QTEST-{i:03d}-{int(datetime.now().timestamp())}"
            rec = _make_fake_audit(db, lc.id, sid)
            sub_q.append(rec.submission_id)
        while len(sub_q) < 10:
            sub_q.append(existing_ids[len(sub_q) % max(1, len(existing_ids))])

        print(f"\n[✓] 找到测试信用证: {lc_number}")

        print("\n" + "-" * 40)
        print("测试1: 交单入队 - 默认优先级(normal)")
        print("-" * 40)

        entry1_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[0],
            lc_number=lc_number,
        )
        entry1 = crud.enqueue_submission(db, entry1_data)
        assert entry1 is not None, "入队失败"
        assert entry1.priority == "normal", f"默认优先级应为 normal，实际为 {entry1.priority}"
        assert entry1.queue_status == "waiting", f"状态应为 waiting，实际为 {entry1.queue_status}"
        assert entry1.batch_number.startswith("BATCH-"), f"批次号格式错误: {entry1.batch_number}"
        assert entry1.timeout_release_count == 0, "初始超时释放次数应为0"
        assert entry1.original_submission_id, "original_submission_id 不应为空"
        print(f"[✓] 入队成功")
        print(f"    交单号: {entry1.submission_id}")
        print(f"    原交单号: {entry1.original_submission_id}")
        print(f"    优先级: {entry1.priority}")
        print(f"    批次号: {entry1.batch_number}")
        print(f"    状态: {entry1.queue_status}")

        print("\n" + "-" * 40)
        print("测试2: 交单入队 - urgent优先级和截止时间")
        print("-" * 40)

        deadline = datetime.utcnow() + timedelta(hours=4)
        entry2_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[1],
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.URGENT,
            deadline=deadline,
        )
        entry2 = crud.enqueue_submission(db, entry2_data)
        assert entry2.priority == "urgent", f"优先级应为 urgent，实际为 {entry2.priority}"
        assert entry2.deadline is not None, "截止时间不应为空"
        assert entry2.batch_number == entry1.batch_number, "同一天入队应为同一批次"
        print(f"[✓] 紧急交单入队成功")
        print(f"    优先级: {entry2.priority}")
        print(f"    截止时间: {entry2.deadline}")
        print(f"    批次号: {entry2.batch_number}")

        print("\n" + "-" * 40)
        print("测试3: 交单入队 - low优先级")
        print("-" * 40)

        entry3_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[2],
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.LOW,
        )
        entry3 = crud.enqueue_submission(db, entry3_data)
        assert entry3.priority == "low", f"优先级应为 low，实际为 {entry3.priority}"
        print(f"[✓] 低优先级交单入队成功")
        print(f"    优先级: {entry3.priority}")

        print("\n" + "-" * 40)
        print("测试4: 重复入队应被拒绝")
        print("-" * 40)

        try:
            dup_data = schemas.SubmissionQueueCreate(
                submission_id=sub_q[0],
                lc_number=lc_number,
            )
            crud.enqueue_submission(db, dup_data)
            print("[✗] 应该拒绝重复入队")
            assert False, "同一交单不应重复入队"
        except ValueError as e:
            print(f"[✓] 正确拒绝了重复入队")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试5: 获取下一笔待处理交单 - urgent优先出队")
        print("-" * 40)

        next_entry = crud.get_next_submission(db)
        assert next_entry is not None, "队列不应为空"
        assert next_entry.id == entry2.id, f"应先取出 urgent 交单(id={entry2.id})，实际取出 id={next_entry.id}"
        assert next_entry.queue_status == "processing", f"状态应为 processing，实际为 {next_entry.queue_status}"
        assert next_entry.processing_started_at is not None, "开始处理时间不应为空"
        print(f"[✓] 正确取出 urgent 优先级交单")
        print(f"    队列id: {next_entry.id}")
        print(f"    交单号: {next_entry.submission_id}")
        print(f"    优先级: {next_entry.priority}")
        print(f"    状态: {next_entry.queue_status}")
        print(f"    开始处理时间: {next_entry.processing_started_at}")

        print("\n" + "-" * 40)
        print("测试6: 再取下一笔 - 应为normal优先级")
        print("-" * 40)

        next_entry2 = crud.get_next_submission(db)
        assert next_entry2 is not None
        assert next_entry2.id == entry1.id, f"应取出 normal 交单(id={entry1.id})，实际取出 id={next_entry2.id}"
        assert next_entry2.priority == "normal"
        print(f"[✓] 正确取出 normal 优先级交单")
        print(f"    队列id: {next_entry2.id}")
        print(f"    优先级: {next_entry2.priority}")

        print("\n" + "-" * 40)
        print("测试7: 再取下一笔 - 应为low优先级")
        print("-" * 40)

        next_entry3 = crud.get_next_submission(db)
        assert next_entry3 is not None
        assert next_entry3.id == entry3.id, f"应取出 low 交单(id={entry3.id})，实际取出 id={next_entry3.id}"
        assert next_entry3.priority == "low"
        print(f"[✓] 正确取出 low 优先级交单")
        print(f"    队列id: {next_entry3.id}")
        print(f"    优先级: {next_entry3.priority}")

        print("\n" + "-" * 40)
        print("测试8: 队列为空时获取下一笔")
        print("-" * 40)

        empty_next = crud.get_next_submission(db)
        assert empty_next is None, "所有交单已取出，应为空"
        print(f"[✓] 队列已空，返回 None")

        print("\n" + "-" * 40)
        print("测试9: 完成交单处理 - 按队列条目 id")
        print("-" * 40)

        completed = crud.complete_submission_in_queue(db, entry2.id)
        assert completed.queue_status == "completed", f"状态应为 completed，实际为 {completed.queue_status}"
        assert completed.processing_completed_at is not None, "完成时间不应为空"
        assert completed.id == entry2.id
        print(f"[✓] 交单处理完成")
        print(f"    队列id: {completed.id}")
        print(f"    交单号: {completed.submission_id}")
        print(f"    状态: {completed.queue_status}")
        print(f"    完成时间: {completed.processing_completed_at}")

        print("\n" + "-" * 40)
        print("测试10: 完成非processing状态的交单应被拒绝")
        print("-" * 40)

        try:
            crud.complete_submission_in_queue(db, entry2.id)
            print("[✗] 应该拒绝完成已完成的交单")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了完成已完成的交单")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试11: 超时释放 - 处理超过2小时自动释放回队列")
        print("-" * 40)

        processing_entry = db.query(models.SubmissionQueue).filter(
            models.SubmissionQueue.id == entry1.id
        ).first()
        assert processing_entry is not None
        assert processing_entry.queue_status == "processing"

        processing_entry.processing_started_at = datetime.utcnow() - timedelta(hours=3)
        db.commit()

        released_count = crud.release_timeout_submissions(db)
        assert released_count >= 1, f"应至少释放1笔超时交单，实际释放 {released_count}"

        db.refresh(processing_entry)
        assert processing_entry.queue_status == "waiting", f"释放后状态应为 waiting，实际为 {processing_entry.queue_status}"
        assert processing_entry.processing_started_at is None, "释放后开始处理时间应为空"
        assert processing_entry.timeout_release_count >= 1, f"超时释放次数应>=1，实际为 {processing_entry.timeout_release_count}"
        print(f"[✓] 超时释放正常工作")
        print(f"    释放数量: {released_count}")
        print(f"    交单状态: {processing_entry.queue_status}")
        print(f"    超时释放次数: {processing_entry.timeout_release_count}")

        print("\n" + "-" * 40)
        print("测试12: 释放后的交单可再次被取出")
        print("-" * 40)

        re_fetched = crud.get_next_submission(db)
        assert re_fetched is not None, "释放后的交单应可再次取出"
        assert re_fetched.id == entry1.id, f"应取出释放的交单(id={entry1.id})，实际为 id={re_fetched.id}"
        print(f"[✓] 释放后的交单可再次取出")
        print(f"    队列id: {re_fetched.id}")

        crud.complete_submission_in_queue(db, entry1.id)

        print("\n" + "-" * 40)
        print("测试13: 按批次查询交单")
        print("-" * 40)

        batch_result = crud.get_batch_submissions(db, entry1.batch_number)
        assert batch_result["batch_number"] == entry1.batch_number
        assert batch_result["total_count"] >= 3, f"批次应有>=3笔交单，实际有 {batch_result['total_count']}"
        assert len(batch_result["submissions"]) >= 3
        for sub in batch_result["submissions"]:
            assert "lc_number" in sub, "应包含 lc_number"
            assert "audit_conclusion" in sub, "应包含 audit_conclusion"
            assert "original_submission_id" in sub, "应包含 original_submission_id"
        print(f"[✓] 批次查询成功")
        print(f"    批次号: {batch_result['batch_number']}")
        print(f"    总笔数: {batch_result['total_count']}")
        for sub in batch_result["submissions"]:
            print(f"    - id={sub['id']} {sub['submission_id']} 优先级:{sub['priority']} 状态:{sub['queue_status']}")

        print("\n" + "-" * 40)
        print("测试14: 批次效率统计")
        print("-" * 40)

        stats = crud.get_batch_stats(db, entry1.batch_number)
        assert stats["batch_number"] == entry1.batch_number
        assert stats["total_count"] >= 3, f"总笔数应>=3，实际为 {stats['total_count']}"
        assert stats["completed_count"] >= 2, f"已完成笔数应>=2，实际为 {stats['completed_count']}"
        assert stats["timeout_release_total_count"] >= 1, f"超时释放总次数应>=1，实际为 {stats['timeout_release_total_count']}"
        print(f"[✓] 批次统计成功")
        print(f"    总笔数: {stats['total_count']}")
        print(f"    已完成: {stats['completed_count']}")
        print(f"    平均处理耗时: {stats['avg_processing_seconds']}秒")
        print(f"    超时释放次数: {stats['timeout_release_total_count']}")

        print("\n" + "-" * 40)
        print("测试15: 队列状态查询")
        print("-" * 40)

        queue_status = crud.get_queue_status(db)
        assert "total_waiting" in queue_status
        assert "by_priority" in queue_status
        print(f"[✓] 队列状态查询成功")
        print(f"    当前等待总数: {queue_status['total_waiting']}")
        for item in queue_status["by_priority"]:
            print(f"    {item['priority']}: {item['count']}笔")

        print("\n" + "-" * 40)
        print("测试16: 队列状态 - 加入新的urgent交单后查询")
        print("-" * 40)

        entry4_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[3],
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.URGENT,
        )
        entry4 = crud.enqueue_submission(db, entry4_data)

        entry5_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[4],
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.NORMAL,
        )
        entry5 = crud.enqueue_submission(db, entry5_data)

        queue_status2 = crud.get_queue_status(db)
        urgent_count = next((item["count"] for item in queue_status2["by_priority"] if item["priority"] == "urgent"), 0)
        normal_count = next((item["count"] for item in queue_status2["by_priority"] if item["priority"] == "normal"), 0)
        assert urgent_count >= 1, f"urgent应>=1，实际为 {urgent_count}"
        assert normal_count >= 1, f"normal应>=1，实际为 {normal_count}"
        print(f"[✓] 队列状态查询正确")
        print(f"    等待总数: {queue_status2['total_waiting']}")
        for item in queue_status2["by_priority"]:
            print(f"    {item['priority']}: {item['count']}笔")

        print("\n" + "-" * 40)
        print("测试17: 同优先级先进先出")
        print("-" * 40)

        entry6_data = schemas.SubmissionQueueCreate(
            submission_id=sub_q[5],
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.NORMAL,
        )
        entry6 = crud.enqueue_submission(db, entry6_data)

        next_urgent = crud.get_next_submission(db)
        assert next_urgent is not None
        assert next_urgent.priority == "urgent", f"应先取urgent，实际取到 {next_urgent.priority}"
        assert next_urgent.id == entry4.id
        crud.complete_submission_in_queue(db, entry4.id)

        next_n1 = crud.get_next_submission(db)
        assert next_n1 is not None
        assert next_n1.priority == "normal", f"应取normal，实际取到 {next_n1.priority}"
        assert next_n1.id == entry5.id, f"同优先级应先进先出，应先取 entry5(id={entry5.id})，实际取到 id={next_n1.id}"
        crud.complete_submission_in_queue(db, entry5.id)

        next_n2 = crud.get_next_submission(db)
        assert next_n2 is not None
        assert next_n2.id == entry6.id, f"应取 entry6(id={entry6.id})，实际取到 id={next_n2.id}"
        crud.complete_submission_in_queue(db, entry6.id)

        print(f"[✓] 同优先级先进先出验证通过")
        print(f"    先取: entry4 id={entry4.id} (urgent)")
        print(f"    次取: entry5 id={entry5.id} (normal, 先入队)")
        print(f"    后取: entry6 id={entry6.id} (normal, 后入队)")

        print("\n" + "-" * 40)
        print("测试18: 不存在的交单入队应被拒绝")
        print("-" * 40)

        try:
            bad_data = schemas.SubmissionQueueCreate(
                submission_id="SUB-NOT-EXIST-99999",
                lc_number=lc_number,
            )
            crud.enqueue_submission(db, bad_data)
            print("[✗] 应该拒绝不存在的交单")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了不存在的交单")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试19: 空批次统计")
        print("-" * 40)

        empty_stats = crud.get_batch_stats(db, "BATCH-20990101")
        assert empty_stats["total_count"] == 0, f"空批次笔数应为0，实际为 {empty_stats['total_count']}"
        assert empty_stats["avg_processing_seconds"] is None, "空批次平均耗时应为None"
        print(f"[✓] 空批次统计正确")
        print(f"    总笔数: {empty_stats['total_count']}")

        print("\n" + "-" * 40)
        print("测试20: 完成 entry3 并验证批次统计")
        print("-" * 40)

        crud.complete_submission_in_queue(db, entry3.id)

        final_stats = crud.get_batch_stats(db, entry1.batch_number)
        assert final_stats["total_count"] >= 6
        assert final_stats["completed_count"] >= 6, f"已完成笔数应>=6，实际为 {final_stats['completed_count']}"
        assert final_stats["avg_processing_seconds"] is not None, "应存在平均耗时"
        print(f"[✓] 全部完成后统计正确")
        print(f"    总笔数: {final_stats['total_count']}")
        print(f"    已完成: {final_stats['completed_count']}")
        print(f"    平均处理耗时: {final_stats['avg_processing_seconds']}秒")
        print(f"    超时释放总次数: {final_stats['timeout_release_total_count']}")

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
    test_batch_queue_module()
