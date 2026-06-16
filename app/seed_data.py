import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.audit_engine import AuditEngine
from app.models import FEE_TYPE_FIRST_SUBMISSION, REVIEW_STATUS_PENDING


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_data():
    db = SessionLocal()

    try:
        crud.migrate_existing_audit_records(db)

        existing_lc1 = crud.get_letter_of_credit_by_number(db, "LC-SEA-CIF-2024-001")
        if existing_lc1:
            print("预置数据已存在，跳过初始化")
            return

        lc1_data = schemas.LetterOfCreditCreate(
            lc_number="LC-SEA-CIF-2024-001",
            issuing_bank="中国银行上海分行 BANK OF CHINA SHANGHAI BRANCH",
            beneficiary_name="上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.",
            applicant_name="ABC IMPORTING COMPANY S.A.",
            currency=schemas.Currency.USD,
            amount=50000.00,
            latest_shipment_date=date(2024, 3, 10),
            latest_presentation_date=date(2024, 3, 31),
            expiry_date=date(2024, 4, 10),
            transport_mode=schemas.TransportMode.SEA,
            port_of_loading="SHANGHAI PORT",
            port_of_discharge="ROTTERDAM PORT",
            partial_shipment_allowed=False,
            transshipment_allowed=False,
            goods_description="100% COTTON MEN'S T-SHIRTS, WHITE COLOR, SIZE M/L/XL, 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
            additional_terms=[
                "保险金额不低于发票金额110%",
                "提单必须做成指示抬头(TO ORDER)",
                "提单显示运费预付(FREIGHT PREPAID)",
                "提交清洁已装船提单"
            ],
            fee_tier=schemas.FeeTier.STANDARD,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=3, copy_copies=3),
                schemas.DocumentRequirementCreate(document_type="packing_list", original_copies=2, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="insurance", original_copies=2, copy_copies=1),
                schemas.DocumentRequirementCreate(document_type="origin_cert", original_copies=1, copy_copies=1),
            ]
        )
        lc1 = crud.create_letter_of_credit(db, lc1_data)
        print(f"创建信用证1: {lc1.lc_number}")

        lc2_data = schemas.LetterOfCreditCreate(
            lc_number="LC-AIR-CFR-2024-002",
            issuing_bank="汇丰银行香港分行 HSBC HONG KONG BRANCH",
            beneficiary_name="深圳电子科技有限公司 SHENZHEN ELECTRONICS TECHNOLOGY CO., LTD.",
            applicant_name="XYZ ELECTRONICS DISTRIBUTOR INC.",
            currency=schemas.Currency.EUR,
            amount=35000.00,
            latest_shipment_date=date(2024, 4, 15),
            latest_presentation_date=date(2024, 5, 5),
            expiry_date=date(2024, 5, 15),
            transport_mode=schemas.TransportMode.AIR,
            port_of_loading="SHENZHEN BAO'AN INTERNATIONAL AIRPORT",
            port_of_discharge="FRANKFURT AM MAIN AIRPORT",
            partial_shipment_allowed=True,
            transshipment_allowed=True,
            goods_description="WIRELESS BLUETOOTH EARPHONES MODEL X200, 7000SETS AT EUR5.00 PER SET CFR FRANKFURT",
            additional_terms=[
                "空运单显示运费到付(FREIGHT COLLECT)",
                "原产地证由中国国际贸易促进委员会签发"
            ],
            fee_tier=schemas.FeeTier.PREFERRED,
            document_requirements=[
                schemas.DocumentRequirementCreate(document_type="invoice", original_copies=3, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="bill_of_lading", original_copies=1, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="packing_list", original_copies=2, copy_copies=2),
                schemas.DocumentRequirementCreate(document_type="origin_cert", original_copies=1, copy_copies=1),
                schemas.DocumentRequirementCreate(document_type="inspection_cert", original_copies=1, copy_copies=1),
            ]
        )
        lc2 = crud.create_letter_of_credit(db, lc2_data)
        print(f"创建信用证2: {lc2.lc_number}")

        submission1_id = "SUB-LC1-20240308-COMPLIANT"
        presentation_date1 = date(2024, 3, 8)

        docs1 = [
            models.Document(
                lc_id=lc1.id, submission_id=submission1_id,
                original_submission_id=submission1_id, resubmission_round=0,
                document_type="invoice",
                original_copies_submitted=3, copy_copies_submitted=2,
                content={
                    "invoice_number": "INV-2024-0308-001",
                    "invoice_date": "2024-03-05",
                    "beneficiary": "上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.",
                    "applicant": "ABC IMPORTING COMPANY S.A.",
                    "currency": "USD",
                    "goods": [
                        {"name": "100% COTTON MEN'S T-SHIRTS", "specification": "WHITE COLOR, SIZE M/L/XL", "quantity": 5000, "unit": "PCS", "unit_price": 10.00}
                    ],
                    "goods_description": "100% COTTON MEN'S T-SHIRTS, WHITE COLOR, SIZE M/L/XL, 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
                    "total_amount": 50000.00
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission1_id,
                original_submission_id=submission1_id, resubmission_round=0,
                document_type="bill_of_lading",
                original_copies_submitted=3, copy_copies_submitted=3,
                content={
                    "bl_number": "MAEU-2024-0305-8899",
                    "shipper": "上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.",
                    "consignee": "TO ORDER",
                    "notify_party": "ABC IMPORTING COMPANY S.A. ROTTERDAM, NETHERLANDS",
                    "vessel_voyage": "MAERSK EMDEN V.123E",
                    "port_of_loading": "SHANGHAI PORT",
                    "port_of_discharge": "ROTTERDAM PORT",
                    "shipment_date": "2024-03-08",
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
            models.Document(
                lc_id=lc1.id, submission_id=submission1_id,
                original_submission_id=submission1_id, resubmission_round=0,
                document_type="packing_list",
                original_copies_submitted=2, copy_copies_submitted=2,
                content={
                    "packing_number": "PL-2024-0308-001",
                    "date": "2024-03-05",
                    "total_packages": 250,
                    "package_type": "CTNS",
                    "gross_weight": 5250.00,
                    "net_weight": 5000.00,
                    "goods_description": "COTTON MEN'S T-SHIRTS"
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission1_id,
                original_submission_id=submission1_id, resubmission_round=0,
                document_type="insurance",
                original_copies_submitted=2, copy_copies_submitted=1,
                content={
                    "policy_number": "PICC-2024-SEA-00088",
                    "issue_date": "2024-03-07",
                    "insured": "上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.",
                    "insurance_amount": 55000.00,
                    "currency": "USD",
                    "risks": "COVERING ALL RISKS AND WAR RISKS AS PER CIC 1/1/1981",
                    "voyage": "FROM SHANGHAI TO ROTTERDAM",
                    "goods_description": "COTTON T-SHIRTS"
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission1_id,
                original_submission_id=submission1_id, resubmission_round=0,
                document_type="origin_cert",
                original_copies_submitted=1, copy_copies_submitted=1,
                content={
                    "cert_number": "CCO-2024-0305-012",
                    "issue_date": "2024-03-06",
                    "issuing_authority": "CCPIT SHANGHAI",
                    "origin_country": "CHINA",
                    "goods_description": "MEN'S COTTON T-SHIRTS",
                    "exporter": "SHANGHAI INTERNATIONAL TRADING CO., LTD."
                }
            ),
        ]

        for d in docs1:
            db.add(d)
        db.flush()

        engine1 = AuditEngine(lc1, docs1, presentation_date1)
        conclusion1, discrepancies1 = engine1.run_audit()
        critical1 = sum(1 for d in discrepancies1 if d["severity"] == "critical")
        minor1 = sum(1 for d in discrepancies1 if d["severity"] == "minor")

        audit1 = models.AuditRecord(
            lc_id=lc1.id, submission_id=submission1_id,
            original_submission_id=submission1_id, resubmission_round=0,
            modification_remark=None,
            conclusion=conclusion1,
            auto_conclusion=conclusion1,
            final_conclusion=None,
            total_discrepancies=len(discrepancies1), critical_count=critical1,
            minor_count=minor1, presentation_date=presentation_date1,
            review_status=REVIEW_STATUS_PENDING
        )
        db.add(audit1)
        db.flush()

        for d in discrepancies1:
            db.add(models.Discrepancy(audit_record_id=audit1.id, **d))
        print(f"创建审核记录1: 结论={conclusion1}, 不符点数量={len(discrepancies1)}")

        crud.create_fee_record(db, lc1, audit1, FEE_TYPE_FIRST_SUBMISSION, len(docs1))
        print(f"创建收费记录1: 费用编号 FEE-{lc1.lc_number}-...")

        submission2_id = "SUB-LC2-20240420-DISCREPANT"
        presentation_date2 = date(2024, 4, 25)

        docs2 = [
            models.Document(
                lc_id=lc2.id, submission_id=submission2_id,
                original_submission_id=submission2_id, resubmission_round=0,
                document_type="invoice",
                original_copies_submitted=3, copy_copies_submitted=2,
                content={
                    "invoice_number": "INV-2024-0420-007",
                    "invoice_date": "2024-04-18",
                    "beneficiary": "深圳电子科技有限公司 shenzhen electronics technology co., ltd.",
                    "applicant": "XYZ Electronics Distributor Inc.",
                    "currency": "EUR",
                    "goods": [
                        {"name": "WIRELESS BLUETOOTH EARPHONES", "specification": "MODEL X200", "quantity": 7000, "unit": "SETS", "unit_price": 5.00}
                    ],
                    "goods_description": "WIRELESS BLUETOOTH EARPHONES MODEL X200, 7000SETS AT EUR5.00 PER SET CFR FRANKFURT",
                    "total_amount": 35000.00
                }
            ),
            models.Document(
                lc_id=lc2.id, submission_id=submission2_id,
                original_submission_id=submission2_id, resubmission_round=0,
                document_type="bill_of_lading",
                original_copies_submitted=1, copy_copies_submitted=2,
                content={
                    "bl_number": "CAW-2024-0420-7788",
                    "shipper": "深圳电子科技有限公司 SHENZHEN ELECTRONICS TECHNOLOGY CO., LTD.",
                    "consignee": "XYZ ELECTRONICS DISTRIBUTOR INC.",
                    "notify_party": "XYZ ELECTRONICS DISTRIBUTOR INC. FRANKFURT, GERMANY",
                    "flight_number": "CA1234 / LH5678",
                    "port_of_loading": "SHENZHEN BAO'AN INTERNATIONAL AIRPORT",
                    "port_of_discharge": "FRANKFURT AM MAIN AIRPORT",
                    "shipment_date": "2024-04-20",
                    "packages": 7000,
                    "package_unit": "SETS",
                    "freight_term": "FREIGHT COLLECT",
                    "clean": True,
                    "transshipment": True,
                    "goods_description": "WIRELESS BLUETOOTH EARPHONES"
                }
            ),
            models.Document(
                lc_id=lc2.id, submission_id=submission2_id,
                original_submission_id=submission2_id, resubmission_round=0,
                document_type="packing_list",
                original_copies_submitted=2, copy_copies_submitted=2,
                content={
                    "packing_number": "PL-2024-0420-007",
                    "date": "2024-04-18",
                    "total_packages": 350,
                    "package_type": "CTNS",
                    "gross_weight": 1050.00,
                    "net_weight": 980.00,
                    "goods_description": "BLUETOOTH EARPHONES"
                }
            ),
            models.Document(
                lc_id=lc2.id, submission_id=submission2_id,
                original_submission_id=submission2_id, resubmission_round=0,
                document_type="origin_cert",
                original_copies_submitted=1, copy_copies_submitted=1,
                content={
                    "cert_number": "CCO-2024-0418-033",
                    "issue_date": "2024-04-19",
                    "issuing_authority": "CCPIT SHENZHEN",
                    "origin_country": "CHINA",
                    "goods_description": "WIRELESS EARPHONES",
                    "exporter": "SHENZHEN ELECTRONICS TECHNOLOGY CO., LTD."
                }
            ),
            models.Document(
                lc_id=lc2.id, submission_id=submission2_id,
                original_submission_id=submission2_id, resubmission_round=0,
                document_type="inspection_cert",
                original_copies_submitted=1, copy_copies_submitted=1,
                content={
                    "cert_number": "SGS-2024-0419-088",
                    "issue_date": "2024-04-19",
                    "issuing_authority": "SGS SHENZHEN",
                    "inspection_date": "2024-04-18",
                    "result": "PASSED",
                    "goods_description": "WIRELESS BLUETOOTH EARPHONES MODEL X200",
                    "quantity": 7000
                }
            ),
        ]

        for d in docs2:
            db.add(d)
        db.flush()

        engine2 = AuditEngine(lc2, docs2, presentation_date2)
        conclusion2, discrepancies2 = engine2.run_audit()
        critical2 = sum(1 for d in discrepancies2 if d["severity"] == "critical")
        minor2 = sum(1 for d in discrepancies2 if d["severity"] == "minor")

        audit2 = models.AuditRecord(
            lc_id=lc2.id, submission_id=submission2_id,
            original_submission_id=submission2_id, resubmission_round=0,
            modification_remark=None,
            conclusion=conclusion2,
            auto_conclusion=conclusion2,
            final_conclusion=None,
            total_discrepancies=len(discrepancies2), critical_count=critical2,
            minor_count=minor2, presentation_date=presentation_date2,
            review_status=REVIEW_STATUS_PENDING
        )
        db.add(audit2)
        db.flush()

        for d in discrepancies2:
            db.add(models.Discrepancy(audit_record_id=audit2.id, **d))
        print(f"创建审核记录2: 结论={conclusion2}, 不符点数量={len(discrepancies2)} (critical={critical2}, minor={minor2})")
        for d in discrepancies2:
            print(f"  - [{d['severity']}] {d['description']}")

        crud.create_fee_record(db, lc2, audit2, FEE_TYPE_FIRST_SUBMISSION, len(docs2))
        print(f"创建收费记录2: 费用编号 FEE-{lc2.lc_number}-...")

        db.commit()
        print("预置数据初始化完成！")

    except Exception as e:
        db.rollback()
        print(f"预置数据初始化失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_data()
