import urllib.request
import urllib.parse
import json

BASE = "http://localhost:8000"

def get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

print("=" * 60)
print("测试1: 验证两份信用证各有1套交单记录")
print("=" * 60)

for lc_num in ["LC-SEA-CIF-2024-001", "LC-AIR-CFR-2024-002"]:
    records = get(f"{BASE}/api/audit/lc/{lc_num}")
    print(f"  {lc_num}: {len(records)} 条审核记录")
    for r in records:
        print(f"    - {r['submission_id']}: {r['conclusion']} (不符点: {r['total_discrepancies']})")

print("\n" + "=" * 60)
print("测试2: 对已有交单的信用证再次提交 → 应该被拒绝")
print("=" * 60)

submission_data = {
    "lc_number": "LC-SEA-CIF-2024-001",
    "submission_id": "SUB-DUPLICATE-TEST-001",
    "presentation_date": "2024-03-25",
    "documents": [
        {
            "lc_number": "LC-SEA-CIF-2024-001",
            "submission_id": "SUB-DUPLICATE-TEST-001",
            "document_type": "invoice",
            "original_copies_submitted": 3,
            "copy_copies_submitted": 2,
            "content": {
                "invoice_number": "INV-TEST-001",
                "invoice_date": "2024-03-20",
                "beneficiary": "测试公司",
                "applicant": "测试申请人",
                "currency": "USD",
                "total_amount": 10000.00
            }
        }
    ]
}

status_code, response = post(f"{BASE}/api/submission", submission_data)
print(f"  HTTP状态码: {status_code}")
print(f"  响应: {json.dumps(response, ensure_ascii=False, indent=4)}")

if status_code == 400 and "已有一次交单记录" in response.get("detail", ""):
    print("\n  ✅ 验证通过：重复提交被正确拒绝！")
else:
    print("\n  ❌ 验证失败：重复提交未被拦截！")

print("\n" + "=" * 60)
print("测试3: 对另一份已有交单的信用证再次提交 → 也应该被拒绝")
print("=" * 60)

submission_data2 = {
    "lc_number": "LC-AIR-CFR-2024-002",
    "submission_id": "SUB-DUPLICATE-TEST-002",
    "presentation_date": "2024-04-30",
    "documents": [
        {
            "lc_number": "LC-AIR-CFR-2024-002",
            "submission_id": "SUB-DUPLICATE-TEST-002",
            "document_type": "invoice",
            "original_copies_submitted": 1,
            "copy_copies_submitted": 1,
            "content": {
                "invoice_number": "INV-TEST-002",
                "invoice_date": "2024-04-28",
                "total_amount": 5000.00
            }
        }
    ]
}

status_code2, response2 = post(f"{BASE}/api/submission", submission_data2)
print(f"  HTTP状态码: {status_code2}")
print(f"  响应: {json.dumps(response2, ensure_ascii=False, indent=4)}")

if status_code2 == 400 and "已有一次交单记录" in response2.get("detail", ""):
    print("\n  ✅ 验证通过：重复提交被正确拒绝！")
else:
    print("\n  ❌ 验证失败：重复提交未被拦截！")

print("\n✅ 全部测试完成！")
