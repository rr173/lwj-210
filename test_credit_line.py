import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app import models, schemas, crud


def test_credit_line_module():
    print("=" * 60)
    print("授信额度管理模块功能测试")
    print("=" * 60)

    test_db_path = "./data/test_credit_line.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    test_db_url = f"sqlite:///{test_db_path}"
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    try:
        applicant_name = "TEST APPLICANT CO., LTD."
        currency = "USD"
        total_amount = 100000.00

        print("\n" + "-" * 40)
        print("测试1: 创建授信额度")
        print("-" * 40)

        credit_line_data = schemas.CreditLineCreate(
            applicant_name=applicant_name,
            total_amount=total_amount,
            currency=schemas.Currency.USD,
        )
        credit_line = crud.create_credit_line(db, credit_line_data)
        assert credit_line is not None
        assert credit_line.applicant_name == applicant_name
        assert credit_line.currency == currency
        assert credit_line.total_amount == total_amount
        print(f"[✓] 授信额度创建成功: ID={credit_line.id}")
        print(f"    申请人: {credit_line.applicant_name}")
        print(f"    币种: {credit_line.currency}")
        print(f"    总额度: {credit_line.total_amount}")

        print("\n" + "-" * 40)
        print("测试2: 重复创建授信额度（应失败）")
        print("-" * 40)

        try:
            crud.create_credit_line(db, credit_line_data)
            print("[✗] 重复创建应该失败，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 重复创建被拒绝: {e}")

        print("\n" + "-" * 40)
        print("测试3: 查询授信额度详情（无信用证）")
        print("-" * 40)

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        assert detail["total_amount"] == total_amount
        assert detail["used_amount"] == 0
        assert detail["available_amount"] == total_amount
        assert len(detail["occupancy_details"]) == 0
        print(f"[✓] 额度查询成功")
        print(f"    总额度: {detail['total_amount']}")
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")

        print("\n" + "-" * 40)
        print("测试4: 开立信用证 - 额度充足")
        print("-" * 40)

        lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-2025-001",
            issuing_bank="TEST BANK",
            beneficiary_name="TEST BENEFICIARY",
            applicant_name=applicant_name,
            currency=schemas.Currency.USD,
            amount=30000.00,
            latest_shipment_date=date.today() + timedelta(days=30),
            latest_presentation_date=date.today() + timedelta(days=45),
            expiry_date=date.today() + timedelta(days=60),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="LOS ANGELES",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="TEST GOODS",
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type="invoice", original_copies=3, copy_copies=2
                ),
                schemas.DocumentRequirementCreate(
                    document_type="bill_of_lading", original_copies=3, copy_copies=3
                ),
            ],
        )
        lc = crud.create_letter_of_credit(db, lc_data)
        assert lc is not None
        print(f"[✓] 信用证开立成功: {lc.lc_number}, 金额: {lc.amount}")

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")
        assert detail["used_amount"] == 30000.00
        assert detail["available_amount"] == 70000.00
        assert len(detail["occupancy_details"]) == 1
        assert detail["occupancy_details"][0]["lc_number"] == "LC-TEST-2025-001"
        assert detail["occupancy_details"][0]["amount"] == 30000.00
        print(f"[✓] 额度占用正确")

        print("\n" + "-" * 40)
        print("测试5: 开立信用证 - 额度不足（应失败）")
        print("-" * 40)

        lc_data2 = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-2025-002",
            issuing_bank="TEST BANK",
            beneficiary_name="TEST BENEFICIARY 2",
            applicant_name=applicant_name,
            currency=schemas.Currency.USD,
            amount=80000.00,
            latest_shipment_date=date.today() + timedelta(days=30),
            latest_presentation_date=date.today() + timedelta(days=45),
            expiry_date=date.today() + timedelta(days=60),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="LOS ANGELES",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="TEST GOODS 2",
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type="invoice", original_copies=3, copy_copies=2
                ),
            ],
        )
        try:
            crud.create_letter_of_credit(db, lc_data2)
            print("[✗] 额度不足时开证应该失败，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 额度不足被拒绝: {e}")

        print("\n" + "-" * 40)
        print("测试6: 再开一张信用证（额度内）")
        print("-" * 40)

        lc_data3 = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-2025-003",
            issuing_bank="TEST BANK",
            beneficiary_name="TEST BENEFICIARY 3",
            applicant_name=applicant_name,
            currency=schemas.Currency.USD,
            amount=40000.00,
            latest_shipment_date=date.today() + timedelta(days=30),
            latest_presentation_date=date.today() + timedelta(days=45),
            expiry_date=date.today() + timedelta(days=60),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="LOS ANGELES",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="TEST GOODS 3",
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type="invoice", original_copies=3, copy_copies=2
                ),
            ],
        )
        lc3 = crud.create_letter_of_credit(db, lc_data3)
        assert lc3 is not None
        print(f"[✓] 信用证开立成功: {lc3.lc_number}, 金额: {lc3.amount}")

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")
        assert detail["used_amount"] == 70000.00
        assert detail["available_amount"] == 30000.00
        assert len(detail["occupancy_details"]) == 2
        print(f"[✓] 多张信用证额度累计正确")

        print("\n" + "-" * 40)
        print("测试7: 到期信用证自动释放额度")
        print("-" * 40)

        expired_lc_data = schemas.LetterOfCreditCreate(
            lc_number="LC-TEST-2025-EXPIRED",
            issuing_bank="TEST BANK",
            beneficiary_name="TEST BENEFICIARY 4",
            applicant_name=applicant_name,
            currency=schemas.Currency.USD,
            amount=20000.00,
            latest_shipment_date=date.today() - timedelta(days=60),
            latest_presentation_date=date.today() - timedelta(days=45),
            expiry_date=date.today() - timedelta(days=30),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI",
            port_of_discharge="LOS ANGELES",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="EXPIRED GOODS",
            fee_tier=schemas.FeeTier.STANDARD,
            payment_method=schemas.PaymentMethod.SIGHT,
            document_requirements=[
                schemas.DocumentRequirementCreate(
                    document_type="invoice", original_copies=3, copy_copies=2
                ),
            ],
        )
        expired_lc = crud.create_letter_of_credit(db, expired_lc_data)
        assert expired_lc is not None
        print(f"[✓] 已过期信用证创建成功: {expired_lc.lc_number}")

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")
        print(f"    占用明细数量: {len(detail['occupancy_details'])}")
        assert detail["used_amount"] == 70000.00
        assert detail["available_amount"] == 30000.00
        assert len(detail["occupancy_details"]) == 2
        lc_numbers = [d["lc_number"] for d in detail["occupancy_details"]]
        assert "LC-TEST-2025-EXPIRED" not in lc_numbers
        print(f"[✓] 过期信用证不占用额度，自动释放")

        print("\n" + "-" * 40)
        print("测试8: Amendment 增加金额 - 额度充足")
        print("-" * 40)

        amendment_data = schemas.AmendmentCreate(
            lc_number="LC-TEST-2025-001",
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=30000.00,
                    new_value=50000.00,
                )
            ],
        )
        amendment = crud.create_amendment(db, amendment_data)
        accepted = crud.accept_amendment(db, amendment.amendment_number)
        assert accepted.status == "accepted"
        print(f"[✓] 修改接受成功，金额从 30000 增加到 50000")

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")
        assert detail["used_amount"] == 90000.00
        assert detail["available_amount"] == 10000.00
        print(f"[✓] 增加金额后额度占用正确")

        print("\n" + "-" * 40)
        print("测试9: Amendment 增加金额 - 额度不足（应失败）")
        print("-" * 40)

        amendment_data2 = schemas.AmendmentCreate(
            lc_number="LC-TEST-2025-003",
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=40000.00,
                    new_value=60000.00,
                )
            ],
        )
        amendment2 = crud.create_amendment(db, amendment_data2)
        try:
            crud.accept_amendment(db, amendment2.amendment_number)
            print("[✗] 额度不足时增加金额应该失败，但成功了")
            assert False
        except ValueError as e:
            print(f"[✓] 额度不足被拒绝: {e}")

        print("\n" + "-" * 40)
        print("测试10: Amendment 减少金额")
        print("-" * 40)

        amendment_data3 = schemas.AmendmentCreate(
            lc_number="LC-TEST-2025-001",
            field_changes=[
                schemas.FieldChange(
                    field_name="amount",
                    old_value=50000.00,
                    new_value=35000.00,
                )
            ],
        )
        amendment3 = crud.create_amendment(db, amendment_data3)
        accepted3 = crud.accept_amendment(db, amendment3.amendment_number)
        assert accepted3.status == "accepted"
        print(f"[✓] 修改接受成功，金额从 50000 减少到 35000")

        detail = crud.get_credit_line_detail(db, applicant_name, currency)
        print(f"    已用额度: {detail['used_amount']}")
        print(f"    可用额度: {detail['available_amount']}")
        assert detail["used_amount"] == 75000.00
        assert detail["available_amount"] == 25000.00
        print(f"[✓] 减少金额后额度释放正确")

        print("\n" + "-" * 40)
        print("测试11: 查询额度流水")
        print("-" * 40)

        transactions = crud.get_credit_line_transactions(db, applicant_name, currency)
        print(f"[✓] 查询到 {len(transactions)} 条流水记录")
        assert len(transactions) >= 5

        print(f"\n    流水列表（按时间倒序）:")
        for i, tx in enumerate(transactions[:10]):
            print(
                f"    {i + 1}. {tx.transaction_type:8s} | "
                f"金额: {tx.change_amount:>10.2f} | "
                f"余额前: {tx.balance_before:>10.2f} | "
                f"余额后: {tx.balance_after:>10.2f} | "
                f"LC: {tx.lc_number or '-'} | "
                f"时间: {tx.created_at}"
            )

        print(f"\n[✓] 额度流水记录完整")

        print("\n" + "-" * 40)
        print("测试12: 不同币种额度独立")
        print("-" * 40)

        eur_credit_line_data = schemas.CreditLineCreate(
            applicant_name=applicant_name,
            total_amount=50000.00,
            currency=schemas.Currency.EUR,
        )
        eur_credit_line = crud.create_credit_line(db, eur_credit_line_data)
        assert eur_credit_line is not None
        print(f"[✓] EUR 授信额度创建成功: {eur_credit_line.total_amount} EUR")

        eur_detail = crud.get_credit_line_detail(db, applicant_name, "EUR")
        assert eur_detail["total_amount"] == 50000.00
        assert eur_detail["used_amount"] == 0
        print(f"[✓] EUR 额度独立，不与 USD 混淆")

        print("\n" + "=" * 60)
        print("所有测试通过！✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n[✗] 测试失败: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_credit_line_module()
