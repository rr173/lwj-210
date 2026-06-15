import urllib.request
import urllib.parse
import json

BASE = "http://localhost:8000"

def get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())

print("=" * 60)
print("1. 不符点类型统计")
print("=" * 60)
data = get(f"{BASE}/api/stats/discrepancies")
for d in data:
    print(f"  - {d['discrepancy_type']}: {d['count']} 次")

print("\n" + "=" * 60)
print("2. 受益人历史不符率")
print("=" * 60)
beneficiary = "上海国际贸易有限公司 SHANGHAI INTERNATIONAL TRADING CO., LTD."
encoded = urllib.parse.quote(beneficiary)
d = get(f"{BASE}/api/stats/beneficiary/{encoded}")
print(f"  受益人: {d['beneficiary_name']}")
print(f"  总审核次数: {d['total_audits']}")
print(f"  总不符点数: {d['total_discrepancies']}")
print(f"  平均不符率: {d['discrepancy_rate']} 个/次")

print("\n" + "=" * 60)
print("3. 信用证详情 LC-SEA-CIF-2024-001")
print("=" * 60)
d = get(f"{BASE}/api/lc/LC-SEA-CIF-2024-001")
print(f"  信用证号: {d['lc_number']}")
print(f"  开证行: {d['issuing_bank']}")
print(f"  受益人: {d['beneficiary_name']}")
print(f"  申请人: {d['applicant_name']}")
print(f"  金额: {d['currency']} {d['amount']}")
print(f"  最迟装运: {d['latest_shipment_date']}, 最迟交单: {d['latest_presentation_date']}, 到期日: {d['expiry_date']}")
print(f"  运输方式: {d['transport_mode']}")
print(f"  装运港 → 目的港: {d['port_of_loading']} → {d['port_of_discharge']}")
partial = '允许' if d['partial_shipment_allowed'] else '禁止'
trans = '允许' if d['transshipment_allowed'] else '禁止'
print(f"  分批装运: {partial}, 转运: {trans}")
print(f"  货物描述: {d['goods_description']}")
print("  单据要求:")
for req in d['document_requirements']:
    print(f"    - {req['document_type']}: {req['original_copies']}正{req['copy_copies']}副")
print("  附加条款:")
for i, term in enumerate(d['additional_terms'], 1):
    print(f"    {i}. {term}")

print("\n" + "=" * 60)
print("4. 信用证详情 LC-AIR-CFR-2024-002（空运CFR允许分批）")
print("=" * 60)
d = get(f"{BASE}/api/lc/LC-AIR-CFR-2024-002")
print(f"  信用证号: {d['lc_number']}")
print(f"  开证行: {d['issuing_bank']}")
print(f"  金额: {d['currency']} {d['amount']}")
print(f"  运输方式: {d['transport_mode']}")
print(f"  装运港 → 目的港: {d['port_of_loading']} → {d['port_of_discharge']}")
partial = '允许' if d['partial_shipment_allowed'] else '禁止'
trans = '允许' if d['transshipment_allowed'] else '禁止'
print(f"  分批装运: {partial}, 转运: {trans}")
print("  单据要求:")
for req in d['document_requirements']:
    print(f"    - {req['document_type']}: {req['original_copies']}正{req['copy_copies']}副")
print("  附加条款:")
for i, term in enumerate(d['additional_terms'], 1):
    print(f"    {i}. {term}")

print("\n" + "=" * 60)
print("5. 全部审核记录列表")
print("=" * 60)
data = get(f"{BASE}/api/audit/all")
for d in data:
    status_icon = {'compliant': '✅', 'minor_discrepancy': '⚠️', 'discrepant': '❌'}.get(d['conclusion'], '?')
    print(f"  {status_icon} LC-{d['lc_id']} | {d['submission_id']} | {d['conclusion']} | 不符点: {d['total_discrepancies']} (C={d['critical_count']}, M={d['minor_count']})")

print("\n✅ 所有API测试通过!")
