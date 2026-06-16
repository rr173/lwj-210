import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from app.database import SessionLocal
from app import crud, models, schemas

db = SessionLocal()

print("=" * 70)
print("真实数据库状态检查与迁移")
print("=" * 70)

print("\n1. 执行数据迁移...")
migrated = crud.migrate_existing_audit_records(db)
print(f"   迁移了 {migrated} 项")

print("\n2. 检查预置数据的复核状态...")
from sqlalchemy import text
try:
    audits = db.query(models.AuditRecord).limit(3).all()
    if audits:
        for i, audit in enumerate(audits):
            print(f"   审核记录 {i+1}: {audit.submission_id}")
            print(f"     review_status = {audit.review_status}")
            print(f"     auto_conclusion = {audit.auto_conclusion}")
            print(f"     conclusion = {audit.conclusion}")
            if audit.review_status == models.REVIEW_STATUS_PENDING:
                print(f"     ✅ 复核状态正确")
            else:
                print(f"     ⚠️  复核状态: {audit.review_status}")
    else:
        print("   没有找到审核记录")
except Exception as e:
    print(f"   查询出错: {e}")

print("\n3. 检查不符点新字段...")
try:
    discs = db.query(models.Discrepancy).limit(2).all()
    if discs:
        for i, d in enumerate(discs):
            print(f"   不符点 {i+1}: {d.discrepancy_type}")
            print(f"     source = {d.source}")
            print(f"     is_removed = {d.is_removed}")
    else:
        print("   没有找到不符点")
except Exception as e:
    print(f"   查询出错: {e}")

print("\n4. 检查审单员表...")
try:
    reviewers = db.query(models.Reviewer).all()
    print(f"   审单员数量: {len(reviewers)}")
    for r in reviewers:
        print(f"     {r.employee_id} - {r.name}")
except Exception as e:
    print(f"   查询出错: {e}")

print("\n5. 快速功能验证 - 创建测试审单员并统计...")
try:
    test_reviewer = crud.get_reviewer_by_employee_id(db, "VERIFY-001")
    if not test_reviewer:
        test_reviewer = crud.create_reviewer(db, schemas.ReviewerCreate(
            employee_id="VERIFY-001",
            name="验证账号",
            department="验证部门"
        ))
        print(f"   创建了测试审单员: {test_reviewer.employee_id}")
    else:
        print(f"   测试审单员已存在: {test_reviewer.employee_id}")

    today = date.today()
    stats = crud.get_reviewer_stats(db, test_reviewer.id, today - timedelta(days=30), today + timedelta(days=1))
    print(f"   统计结果:")
    print(f"     total_reviewed = {stats['total_reviewed']} (类型: {type(stats['total_reviewed']).__name__})")
    print(f"     confirm_count = {stats['confirm_count']}")
    print(f"     confirm_rate = {stats['confirm_rate']}")
    print(f"     avg_review_duration_seconds = {stats['avg_review_duration_seconds']} (类型: {type(stats['avg_review_duration_seconds']).__name__})")

    if isinstance(stats['total_reviewed'], int) and isinstance(stats['avg_review_duration_seconds'], float):
        print(f"   ✅ 统计字段都是数字类型")
    else:
        print(f"   ❌ 统计字段类型不正确")

except Exception as e:
    print(f"   验证出错: {e}")
    import traceback
    traceback.print_exc()

db.close()

print("\n" + "=" * 70)
print("验证完成！")
print("=" * 70)
