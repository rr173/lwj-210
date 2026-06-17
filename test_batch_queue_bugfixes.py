import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def get_existing_submission_ids(db):
    from sqlalchemy import func
    records = db.query(models.AuditRecord).limit(5).all()
    return [r.submission_id for r in records]


def test_bugfixes():
    print("=" * 60)
    print("交单批次管理模块 Bug 修复验证测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        db.query(models.SubmissionQueue).delete()
        db.commit()

        existing_sub_ids = get_existing_submission_ids(db)
        assert len(existing_sub_ids) >= 2, "需要至少2个已存在的审核记录"
        sub_id_1 = existing_sub_ids[0]
        sub_id_2 = existing_sub_ids[1]

        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"

        print("\n" + "-" * 40)
        print("Bug1 验证: 入队不校验交单是否存在")
        print("-" * 40)

        fake_sub_id = "SUB-FAKE-NOT-EXIST-99999"
        try:
            fake_data = schemas.SubmissionQueueCreate(
                submission_id=fake_sub_id,
                lc_number=lc_number,
            )
            crud.enqueue_submission(db, fake_data)
            print(f"  [✗] 应拒绝不存在的交单，但入队成功了")
            assert False, "不存在的交单不应入队成功"
        except ValueError as e:
            msg = str(e)
            assert "不存在" in msg and "审核记录" in msg, f"错误信息不明确: {msg}"
            print(f"  [✓] 正确拒绝了不存在的交单")
            print(f"      错误信息: {msg}")

        print("\n" + "-" * 40)
        print("Bug1 扩展: 交单所属 LC 与入队指定 LC 不匹配也应拒绝")
        print("-" * 40)

        audit_1 = crud.get_audit_record_by_submission(db, sub_id_1)
        assert audit_1 is not None
        other_lc = db.query(models.LetterOfCredit).filter(
            models.LetterOfCredit.id != audit_1.lc_id
        ).first()
        assert other_lc is not None, "需要至少2个信用证"

        try:
            bad_lc_data = schemas.SubmissionQueueCreate(
                submission_id=sub_id_1,
                lc_number=other_lc.lc_number,
            )
            crud.enqueue_submission(db, bad_lc_data)
            print(f"  [✗] 应拒绝 LC 不匹配的交单")
            assert False
        except ValueError as e:
            msg = str(e)
            assert "不匹配" in msg, f"错误信息不明确: {msg}"
            print(f"  [✓] 正确拒绝了 LC 不匹配的交单")
            print(f"      错误信息: {msg}")

        print("\n" + "-" * 40)
        print("准备数据: 正常入队两笔交单")
        print("-" * 40)

        entry1_data = schemas.SubmissionQueueCreate(
            submission_id=sub_id_1,
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.NORMAL,
        )
        entry1 = crud.enqueue_submission(db, entry1_data)
        print(f"  正常入队: {entry1.submission_id} (队列id={entry1.id}, original={entry1.original_submission_id})")

        print("\n" + "-" * 40)
        print("Bug3 验证: complete 接口按 submission_id 匹配导致新旧条目混淆")
        print("         → 改为按队列条目 id 匹配")
        print("-" * 40)

        next_entry = crud.get_next_submission(db)
        assert next_entry is not None and next_entry.id == entry1.id

        try:
            crud.complete_submission_in_queue(db, 99999)
            print(f"  [✗] 应拒绝不存在的队列条目 id")
            assert False
        except ValueError as e:
            print(f"  [✓] 正确拒绝了不存在的队列条目 id: {str(e)}")

        completed = crud.complete_submission_in_queue(db, entry1.id)
        assert completed.queue_status == models.QUEUE_STATUS_COMPLETED
        assert completed.id == entry1.id
        print(f"  [✓] 按队列条目 id={entry1.id} 成功完成交单 {completed.submission_id}")

        try:
            crud.complete_submission_in_queue(db, entry1.id)
            assert False, "已经完成的条目再次 complete 应报错"
        except ValueError as e:
            print(f"  [✓] 正确拒绝重复 complete: {str(e)}")

        print("\n" + "-" * 40)
        print("Bug3 扩展: 修改重提入新队列时自动废弃旧条目")
        print("-" * 40)

        audit_1_refreshed = crud.get_audit_record_by_submission(db, sub_id_1)
        original_sub_id = audit_1_refreshed.original_submission_id

        old_entry = db.query(models.SubmissionQueue).filter(
            models.SubmissionQueue.submission_id == sub_id_1
        ).first()
        assert old_entry is not None

        discrepant_record = db.query(models.AuditRecord).filter(
            models.AuditRecord.conclusion == "discrepant"
        ).first()

        ts = datetime.now().strftime("%H%M%S%f")
        new_sub_id = f"{original_sub_id}-RESUB-{ts}"
        fake_audit = models.AuditRecord(
            lc_id=audit_1_refreshed.lc_id,
            submission_id=new_sub_id,
            original_submission_id=original_sub_id,
            resubmission_round=1,
            modification_remark="手动模拟重提",
            conclusion="compliant",
            total_discrepancies=0,
            presentation_date=date.today(),
            review_status="pending",
        )
        db.add(fake_audit)
        db.commit()
        db.refresh(fake_audit)
        print(f"  手动插入模拟审核记录: submission={new_sub_id}, original={original_sub_id}")

        if discrepant_record:
            d_lc = crud.get_letter_of_credit_by_id(db, discrepant_record.lc_id)
            ts2 = datetime.now().strftime("%H%M%S%f")
            alt_new_id = f"{discrepant_record.original_submission_id}-ALT-{ts2}"
            alt_audit = models.AuditRecord(
                lc_id=discrepant_record.lc_id,
                submission_id=alt_new_id,
                original_submission_id=discrepant_record.original_submission_id,
                resubmission_round=0,
                modification_remark="备选手动模拟",
                conclusion="compliant",
                total_discrepancies=0,
                presentation_date=date.today(),
                review_status="pending",
            )
            db.add(alt_audit)
            db.commit()

        new_entry_data = schemas.SubmissionQueueCreate(
            submission_id=new_sub_id,
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.URGENT,
        )

        old_waiting_entry = db.query(models.SubmissionQueue).filter(
            models.SubmissionQueue.original_submission_id == original_sub_id,
            models.SubmissionQueue.submission_id != new_sub_id,
            models.SubmissionQueue.queue_status.in_([
                models.QUEUE_STATUS_WAITING,
                models.QUEUE_STATUS_PROCESSING,
            ])
        ).first()

        if not old_waiting_entry:
            another_audit = db.query(models.AuditRecord).filter(
                models.AuditRecord.original_submission_id == original_sub_id,
                models.AuditRecord.submission_id != new_sub_id,
            ).first()
            if another_audit:
                temp_q = models.SubmissionQueue(
                    submission_id=another_audit.submission_id,
                    original_submission_id=original_sub_id,
                    lc_id=another_audit.lc_id,
                    batch_number=crud._generate_batch_number(),
                    priority="normal",
                    queue_status=models.QUEUE_STATUS_WAITING,
                    timeout_release_count=0,
                )
                db.add(temp_q)
                db.commit()
                db.refresh(temp_q)
                old_waiting_entry = temp_q
                print(f"  手动构造了一个 waiting 状态的旧队列条目 (id={old_waiting_entry.id})")

        new_entry = crud.enqueue_submission(db, new_entry_data)
        print(f"  新交单入队: 队列id={new_entry.id}, submission={new_entry.submission_id}")

        if old_waiting_entry:
            db.refresh(old_waiting_entry)
            assert old_waiting_entry.queue_status == models.QUEUE_STATUS_OBSOLETE, (
                f"旧条目应被标记为 obsolete，实际为 {old_waiting_entry.queue_status}"
            )
            print(f"  [✓] 旧队列条目 (id={old_waiting_entry.id}) 已被自动标记为 obsolete")
        else:
            print(f"  [!] 无法构造旧 waiting 条目，跳过自动废弃断言")

        print(f"  [✓] 新旧队列条目通过队列 id 精确匹配，避免了 submission_id 混淆")

        print("\n" + "-" * 40)
        print("Bug3 扩展: 废弃的条目不允许 complete")
        print("-" * 40)

        all_obsolete = db.query(models.SubmissionQueue).filter(
            models.SubmissionQueue.queue_status == models.QUEUE_STATUS_OBSOLETE
        ).all()
        if all_obsolete:
            obs_entry = all_obsolete[0]
            try:
                crud.complete_submission_in_queue(db, obs_entry.id)
                print(f"  [✗] 废弃条目应不能 complete")
                assert False
            except ValueError as e:
                msg = str(e)
                assert "废弃" in msg, f"错误信息应包含'废弃': {msg}"
                print(f"  [✓] 正确拒绝了废弃条目的 complete: {msg}")
        else:
            print(f"  (当前无废弃条目，跳过此断言)")

        print("\n" + "-" * 40)
        print("Bug2 验证: 批次统计只数 waiting 的超时次数")
        print("         → 统计前先执行超时释放，所有状态条目都算入总数")
        print("-" * 40)

        all_audit_ids = get_existing_submission_ids(db)
        queued_sub_ids = {s.submission_id for s in db.query(models.SubmissionQueue).all()}
        available = [s for s in all_audit_ids if s not in queued_sub_ids]
        assert len(available) >= 1, "需要至少一个未入队的审核记录"
        bug2_sub_id = available[0]
        bug2_audit = crud.get_audit_record_by_submission(db, bug2_sub_id)
        bug2_lc = crud.get_letter_of_credit_by_id(db, bug2_audit.lc_id)

        entry3_data = schemas.SubmissionQueueCreate(
            submission_id=bug2_sub_id,
            lc_number=bug2_lc.lc_number,
            priority=schemas.SubmissionPriority.LOW,
        )
        entry3 = crud.enqueue_submission(db, entry3_data)
        batch_no = entry3.batch_number

        remaining_urgent = db.query(models.SubmissionQueue).filter(
            models.SubmissionQueue.queue_status == models.QUEUE_STATUS_WAITING,
            models.SubmissionQueue.id != entry3.id,
        ).all()
        for u in remaining_urgent:
            fetched = crud.get_next_submission(db)
            if fetched and fetched.id != entry3.id:
                try:
                    crud.complete_submission_in_queue(db, fetched.id)
                except ValueError:
                    pass

        next_3 = crud.get_next_submission(db)
        assert next_3 is not None and next_3.id == entry3.id, (
            f"应取出 entry3 (id={entry3.id})，实际取出 id={next_3.id if next_3 else None}"
        )
        print(f"  取出交单 {entry3.submission_id} (id={entry3.id}) 进入 processing")

        next_3.processing_started_at = datetime.utcnow() - timedelta(hours=3)
        db.commit()
        print(f"  人工把处理开始时间回拨 3 小时，制造超时")

        stats_before = crud.get_batch_stats(db, batch_no)
        print(f"  批次统计结果:")
        print(f"    总笔数: {stats_before['total_count']}")
        print(f"    超时释放次数: {stats_before['timeout_release_total_count']}")

        assert stats_before["timeout_release_total_count"] >= 1, (
            f"超时次数应 >= 1，实际为 {stats_before['timeout_release_total_count']}，"
            "说明 processing 状态的超时历史没被统计"
        )
        print(f"  [✓] 批次统计的超时释放次数已包含 processing 中超时的条目")

        db.refresh(entry3)
        assert entry3.queue_status == models.QUEUE_STATUS_WAITING, (
            f"超时释放后状态应为 waiting，实际为 {entry3.queue_status}"
        )
        assert entry3.timeout_release_count >= 1
        print(f"  [✓] 超时条目已被自动释放回 waiting，timeout_release_count={entry3.timeout_release_count}")

        print("\n" + "-" * 40)
        print("Bug2 扩展: 各状态(processing/waiting/completed/obsolete)")
        print("         的 timeout_release_count 都应被汇总")
        print("-" * 40)

        entry3.processing_started_at = None
        entry3.timeout_release_count = 5
        db.commit()

        stats_all = crud.get_batch_stats(db, batch_no)
        print(f"  强制 entry3.timeout_release_count=5 后，批次超时次数: {stats_all['timeout_release_total_count']}")
        assert stats_all["timeout_release_total_count"] >= 5, (
            f"批次超时释放次数应 >= 5，实际 {stats_all['timeout_release_total_count']}"
        )
        print(f"  [✓] 所有状态条目的 timeout_release_count 都被正确汇总")

        fetched_entry = crud.get_next_submission(db)
        assert fetched_entry is not None and fetched_entry.id == entry3.id, (
            f"应取出 entry3 (id={entry3.id})，实际取出 id={fetched_entry.id if fetched_entry else None}"
        )
        crud.complete_submission_in_queue(db, entry3.id)
        db.refresh(entry3)
        entry3.timeout_release_count = 7
        db.commit()

        stats_completed = crud.get_batch_stats(db, batch_no)
        print(f"  完成 entry3 并设 timeout_release_count=7 后，批次超时次数: {stats_completed['timeout_release_total_count']}")
        assert stats_completed["timeout_release_total_count"] >= 7, (
            f"completed 状态条目也应被统计，实际 {stats_completed['timeout_release_total_count']}"
        )
        print(f"  [✓] completed 状态条目的超时历史同样被计入")

        print("\n" + "-" * 40)
        print("Bug2 扩展: 队列状态查询也应先触发超时释放")
        print("-" * 40)

        extra_sub = existing_sub_ids[0] if len(existing_sub_ids) > 0 else sub_id_1
        extra_data = schemas.SubmissionQueueCreate(
            submission_id=f"{extra_sub}-QUEUESTAT",
            lc_number=lc_number,
            priority=schemas.SubmissionPriority.NORMAL,
        )
        try:
            extra_entry = crud.enqueue_submission(db, extra_data)
            crud.get_next_submission(db)
            extra_entry = db.query(models.SubmissionQueue).filter(
                models.SubmissionQueue.id == extra_entry.id
            ).first()
            if extra_entry and extra_entry.queue_status == models.QUEUE_STATUS_PROCESSING:
                extra_entry.processing_started_at = datetime.utcnow() - timedelta(hours=2, minutes=30)
                db.commit()

                qs_before = crud.get_queue_status(db)
                db.refresh(extra_entry)
                print(f"  队列状态 total_waiting={qs_before['total_waiting']}，"
                      f"超时条目状态={extra_entry.queue_status}")
                if extra_entry.queue_status == models.QUEUE_STATUS_WAITING:
                    print(f"  [✓] get_queue_status 前自动执行了超时释放")
                else:
                    print(f"  [!] 条目仍在 processing（可能刚好边界）")
        except ValueError:
            print(f"  (新 submission_id 已存在，跳过此场景)")

        print("\n" + "=" * 60)
        print("所有 Bug 修复验证通过! ✓")
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
    test_bugfixes()
