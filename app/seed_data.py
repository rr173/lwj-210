import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from app.database import Base, engine, SessionLocal
from app import models, schemas, crud
from app.audit_engine import AuditEngine


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_data():
    db = SessionLocal()

    try:
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
                lc_id=lc1.id, submission_id=submission1_id, document_type="invoice",
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
                lc_id=lc1.id, submission_id=submission1_id, document_type="bill_of_lading",
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
                lc_id=lc1.id, submission_id=submission1_id, document_type="packing_list",
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
                lc_id=lc1.id, submission_id=submission1_id, document_type="insurance",
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
                lc_id=lc1.id, submission_id=submission1_id, document_type="origin_cert",
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
            lc_id=lc1.id, submission_id=submission1_id, conclusion=conclusion1,
            total_discrepancies=len(discrepancies1), critical_count=critical1,
            minor_count=minor1, presentation_date=presentation_date1
        )
        db.add(audit1)
        db.flush()

        for d in discrepancies1:
            db.add(models.Discrepancy(audit_record_id=audit1.id, **d))
        print(f"创建审核记录1: 结论={conclusion1}, 不符点数量={len(discrepancies1)}")

        submission2_id = "SUB-LC1-20240315-DISCREPANT"
        presentation_date2 = date(2024, 3, 20)

        docs2 = [
            models.Document(
                lc_id=lc1.id, submission_id=submission2_id, document_type="invoice",
                original_copies_submitted=3, copy_copies_submitted=2,
                content={
                    "invoice_number": "INV-2024-0315-002",
                    "invoice_date": "2024-03-12",
                    "beneficiary": "上海国际贸易有限公司 shanghai international trading co., ltd.",
                    "applicant": "ABC Importing Company S.A.",
                    "currency": "USD",
                    "goods": [
                        {"name": "100% COTTON MEN'S T-SHIRTS", "specification": "WHITE COLOR, SIZE M/L/XL", "quantity": 5000, "unit": "PCS", "unit_price": 10.00}
                    ],
                    "goods_description": "100% COTTON MEN'S T-SHIRTS, WHITE COLOR, SIZE M/L/XL, 5000PCS AT USD10.00 PER PC CIF ROTTERDAM",
                    "total_amount": 50000.00
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission2_id, document_type="bill_of_lading",
                original_copies_submitted=3, copy_copies_submitted=3,
                content={
                    "bl_number": "MAEU-2024-0315-9900",
                    "shipper": "上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD.",
                    "consignee": "TO ORDER",
                    "notify_party": "ABC IMPORTING COMPANY S.A. ROTTERDAM, NETHERLANDS",
                    "vessel_voyage": "MAERSK EMDEN V.125E",
                    "port_of_loading": "SHANGHAI PORT",
                    "port_of_discharge": "ROTTERDAM PORT",
                    "shipment_date": "2024-03-15",
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
                lc_id=lc1.id, submission_id=submission2_id, document_type="packing_list",
                original_copies_submitted=2, copy_copies_submitted=2,
                content={
                    "packing_number": "PL-2024-0315-002",
                    "date": "2024-03-12",
                    "total_packages": 250,
                    "package_type": "CTNS",
                    "gross_weight": 5250.00,
                    "net_weight": 5000.00,
                    "goods_description": "COTTON MEN'S T-SHIRTS"
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission2_id, document_type="insurance",
                original_copies_submitted=2, copy_copies_submitted=1,
                content={
                    "policy_number": "PICC-2024-SEA-00099",
                    "issue_date": "2024-03-14",
                    "insured": "上海国际贸易有限公司 shanghai international trading co., ltd.",
                    "insurance_amount": 55000.00,
                    "currency": "USD",
                    "risks": "COVERING ALL RISKS AND WAR RISKS AS PER CIC 1/1/1981",
                    "voyage": "FROM SHANGHAI TO ROTTERDAM",
                    "goods_description": "COTTON T-SHIRTS"
                }
            ),
            models.Document(
                lc_id=lc1.id, submission_id=submission2_id, document_type="origin_cert",
                original_copies_submitted=1, copy_copies_submitted=1,
                content={
                    "cert_number": "CCO-2024-0312-015",
                    "issue_date": "2024-03-13",
                    "issuing_authority": "CCPIT SHANGHAI",
                    "origin_country": "CHINA",
                    "goods_description": "MEN'S COTTON T-SHIRTS",
                    "exporter": "SHANGHAI INTERNATIONAL TRADING CO., LTD."
                }
            ),
        ]

        for d in docs2:
            db.add(d)
        db.flush()

        engine2 = AuditEngine(lc1, docs2, presentation_date2)
        conclusion2, discrepancies2 = engine2.run_audit()
        critical2 = sum(1 for d in discrepancies2 if d["severity"] == "critical")
        minor2 = sum(1 for d in discrepancies2 if d["severity"] == "minor")

        audit2 = models.AuditRecord(
            lc_id=lc1.id, submission_id=submission2_id, conclusion=conclusion2,
            total_discrepancies=len(discrepancies2), critical_count=critical2,
            minor_count=minor2, presentation_date=presentation_date2
        )
        db.add(audit2)
        db.flush()

        for d in discrepancies2:
            db.add(models.Discrepancy(audit_record_id=audit2.id, **d))
        print(f"创建审核记录2: 结论={conclusion2}, 不符点数量={len(discrepancies2)} (critical={critical2}, minor={minor2})")
        for d in discrepancies2:
            print(f"  - [{d['severity']}] {d['description']}")

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
