import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.seed_data import init_db, seed_data


def test_transfer_and_back_to_back():
    print("=" * 60)
    print("信用证转让与背对背开证管理模块测试")
    print("=" * 60)

    init_db()
    seed_data()

    db = SessionLocal()

    try:
        lc_number = "LC-SEA-CIF-2024-001"
        lc = crud.get_letter_of_credit_by_number(db, lc_number)
        assert lc is not None, f"信用证 {lc_number} 不存在"
        print(f"\n[✓] 找到测试信用证: {lc_number}")
        print(f"    金额: {lc.amount} {lc.currency}")
        print(f"    最迟装运日期: {lc.latest_shipment_date}")
        print(f"    到期日: {lc.expiry_date}")

        # ========================================
        # 转让模块测试
        # ========================================
        print("\n" + "=" * 60)
        print("一、信用证转让测试")
        print("=" * 60)

        print("\n" + "-" * 40)
        print("测试1: 创建部分转让申请")
        print("-" * 40)

        transfer1_data = schemas.TransferCreate(
            lc_number=lc_number,
            second_beneficiary_name="苏州纺织供应有限公司 SUZHOU TEXTILE SUPPLY CO., LTD.",
            transfer_amount=35000.00,
            transfer_type=schemas.TransferType.PARTIAL,
        )
        transfer1 = crud.create_transfer(db, transfer1_data)
        assert transfer1 is not None
        assert transfer1.status == "pending"
        assert transfer1.transfer_number == f"{lc_number}-T-001"
        assert transfer1.transfer_type == "partial"
        assert transfer1.transfer_amount == 35000.00
        assert transfer1.inherited_terms is not None
        assert transfer1.inherited_terms["port_of_loading"] == "SHANGHAI PORT"
        assert transfer1.inherited_terms["port_of_discharge"] == "ROTTERDAM PORT"
        assert transfer1.inherited_terms["goods_description"] == lc.goods_description
        print(f"[✓] 部分转让申请创建成功")
        print(f"    转让证编号: {transfer1.transfer_number}")
        print(f"    转让金额: {transfer1.transfer_amount}")
        print(f"    转让类型: {transfer1.transfer_type}")
        print(f"    状态: {transfer1.status}")
        print(f"    继承条款-装运港: {transfer1.inherited_terms['port_of_loading']}")
        print(f"    继承条款-目的港: {transfer1.inherited_terms['port_of_discharge']}")

        print("\n" + "-" * 40)
        print("测试2: 部分转让金额不超过原证80%限制")
        print("-" * 40)

        try:
            over_limit_data = schemas.TransferCreate(
                lc_number=lc_number,
                second_beneficiary_name="杭州贸易供应有限公司 HANGZHOU TRADE SUPPLY CO., LTD.",
                transfer_amount=41000.00,
                transfer_type=schemas.TransferType.PARTIAL,
            )
            crud.create_transfer(db, over_limit_data)
            print("[✗] 应该拒绝超过80%的部分转让")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了超过80%的部分转让")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试3: 全额转让金额必须等于原证金额")
        print("-" * 40)

        try:
            wrong_full_data = schemas.TransferCreate(
                lc_number=lc_number,
                second_beneficiary_name="杭州贸易供应有限公司 HANGZHOU TRADE SUPPLY CO., LTD.",
                transfer_amount=40000.00,
                transfer_type=schemas.TransferType.FULL,
            )
            crud.create_transfer(db, wrong_full_data)
            print("[✗] 应该拒绝金额不等于原证金额的全额转让")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了金额不等于原证的全额转让")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试4: 确认转让申请")
        print("-" * 40)

        confirmed = crud.confirm_transfer(db, transfer1.transfer_number, "confirm")
        assert confirmed.status == "confirmed"
        assert confirmed.confirmation_time is not None
        print(f"[✓] 转让已确认")
        print(f"    状态: {confirmed.status}")
        print(f"    确认时间: {confirmed.confirmation_time}")

        print("\n" + "-" * 40)
        print("测试5: 确认后原证可用金额减少")
        print("-" * 40)

        available = crud.get_lc_available_amount(db, lc_number)
        assert available["total_transferred_amount"] == 35000.00
        expected_remaining = 50000.00 - 35000.00
        assert available["remaining_available_amount"] == expected_remaining
        print(f"[✓] 可用金额计算正确")
        print(f"    原证金额: {available['original_amount']}")
        print(f"    已转让金额: {available['total_transferred_amount']}")
        print(f"    背对背证金额: {available['total_back_to_back_amount']}")
        print(f"    剩余可用金额: {available['remaining_available_amount']}")

        print("\n" + "-" * 40)
        print("测试6: 第二份部分转让给不同第二受益人")
        print("-" * 40)

        transfer2_data = schemas.TransferCreate(
            lc_number=lc_number,
            second_beneficiary_name="杭州贸易供应有限公司 HANGZHOU TRADE SUPPLY CO., LTD.",
            transfer_amount=10000.00,
            transfer_type=schemas.TransferType.PARTIAL,
        )
        transfer2 = crud.create_transfer(db, transfer2_data)
        assert transfer2.transfer_number == f"{lc_number}-T-002"
        print(f"[✓] 第二份转让创建成功")
        print(f"    转让证编号: {transfer2.transfer_number}")
        print(f"    第二受益人: {transfer2.second_beneficiary_name}")

        print("\n" + "-" * 40)
        print("测试7: 最多3个不同第二受益人限制")
        print("-" * 40)

        transfer3_data = schemas.TransferCreate(
            lc_number=lc_number,
            second_beneficiary_name="无锡制造供应有限公司 WUXI MFG SUPPLY CO., LTD.",
            transfer_amount=5000.00,
            transfer_type=schemas.TransferType.PARTIAL,
        )
        transfer3 = crud.create_transfer(db, transfer3_data)
        assert transfer3.transfer_number == f"{lc_number}-T-003"
        print(f"[✓] 第三份转让创建成功 (第3个受益人)")

        try:
            transfer4_data = schemas.TransferCreate(
                lc_number=lc_number,
                second_beneficiary_name="南京新材料有限公司 NANJING NEW MATERIALS CO., LTD.",
                transfer_amount=1000.00,
                transfer_type=schemas.TransferType.PARTIAL,
            )
            crud.create_transfer(db, transfer4_data)
            print("[✗] 应该拒绝第4个不同第二受益人")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了第4个不同第二受益人")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试8: 同一受益人可以再次转让(不占新名额)")
        print("-" * 40)

        transfer5_data = schemas.TransferCreate(
            lc_number=lc_number,
            second_beneficiary_name="杭州贸易供应有限公司 HANGZHOU TRADE SUPPLY CO., LTD.",
            transfer_amount=2000.00,
            transfer_type=schemas.TransferType.PARTIAL,
        )
        transfer5 = crud.create_transfer(db, transfer5_data)
        assert transfer5.transfer_number == f"{lc_number}-T-004"
        print(f"[✓] 同一受益人可再次转让，编号: {transfer5.transfer_number}")

        print("\n" + "-" * 40)
        print("测试9: 拒绝转让申请")
        print("-" * 40)

        rejected = crud.confirm_transfer(db, transfer5.transfer_number, "reject")
        assert rejected.status == "rejected"
        print(f"[✓] 转让已拒绝")
        print(f"    状态: {rejected.status}")

        print("\n" + "-" * 40)
        print("测试10: 已确认/拒绝的转让不能再次操作")
        print("-" * 40)

        try:
            crud.confirm_transfer(db, transfer1.transfer_number, "confirm")
            print("[✗] 应该拒绝重复确认")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了重复确认")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试11: 转让金额超过剩余可用金额时拒绝")
        print("-" * 40)

        current_available = crud.get_lc_available_amount(db, lc_number)
        print(f"    当前剩余可用金额: {current_available['remaining_available_amount']}")

        try:
            over_remaining_data = schemas.TransferCreate(
                lc_number=lc_number,
                second_beneficiary_name="苏州纺织供应有限公司 SUZHOU TEXTILE SUPPLY CO., LTD.",
                transfer_amount=current_available["remaining_available_amount"] + 1000,
                transfer_type=schemas.TransferType.PARTIAL,
            )
            crud.create_transfer(db, over_remaining_data)
            print("[✗] 应该拒绝超过剩余可用金额的转让")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了超过剩余可用金额的转让")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试12: 查看转让证详情")
        print("-" * 40)

        detail = crud.get_transfer_detail(db, transfer1.transfer_number)
        assert detail is not None
        assert detail["transfer_number"] == transfer1.transfer_number
        assert detail["original_lc"] is not None
        assert detail["original_lc"].lc_number == lc_number
        print(f"[✓] 转让证详情查询成功")
        print(f"    转让证编号: {detail['transfer_number']}")
        print(f"    原证编号: {detail['original_lc'].lc_number}")
        print(f"    继承单据要求数量: {len(detail['inherited_terms'].get('document_requirements', []))}")

        print("\n" + "-" * 40)
        print("测试13: 查询信用证所有转让记录")
        print("-" * 40)

        transfers = crud.get_transfers_by_lc(db, lc_number)
        assert len(transfers) >= 4
        print(f"[✓] 查询到 {len(transfers)} 条转让记录")
        for t in transfers:
            print(f"    - {t.transfer_number} | 受益人: {t.second_beneficiary_name} | 金额: {t.transfer_amount} | 状态: {t.status}")

        # ========================================
        # 背对背信用证测试
        # ========================================
        print("\n" + "=" * 60)
        print("二、背对背信用证测试")
        print("=" * 60)

        lc2_number = "LC-AIR-CFR-2024-002"
        lc2 = crud.get_letter_of_credit_by_number(db, lc2_number)
        assert lc2 is not None
        print(f"\n[✓] 找到测试信用证2: {lc2_number}")
        print(f"    金额: {lc2.amount} {lc2.currency}")
        print(f"    最迟装运日期: {lc2.latest_shipment_date}")
        print(f"    到期日: {lc2.expiry_date}")

        print("\n" + "-" * 40)
        print("测试14: 创建背对背信用证")
        print("-" * 40)

        max_shipment = lc2.latest_shipment_date - timedelta(days=5)
        max_expiry = lc2.expiry_date - timedelta(days=10)

        btb1_data = schemas.BackToBackLCCreate(
            lc_number=lc2_number,
            beneficiary_name="东莞电子组件厂 DONGGUAN ELECTRONIC COMPONENTS FACTORY",
            applicant_name="深圳电子科技有限公司 SHENZHEN ELECTRONICS TECHNOLOGY CO., LTD.",
            issuing_bank="中国银行深圳分行 BANK OF CHINA SHENZHEN BRANCH",
            amount=30000.00,
            latest_shipment_date=max_shipment,
            latest_presentation_date=max_shipment + timedelta(days=15),
            expiry_date=max_expiry,
            transport_mode=schemas.TransportMode.AIR,
            port_of_loading="SHENZHEN BAO'AN INTERNATIONAL AIRPORT",
            port_of_discharge="FRANKFURT AM MAIN AIRPORT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="WIRELESS BLUETOOTH EARPHONES COMPONENTS MODEL X200",
            additional_terms=["空运单显示运费到付(FREIGHT COLLECT)"],
            document_requirements=[
                schemas.BackToBackDocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
                schemas.BackToBackDocumentRequirementCreate(document_type="bill_of_lading", original_copies=1, copy_copies=1),
                schemas.BackToBackDocumentRequirementCreate(document_type="packing_list", original_copies=1, copy_copies=1),
            ],
        )
        btb1 = crud.create_back_to_back_lc(db, btb1_data)
        assert btb1 is not None
        assert btb1.back_to_back_number == f"{lc2_number}-BB-001"
        assert btb1.status == "pending_review"
        assert btb1.conflict_status == "normal"
        assert btb1.currency == lc2.currency
        assert len(btb1.document_requirements) == 3
        print(f"[✓] 背对背证创建成功")
        print(f"    编号: {btb1.back_to_back_number}")
        print(f"    金额: {btb1.amount}")
        print(f"    装运日期: {btb1.latest_shipment_date}")
        print(f"    到期日: {btb1.expiry_date}")
        print(f"    币种: {btb1.currency} (继承自原证)")
        print(f"    单据要求数量: {len(btb1.document_requirements)}")

        print("\n" + "-" * 40)
        print("测试15: 背对背证金额不超过原证95%")
        print("-" * 40)

        try:
            over_amount_data = schemas.BackToBackLCCreate(
                lc_number=lc2_number,
                beneficiary_name="测试供应商 TEST SUPPLIER",
                applicant_name="深圳电子科技有限公司",
                issuing_bank="测试银行",
                amount=35000.00,
                latest_shipment_date=max_shipment,
                latest_presentation_date=max_shipment + timedelta(days=10),
                expiry_date=max_expiry,
                transport_mode=schemas.TransportMode.AIR,
                port_of_loading="SHENZHEN",
                port_of_discharge="FRANKFURT",
                goods_description="TEST",
                document_requirements=[],
            )
            crud.create_back_to_back_lc(db, over_amount_data)
            print("[✗] 应该拒绝超过95%金额的背对背证")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了超过95%金额的背对背证")
            print(f"    错误信息: {str(e)}")

        print("\n" + "-" * 40)
        print("测试16: 背对背证装运日期不晚于原证装运日期前5天")
        print("-" * 40)

        try:
            late_shipment_data = schemas.BackToBackLCCreate(
                lc_number=lc2_number,
                beneficiary_name="测试供应商2",
                applicant_name="深圳电子科技有限公司",
                issuing_bank="测试银行",
                amount=5000.00,
                latest_shipment_date=lc2.latest_shipment_date,
                latest_presentation_date=lc2.latest_shipment_date + timedelta(days=5),
                expiry_date=max_expiry,
                transport_mode=schemas.TransportMode.AIR,
                port_of_loading="SHENZHEN",
                port_of_discharge="FRANKFURT",
                goods_description="TEST",
                document_requirements=[],
            )
            crud.create_back_to_back_lc(db, late_shipment_data)
            print("[✗] 应该拒绝装运日期违规的背对背证")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了装运日期违规的背对背证")
            print(f"    错误信息: {str(e)[:80]}...")

        print("\n" + "-" * 40)
        print("测试17: 背对背证到期日不晚于原证到期日前10天")
        print("-" * 40)

        try:
            late_expiry_data = schemas.BackToBackLCCreate(
                lc_number=lc2_number,
                beneficiary_name="测试供应商3",
                applicant_name="深圳电子科技有限公司",
                issuing_bank="测试银行",
                amount=5000.00,
                latest_shipment_date=max_shipment,
                latest_presentation_date=max_shipment + timedelta(days=5),
                expiry_date=lc2.expiry_date,
                transport_mode=schemas.TransportMode.AIR,
                port_of_loading="SHENZHEN",
                port_of_discharge="FRANKFURT",
                goods_description="TEST",
                document_requirements=[],
            )
            crud.create_back_to_back_lc(db, late_expiry_data)
            print("[✗] 应该拒绝到期日违规的背对背证")
            assert False
        except ValueError as e:
            print(f"[✓] 正确拒绝了到期日违规的背对背证")
            print(f"    错误信息: {str(e)[:80]}...")

        print("\n" + "-" * 40)
        print("测试18: 查看背对背证详情")
        print("-" * 40)

        btb_detail = crud.get_back_to_back_detail(db, btb1.back_to_back_number)
        assert btb_detail is not None
        assert btb_detail["original_lc"] is not None
        assert btb_detail["original_lc"].lc_number == lc2_number
        print(f"[✓] 背对背证详情查询成功")
        print(f"    编号: {btb_detail['back_to_back_number']}")
        print(f"    关联原证: {btb_detail['original_lc'].lc_number}")
        print(f"    冲突状态: {btb_detail['conflict_status']}")

        print("\n" + "-" * 40)
        print("测试19: 查询原证所有背对背证")
        print("-" * 40)

        btb_list = crud.get_back_to_back_lcs_by_lc(db, lc2_number)
        assert len(btb_list) >= 1
        print(f"[✓] 查询到 {len(btb_list)} 条背对背证记录")

        # ========================================
        # 修改联动冲突检测测试
        # ========================================
        print("\n" + "=" * 60)
        print("三、修改联动冲突检测测试")
        print("=" * 60)

        print("\n" + "-" * 40)
        print("测试20: 原证修改导致背对背证冲突(装运日期)")
        print("-" * 40)

        db.refresh(lc2)
        print(f"    原证当前装运日期: {lc2.latest_shipment_date}")
        print(f"    背对背证装运日期: {btb1.latest_shipment_date}")
        print(f"    背对背证冲突状态: {btb1.conflict_status}")

        amendment_data = schemas.AmendmentCreate(
            lc_number=lc2_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="latest_shipment_date",
                    old_value="2024-04-15",
                    new_value="2024-04-05",
                ),
            ]
        )

        amend1 = crud.create_amendment(db, amendment_data)
        accepted_amend = crud.accept_amendment(db, amend1.amendment_number)

        db.refresh(btb1)
        assert btb1.conflict_status == "conflict", f"背对背证应标记为冲突，实际为: {btb1.conflict_status}"
        assert btb1.conflict_details is not None
        assert len(btb1.conflict_details) > 0
        print(f"[✓] 原证修改后背对背证正确标记为冲突")
        print(f"    背对背证冲突状态: {btb1.conflict_status}")
        for detail in btb1.conflict_details:
            print(f"    冲突详情: {detail.get('message', '')}")

        print("\n" + "-" * 40)
        print("测试21: 原证修改导致背对背证冲突(到期日)")
        print("-" * 40)

        db.refresh(lc2)
        amend2_data = schemas.AmendmentCreate(
            lc_number=lc2_number,
            field_changes=[
                schemas.FieldChange(
                    field_name="expiry_date",
                    old_value="2024-05-15",
                    new_value="2024-05-01",
                ),
            ]
        )
        amend2 = crud.create_amendment(db, amend2_data)
        crud.accept_amendment(db, amend2.amendment_number)

        db.refresh(btb1)
        assert btb1.conflict_status == "conflict"
        expiry_conflicts = [d for d in btb1.conflict_details if d.get("field") == "expiry_date"]
        assert len(expiry_conflicts) > 0
        print(f"[✓] 原证到期日修改导致背对背证到期日冲突")
        for detail in expiry_conflicts:
            print(f"    冲突详情: {detail.get('message', '')}")

        print("\n" + "-" * 40)
        print("测试22: 原证修改不影响背对背证(无冲突)")
        print("-" * 40)

        lc3_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-NO-CONFLICT-003",
            issuing_bank="中国银行北京分行",
            beneficiary_name="北京进出口有限公司",
            applicant_name="OVERSEAS BUYER INC.",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=date(2024, 6, 30),
            latest_presentation_date=date(2024, 7, 15),
            expiry_date=date(2024, 7, 31),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="TIANJIN PORT",
            port_of_discharge="LOS ANGELES PORT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="ELECTRONIC PRODUCTS",
            additional_terms=["所有单据须显示信用证号"],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
            ]
        )
        lc3 = crud.create_letter_of_credit(db, lc3_data)

        btb3_data = schemas.BackToBackLCCreate(
            lc_number="LC-TEST-NO-CONFLICT-003",
            beneficiary_name="天津电子厂 TIANJIN ELECTRONICS FACTORY",
            applicant_name="北京进出口有限公司",
            issuing_bank="中国银行天津分行",
            amount=80000.00,
            latest_shipment_date=date(2024, 6, 25),
            latest_presentation_date=date(2024, 7, 10),
            expiry_date=date(2024, 7, 21),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="TIANJIN PORT",
            port_of_discharge="LOS ANGELES PORT",
            goods_description="ELECTRONIC COMPONENTS",
            document_requirements=[
                schemas.BackToBackDocumentRequirementCreate(document_type="invoice", original_copies=1, copy_copies=1),
            ],
        )
        btb3 = crud.create_back_to_back_lc(db, btb3_data)
        assert btb3.conflict_status == "normal"

        amend3_data = schemas.AmendmentCreate(
            lc_number="LC-TEST-NO-CONFLICT-003",
            field_changes=[
                schemas.FieldChange(
                    field_name="goods_description",
                    old_value="ELECTRONIC PRODUCTS",
                    new_value="ELECTRONIC PRODUCTS AND ACCESSORIES",
                ),
            ]
        )
        amend3 = crud.create_amendment(db, amend3_data)
        crud.accept_amendment(db, amend3.amendment_number)

        db.refresh(btb3)
        assert btb3.conflict_status == "normal", f"非关键字段修改不应导致冲突，实际为: {btb3.conflict_status}"
        print(f"[✓] 非约束字段修改不影响背对背证冲突状态")

        print("\n" + "-" * 40)
        print("测试23: 原证金额减少导致背对背证冲突")
        print("-" * 40)

        lc4_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-AMOUNT-CONFLICT-004",
            issuing_bank="工商银行上海分行",
            beneficiary_name="上海贸易公司",
            applicant_name="FOREIGN BUYER LTD.",
            currency=schemas.Currency.USD,
            amount=200000.00,
            latest_shipment_date=date(2024, 9, 30),
            latest_presentation_date=date(2024, 10, 15),
            expiry_date=date(2024, 10, 31),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI PORT",
            port_of_discharge="NEW YORK PORT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="MACHINERY EQUIPMENT",
            additional_terms=[],
            fee_tier=schemas.FeeTier.VIP,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
            ]
        )
        lc4 = crud.create_letter_of_credit(db, lc4_data)

        btb4_data = schemas.BackToBackLCCreate(
            lc_number="LC-TEST-AMOUNT-CONFLICT-004",
            beneficiary_name="江苏机械制造厂 JIANGSU MACHINERY FACTORY",
            applicant_name="上海贸易公司",
            issuing_bank="工商银行南京分行",
            amount=180000.00,
            latest_shipment_date=date(2024, 9, 25),
            latest_presentation_date=date(2024, 10, 10),
            expiry_date=date(2024, 10, 21),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI PORT",
            port_of_discharge="NEW YORK PORT",
            goods_description="MACHINERY COMPONENTS",
            document_requirements=[
                schemas.BackToBackDocumentRequirementCreate(document_type="invoice", original_copies=1, copy_copies=1),
            ],
        )
        btb4 = crud.create_back_to_back_lc(db, btb4_data)

        amend4_data = schemas.AmendmentCreate(
            lc_number="LC-TEST-AMOUNT-CONFLICT-004",
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=200000.00,
                    new_value=180000.00,
                ),
            ]
        )
        amend4 = crud.create_amendment(db, amend4_data)
        crud.accept_amendment(db, amend4.amendment_number)

        db.refresh(btb4)
        max_btb_amount = 180000.00 * 0.95
        assert btb4.conflict_status == "conflict"
        amount_conflicts = [d for d in btb4.conflict_details if d.get("field") == "amount"]
        assert len(amount_conflicts) > 0
        print(f"[✓] 原证金额减少导致背对背证金额冲突")
        print(f"    新的原证95%上限: {max_btb_amount}")
        print(f"    背对背证金额: {btb4.amount}")
        for detail in amount_conflicts:
            print(f"    冲突详情: {detail.get('message', '')}")

        # ========================================
        # 综合查询测试
        # ========================================
        print("\n" + "=" * 60)
        print("四、综合查询测试")
        print("=" * 60)

        print("\n" + "-" * 40)
        print("测试24: 查询原证剩余可用金额")
        print("-" * 40)

        available1 = crud.get_lc_available_amount(db, lc_number)
        print(f"[✓] 信用证 {lc_number} 可用金额查询:")
        print(f"    原证金额: {available1['original_amount']}")
        print(f"    已转让金额: {available1['total_transferred_amount']}")
        print(f"    背对背证金额: {available1['total_back_to_back_amount']}")
        print(f"    剩余可用: {available1['remaining_available_amount']}")

        confirmed_transfers = [t for t in available1["transfers"] if t.status == "confirmed"]
        expected_transferred = sum(t.transfer_amount for t in confirmed_transfers)
        assert abs(available1["total_transferred_amount"] - expected_transferred) < 0.01

        print("\n" + "-" * 40)
        print("测试25: 查询原证所有转让记录和背对背证汇总")
        print("-" * 40)

        summary = crud.get_lc_transfer_and_back_to_back_summary(db, lc_number)
        assert summary["lc_number"] == lc_number
        print(f"[✓] 转让与背对背汇总查询成功")
        print(f"    转让记录数: {len(summary['transfers'])}")
        print(f"    背对背证数: {len(summary['back_to_back_lcs'])}")

        print("\n" + "-" * 40)
        print("测试26: 不存在的信用证查询返回错误")
        print("-" * 40)

        try:
            crud.get_lc_available_amount(db, "LC-NONEXISTENT-999")
            print("[✗] 应该报错")
            assert False
        except ValueError as e:
            print(f"[✓] 正确报错: {str(e)}")

        print("\n" + "-" * 40)
        print("测试27: 不存在的转让证查询返回空")
        print("-" * 40)

        not_found = crud.get_transfer_by_number(db, "LC-NONEXISTENT-T-001")
        assert not_found is None
        print(f"[✓] 不存在的转让证返回 None")

        print("\n" + "-" * 40)
        print("测试28: 转让与背对背证共存时的可用金额计算")
        print("-" * 40)

        lc5_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-MIXED-005",
            issuing_bank="建设银行广州分行",
            beneficiary_name="广州外贸公司",
            applicant_name="IMPORT CORP.",
            currency=schemas.Currency.USD,
            amount=100000.00,
            latest_shipment_date=date(2024, 12, 15),
            latest_presentation_date=date(2025, 1, 5),
            expiry_date=date(2025, 1, 31),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="GUANGZHOU PORT",
            port_of_discharge="HAMBURG PORT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="FURNITURE PRODUCTS",
            additional_terms=[],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=2, copy_copies=1),
            ]
        )
        lc5 = crud.create_letter_of_credit(db, lc5_data)

        transfer_mixed = schemas.TransferCreate(
            lc_number="LC-TEST-MIXED-005",
            second_beneficiary_name="佛山家具厂 FOSHAN FURNITURE FACTORY",
            transfer_amount=30000.00,
            transfer_type=schemas.TransferType.PARTIAL,
        )
        t_mixed = crud.create_transfer(db, transfer_mixed)
        crud.confirm_transfer(db, t_mixed.transfer_number, "confirm")

        btb_mixed_data = schemas.BackToBackLCCreate(
            lc_number="LC-TEST-MIXED-005",
            beneficiary_name="东莞木材供应厂 DONGGUAN WOOD SUPPLIER",
            applicant_name="广州外贸公司",
            issuing_bank="建设银行东莞分行",
            amount=40000.00,
            latest_shipment_date=date(2024, 12, 10),
            latest_presentation_date=date(2024, 12, 25),
            expiry_date=date(2025, 1, 21),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="GUANGZHOU PORT",
            port_of_discharge="HAMBURG PORT",
            goods_description="WOOD MATERIALS",
            document_requirements=[
                schemas.BackToBackDocumentRequirementCreate(document_type="invoice", original_copies=1, copy_copies=1),
            ],
        )
        btb_mixed = crud.create_back_to_back_lc(db, btb_mixed_data)

        available5 = crud.get_lc_available_amount(db, "LC-TEST-MIXED-005")
        assert available5["total_transferred_amount"] == 30000.00
        assert available5["total_back_to_back_amount"] == 40000.00
        assert available5["remaining_available_amount"] == 30000.00
        print(f"[✓] 转让与背对背证共存时可用金额计算正确")
        print(f"    原证金额: {available5['original_amount']}")
        print(f"    已转让: {available5['total_transferred_amount']}")
        print(f"    背对背证: {available5['total_back_to_back_amount']}")
        print(f"    剩余可用: {available5['remaining_available_amount']}")

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
    test_transfer_and_back_to_back()
