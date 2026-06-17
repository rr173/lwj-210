from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime

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
        try:
            updated = crud.update_letter_of_credit(db, lc.id, lc_data)
            return updated
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"更新信用证失败: {str(e)}")

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
            "auto_conclusion": audit_record.auto_conclusion,
            "final_conclusion": audit_record.final_conclusion,
            "total_discrepancies": audit_record.total_discrepancies,
            "critical_count": audit_record.critical_count,
            "minor_count": audit_record.minor_count,
            "presentation_date": audit_record.presentation_date,
            "review_status": audit_record.review_status,
            "rule_version_id": audit_record.rule_version_id,
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

    @app.post("/api/reviewers", response_model=schemas.ReviewerResponse, tags=["审单员管理"], status_code=status.HTTP_201_CREATED)
    async def create_reviewer(reviewer_data: schemas.ReviewerCreate, db: Session = Depends(get_db)):
        try:
            return crud.create_reviewer(db, reviewer_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/reviewers", response_model=List[schemas.ReviewerResponse], tags=["审单员管理"])
    async def list_reviewers(skip: int = 0, limit: int = 100, active_only: bool = True, db: Session = Depends(get_db)):
        return crud.get_all_reviewers(db, skip, limit, active_only)

    @app.get("/api/reviewers/{employee_id}", response_model=schemas.ReviewerResponse, tags=["审单员管理"])
    async def get_reviewer(employee_id: str, db: Session = Depends(get_db)):
        reviewer = crud.get_reviewer_by_employee_id(db, employee_id)
        if not reviewer:
            raise HTTPException(status_code=404, detail=f"审单员工号 {employee_id} 不存在")
        return reviewer

    @app.get("/api/review/pending", response_model=List[schemas.AuditRecordResponse], tags=["审单员工作台"])
    async def list_pending_reviews(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        return crud.get_pending_review_audits(db, skip, limit)

    @app.post("/api/audit/{audit_record_id}/claim", response_model=schemas.ReviewAssignmentResponse, tags=["审单员工作台"])
    async def claim_review(audit_record_id: int, claim_req: schemas.ReviewClaimRequest, db: Session = Depends(get_db)):
        try:
            assignment = crud.claim_review_task(db, audit_record_id, claim_req.employee_id)
            reviewer = crud.get_reviewer_by_id(db, assignment.reviewer_id)
            return {
                "id": assignment.id,
                "audit_record_id": assignment.audit_record_id,
                "reviewer_id": assignment.reviewer_id,
                "reviewer_name": reviewer.name if reviewer else None,
                "claimed_at": assignment.claimed_at,
                "expires_at": assignment.expires_at,
                "completed_at": assignment.completed_at,
                "is_expired": assignment.is_expired
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/reviewer/{employee_id}/assignments", response_model=List[schemas.ReviewAssignmentResponse], tags=["审单员工作台"])
    async def get_reviewer_assignments(employee_id: str, db: Session = Depends(get_db)):
        reviewer = crud.get_reviewer_by_employee_id(db, employee_id)
        if not reviewer:
            raise HTTPException(status_code=404, detail=f"审单员工号 {employee_id} 不存在")
        assignments = crud.get_reviewer_active_assignments(db, reviewer.id)
        result = []
        for assignment in assignments:
            result.append({
                "id": assignment.id,
                "audit_record_id": assignment.audit_record_id,
                "reviewer_id": assignment.reviewer_id,
                "reviewer_name": reviewer.name,
                "claimed_at": assignment.claimed_at,
                "expires_at": assignment.expires_at,
                "completed_at": assignment.completed_at,
                "is_expired": assignment.is_expired
            })
        return result

    @app.get("/api/audit/{audit_record_id}/review", response_model=schemas.AuditRecordWithReviewResponse, tags=["审单员工作台"])
    async def get_audit_for_review(audit_record_id: int, db: Session = Depends(get_db)):
        result = crud.get_audit_record_with_review(db, audit_record_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"审核记录 {audit_record_id} 不存在")
        return result

    @app.post("/api/audit/{audit_record_id}/review", tags=["审单员工作台"])
    async def complete_review(audit_record_id: int, review_data: schemas.ReviewCompleteRequest, db: Session = Depends(get_db)):
        assignments = crud.get_active_assignment_for_audit(db, audit_record_id)
        if not assignments:
            raise HTTPException(status_code=400, detail="该交单未被认领或认领已过期")

        try:
            result = crud.complete_review(db, audit_record_id, assignments.reviewer_id, review_data)
            return {
                "message": "复核完成",
                "submission_id": result["audit_record"].submission_id,
                "final_conclusion": result["audit_record"].final_conclusion,
                "review_duration_seconds": result["review_duration_seconds"],
                "review_status": result["audit_record"].review_status
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/review/expire-check", tags=["审单员工作台"])
    async def expire_overdue_reviews(db: Session = Depends(get_db)):
        count = crud.expire_overdue_assignments(db)
        return {"expired_count": count, "message": f"已释放 {count} 个过期认领任务"}

    @app.get("/api/reviewer/{employee_id}/stats", response_model=schemas.ReviewerStatsResponse, tags=["审单员工作台"])
    async def get_reviewer_statistics(
        employee_id: str,
        start_date: date,
        end_date: date,
        db: Session = Depends(get_db)
    ):
        reviewer = crud.get_reviewer_by_employee_id(db, employee_id)
        if not reviewer:
            raise HTTPException(status_code=404, detail=f"审单员工号 {employee_id} 不存在")
        try:
            if start_date > end_date:
                raise HTTPException(status_code=400, detail="开始日期不能大于结束日期")
            return crud.get_reviewer_stats(db, reviewer.id, start_date, end_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/transfer", response_model=schemas.TransferResponse, tags=["信用证转让"], status_code=status.HTTP_201_CREATED)
    async def create_transfer(transfer_data: schemas.TransferCreate, db: Session = Depends(get_db)):
        try:
            transfer = crud.create_transfer(db, transfer_data)
            return transfer
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建转让申请失败: {str(e)}")

    @app.get("/api/transfer/{transfer_number}", response_model=schemas.TransferDetailResponse, tags=["信用证转让"])
    async def get_transfer(transfer_number: str, db: Session = Depends(get_db)):
        result = crud.get_transfer_detail(db, transfer_number)
        if not result:
            raise HTTPException(status_code=404, detail=f"转让证 {transfer_number} 不存在")
        return result

    @app.post("/api/transfer/{transfer_number}/action", response_model=schemas.TransferResponse, tags=["信用证转让"])
    async def transfer_action(transfer_number: str, action_req: schemas.TransferConfirmRequest, db: Session = Depends(get_db)):
        action = action_req.action.lower()
        if action not in ["confirm", "reject"]:
            raise HTTPException(status_code=400, detail=f"无效的操作: {action}，仅支持 confirm 或 reject")
        try:
            transfer = crud.confirm_transfer(db, transfer_number, action)
            return transfer
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"转让操作失败: {str(e)}")

    @app.get("/api/lc/{lc_number}/transfers", response_model=List[schemas.TransferResponse], tags=["信用证转让"])
    async def get_lc_transfers(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return crud.get_transfers_by_lc(db, lc_number)

    @app.post("/api/back-to-back", response_model=schemas.BackToBackLCResponse, tags=["背对背信用证"], status_code=status.HTTP_201_CREATED)
    async def create_back_to_back(btb_data: schemas.BackToBackLCCreate, db: Session = Depends(get_db)):
        try:
            btb = crud.create_back_to_back_lc(db, btb_data)
            return btb
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建背对背证失败: {str(e)}")

    @app.get("/api/back-to-back/{back_to_back_number}", response_model=schemas.BackToBackLCDetailResponse, tags=["背对背信用证"])
    async def get_back_to_back(back_to_back_number: str, db: Session = Depends(get_db)):
        result = crud.get_back_to_back_detail(db, back_to_back_number)
        if not result:
            raise HTTPException(status_code=404, detail=f"背对背证 {back_to_back_number} 不存在")
        return result

    @app.get("/api/lc/{lc_number}/back-to-back", response_model=List[schemas.BackToBackLCResponse], tags=["背对背信用证"])
    async def get_lc_back_to_back(lc_number: str, db: Session = Depends(get_db)):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return crud.get_back_to_back_lcs_by_lc(db, lc_number)

    @app.get("/api/lc/{lc_number}/available-amount", response_model=schemas.LcAvailableAmountResponse, tags=["转让与背对背查询"])
    async def get_available_amount(lc_number: str, db: Session = Depends(get_db)):
        try:
            return crud.get_lc_available_amount(db, lc_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询可用金额失败: {str(e)}")

    @app.get("/api/lc/{lc_number}/transfer-backtoback-summary", response_model=schemas.LcTransferBackToBackSummaryResponse, tags=["转让与背对背查询"])
    async def get_transfer_backtoback_summary(lc_number: str, db: Session = Depends(get_db)):
        try:
            return crud.get_lc_transfer_and_back_to_back_summary(db, lc_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询转让与背对背摘要失败: {str(e)}")

    @app.post("/api/alerts/scan", tags=["预警管理"])
    async def scan_and_generate_alerts(db: Session = Depends(get_db)):
        try:
            result = crud.scan_and_generate_alerts(db)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"预警扫描失败: {str(e)}")

    @app.post("/api/alerts/expire-check", tags=["预警管理"])
    async def expire_check(db: Session = Depends(get_db)):
        try:
            result = crud.check_and_process_expired_alerts(db)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"逾期检查失败: {str(e)}")

    @app.get("/api/alerts/lc/{lc_number}", response_model=List[schemas.AlertResponse], tags=["预警管理"])
    async def get_alerts_by_lc(lc_number: str, db: Session = Depends(get_db)):
        try:
            crud.check_and_process_expired_alerts(db)
            return crud.get_alerts_by_lc(db, lc_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询预警失败: {str(e)}")

    @app.get("/api/alerts/active", response_model=List[schemas.AlertResponse], tags=["预警管理"])
    async def get_active_alerts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            crud.check_and_process_expired_alerts(db)
            return crud.get_active_alerts(db, skip, limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询活跃预警失败: {str(e)}")

    @app.get("/api/alerts/{alert_number}", response_model=schemas.AlertResponse, tags=["预警管理"])
    async def get_alert_detail(alert_number: str, db: Session = Depends(get_db)):
        alert = crud.get_alert_by_number(db, alert_number)
        if not alert:
            raise HTTPException(status_code=404, detail=f"预警记录 {alert_number} 不存在")
        crud.check_and_process_expired_alerts(db)
        db.refresh(alert)
        return alert

    @app.post("/api/alerts/{alert_number}/acknowledge", response_model=schemas.AlertResponse, tags=["预警管理"])
    async def acknowledge_alert(alert_number: str, ack_req: schemas.AlertAcknowledgeRequest, db: Session = Depends(get_db)):
        try:
            return crud.acknowledge_alert(db, alert_number, ack_req.acknowledged_by)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"确认预警失败: {str(e)}")

    @app.get("/api/alerts/stats/by-type", response_model=List[schemas.AlertStatsResponse], tags=["查询统计"])
    async def get_alert_statistics(db: Session = Depends(get_db)):
        try:
            crud.check_and_process_expired_alerts(db)
            return crud.get_alert_statistics(db)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询预警统计失败: {str(e)}")

    @app.get("/api/freezes/lc/{lc_number}", response_model=List[schemas.FreezeRecordResponse], tags=["冻结管理"])
    async def get_freeze_records_by_lc(lc_number: str, db: Session = Depends(get_db)):
        try:
            return crud.get_freeze_records_by_lc(db, lc_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询冻结记录失败: {str(e)}")

    @app.get("/api/freezes/active", response_model=List[schemas.FreezeRecordResponse], tags=["冻结管理"])
    async def get_active_freezes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            return crud.get_all_active_freezes(db, skip, limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询活跃冻结失败: {str(e)}")

    @app.get("/api/freezes/{freeze_number}", response_model=schemas.FreezeRecordResponse, tags=["冻结管理"])
    async def get_freeze_detail(freeze_number: str, db: Session = Depends(get_db)):
        freeze = crud.get_freeze_record_by_number(db, freeze_number)
        if not freeze:
            raise HTTPException(status_code=404, detail=f"冻结记录 {freeze_number} 不存在")
        return freeze

    @app.post("/api/freezes/{freeze_number}/release", response_model=schemas.FreezeRecordResponse, tags=["冻结管理"])
    async def release_freeze(freeze_number: str, release_req: schemas.FreezeReleaseRequest, db: Session = Depends(get_db)):
        try:
            return crud.release_freeze(db, freeze_number, release_req.released_by, release_req.release_reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"解除冻结失败: {str(e)}")

    @app.post("/api/swift/generate", response_model=schemas.SwiftMessageResponse, tags=["SWIFT报文"], status_code=status.HTTP_201_CREATED)
    async def generate_swift_message(req: schemas.SwiftMessageGenerateRequest, db: Session = Depends(get_db)):
        try:
            msg_type = req.message_type.value if hasattr(req.message_type, 'value') else req.message_type
            if msg_type == "MT700":
                msg = crud.generate_and_enqueue_mt700(db, req.lc_number)
            elif msg_type == "MT707":
                lc = crud.get_letter_of_credit_by_number(db, req.lc_number)
                if not lc:
                    raise HTTPException(status_code=404, detail=f"信用证 {req.lc_number} 不存在")
                amendments = crud.get_amendments_by_lc(db, req.lc_number)
                if not amendments:
                    raise HTTPException(status_code=400, detail=f"信用证 {req.lc_number} 没有修改记录，无法生成MT707报文")
                latest_amendment = amendments[0]
                msg = crud.generate_and_enqueue_mt707(db, latest_amendment.amendment_number)
            elif msg_type == "MT799":
                if not req.narrative:
                    raise HTTPException(status_code=400, detail="MT799报文必须提供narrative叙述内容")
                msg = crud.generate_and_enqueue_mt799(db, req.lc_number, req.narrative)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的报文类型: {msg_type}")
            return msg
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成SWIFT报文失败: {str(e)}")

    @app.post("/api/swift/generate/mt707/{amendment_number}", response_model=schemas.SwiftMessageResponse, tags=["SWIFT报文"], status_code=status.HTTP_201_CREATED)
    async def generate_mt707_by_amendment(amendment_number: str, db: Session = Depends(get_db)):
        try:
            msg = crud.generate_and_enqueue_mt707(db, amendment_number)
            return msg
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"生成MT707报文失败: {str(e)}")

    @app.post("/api/swift/parse", response_model=schemas.SwiftParseResponse, tags=["SWIFT报文"])
    async def parse_swift_message(req: schemas.SwiftParseRequest, db: Session = Depends(get_db)):
        try:
            result = crud.parse_and_process_swift_message(db, req.raw_message)
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"解析SWIFT报文失败: {str(e)}")

    @app.get("/api/swift/{message_number}", response_model=schemas.SwiftMessageResponse, tags=["SWIFT报文"])
    async def get_swift_message(message_number: str, db: Session = Depends(get_db)):
        msg = crud.get_swift_message_by_number(db, message_number)
        if not msg:
            raise HTTPException(status_code=404, detail=f"报文 {message_number} 不存在")
        return msg

    @app.get("/api/swift/lc/{lc_number}", response_model=List[schemas.SwiftMessageResponse], tags=["SWIFT报文"])
    async def get_swift_messages_by_lc(
        lc_number: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db),
    ):
        from app.models import VALID_SWIFT_SEND_STATUSES
        if status and status not in VALID_SWIFT_SEND_STATUSES:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}，允许值: {', '.join(VALID_SWIFT_SEND_STATUSES)}")
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return crud.get_swift_messages_by_lc(db, lc_number, status=status, skip=skip, limit=limit)

    @app.get("/api/swift/query/time-range", response_model=List[schemas.SwiftMessageResponse], tags=["SWIFT报文"])
    async def query_swift_messages_by_time(
        start_time: datetime,
        end_time: datetime,
        lc_number: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db),
    ):
        from app.models import VALID_SWIFT_SEND_STATUSES
        if status and status not in VALID_SWIFT_SEND_STATUSES:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}，允许值: {', '.join(VALID_SWIFT_SEND_STATUSES)}")
        if start_time > end_time:
            raise HTTPException(status_code=400, detail="开始时间不能大于结束时间")
        return crud.get_swift_messages_by_time_range(
            db, start_time, end_time, lc_number=lc_number, status=status, skip=skip, limit=limit
        )

    @app.post("/api/swift/{message_number}/resend", response_model=schemas.SwiftMessageResponse, tags=["SWIFT报文"])
    async def resend_swift_message(message_number: str, db: Session = Depends(get_db)):
        try:
            return crud.resend_swift_message(db, message_number)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"重发报文失败: {str(e)}")

    @app.post("/api/parties", response_model=schemas.PartyResponse, tags=["多方通知与事件订阅"], status_code=status.HTTP_201_CREATED)
    async def create_party(party_data: schemas.PartyCreate, db: Session = Depends(get_db)):
        try:
            return crud.create_party(db, party_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建参与方失败: {str(e)}")

    @app.get("/api/parties", response_model=List[schemas.PartyResponse], tags=["多方通知与事件订阅"])
    async def list_parties(
        skip: int = 0,
        limit: int = 100,
        role: Optional[str] = None,
        db: Session = Depends(get_db)
    ):
        if role and role not in models.VALID_PARTY_ROLES:
            raise HTTPException(status_code=400, detail=f"无效的角色: {role}，允许值: {', '.join(models.VALID_PARTY_ROLES)}")
        return crud.get_all_parties(db, skip, limit, role)

    @app.get("/api/parties/{party_id}", response_model=schemas.PartyResponse, tags=["多方通知与事件订阅"])
    async def get_party(party_id: int, db: Session = Depends(get_db)):
        party = crud.get_party_by_id(db, party_id)
        if not party:
            raise HTTPException(status_code=404, detail=f"参与方 {party_id} 不存在")
        return party

    @app.get("/api/parties/{party_id}/subscriptions", response_model=List[schemas.PartySubscriptionResponse], tags=["多方通知与事件订阅"])
    async def get_party_subscriptions(party_id: int, db: Session = Depends(get_db)):
        party = crud.get_party_by_id(db, party_id)
        if not party:
            raise HTTPException(status_code=404, detail=f"参与方 {party_id} 不存在")
        return crud.get_party_subscriptions(db, party_id)

    @app.put("/api/parties/{party_id}/subscriptions", response_model=List[schemas.PartySubscriptionResponse], tags=["多方通知与事件订阅"])
    async def update_party_subscriptions(
        party_id: int,
        req: schemas.SubscriptionBatchUpdate,
        db: Session = Depends(get_db)
    ):
        try:
            updates = [
                {"event_type": s.event_type, "is_active": s.is_active}
                for s in req.subscriptions
            ]
            return crud.update_party_subscriptions(db, party_id, updates)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/notifications/party/{party_id}", response_model=List[schemas.NotificationResponse], tags=["多方通知与事件订阅"])
    async def get_party_notifications(
        party_id: int,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
    ):
        party = crud.get_party_by_id(db, party_id)
        if not party:
            raise HTTPException(status_code=404, detail=f"参与方 {party_id} 不存在")
        if start_time and end_time and start_time > end_time:
            raise HTTPException(status_code=400, detail="开始时间不能大于结束时间")
        try:
            return crud.get_notifications_by_party(db, party_id, status, start_time, end_time, skip, limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/notifications/party/{party_id}/mark-read", tags=["多方通知与事件订阅"])
    async def mark_notifications_read(
        party_id: int,
        req: schemas.NotificationMarkReadRequest,
        db: Session = Depends(get_db)
    ):
        party = crud.get_party_by_id(db, party_id)
        if not party:
            raise HTTPException(status_code=404, detail=f"参与方 {party_id} 不存在")
        count = crud.mark_notifications_read(db, party_id, req.notification_ids)
        return {"marked_count": count, "message": f"已标记 {count} 条通知为已读"}

    @app.post("/api/notifications/party/{party_id}/archive", tags=["多方通知与事件订阅"])
    async def archive_notifications(
        party_id: int,
        req: schemas.NotificationArchiveRequest,
        db: Session = Depends(get_db)
    ):
        party = crud.get_party_by_id(db, party_id)
        if not party:
            raise HTTPException(status_code=404, detail=f"参与方 {party_id} 不存在")
        count = crud.archive_notifications(db, party_id, req.notification_ids)
        return {"archived_count": count, "message": f"已归档 {count} 条通知"}

    @app.get("/api/lc/{lc_number}/event-stream", response_model=List[schemas.LCEventStreamResponse], tags=["多方通知与事件订阅"])
    async def get_lc_event_stream(
        lc_number: str,
        skip: int = 0,
        limit: int = 200,
        db: Session = Depends(get_db)
    ):
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        if not lc:
            raise HTTPException(status_code=404, detail=f"信用证 {lc_number} 不存在")
        return crud.get_lc_event_stream(db, lc.id, skip, limit)

    @app.post("/api/rule-versions", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"], status_code=status.HTTP_201_CREATED)
    async def create_rule_version(data: schemas.RuleVersionCreate, db: Session = Depends(get_db)):
        try:
            return crud.create_rule_version(db, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建规则版本失败: {str(e)}")

    @app.get("/api/rule-versions", response_model=List[schemas.RuleVersionResponse], tags=["规则版本管理"])
    async def list_rule_versions(status: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            return crud.get_all_rule_versions(db, status=status, skip=skip, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/rule-versions/{version_number}", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"])
    async def get_rule_version(version_number: str, db: Session = Depends(get_db)):
        rv = crud.get_rule_version_by_number(db, version_number)
        if not rv:
            raise HTTPException(status_code=404, detail=f"规则版本 {version_number} 不存在")
        return rv

    @app.put("/api/rule-versions/{version_number}", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"])
    async def update_rule_version(version_number: str, data: schemas.RuleVersionUpdate, db: Session = Depends(get_db)):
        try:
            return crud.update_rule_version(db, version_number, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"更新规则版本失败: {str(e)}")

    @app.post("/api/rule-versions/{version_number}/publish-testing", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"])
    async def publish_rule_version_testing(version_number: str, req: schemas.RuleVersionPublishTesting, db: Session = Depends(get_db)):
        try:
            return crud.publish_rule_version_to_testing(db, version_number, req.grayscale_percentage)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"发布灰度测试失败: {str(e)}")

    @app.post("/api/rule-versions/{version_number}/publish-active", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"])
    async def publish_rule_version_active(version_number: str, db: Session = Depends(get_db)):
        try:
            return crud.publish_rule_version_to_active(db, version_number)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"发布正式版本失败: {str(e)}")

    @app.post("/api/rule-versions/{version_number}/revert-draft", response_model=schemas.RuleVersionResponse, tags=["规则版本管理"])
    async def revert_rule_version_to_draft(version_number: str, db: Session = Depends(get_db)):
        try:
            return crud.revert_testing_to_draft(db, version_number)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"回退版本失败: {str(e)}")

    @app.get("/api/rule-versions/compare", response_model=schemas.RuleVersionDiffResponse, tags=["规则版本管理"])
    async def compare_rule_versions(version_a: str, version_b: str, db: Session = Depends(get_db)):
        try:
            return crud.compare_rule_versions(db, version_a, version_b)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"版本对比失败: {str(e)}")

    @app.get("/api/rule-versions/{version_number}/submissions", response_model=schemas.SubmissionByRuleVersionResponse, tags=["规则版本管理"])
    async def get_submissions_by_rule_version(version_number: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            return crud.get_submissions_by_rule_version(db, version_number, skip, limit)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询交单列表失败: {str(e)}")

    @app.post("/api/payments", response_model=schemas.PaymentResponse, tags=["承兑与付款管理"], status_code=status.HTTP_201_CREATED)
    async def create_payment(payment_req: schemas.PaymentCreateRequest, db: Session = Depends(get_db)):
        try:
            payment = crud.create_payment_application(db, payment_req.submission_id)
            return payment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建付款申请失败: {str(e)}")

    @app.get("/api/payments/{payment_number}", response_model=schemas.PaymentDetailResponse, tags=["承兑与付款管理"])
    async def get_payment_detail(payment_number: str, db: Session = Depends(get_db)):
        try:
            crud.check_and_update_matured_payments(db)
            return crud.get_payment_detail(db, payment_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询付款详情失败: {str(e)}")

    @app.post("/api/payments/{payment_number}/accept", response_model=schemas.PaymentResponse, tags=["承兑与付款管理"])
    async def accept_payment(payment_number: str, accept_req: schemas.PaymentAcceptRequest, db: Session = Depends(get_db)):
        try:
            payment = crud.accept_payment(db, payment_number, accept_req.accepted_by)
            return payment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"承兑失败: {str(e)}")

    @app.post("/api/payments/{payment_number}/reject", response_model=schemas.PaymentResponse, tags=["承兑与付款管理"])
    async def reject_payment(payment_number: str, reject_req: schemas.PaymentRejectRequest, db: Session = Depends(get_db)):
        try:
            payment = crud.reject_payment(db, payment_number, reject_req.rejection_reason, reject_req.rejected_by)
            return payment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"拒付失败: {str(e)}")

    @app.post("/api/payments/{payment_number}/settle", response_model=schemas.PaymentResponse, tags=["承兑与付款管理"])
    async def settle_payment(payment_number: str, settle_req: schemas.PaymentSettleRequest, db: Session = Depends(get_db)):
        try:
            payment = crud.settle_payment(
                db,
                payment_number,
                settle_req.payment_date,
                settle_req.amount,
                settle_req.reference,
                settle_req.settled_by,
            )
            return payment
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"付款结算失败: {str(e)}")

    @app.get("/api/payments/lc/{lc_number}", response_model=schemas.LcPaymentSummaryResponse, tags=["承兑与付款管理"])
    async def get_lc_payments(lc_number: str, db: Session = Depends(get_db)):
        try:
            return crud.get_lc_payment_summary(db, lc_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询信用证付款记录失败: {str(e)}")

    @app.get("/api/payments/status/{status}", response_model=List[schemas.PaymentResponse], tags=["承兑与付款管理"])
    async def get_payments_by_status(status: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            crud.check_and_update_matured_payments(db)
            return crud.get_payments_by_status(db, status, skip, limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"按状态查询付款失败: {str(e)}")

    @app.get("/api/payments/stats/summary", response_model=schemas.PaymentStatsResponse, tags=["承兑与付款管理"])
    async def get_payment_stats(
        start_date: date,
        end_date: date,
        db: Session = Depends(get_db)
    ):
        try:
            if start_date > end_date:
                raise HTTPException(status_code=400, detail="开始日期不能大于结束日期")
            return crud.get_payment_stats_by_time_range(db, start_date, end_date)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询付款统计失败: {str(e)}")

    @app.get("/api/payments/{payment_number}/status-history", response_model=List[schemas.PaymentStatusHistoryResponse], tags=["承兑与付款管理"])
    async def get_payment_status_history(payment_number: str, db: Session = Depends(get_db)):
        try:
            return crud.get_payment_status_history(db, payment_number)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询状态历史失败: {str(e)}")

    @app.post("/api/payments/maturity-check", tags=["承兑与付款管理"])
    async def check_maturity(db: Session = Depends(get_db)):
        try:
            count = crud.check_and_update_matured_payments(db)
            return {"matured_count": count, "message": f"已将 {count} 笔到期付款标记为 matured"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"到期检查失败: {str(e)}")

    @app.get("/api/payments", response_model=List[schemas.PaymentResponse], tags=["承兑与付款管理"])
    async def list_all_payments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        try:
            crud.check_and_update_matured_payments(db)
            return crud.get_all_payments(db, skip, limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询付款列表失败: {str(e)}")

    return app


app = create_app()
