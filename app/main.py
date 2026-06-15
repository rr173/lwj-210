from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.database import get_db, Base, engine
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def create_app() -> FastAPI:
    app = FastAPI(
        title="外贸信用证单据审核与不符点检测服务",
        description="银行信用证单据自动审核系统，支持7大类校验规则与不符点检测",
        version="1.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        init_db()
        seed_data()

    @app.get("/", tags=["系统"])
    async def root():
        return {
            "service": "外贸信用证单据审核与不符点检测服务",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "redoc": "/redoc"
        }

    @app.get("/health", tags=["系统"])
    async def health_check():
        return {"status": "healthy"}

    @app.post("/api/lc", response_model=schemas.LetterOfCreditResponse, tags=["信用证管理"], status_code=status.HTTP_201_CREATED)
    async def create_lc(lc_data: schemas.LetterOfCreditCreate, db: Session = Depends(get_db)):
        existing = crud.get_letter_of_credit_by_number(db, lc_data.lc_number)
        if existing:
            raise HTTPException(status_code=400, detail=f"信用证编号 {lc_data.lc_number} 已存在")
        try:
            lc = crud.create_letter_of_credit(db, lc_data)
            return lc
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建信用证失败: {str(e)}")

    @app.get("/api/lc", response_model=List[schemas.LetterOfCreditResponse], tags=["信用证管理"])
    async def list_lc(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        return crud.get_all_letter_of_credits(db, skip, limit)

    @app.get("/api/lc/{lc_number}", response_model=schemas.LetterOfCreditResponse, tags=["信用证管理"])
    async def get_lc(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return lc

    @app.put("/api/lc/{lc_number}", response_model=schemas.LetterOfCreditResponse, tags=["信用证管理"])
    async def update_lc(lc_number: str, lc_data: schemas.LetterOfCreditCreate, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        if lc_data.lc_number != lc_number:
            other = crud.get_letter_of_credit_by_number(db, lc_data.lc_number)
            if other and other.id != lc.id:
                raise HTTPException(status_code=400, detail=f"新信用证编号 {lc_data.lc_number} 已被其他信用证使用")
        updated = crud.update_letter_of_credit(db, lc.id, lc_data)
        return updated

    @app.delete("/api/lc/{lc_number}", tags=["信用证管理"])
    async def delete_lc(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        crud.delete_letter_of_credit(db, lc.id)
        return {"message": f"信用证 {lc_number} 已删除"}

    @app.post("/api/submission", response_model=schemas.AuditRecordResponse, tags=["单据提交与审核"], status_code=status.HTTP_201_CREATED)
    async def submit_and_audit(submission: schemas.SubmissionSubmit, db: Session = Depends(get_db)):
        try:
            audit_record = crud.submit_documents_and_audit(db, submission)
            return audit_record
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"审核失败: {str(e)}")

    @app.get("/api/submission/{submission_id}", response_model=schemas.AuditRecordDetailResponse, tags=["单据提交与审核"])
    async def get_submission_detail(submission_id: str, db: Session = Depends(get_db)):
        audit_record = crud.get_audit_record_by_submission(db, submission_id)
        if not audit_record:
            raise HTTPException(status_code=404, detail=f"提交记录 {submission_id} 不存在")

        lc = crud.get_letter_of_credit_by_id(db, audit_record.lc_id)
        documents = crud.get_documents_by_submission(db, submission_id)

        return {
            "id": audit_record.id,
            "lc_id": audit_record.lc_id,
            "submission_id": audit_record.submission_id,
            "original_submission_id": audit_record.original_submission_id,
            "resubmission_round": audit_record.resubmission_round,
            "modification_remark": audit_record.modification_remark,
            "conclusion": audit_record.conclusion,
            "total_discrepancies": audit_record.total_discrepancies,
            "critical_count": audit_record.critical_count,
            "minor_count": audit_record.minor_count,
            "presentation_date": audit_record.presentation_date,
            "discrepancies": audit_record.discrepancies,
            "created_at": audit_record.created_at,
            "lc": lc,
            "documents": documents
        }

    @app.post("/api/submission/{submission_id}/resubmit", response_model=schemas.AuditRecordResponse, tags=["修改重提"], status_code=status.HTTP_201_CREATED)
    async def resubmit_submission(submission_id: str, resubmit: schemas.SubmissionResubmitRequest, db: Session = Depends(get_db)):
        try:
            audit_record = crud.resubmit_documents_and_audit(db, submission_id, resubmit)
            return audit_record
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"修改重提审核失败: {str(e)}")

    @app.get("/api/submission/{submission_id}/history", response_model=schemas.SubmissionHistoryResponse, tags=["修改重提"])
    async def get_submission_history(submission_id: str, db: Session = Depends(get_db)):
        records = crud.get_audit_records_by_original_submission(db, submission_id)
        if not records:
            raise HTTPException(status_code=404, detail=f"交单 {submission_id} 不存在")

        lc = crud.get_letter_of_credit_by_id(db, records[0].lc_id)
        latest_record = records[-1]

        return {
            "original_submission_id": submission_id,
            "lc_number": lc.lc_number if lc else "",
            "total_rounds": len(records),
            "max_allowed_rounds": crud.MAX_RESUBMISSION_ROUNDS + 1,
            "current_conclusion": latest_record.conclusion,
            "history": records
        }

    @app.get("/api/audit/lc/{lc_number}", response_model=List[schemas.AuditRecordResponse], tags=["查询"])
    async def get_audit_history_by_lc(lc_number: str, db: Session = Depends(get_db)):
        records = crud.get_audit_records_by_lc(db, lc_number)
        if not records:
            lc = crud.get_letter_of_credit_by_number(db, lc_number)
            if not lc:
                raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return records

    @app.get("/api/audit/all", response_model=List[schemas.AuditRecordResponse], tags=["查询"])
    async def list_all_audits(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        return crud.get_all_audit_records(db, skip, limit)

    @app.get("/api/stats/discrepancies", response_model=List[schemas.DiscrepancyStatsResponse], tags=["查询统计"])
    async def get_discrepancy_stats(db: Session = Depends(get_db)):
        return crud.get_discrepancy_statistics(db)

    @app.get("/api/stats/beneficiary/{beneficiary_name}", response_model=schemas.BeneficiaryDiscrepancyRateResponse, tags=["查询统计"])
    async def get_beneficiary_rate(beneficiary_name: str, db: Session = Depends(get_db)):
        return crud.get_beneficiary_discrepancy_rate(db, beneficiary_name)

    @app.post("/api/amendment", response_model=schemas.AmendmentResponse, tags=["信用证修改"], status_code=status.HTTP_201_CREATED)
    async def create_amendment(amendment_data: schemas.AmendmentCreate, db: Session = Depends(get_db)):
        try:
            amendment = crud.create_amendment(db, amendment_data)
            return amendment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建修改请求失败: {str(e)}")

    @app.get("/api/amendment/{amendment_number}", response_model=schemas.AmendmentResponse, tags=["信用证修改"])
    async def get_amendment(amendment_number: str, db: Session = Depends(get_db)):
        amendment = crud.get_amendment_by_number(db, amendment_number)
        if not amendment:
            raise HTTPException(status_code=404, detail=f"修改 {amendment_number} 不存在")
        crud.check_and_expire_amendments(db, amendment.lc_id)
        db.refresh(amendment)
        return amendment

    @app.post("/api/amendment/{amendment_number}/action", response_model=schemas.AmendmentResponse, tags=["信用证修改"])
    async def amendment_action(amendment_number: str, action_req: schemas.AmendmentActionRequest, db: Session = Depends(get_db)):
        action = action_req.action.lower()
        if action not in ["accept", "reject"]:
            raise HTTPException(status_code=400, detail=f"无效的操作: {action}，仅支持 accept 或 reject")
        try:
            if action == "accept":
                amendment = crud.accept_amendment(db, amendment_number)
            else:
                amendment = crud.reject_amendment(db, amendment_number)
            return amendment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"修改操作失败: {str(e)}")

    @app.get("/api/lc/{lc_number}/amendments", response_model=List[schemas.AmendmentResponse], tags=["信用证修改"])
    async def get_lc_amendments(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        crud.check_and_expire_amendments(db, lc.id)
        return crud.get_amendments_by_lc(db, lc_number)

    @app.get("/api/amendment/{amendment_number}/snapshot", response_model=schemas.AmendmentSnapshotResponse, tags=["信用证修改"])
    async def get_amendment_snapshot(amendment_number: str, db: Session = Depends(get_db)):
        try:
            snapshot = crud.get_amendment_snapshot(db, amendment_number)
            return snapshot
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/amendments/pending", response_model=List[schemas.AmendmentResponse], tags=["信用证修改"])
    async def list_pending_amendments(db: Session = Depends(get_db)):
        from app.models import AMENDMENT_STATUS_PENDING
        amendments = crud.get_all_pending_amendments(db)
        result = []
        for a in amendments:
            crud.check_and_expire_amendments(db, a.lc_id)
            db.refresh(a)
            if a.status == AMENDMENT_STATUS_PENDING:
                result.append(a)
        return result

    @app.post("/api/amendments/expire-check", tags=["信用证修改"])
    async def expire_overdue_amendments(db: Session = Depends(get_db)):
        count = crud.expire_all_overdue_amendments(db)
        return {"expired_count": count, "message": f"已将 {count} 个过期修改标记为 expired"}

    @app.get("/api/lc/{lc_number}/with-amendments", response_model=schemas.LcWithAmendmentsResponse, tags=["信用证管理"])
    async def get_lc_with_amendments(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        crud.check_and_expire_amendments(db, lc.id)
        amendments = crud.get_amendments_by_lc(db, lc_number)
        result = {
            "id": lc.id,
            "lc_number": lc.lc_number,
            "issuing_bank": lc.issuing_bank,
            "beneficiary_name": lc.beneficiary_name,
            "applicant_name": lc.applicant_name,
            "currency": lc.currency,
            "amount": lc.amount,
            "latest_shipment_date": lc.latest_shipment_date,
            "latest_presentation_date": lc.latest_presentation_date,
            "expiry_date": lc.expiry_date,
            "transport_mode": lc.transport_mode,
            "port_of_loading": lc.port_of_loading,
            "port_of_discharge": lc.port_of_discharge,
            "partial_shipment_allowed": lc.partial_shipment_allowed,
            "transshipment_allowed": lc.transshipment_allowed,
            "goods_description": lc.goods_description,
            "additional_terms": lc.additional_terms,
            "document_requirements": lc.document_requirements,
            "created_at": lc.created_at,
            "fee_tier": lc.fee_tier,
            "amendments": amendments
        }
        return result

    @app.get("/api/fees/lc/{lc_number}", response_model=schemas.LcFeeSummaryResponse, tags=["收费管理"])
    async def get_lc_fee_summary(lc_number: str, db: Session = Depends(get_db)):
        try:
            result = crud.get_fee_records_by_lc(db, lc_number)
            return result
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询费用失败: {str(e)}")

    @app.get("/api/fees/summary", response_model=schemas.FeeSummaryResponse, tags=["收费管理"])
    async def get_fee_summary(
        start_date: date,
        end_date: date,
        db: Session = Depends(get_db)
    ):
        try:
            if start_date > end_date:
                raise HTTPException(status_code=400, detail="开始日期不能大于结束日期")
            result = crud.get_fee_records_by_time_range(db, start_date, end_date)
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询费用汇总失败: {str(e)}")

    @app.get("/api/fees/all", response_model=List[schemas.FeeRecordResponse], tags=["收费管理"])
    async def list_all_fees(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        return crud.get_all_fee_records(db, skip, limit)

    return app


app = create_app()
