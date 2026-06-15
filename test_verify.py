#!/usr/bin/env python3
"""Verification test script for LC audit service"""
import requests
import json

BASE = "http://localhost:8000"

def test_submit(lc_number, submission_id, presentation_date, docs):
    payload = {
        "lc_number": lc_number,
        "submission_id": submission_id,
        "presentation_date": presentation_date,
        "documents": docs
    }
    r = requests.post(f"{BASE}/api/submission", json=payload)
    return r.status_code, r.json()

# LC2 info: LC-AIR-CFR-2024-002
# latest_shipment_date: 2024-04-20
# latest_presentation_date: 2024-05-05
# expiry_date: 2024-05-15
# beneficiary: 深圳创新电子科技有限公司 SHENZHEN INNOVATION ELECTRONICS CO., LTD.
# applicant: MÜLLER ELECTRONICS GMBH
# transport_mode: 空运
# port_of_loading: 深圳宝安国际机场 SHENZHEN BAOAN INTERNATIONAL AIRPORT
# port_of_discharge: 法兰克福国际机场 FRANKFURT INTERNATIONAL AIRPORT
# partial_shipment_allowed: True
# transshipment_allowed: True
# currency: EUR, amount: 35000
# goods_description: Electronic Components - Microcontroller Units (MCU) STM32F407VGT6, Qty: 10000pcs, Unit Price: EUR 3.50/pc

# Get LC2 details
r = requests.get(f"{BASE}/api/lc/LC-AIR-CFR-2024-002")
lc2 = r.json()
print("=== LC2 详情 ===")
print(f"  受益人: {lc2['beneficiary_name']}")
print(f"  申请人: {lc2['applicant_name']}")
print(f"  最迟装运: {lc2['latest_shipment_date']}")
print(f"  最迟交单: {lc2['latest_presentation_date']}")
print(f"  到期日: {lc2['expiry_date']}")
print(f"  单据要求: {[(d['document_type'], d['original_copies'], d['copy_copies']) for d in lc2['document_requirements']]}")
print(f"  附加条款: {lc2.get('additional_terms', [])}")
print()

# Test 1: Submit with shipment_date = latest (boundary, should pass)
print("=== TEST 1: 装船日期=最迟装运日 (边界值,应该通过) ===")
docs_ok = [
    {"document_type": "invoice", "original_copies_submitted": 3, "copy_copies_submitted": 2,
     "data": {"beneficiary_name": lc2["beneficiary_name"], "applicant_name": lc2["applicant_name"],
              "goods_description": lc2["goods_description"], "quantity": "10000pcs", "unit_price": "EUR 3.50/pc",
              "total_amount": 35000.00, "currency": "EUR", "invoice_date": "2024-04-18"}},
    {"document_type": "air_waybill", "original_copies_submitted": 3, "copy_copies_submitted": 0,
     "data": {"shipper": lc2["beneficiary_name"], "consignee": lc2["applicant_name"],
              "notify_party": lc2["applicant_name"], "flight_number": "CZ329",
              "airport_of_departure": "深圳宝安国际机场 SHENZHEN BAOAN INTERNATIONAL AIRPORT",
              "airport_of_destination": "法兰克福国际机场 FRANKFURT INTERNATIONAL AIRPORT",
              "shipment_date": "2024-04-20", "awb_number": "784-12345678", "pieces": 50,
              "freight_terms": "FREIGHT COLLECT"}},
    {"document_type": "packing_list", "original_copies_submitted": 3, "copy_copies_submitted": 2,
     "data": {"beneficiary_name": lc2["beneficiary_name"], "total_packages": 50,
              "total_gross_weight": "500 KGS", "total_net_weight": "450 KGS"}},
    {"document_type": "origin_cert", "original_copies_submitted": 1, "copy_copies_submitted": 2,
     "data": {"beneficiary_name": lc2["beneficiary_name"], "country_of_origin": "CHINA",
              "goods_description": "Electronic Components"}},
    {"document_type": "inspection_cert", "original_copies_submitted": 1, "copy_copies_submitted": 1,
     "data": {"inspector": "SGS", "inspection_date": "2024-04-17", "result": "PASS",
              "goods_description": "Electronic Components"}}
]
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-BOUNDARY-OK", "2024-04-20", docs_ok)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    print(f"  不符点数: {len(result.get('discrepancies', []))}")
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)}")
print()

# Test 2: Submit with shipment_date = latest+1 (should produce critical date discrepancy)
print("=== TEST 2: 装船日期=最迟装运日+1天 (应产生critical不符点) ===")
docs_late = json.loads(json.dumps(docs_ok))
docs_late[1]["data"]["shipment_date"] = "2024-04-21"  # 1 day late
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-LATE-SHIP", "2024-04-25", docs_late)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    print(f"  不符点数: {len(result.get('discrepancies', []))}")
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)}")
print()

# Test 3: Invoice amount > LC amount (should produce critical)
print("=== TEST 3: 发票金额超过信用证金额 (应产生critical) ===")
docs_over = json.loads(json.dumps(docs_ok))
docs_over[0]["data"]["total_amount"] = 35000.01
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-OVER-AMOUNT", "2024-04-20", docs_over)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    print(f"  不符点数: {len(result.get('discrepancies', []))}")
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)}")
print()

# Test 4: Party name case difference (should produce minor)
print("=== TEST 4: 受益人名称大小写差异 (应产生minor) ===")
docs_case = json.loads(json.dumps(docs_ok))
docs_case[0]["data"]["beneficiary_name"] = lc2["beneficiary_name"].lower()
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-CASE-DIFF", "2024-04-20", docs_case)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    print(f"  不符点数: {len(result.get('discrepancies', []))}")
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)}")
print()

# Test 5: Check "one submission at a time" constraint
# The LC1 already has submissions, try LC2 which now has TEST-BOUNDARY-OK
# Actually let me check if there's a constraint mechanism
print("=== TEST 5: 一证一审排他约束 ===")
# First check if there's a mechanism for this - try submitting again to same LC
docs_dup = json.loads(json.dumps(docs_ok))
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-DUPLICATE-CHECK", "2024-04-20", docs_dup)
print(f"  第二次提交状态码: {status}")
if status != 200:
    print(f"  被拒绝 (符合预期): {json.dumps(result, ensure_ascii=False)[:200]}")
else:
    print(f"  未被拒绝! 结论: {result.get('conclusion')} (可能缺少排他约束)")
print()

# Test 6: Check presentation_date > shipment_date + 21 days (UCP600 14c)
print("=== TEST 6: 交单日期超过装船日后21天 (UCP600 14c) ===")
docs_late_pres = json.loads(json.dumps(docs_ok))
# shipment 2024-04-20, presentation should be <= 2024-05-11 (20+21=May11)
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-LATE-PRES", "2024-05-12", docs_late_pres)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    has_21day = False
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
        if "21" in d.get("description", ""):
            has_21day = True
    if not has_21day:
        print("  ⚠️ 没有检出21天规则不符点!")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)[:200]}")
print()

# Test 7: Check persistence - query stats
print("=== TEST 7: 不符类型统计 ===")
r = requests.get(f"{BASE}/api/stats/discrepancies")
print(f"  状态码: {r.status_code}")
if r.status_code == 200:
    for s in r.json():
        print(f"  {s['discrepancy_type']}: {s['count']}")
print()

# Test 8: Beneficiary discrepancy rate
print("=== TEST 8: 受益人不符率查询 ===")
import urllib.parse
bene = lc2["beneficiary_name"]
r = requests.get(f"{BASE}/api/stats/beneficiary/{urllib.parse.quote(bene)}")
print(f"  状态码: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  受益人: {d['beneficiary_name']}")
    print(f"  总审核: {d['total_audits']}, 不符点总数: {d['total_discrepancies']}, 不符率: {d['discrepancy_rate']}")
print()

# Test 9: Check LC1 transshipment constraint
print("=== TEST 9: 对禁止转运的LC1提交含转运标记的提单 ===")
r = requests.get(f"{BASE}/api/lc/LC-SEA-CIF-2024-001")
lc1 = r.json()
print(f"  LC1 禁止转运: {not lc1['transshipment_allowed']}")
print(f"  LC1 禁止分批: {not lc1['partial_shipment_allowed']}")
docs_trans = [
    {"document_type": "invoice", "original_copies_submitted": 3, "copy_copies_submitted": 2,
     "data": {"beneficiary_name": lc1["beneficiary_name"], "applicant_name": lc1["applicant_name"],
              "goods_description": lc1["goods_description"], "quantity": "5000pcs", "unit_price": "USD 10.00/pc",
              "total_amount": 50000.00, "currency": "USD", "invoice_date": "2024-03-05"}},
    {"document_type": "bill_of_lading", "original_copies_submitted": 3, "copy_copies_submitted": 3,
     "data": {"shipper": lc1["beneficiary_name"], "consignee": "TO ORDER",
              "notify_party": lc1["applicant_name"],
              "vessel_name": "EVER GIVEN", "voyage_number": "V.2024E",
              "port_of_loading": "上海港 SHANGHAI PORT",
              "port_of_discharge": "鹿特丹港 ROTTERDAM PORT",
              "shipment_date": "2024-03-08", "bl_number": "HDMU1234567",
              "pieces": 100, "freight_terms": "FREIGHT PREPAID",
              "transshipment": True}},
    {"document_type": "packing_list", "original_copies_submitted": 3, "copy_copies_submitted": 2,
     "data": {"beneficiary_name": lc1["beneficiary_name"], "total_packages": 100,
              "total_gross_weight": "2000 KGS", "total_net_weight": "1800 KGS"}},
    {"document_type": "insurance", "original_copies_submitted": 2, "copy_copies_submitted": 1,
     "data": {"insured_name": lc1["beneficiary_name"], "insurance_amount": 55000.00,
              "currency": "USD", "coverage": "ALL RISKS", "insurance_date": "2024-03-07"}}
]
status, result = test_submit("LC-SEA-CIF-2024-001", "TEST-TRANSSHIP", "2024-03-10", docs_trans)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    has_trans = False
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
        if "转运" in d.get("description", "") or "transship" in d.get("description", "").lower():
            has_trans = True
    if not has_trans:
        print("  ⚠️ 没有检出转运不符点!")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)[:200]}")
print()

# Test 10: Goods description mismatch
print("=== TEST 10: 货物描述与信用证不一致 ===")
docs_goods = json.loads(json.dumps(docs_ok))
docs_goods[0]["data"]["goods_description"] = "Electronic Parts - Something Different"
status, result = test_submit("LC-AIR-CFR-2024-002", "TEST-GOODS-MISMATCH", "2024-04-20", docs_goods)
print(f"  状态码: {status}")
if status == 200:
    print(f"  结论: {result.get('conclusion')}")
    has_goods = False
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
        if d['discrepancy_type'] == 'goods':
            has_goods = True
    if not has_goods:
        print("  ⚠️ 没有检出货物描述不符点!")
else:
    print(f"  错误: {json.dumps(result, ensure_ascii=False)[:200]}")
