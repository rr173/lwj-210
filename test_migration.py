import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.database import SessionLocal
from app import crud, models, schemas

print("=" * 60)
print("测试1: 旧数据库迁移验证")
print("=" * 60)

db = SessionLocal()

print("\n1. 迁移前检查...")
try:
    audit = crud.get_audit_record_by_submission(db, 'SUB-SEA-CIF-2024-001')
    if audit:
        print(f"   审核记录存在: ID={audit.id}")
        print(f"   review_status: {audit.review_status}")
        print(f"   auto_conclusion: {audit.auto_conclusion}")
        print(f"   final_conclusion: {audit.final_conclusion}")
    else:
        print("   未找到审核记录")
except Exception as e:
    print(f"   查询出错: {e}")

print("\n2. 执行数据迁移...")
count = crud.migrate_existing_audit_records(db)
print(f"   迁移了 {count} 项")

print("\n3. 迁移后检查...")
audit = crud.get_audit_record_by_submission(db, 'SUB-SEA-CIF-2024-001')
if audit:
    print(f"   review_status: {audit.review_status}")
    print(f"   auto_conclusion: {audit.auto_conclusion}")
    print(f"   final_conclusion: {audit.final_conclusion}")
    if audit.review_status == models.REVIEW_STATUS_PENDING:
        print("   ✅ 复核状态正确: pending_review")
    else:
        print(f"   ❌ 复核状态错误: {audit.review_status}")

print("\n4. 检查不符点新字段...")
if audit and audit.discrepancies:
    d = audit.discrepancies[0]
    print(f"   不符点 ID: {d.id}")
    print(f"   source: {d.source}")
    print(f"   is_removed: {d.is_removed}")
    if d.source == "auto" and d.is_removed == False:
        print("   ✅ 不符点字段正确")
    else:
        print("   ❌ 不符点字段有问题")

print("\n" + "=" * 60)
print("测试2: 审单员注册与认领")
print("=" * 60)

print("\n5. 创建审单员...")
try:
    reviewer = crud.create_reviewer(db, schemas.ReviewerCreate(
        employee_id="TEST-R001",
        name="测试审单员",
        department="测试部"
    ))
    print(f"   ✅ 审单员创建成功: {reviewer.employee_id} - {reviewer.name}")
except ValueError as e:
    reviewer = crud.get_reviewer_by_employee_id(db, "TEST-R001")
    print(f"   审单员已存在: {reviewer.employee_id}")

print("\n6. 认领复核任务...")
try:
    assignment = crud.claim_review_task(db, audit.id, "TEST-R001")
    print(f"   ✅ 认领成功: 任务ID={assignment.id}")
    print(f"   认领时间: {assignment.claimed_at}")
    print(f"   到期时间: {assignment.expires_at}")
except ValueError as e:
    print(f"   认领失败: {e}")
    assignment = crud.get_active_assignment_for_audit(db, audit.id)
    if assignment:
        print(f"   当前认领人ID: {assignment.reviewer_id}")

db.refresh(audit)
print(f"   当前审核状态: {audit.review_status}")

print("\n" + "=" * 60)
print("测试3: 确认复核与费用状态")
print("=" * 60)

print("\n7. 复核前费用状态...")
fee_records = db.query(models.FeeRecord).filter(
    models.FeeRecord.audit_record_id == audit.id
).all()
for fr in fee_records:
    print(f"   费用编号: {fr.fee_number}")
    print(f"   当前状态: {fr.status}")

print("\n8. 执行确认复核...")
review_data = schemas.ReviewCompleteRequest(
    action=schemas.ReviewAction.CONFIRM,
    remarks="测试确认复核"
)
result = crud.complete_review(db, audit.id, reviewer.id, review_data)
print(f"   ✅ 复核完成")
print(f"   最终结论: {result['audit_record'].final_conclusion}")
print(f"   复核耗时: {result['review_duration_seconds']} 秒")
print(f"   审核状态: {result['audit_record'].review_status}")

print("\n9. 复核后费用状态...")
for fr in fee_records:
    db.refresh(fr)
    print(f"   费用编号: {fr.fee_number}")
    print(f"   当前状态: {fr.status}")

expected_status = crud.determine_fee_status(result['audit_record'].final_conclusion)
actual_status = fee_records[0].status if fee_records else None
if actual_status == expected_status:
    print(f"   ✅ 费用状态正确: {actual_status}")
else:
    print(f"   ❌ 费用状态错误: 实际={actual_status}, 预期={expected_status}")

print("\n" + "=" * 60)
print("测试4: 工作量统计")
print("=" * 60)

print("\n10. 查询统计数据...")
today = date.today()
start_date = today - timedelta(days=30)
end_date = today + timedelta(days=1)
stats = crud.get_reviewer_stats(db, reviewer.id, start_date, end_date)

print(f"    审单员: {stats['reviewer_name']} ({stats['employee_id']})")
print(f"    统计范围: {stats['start_date']} ~ {stats['end_date']}")
print(f"    复核笔数: {stats['total_reviewed']}")
print(f"    确认笔数: {stats['confirm_count']}")
print(f"    确认率: {stats['confirm_rate']}")
print(f"    平均耗时: {stats['avg_review_duration_seconds']} 秒")
print(f"    总耗时: {stats['total_review_duration_seconds']} 秒")

all_numbers = (
    isinstance(stats['total_reviewed'], int) and
    isinstance(stats['confirm_count'], int) and
    isinstance(stats['confirm_rate'], float) and
    isinstance(stats['avg_review_duration_seconds'], float) and
    isinstance(stats['total_review_duration_seconds'], int)
)

if stats['total_reviewed'] >= 1 and all_numbers:
    print(f"    ✅ 统计数据正确，都是数字类型")
else:
    print(f"    ❌ 统计数据有问题")
    print(f"       total_reviewed 类型: {type(stats['total_reviewed'])}")
    print(f"       avg_review_duration_seconds 类型: {type(stats['avg_review_duration_seconds'])}")

db.close()

print("\n" + "=" * 60)
print("所有测试完成！")
print("=" * 60)
