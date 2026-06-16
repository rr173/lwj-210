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
print("费用状态与复核状态对应检查")
print("=" * 70)

db = SessionLocal()

try:
    audits = db.query(models.AuditRecord).all()
    for i, audit in enumerate(audits):
        print(f"\n审核记录 {i+1}: {audit.submission_id}")
        print(f"  审核结论 (conclusion): {audit.conclusion}")
        print(f"  系统结论 (auto_conclusion): {audit.auto_conclusion}")
        print(f"  最终结论 (final_conclusion): {audit.final_conclusion}")
        print(f"  复核状态 (review_status): {audit.review_status}")

        fee = db.query(models.FeeRecord).filter(
            models.FeeRecord.audit_record_id == audit.id
        ).first()
        if fee:
            print(f"  费用状态 (fee.status): {fee.status}")
            expected = crud.determine_fee_status(audit.conclusion)
            match = "✅" if fee.status == expected else "❌"
            print(f"  预期费用状态: {expected} {match}")
        else:
            print(f"  ⚠️  没有找到费用记录")

        opinions = db.query(models.ReviewOpinion).filter(
            models.ReviewOpinion.audit_record_id == audit.id
        ).all()
        if opinions:
            print(f"  复核意见数: {len(opinions)}")
            for op in opinions:
                print(f"    - {op.action_type} by reviewer {op.reviewer_id}")
        else:
            print(f"  复核意见数: 0")

    print("\n" + "=" * 70)
    print("检查完成！")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ 检查出错: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
