import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data
from app.models import (
    FEE_SPLIT_ROLE_ISSUING_BANK,
    FEE_SPLIT_ROLE_ADVISING_BANK,
    FEE_SPLIT_ROLE_NEGOTIATING_BANK,
    FEE_SPLIT_ROLE_CONFIRMING_BANK,
    FEE_SPLIT_RULE_STATUS_ACTIVE,
    FEE_SPLIT_RULE_STATUS_VOID,
    FEE_SPLIT_DETAIL_STATUS_PENDING,
    FEE_SPLIT_DETAIL_STATUS_CONFIRMED,
    FEE_SPLIT_DETAIL_STATUS_DISPUTED,
    FEE_SETTLEMENT_STATUS_PENDING,
    FEE_SETTLEMENT_STATUS_SETTLED,
    FEE_TIER_STANDARD,
)


def _create_test_lc(db, lc_number="LC-SPLIT-TEST-001"):
    existing = crud.get_letter_of_credit_by_number(db, lc_number)
    if existing:
        return existing
    lc_data = schemas.LetterOfCreditCreate(
        lc_number=lc_number,
        issuing_bank="中国银行上海分行",
        beneficiary_name="上海贸易有限公司",
        applicant_name="ABC IMPORTS CO.",
        currency=schemas.Currency.USD,
        amount=50000.00,
        latest_shipment_date=date(2024, 6, 30),
        latest_presentation_date=date(2024, 7, 15),
        expiry_date=date(2024, 7, 20),
        transport_mode=schemas.TransportMode.SEA,
        port_of_loading="SHANGHAI PORT",
        port_of_discharge="ROTTERDAM PORT",
        partial_shipment_allowed=False,
        transshipment_allowed=False,
        goods_description="100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
        additional_terms=[],
        fee_tier=schemas.FeeTier.STANDARD,
        payment_method=schemas.PaymentMethod.SIGHT,
        document_requirements=[
            schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
            schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
            schemas.DocumentRequirementCreate(document_type="packing_list", original_copies=2, copy_copies=2),
        ],
    )
    return crud.create_letter_of_credit(db, lc_data)


def _build_compliant_submission(lc_number, submission_id):
    return schemas.SubmissionSubmit(
        lc_number=lc_number,
        submission_id=submission_id,
        presentation_date=date(2024, 6, 10),
        documents=[
            schemas.DocumentSubmit(
                lc_number=lc_number,
                submission_id=submission_id,
                document_type="invoice",
                original_copies_submitted=3,
                copy_copies_submitted=2,
                content={
                    "invoice_number": f"INV-{submission_id}",
                    "invoice_date": "2024-06-01",
                    "beneficiary": "上海贸易有限公司",
                    "applicant": "ABC IMPORTS CO.",
                    "currency": "USD",
                    "goods": [
                        {"name": "COTTON T-SHIRTS", "specification": "SIZE M", "quantity": 5000, "unit": "PCS", "unit_price": 10.00}
                    ],
                    "goods_description": "100% COTTON MEN'S T-SHIRTS 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
                    "total_amount": 50000.00
                }
            ),
            schemas.DocumentSubmit(
                lc_number=lc_number,
                submission_id=submission_id,
                document_type="bill_of_lading",
                original_copies_submitted=3,
                copy_copies_submitted=3,
                content={
                    "bl_number": f"BL-{submission_id}",
                    "shipper": "上海贸易有限公司",
                    "consignee": "TO ORDER",
                    "notify_party": "ABC IMPORTS CO. ROTTERDAM",
                    "vessel_voyage": "MAERSK TEST V.001",
                    "port_of_loading": "SHANGHAI PORT",
                    "port_of_discharge": "ROTTERDAM PORT",
                    "shipment_date": "2024-06-05",
                    "packages": 5000,
                    "package_unit": "PCS",
                    "freight_term": "FREIGHT PREPAID",
                    "clean": True,
                    "transshipment": False,
                    "endorsement": "BLANK ENDORSED",
                    "remarks": "CLEAN ON BOARD",
                    "goods_description": "100% COTTON MEN'S T-SHIRTS"
                }
            ),
            schemas.DocumentSubmit(
                lc_number=lc_number,
                submission_id=submission_id,
                document_type="packing_list",
                original_copies_submitted=2,
                copy_copies_submitted=2,
                content={
                    "packing_number": f"PL-{submission_id}",
                    "date": "2024-06-01",
                    "total_packages": 250,
                    "package_type": "CTNS",
                    "gross_weight": 5250.00,
                    "net_weight": 5000.00,
                    "goods_description": "COTTON T-SHIRTS"
                }
            ),
        ],
    )


def test_fee_split_rule_creation():
    print("\n" + "=" * 70)
    print("测试1: 创建分账规则")
    print("=" * 70)

    db = SessionLocal()
    try:
        _create_test_lc(db)

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 50},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行鹿特丹分行", "split_ratio": 30},
            {"role": FEE_SPLIT_ROLE_NEGOTIATING_BANK, "bank_name": "汇丰银行香港分行", "split_ratio": 20},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-001", banks)
        assert rule is not None
        assert rule.status == FEE_SPLIT_RULE_STATUS_ACTIVE
        assert len(rule.participating_banks) == 3
        assert rule.participating_banks[0]["role"] == FEE_SPLIT_ROLE_ISSUING_BANK
        assert rule.participating_banks[0]["split_ratio"] == 50
        print(f"  ✅ 分账规则创建成功: {rule.rule_number}")
        print(f"  ✅ 参与银行数量: {len(rule.participating_banks)}")
        for b in rule.participating_banks:
            print(f"     - {b['bank_name']} ({b['role']}): {b['split_ratio']}%")

        try:
            crud.create_fee_split_rule(db, "LC-SPLIT-TEST-001", banks)
            assert False, "应该抛出异常，因为同一信用证不能有多个生效的分账规则"
        except ValueError as e:
            print(f"  ✅ 正确阻止重复创建生效规则: {str(e)[:60]}...")

    finally:
        db.close()


def test_fee_split_ratio_validation():
    print("\n" + "=" * 70)
    print("测试2: 分账比例校验")
    print("=" * 70)

    db = SessionLocal()
    try:
        _create_test_lc(db, "LC-SPLIT-TEST-002")

        invalid_banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行", "split_ratio": 60},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行", "split_ratio": 30},
        ]
        try:
            crud.create_fee_split_rule(db, "LC-SPLIT-TEST-002", invalid_banks)
            assert False, "应该抛出异常，比例之和不等于100%"
        except ValueError as e:
            print(f"  ✅ 正确校验比例之和(90%): {str(e)[:60]}...")

        empty_banks = []
        try:
            crud.create_fee_split_rule(db, "LC-SPLIT-TEST-002", empty_banks)
            assert False, "应该抛出异常，参与银行列表为空"
        except ValueError as e:
            print(f"  ✅ 正确校验空列表: {str(e)[:60]}...")

        negative_ratio = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行", "split_ratio": -10},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行", "split_ratio": 110},
        ]
        try:
            crud.create_fee_split_rule(db, "LC-SPLIT-TEST-002", negative_ratio)
            assert False, "应该抛出异常，比例值超出范围"
        except ValueError as e:
            print(f"  ✅ 正确校验比例范围: {str(e)[:60]}...")

    finally:
        db.close()


def test_auto_split_on_fee_creation():
    print("\n" + "=" * 70)
    print("测试3: 费用产生时自动拆分")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-003")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 50},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行鹿特丹分行", "split_ratio": 30},
            {"role": FEE_SPLIT_ROLE_NEGOTIATING_BANK, "bank_name": "汇丰银行香港分行", "split_ratio": 20},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-003", banks)

        submission = _build_compliant_submission("LC-SPLIT-TEST-003", "SUB-SPLIT-003")
        audit = crud.submit_documents_and_audit(db, submission)
        assert audit is not None
        print(f"  ✅ 交单审核完成，提交ID: {audit.submission_id}")

        fee_records = db.query(models.FeeRecord).filter(models.FeeRecord.lc_id == lc.id).all()
        assert len(fee_records) >= 1
        fee = fee_records[0]
        print(f"  ✅ 费用记录创建: {fee.fee_number}, 总金额: ${fee.total_amount:.2f}")

        splits = crud.get_fee_split_details_by_fee(db, fee.id)
        assert len(splits) == 3, f"应该有3条分账明细，实际: {len(splits)}"
        print(f"  ✅ 自动生成 {len(splits)} 条分账明细")

        total_split = sum(s.current_amount for s in splits)
        assert abs(total_split - fee.total_amount) < 0.02
        print(f"  ✅ 分账金额合计: ${total_split:.2f} (与费用总额 ${fee.total_amount:.2f} 一致)")

        for s in splits:
            print(f"     - {s.receiving_bank_name} ({s.receiving_bank_role}): "
                  f"${s.current_amount:.2f} ({s.split_ratio}%) 状态: {s.status}")
            assert s.status == FEE_SPLIT_DETAIL_STATUS_PENDING

        assert fee.settlement_status == FEE_SETTLEMENT_STATUS_PENDING
        print(f"  ✅ 费用结算状态: {fee.settlement_status}")

    finally:
        db.close()


def test_confirm_split_and_settlement():
    print("\n" + "=" * 70)
    print("测试4: 确认分账明细与费用结算")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-004")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 60},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行鹿特丹分行", "split_ratio": 40},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-004", banks)

        submission = _build_compliant_submission("LC-SPLIT-TEST-004", "SUB-SPLIT-004")
        audit = crud.submit_documents_and_audit(db, submission)

        fee = db.query(models.FeeRecord).filter(models.FeeRecord.lc_id == lc.id).first()
        splits = crud.get_fee_split_details_by_fee(db, fee.id)

        detail1 = crud.confirm_fee_split_detail(db, splits[0].split_number, "user_issuing_bank")
        assert detail1.status == FEE_SPLIT_DETAIL_STATUS_CONFIRMED
        assert detail1.confirmed_by == "user_issuing_bank"
        print(f"  ✅ 分账明细1已确认: {detail1.split_number}")

        fee_reloaded = db.query(models.FeeRecord).filter(models.FeeRecord.id == fee.id).first()
        assert fee_reloaded.settlement_status == FEE_SETTLEMENT_STATUS_PENDING
        print(f"  ✅ 部分确认后费用状态仍为 pending")

        detail2 = crud.confirm_fee_split_detail(db, splits[1].split_number, "user_advising_bank")
        assert detail2.status == FEE_SPLIT_DETAIL_STATUS_CONFIRMED
        print(f"  ✅ 分账明细2已确认: {detail2.split_number}")

        fee_reloaded = db.query(models.FeeRecord).filter(models.FeeRecord.id == fee.id).first()
        assert fee_reloaded.settlement_status == FEE_SETTLEMENT_STATUS_SETTLED
        assert fee_reloaded.settled_at is not None
        print(f"  ✅ 全部确认后费用状态变为 settled，结算时间: {fee_reloaded.settled_at}")

        try:
            crud.confirm_fee_split_detail(db, splits[0].split_number, "user_test")
            assert False, "应该抛出异常，已确认的不能再次确认"
        except ValueError as e:
            print(f"  ✅ 正确阻止重复确认: {str(e)[:60]}...")

    finally:
        db.close()


def test_dispute_and_adjust():
    print("\n" + "=" * 70)
    print("测试5: 争议标记与金额调整")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-005")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 70},
            {"role": FEE_SPLIT_ROLE_NEGOTIATING_BANK, "bank_name": "汇丰银行香港分行", "split_ratio": 30},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-005", banks)

        submission = _build_compliant_submission("LC-SPLIT-TEST-005", "SUB-SPLIT-005")
        audit = crud.submit_documents_and_audit(db, submission)

        fee = db.query(models.FeeRecord).filter(models.FeeRecord.lc_id == lc.id).first()
        splits = crud.get_fee_split_details_by_fee(db, fee.id)

        disputed_split = splits[1]
        original_amount = disputed_split.current_amount
        print(f"  争议前金额: ${original_amount:.2f}")

        disputed = crud.dispute_fee_split_detail(
            db, disputed_split.split_number, "议付行认为应分账金额计算有误，少算了5美元"
        )
        assert disputed.status == FEE_SPLIT_DETAIL_STATUS_DISPUTED
        assert disputed.dispute_reason is not None
        assert disputed.disputed_at is not None
        print(f"  ✅ 分账明细已标记争议: {disputed.status}")
        print(f"     争议原因: {disputed.dispute_reason}")

        try:
            crud.confirm_fee_split_detail(db, disputed.split_number, "user_test")
            assert False, "应该抛出异常，争议状态不能直接确认"
        except ValueError as e:
            print(f"  ✅ 正确阻止争议状态直接确认: {str(e)[:60]}...")

        adjusted = crud.adjust_fee_split_detail(
            db,
            disputed.split_number,
            new_amount=original_amount + 5.0,
            adjustment_reason="管理员核实后，同意增加5美元",
            adjusted_by="admin_user",
        )
        assert adjusted.status == FEE_SPLIT_DETAIL_STATUS_PENDING
        assert abs(adjusted.current_amount - (original_amount + 5.0)) < 0.01
        print(f"  ✅ 金额调整完成，新金额: ${adjusted.current_amount:.2f}，状态恢复为 pending")

        adjustments = crud.get_fee_split_adjustments(db, disputed.split_number)
        assert len(adjustments) == 1
        adj = adjustments[0]
        print(f"  ✅ 调整记录已保存: {adj.adjustment_number}")
        print(f"     调整前: ${adj.amount_before:.2f} -> 调整后: ${adj.amount_after:.2f} (差额: ${adj.amount_diff:.2f})")
        print(f"     调整人: {adj.adjusted_by}, 原因: {adj.adjustment_reason}")

    finally:
        db.close()


def test_void_split_rule():
    print("\n" + "=" * 70)
    print("测试6: 作废分账规则")
    print("=" * 70)

    db = SessionLocal()
    try:
        _create_test_lc(db, "LC-SPLIT-TEST-006")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 100},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-006", banks)

        voided = crud.void_fee_split_rule(
            db, rule.rule_number, "参与行发生变更，需要重新创建规则", "admin_user"
        )
        assert voided.status == FEE_SPLIT_RULE_STATUS_VOID
        assert voided.void_reason is not None
        assert voided.voided_at is not None
        assert voided.voided_by == "admin_user"
        print(f"  ✅ 分账规则已作废: {voided.status}")
        print(f"     作废原因: {voided.void_reason}")
        print(f"     作废人: {voided.voided_by}, 时间: {voided.voided_at}")

        banks2 = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 60},
            {"role": FEE_SPLIT_ROLE_CONFIRMING_BANK, "bank_name": "花旗银行纽约分行", "split_ratio": 40},
        ]
        new_rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-006", banks2)
        assert new_rule.status == FEE_SPLIT_RULE_STATUS_ACTIVE
        print(f"  ✅ 成功创建新的生效规则: {new_rule.rule_number}")

        all_rules = crud.get_all_fee_split_rules_by_lc(db, "LC-SPLIT-TEST-006")
        assert len(all_rules) == 2
        print(f"  ✅ 该信用证共有 {len(all_rules)} 条分账规则记录")

    finally:
        db.close()


def test_lc_fee_split_summary():
    print("\n" + "=" * 70)
    print("测试7: 按信用证查询分账明细")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-007")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 50},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行鹿特丹分行", "split_ratio": 50},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-007", banks)

        submission = _build_compliant_submission("LC-SPLIT-TEST-007", "SUB-SPLIT-007")
        audit = crud.submit_documents_and_audit(db, submission)

        summary = crud.get_lc_fee_split_summary(db, "LC-SPLIT-TEST-007")
        assert summary["lc_number"] == "LC-SPLIT-TEST-007"
        assert summary["split_rule"] is not None
        assert len(summary["fee_records_with_splits"]) >= 1
        print(f"  ✅ 查询成功，信用证: {summary['lc_number']}")
        print(f"  ✅ 分账规则: {summary['split_rule'].rule_number}")
        print(f"  ✅ 费用记录数: {len(summary['fee_records_with_splits'])}")

        for fee_info in summary["fee_records_with_splits"]:
            fee = fee_info["fee_record"]
            print(f"     费用: {fee.fee_number} | 金额: ${fee.total_amount:.2f} | "
                  f"结算状态: {fee_info['settlement_status']}")
            for s in fee_info["split_details"]:
                print(f"       -> {s.receiving_bank_name}: ${s.current_amount:.2f} [{s.status}]")

    finally:
        db.close()


def test_monthly_reconciliation():
    print("\n" + "=" * 70)
    print("测试8: 月度对账汇总")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-008")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 50},
            {"role": FEE_SPLIT_ROLE_ADVISING_BANK, "bank_name": "荷兰银行鹿特丹分行", "split_ratio": 30},
            {"role": FEE_SPLIT_ROLE_NEGOTIATING_BANK, "bank_name": "汇丰银行香港分行", "split_ratio": 20},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-008", banks)

        submission = _build_compliant_submission("LC-SPLIT-TEST-008", "SUB-SPLIT-008")
        audit = crud.submit_documents_and_audit(db, submission)

        splits = crud.get_fee_split_details_by_lc(db, "LC-SPLIT-TEST-008")
        if len(splits) >= 1:
            crud.confirm_fee_split_detail(db, splits[0].split_number, "user_issuing")
        if len(splits) >= 2:
            crud.dispute_fee_split_detail(db, splits[1].split_number, "金额异议")

        now = datetime.utcnow()
        recon = crud.get_monthly_reconciliation(db, now.year, now.month)
        assert recon["year_month"] == f"{now.year:04d}-{now.month:02d}"
        print(f"  ✅ 月度对账: {recon['year_month']}")
        print(f"  ✅ 总分账明细数: {recon['total_split_count']}")
        print(f"  ✅ 总金额: ${recon['total_amount']:.2f}")
        print(f"     已确认: ${recon['total_confirmed_amount']:.2f}")
        print(f"     争议中: ${recon['total_disputed_amount']:.2f}")
        print(f"     待确认: ${recon['total_pending_amount']:.2f}")
        print(f"  ✅ 按银行汇总: {len(recon['by_bank'])} 家银行")
        for bank in recon["by_bank"]:
            print(f"     - {bank['bank_name']} ({bank['bank_role']}):")
            print(f"       应收总额: ${bank['total_receivable']:.2f}")
            print(f"       已确认: ${bank['confirmed_amount']:.2f} | "
                  f"争议: ${bank['disputed_amount']:.2f} | "
                  f"待确认: ${bank['pending_amount']:.2f}")
            print(f"       笔数: 总计{bank['detail_count']}笔 "
                  f"(已确认{bank['confirmed_count']} / 争议{bank['disputed_count']} / 待确认{bank['pending_count']})")

    finally:
        db.close()


def test_retroactive_split_for_existing_fees():
    print("\n" + "=" * 70)
    print("测试9: 创建规则后为历史费用自动补拆分")
    print("=" * 70)

    db = SessionLocal()
    try:
        lc = _create_test_lc(db, "LC-SPLIT-TEST-009")

        submission = _build_compliant_submission("LC-SPLIT-TEST-009", "SUB-SPLIT-009")
        audit = crud.submit_documents_and_audit(db, submission)

        fee = db.query(models.FeeRecord).filter(models.FeeRecord.lc_id == lc.id).first()
        splits_before = crud.get_fee_split_details_by_fee(db, fee.id)
        assert len(splits_before) == 0, "创建分账规则前不应有分账明细"
        print(f"  ✅ 创建分账规则前，费用 {fee.fee_number} 无分账明细")

        banks = [
            {"role": FEE_SPLIT_ROLE_ISSUING_BANK, "bank_name": "中国银行上海分行", "split_ratio": 100},
        ]
        rule = crud.create_fee_split_rule(db, "LC-SPLIT-TEST-009", banks)

        splits_after = crud.get_fee_split_details_by_fee(db, fee.id)
        assert len(splits_after) == 1
        assert abs(splits_after[0].current_amount - fee.total_amount) < 0.02
        print(f"  ✅ 创建分账规则后，自动为历史费用补拆分")
        print(f"     分账金额: ${splits_after[0].current_amount:.2f} (费用总额: ${fee.total_amount:.2f})")

    finally:
        db.close()


if __name__ == "__main__":
    init_db()

    print("\n" + "#" * 70)
    print("#  银行间手续费分账与结算对账模块 - 功能测试")
    print("#" * 70)

    try:
        test_fee_split_rule_creation()
        test_fee_split_ratio_validation()
        test_auto_split_on_fee_creation()
        test_confirm_split_and_settlement()
        test_dispute_and_adjust()
        test_void_split_rule()
        test_lc_fee_split_summary()
        test_monthly_reconciliation()
        test_retroactive_split_for_existing_fees()

        print("\n" + "#" * 70)
        print("#  全部测试通过! ✅")
        print("#" * 70)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
