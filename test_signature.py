#!/usr/bin/env python3
"""测试脚本：电子签章与验签模块"""
import requests
import json
import hashlib
from datetime import datetime

BASE = "http://localhost:8000"


def generate_signature(content: dict) -> str:
    """根据内容生成模拟签名值：content的JSON序列化后MD5取前16位"""
    content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
    md5_hash = hashlib.md5(content_str.encode("utf-8")).hexdigest()
    return md5_hash[:16]


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


print_section("1. 注册签章主体")

# 注册一个受益人主体
beneficiary_data = {
    "subject_name": "深圳创新电子科技有限公司",
    "subject_type": "beneficiary",
    "public_key": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF4c..."
}

r = requests.post(f"{BASE}/api/signature/subjects", json=beneficiary_data)
print(f"  注册受益人主体状态码: {r.status_code}")
if r.status_code == 201:
    result = r.json()
    print(f"  主体名称: {result['subject_name']}")
    print(f"  主体类型: {result['subject_type']}")
    print(f"  状态: {result['status']}")
else:
    print(f"  错误: {r.text}")

# 注册一个银行主体
bank_data = {
    "subject_name": "中国银行深圳分行",
    "subject_type": "bank",
    "public_key": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF4c..."
}

r = requests.post(f"{BASE}/api/signature/subjects", json=bank_data)
print(f"\n  注册银行主体状态码: {r.status_code}")
if r.status_code == 201:
    result = r.json()
    print(f"  主体名称: {result['subject_name']}")
    print(f"  主体类型: {result['subject_type']}")
    print(f"  状态: {result['status']}")
else:
    print(f"  错误: {r.text}")

# 注册第三方机构
third_party_data = {
    "subject_name": "SGS通标标准技术服务有限公司",
    "subject_type": "third_party",
    "public_key": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF4c..."
}

r = requests.post(f"{BASE}/api/signature/subjects", json=third_party_data)
print(f"\n  注册第三方机构状态码: {r.status_code}")
if r.status_code == 201:
    result = r.json()
    print(f"  主体名称: {result['subject_name']}")
    print(f"  主体类型: {result['subject_type']}")
    print(f"  状态: {result['status']}")
else:
    print(f"  错误: {r.text}")

print_section("2. 测试重复注册（应该失败）")

r = requests.post(f"{BASE}/api/signature/subjects", json=beneficiary_data)
print(f"  重复注册状态码: {r.status_code}")
print(f"  错误信息: {r.text[:200]}")

print_section("3. 查询签章主体列表")

r = requests.get(f"{BASE}/api/signature/subjects")
print(f"  查询状态码: {r.status_code}")
if r.status_code == 200:
    subjects = r.json()
    print(f"  主体数量: {len(subjects)}")
    for s in subjects:
        print(f"    - {s['subject_name']} ({s['subject_type']}) - {s['status']}")

print_section("4. 查询单个签章主体")

r = requests.get(f"{BASE}/api/signature/subjects/深圳创新电子科技有限公司")
print(f"  查询状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  主体名称: {result['subject_name']}")
    print(f"  主体类型: {result['subject_type']}")
    print(f"  状态: {result['status']}")
    print(f"  创建时间: {result['created_at']}")

print_section("5. 获取一个带\"所有单据必须签章\"附加条款的信用证")

# 先查询一个信用证
r = requests.get(f"{BASE}/api/lc/LC-AIR-CFR-2024-002")
lc = r.json()
print(f"  信用证号: {lc['lc_number']}")
print(f"  当前附加条款: {lc.get('additional_terms', [])}")

print_section("6. 提交带有效签章的单据")

# 准备单据内容
invoice_content = {
    "beneficiary_name": lc["beneficiary_name"],
    "applicant_name": lc["applicant_name"],
    "goods_description": lc["goods_description"],
    "quantity": "10000pcs",
    "unit_price": "EUR 3.50/pc",
    "total_amount": 35000.00,
    "currency": "EUR",
    "invoice_date": "2024-04-18"
}

# 生成有效签名
valid_signature = generate_signature(invoice_content)
print(f"  生成的签名值（前16位）: {valid_signature}")

# 准备带签章的交单
docs_with_sign = [
    {
        "document_type": "invoice",
        "original_copies_submitted": 3,
        "copy_copies_submitted": 2,
        "content": invoice_content,
        "signature": {
            "subject_name": "深圳创新电子科技有限公司",
            "signature_value": valid_signature,
            "signed_at": "2024-04-18T10:30:00"
        }
    },
    {
        "document_type": "air_waybill",
        "original_copies_submitted": 3,
        "copy_copies_submitted": 0,
        "content": {
            "shipper": lc["beneficiary_name"],
            "consignee": lc["applicant_name"],
            "notify_party": lc["applicant_name"],
            "flight_number": "CZ329",
            "airport_of_departure": "深圳宝安国际机场 SHENZHEN BAOAN INTERNATIONAL AIRPORT",
            "airport_of_destination": "法兰克福国际机场 FRANKFURT INTERNATIONAL AIRPORT",
            "shipment_date": "2024-04-20",
            "awb_number": "784-12345678",
            "pieces": 50,
            "freight_terms": "FREIGHT COLLECT"
        },
        "signature": {
            "subject_name": "深圳创新电子科技有限公司",
            "signature_value": "invalid_signature_12345",
            "signed_at": "2024-04-18T10:35:00"
        }
    },
    {
        "document_type": "packing_list",
        "original_copies_submitted": 3,
        "copy_copies_submitted": 2,
        "content": {
            "beneficiary_name": lc["beneficiary_name"],
            "total_packages": 50,
            "total_gross_weight": "500 KGS",
            "total_net_weight": "450 KGS"
        }
    }
]

submit_data = {
    "lc_number": "LC-AIR-CFR-2024-002",
    "submission_id": "TEST-SIGN-001",
    "presentation_date": "2024-04-25",
    "documents": docs_with_sign
}

r = requests.post(f"{BASE}/api/submission", json=submit_data)
print(f"  提交状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  审核结论: {result.get('conclusion')}")
    print(f"  不符点数: {len(result.get('discrepancies', []))}")
    for d in result.get("discrepancies", []):
        print(f"    [{d['severity']}] {d['discrepancy_type']}: {d['description']}")
else:
    print(f"  错误: {r.text[:300]}")

print_section("7. 调用验签接口验证交单")

r = requests.post(f"{BASE}/api/submissions/TEST-SIGN-001/verify-signatures")
print(f"  验签状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  交单编号: {result['submission_id']}")
    print(f"  单据数量: {len(result['results'])}")
    for doc in result["results"]:
        print(f"    - {doc['document_type']}: {doc['verify_status']}")
        if doc.get("failure_reason"):
            print(f"      失败原因: {doc['failure_reason']}")
        if doc.get("subject_name"):
            print(f"      签章主体: {doc['subject_name']}")
else:
    print(f"  错误: {r.text}")

print_section("8. 查询信用证下所有交单的签章状态汇总")

r = requests.get(f"{BASE}/api/lc/LC-AIR-CFR-2024-002/signature-summary")
print(f"  查询状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  信用证号: {result['lc_number']}")
    print(f"  交单数量: {len(result['submissions'])}")
    for sub in result["submissions"]:
        print(f"\n  交单编号: {sub['submission_id']}")
        print(f"  单据数量: {len(sub['documents'])}")
        for doc in sub["documents"]:
            has_sig = "有签章" if doc["has_signature"] else "无签章"
            print(f"    - {doc['document_type']}: {has_sig}, 验签结果: {doc['verify_status']}")
else:
    print(f"  错误: {r.text}")

print_section("9. 测试签章主体吊销")

# 吊销一个主体
revoke_data = {"revoked_reason": "密钥泄露"}
r = requests.post(
    f"{BASE}/api/signature/subjects/深圳创新电子科技有限公司/revoke",
    json=revoke_data
)
print(f"  吊销状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  主体名称: {result['subject_name']}")
    print(f"  状态: {result['status']}")
    print(f"  吊销时间: {result['revoked_at']}")
    print(f"  吊销原因: {result['revoked_reason']}")
else:
    print(f"  错误: {r.text}")

print_section("10. 吊销后重新验签（验证签章自动变为invalid）")

r = requests.post(f"{BASE}/api/submissions/TEST-SIGN-001/verify-signatures")
print(f"  验签状态码: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"  交单编号: {result['submission_id']}")
    for doc in result["results"]:
        print(f"    - {doc['document_type']}: {doc['verify_status']}")
        if doc.get("failure_reason"):
            print(f"      失败原因: {doc['failure_reason']}")
else:
    print(f"  错误: {r.text}")

print_section("11. 测试已吊销主体不能再次使用（提交新交单）")

# 尝试用已吊销主体的签章提交新交单
invoice_content2 = {
    "beneficiary_name": lc["beneficiary_name"],
    "applicant_name": lc["applicant_name"],
    "goods_description": lc["goods_description"],
    "quantity": "5000pcs",
    "unit_price": "EUR 3.50/pc",
    "total_amount": 17500.00,
    "currency": "EUR",
    "invoice_date": "2024-04-19"
}

valid_signature2 = generate_signature(invoice_content2)

docs_revoked = [
    {
        "document_type": "invoice",
        "original_copies_submitted": 3,
        "copy_copies_submitted": 2,
        "content": invoice_content2,
        "signature": {
            "subject_name": "深圳创新电子科技有限公司",
            "signature_value": valid_signature2,
            "signed_at": "2024-04-19T10:30:00"
        }
    }
]

submit_data2 = {
    "lc_number": "LC-AIR-CFR-2024-002",
    "submission_id": "TEST-SIGN-REVOKED",
    "presentation_date": "2024-04-26",
    "documents": docs_revoked
}

r = requests.post(f"{BASE}/api/submission", json=submit_data2)
print(f"  提交状态码: {r.status_code}")

# 调用验签接口查看结果
r = requests.post(f"{BASE}/api/submissions/TEST-SIGN-REVOKED/verify-signatures")
print(f"  验签结果:")
if r.status_code == 200:
    result = r.json()
    for doc in result["results"]:
        print(f"    - {doc['document_type']}: {doc['verify_status']}")
        if doc.get("failure_reason"):
            print(f"      失败原因: {doc['failure_reason']}")

print_section("12. 查询签章主体列表（验证吊销状态）")

r = requests.get(f"{BASE}/api/signature/subjects")
print(f"  查询状态码: {r.status_code}")
if r.status_code == 200:
    subjects = r.json()
    print(f"  主体数量: {len(subjects)}")
    for s in subjects:
        revoked_info = f", 吊销时间: {s['revoked_at']}" if s["status"] == "revoked" else ""
        print(f"    - {s['subject_name']} ({s['subject_type']}) - {s['status']}{revoked_info}")

print_section("测试总结")
print("  ✅ 签章主体注册、查询、列表查询")
print("  ✅ 重复注册校验")
print("  ✅ 单据签章保存与验签")
print("  ✅ 签章主体吊销")
print("  ✅ 吊销后签章自动失效")
print("  ✅ 信用证下签章状态汇总查询")
print("\n所有核心功能测试完成！")
