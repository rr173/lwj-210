import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date, timedelta

from app.database import Base, get_db
from app import models, crud

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/lc_audit.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("=" * 70)
print("审单员工作量统计验证（真实数据库）")
print("=" * 70)

db = SessionLocal()

try:
    reviewers = db.query(models.Reviewer).all()
    print(f"\n共有 {len(reviewers)} 名审单员")

    today = date.today()
    start_date = today - timedelta(days=365)
    end_date = today + timedelta(days=1)

    for reviewer in reviewers:
        print(f"\n--- {reviewer.employee_id} - {reviewer.name} (id: {reviewer.id}) ---")
        stats = crud.get_reviewer_stats(db, reviewer.id, start_date, end_date)

        print(f"  统计区间: {stats['start_date']} ~ {stats['end_date']}")
        print(f"  复核笔数 (total_reviewed): {stats['total_reviewed']} (类型: {type(stats['total_reviewed']).__name__})")
        print(f"  确认笔数 (confirm_count): {stats['confirm_count']} (类型: {type(stats['confirm_count']).__name__})")
        print(f"  推翻笔数 (overrule_count): {stats['overrule_count']} (类型: {type(stats['overrule_count']).__name__})")
        print(f"  确认率 (confirm_rate): {stats['confirm_rate']} (类型: {type(stats['confirm_rate']).__name__})")
        print(f"  平均耗时 (avg_review_duration_seconds): {stats['avg_review_duration_seconds']} (类型: {type(stats['avg_review_duration_seconds']).__name__})")
        print(f"  总耗时 (total_review_duration_seconds): {stats['total_review_duration_seconds']} (类型: {type(stats['total_review_duration_seconds']).__name__})")

        all_numbers = all(isinstance(v, (int, float)) for k, v in stats.items() 
                         if k not in ['reviewer_id', 'reviewer_name', 'employee_id', 'start_date', 'end_date'])
        if all_numbers:
            print("  ✅ 所有统计字段都是数字类型")
        else:
            print("  ❌ 存在非数字类型的统计字段")

    print("\n" + "=" * 70)
    print("验证完成！")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ 验证出错: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
