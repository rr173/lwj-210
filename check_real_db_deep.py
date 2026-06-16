import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import models, crud

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/lc_audit.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("=" * 70)
print("真实数据库深度检查")
print("=" * 70)

db = SessionLocal()

try:
    print("\n1. 检查表结构 - audit_records 表的列...")
    result = db.execute(text("PRAGMA table_info(audit_records)")).fetchall()
    columns = [row[1] for row in result]
    print(f"   总列数: {len(columns)}")
    print(f"   列名: {columns}")

    has_review_status = "review_status" in columns
    has_auto_conclusion = "auto_conclusion" in columns
    has_final_conclusion = "final_conclusion" in columns

    print(f"   review_status: {'✅ 存在' if has_review_status else '❌ 缺失'}")
    print(f"   auto_conclusion: {'✅ 存在' if has_auto_conclusion else '❌ 缺失'}")
    print(f"   final_conclusion: {'✅ 存在' if has_final_conclusion else '❌ 缺失'}")

    print("\n2. 检查审核记录数量和复核状态分布...")
    total_count = db.query(models.AuditRecord).count()
    print(f"   总审核记录数: {total_count}")

    if has_review_status:
        pending_count = db.query(models.AuditRecord).filter(
            models.AuditRecord.review_status == models.REVIEW_STATUS_PENDING
        ).count()
        in_review_count = db.query(models.AuditRecord).filter(
            models.AuditRecord.review_status == models.REVIEW_STATUS_IN_REVIEW
        ).count()
        reviewed_count = db.query(models.AuditRecord).filter(
            models.AuditRecord.review_status == models.REVIEW_STATUS_REVIEWED
        ).count()
        null_count = db.query(models.AuditRecord).filter(
            models.AuditRecord.review_status == None
        ).count()

        print(f"   待复核 (pending_review): {pending_count}")
        print(f"   复核中 (in_review): {in_review_count}")
        print(f"   已复核 (reviewed): {reviewed_count}")
        print(f"   空值 (NULL): {null_count}")

        if null_count > 0:
            print("   ⚠️  存在 NULL 复核状态的记录，需要迁移！")
        else:
            print("   ✅ 所有记录都有复核状态")
    else:
        print("   ⚠️  没有 review_status 列，需要执行迁移")

    print("\n3. 检查费用状态分布...")
    fee_records = db.query(models.FeeRecord).all()
    print(f"   总费用记录数: {len(fee_records)}")
    if fee_records:
        status_counts = {}
        for fr in fee_records:
            status_counts[fr.status] = status_counts.get(fr.status, 0) + 1
        for status, count in status_counts.items():
            print(f"     {status}: {count} 笔")

    print("\n4. 检查 review_opinions 表...")
    try:
        opinions = db.query(models.ReviewOpinion).all()
        print(f"   复核意见总数: {len(opinions)}")
        if opinions:
            action_counts = {}
            for op in opinions:
                action_counts[op.action_type] = action_counts.get(op.action_type, 0) + 1
            for action, count in action_counts.items():
                print(f"     {action}: {count} 笔")
    except Exception as e:
        print(f"   ⚠️  表不存在或出错: {e}")

    print("\n5. 检查 reviewers 和 review_assignments 表...")
    try:
        reviewers = db.query(models.Reviewer).all()
        print(f"   审单员数量: {len(reviewers)}")
        for r in reviewers:
            print(f"     {r.employee_id} - {r.name}")
    except Exception as e:
        print(f"   ⚠️  reviewers 表不存在或出错: {e}")

    try:
        assignments = db.query(models.ReviewAssignment).all()
        print(f"   复核分配记录数: {len(assignments)}")
    except Exception as e:
        print(f"   ⚠️  review_assignments 表不存在或出错: {e}")

    print("\n" + "=" * 70)
    print("检查完成！")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ 检查出错: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
