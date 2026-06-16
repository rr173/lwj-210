import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime

from app.models import (
    LetterOfCredit,
    LCAmendment,
    SWIFT_MSG_TYPE_MT700,
    SWIFT_MSG_TYPE_MT707,
    SWIFT_MSG_TYPE_MT799,
)


MT700_TAG_MAP = {
    "40A": "信用证类型",
    "20": "信用证编号",
    "31D": "到期日期地点",
    "50": "申请人",
    "59": "受益人",
    "32B": "金额币种",
    "43P": "分批装运",
    "43T": "转运",
    "44A": "装运港",
    "44B": "卸货港",
    "44C": "最迟装运日期",
    "45A": "货物描述",
    "47A": "附加条款",
}

MT700_REQUIRED_TAGS = ["40A", "20", "31D", "50", "59", "32B"]

MT700_TAG_ORDER = [
    "40A", "20", "31D", "50", "59", "32B",
    "43P", "43T", "44A", "44B", "44C",
    "45A", "47A",
]

MT707_TAG_MAP = {
    "20": "信用证编号",
    "21": "关联编号",
    "30": "修改日期",
    "26E": "修改序号",
    "59": "受益人(修改前)",
    "34B": "修改前金额币种",
    "33B": "修改后金额币种",
    "31D": "新到期日期地点",
    "44C": "新最迟装运日期",
    "44A": "新装运港",
    "44B": "新卸货港",
    "43P": "新分批装运",
    "43T": "新转运",
    "45A": "新货物描述",
    "47A": "新附加条款",
    "72": "发送方附言",
}

MT707_REQUIRED_TAGS = ["20", "30", "26E"]

MT707_TAG_ORDER = [
    "20", "21", "30", "26E", "59", "34B",
    "33B", "31D", "44C", "44A", "44B",
    "43P", "43T", "45A", "47A", "72",
]

MT799_TAG_MAP = {
    "20": "交易参考号",
    "21": "关联参考号",
    "79": "叙述内容",
}

MT799_REQUIRED_TAGS = ["20", "79"]

MT799_TAG_ORDER = ["20", "21", "79"]

ALL_TAG_MAPS = {
    SWIFT_MSG_TYPE_MT700: (MT700_TAG_MAP, MT700_REQUIRED_TAGS, MT700_TAG_ORDER),
    SWIFT_MSG_TYPE_MT707: (MT707_TAG_MAP, MT707_REQUIRED_TAGS, MT707_TAG_ORDER),
    SWIFT_MSG_TYPE_MT799: (MT799_TAG_MAP, MT799_REQUIRED_TAGS, MT799_TAG_ORDER),
}


def _format_date(d: Any) -> str:
    if isinstance(d, date):
        return d.strftime("%y%m%d")
    return str(d)


def _format_amount(currency: str, amount: float) -> str:
    if amount == int(amount):
        return f"{currency}{int(amount)},"
    return f"{currency}{amount:.2f}"


def _format_bool(val: Any) -> str:
    if val is True:
        return "ALLOWED"
    elif val is False:
        return "NOT ALLOWED"
    return str(val)


def generate_mt700(lc: LetterOfCredit) -> str:
    lines = []
    lines.append(f":40A:IRREVOCABLE")
    lines.append(f":20:{lc.lc_number}")
    expiry_place = lc.port_of_discharge if lc.port_of_discharge else ""
    lines.append(f":31D:{_format_date(lc.expiry_date)} {expiry_place}")
    lines.append(f":50:{lc.applicant_name}")
    lines.append(f":59:{lc.beneficiary_name}")
    lines.append(f":32B:{_format_amount(lc.currency, lc.amount)}")
    lines.append(f":43P:{_format_bool(lc.partial_shipment_allowed)}")
    lines.append(f":43T:{_format_bool(lc.transshipment_allowed)}")
    lines.append(f":44A:{lc.port_of_loading}")
    lines.append(f":44B:{lc.port_of_discharge}")
    lines.append(f":44C:{_format_date(lc.latest_shipment_date)}")
    lines.append(f":45A:{lc.goods_description}")
    if lc.additional_terms:
        terms = "//".join(lc.additional_terms) if isinstance(lc.additional_terms, list) else str(lc.additional_terms)
        lines.append(f":47A:{terms}")
    return "\n".join(lines)


def generate_mt707(amendment: LCAmendment, lc: LetterOfCredit) -> str:
    lines = []
    lines.append(f":20:{lc.lc_number}")
    lines.append(f":21:{amendment.amendment_number}")
    lines.append(f":30:{_format_date(amendment.created_at if amendment.created_at else datetime.utcnow())}")
    lines.append(f":26E:{amendment.sequence_number}")
    lines.append(f":59:{lc.beneficiary_name}")
    lines.append(f":34B:{_format_amount(lc.currency, lc.amount)}")

    changes_map = {}
    if amendment.field_changes:
        for change in amendment.field_changes:
            if isinstance(change, dict):
                changes_map[change.get("field_name")] = change.get("new_value")

    if "amount" in changes_map:
        lines.append(f":33B:{_format_amount(lc.currency, float(changes_map['amount']))}")
    else:
        lines.append(f":33B:{_format_amount(lc.currency, lc.amount)}")

    if "expiry_date" in changes_map:
        new_val = changes_map["expiry_date"]
        if isinstance(new_val, str):
            try:
                new_val = date.fromisoformat(new_val)
            except ValueError:
                pass
        lines.append(f":31D:{_format_date(new_val)} {lc.port_of_discharge or ''}")

    if "latest_shipment_date" in changes_map:
        new_val = changes_map["latest_shipment_date"]
        if isinstance(new_val, str):
            try:
                new_val = date.fromisoformat(new_val)
            except ValueError:
                pass
        lines.append(f":44C:{_format_date(new_val)}")

    if "port_of_loading" in changes_map:
        lines.append(f":44A:{changes_map['port_of_loading']}")

    if "port_of_discharge" in changes_map:
        lines.append(f":44B:{changes_map['port_of_discharge']}")

    if "partial_shipment_allowed" in changes_map:
        lines.append(f":43P:{_format_bool(changes_map['partial_shipment_allowed'])}")

    if "transshipment_allowed" in changes_map:
        lines.append(f":43T:{_format_bool(changes_map['transshipment_allowed'])}")

    if "goods_description" in changes_map:
        lines.append(f":45A:{changes_map['goods_description']}")

    if "additional_terms" in changes_map:
        new_val = changes_map["additional_terms"]
        if isinstance(new_val, list):
            terms = "//".join(str(t) for t in new_val)
        else:
            terms = str(new_val)
        lines.append(f":47A:{terms}")

    lines.append(f":72:AMENDMENT {amendment.amendment_number}")
    return "\n".join(lines)


def generate_mt799(lc_number: str, narrative: str) -> str:
    lines = []
    lines.append(f":20:{lc_number}")
    lines.append(f":21:{lc_number}")
    lines.append(f":79:{narrative}")
    return "\n".join(lines)


def parse_swift_message(raw_message: str) -> Tuple[str, Dict[str, str], List[Dict[str, str]]]:
    tag_pattern = re.compile(r"^:([0-9A-Za-z]+):(.*)$")
    parsed_tags: Dict[str, str] = {}
    tag_order_list: List[Dict[str, str]] = []
    current_tag = None
    current_value_lines: List[str] = []

    for line in raw_message.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        match = tag_pattern.match(line)
        if match:
            if current_tag is not None:
                parsed_tags[current_tag] = "\n".join(current_value_lines)
                tag_order_list.append({"tag": current_tag, "value": parsed_tags[current_tag]})
            current_tag = match.group(1)
            current_value_lines = [match.group(2)]
        else:
            if current_tag is not None:
                current_value_lines.append(line)
            else:
                raise ValueError(f"报文格式错误：首行不是有效的标签行 '{line}'")

    if current_tag is not None:
        parsed_tags[current_tag] = "\n".join(current_value_lines)
        tag_order_list.append({"tag": current_tag, "value": parsed_tags[current_tag]})

    if not parsed_tags:
        raise ValueError("报文中未找到任何有效标签")

    message_type = _detect_message_type(parsed_tags)
    return message_type, parsed_tags, tag_order_list


def _detect_message_type(tags: Dict[str, str]) -> str:
    if "26E" in tags:
        return SWIFT_MSG_TYPE_MT707
    if "40A" in tags:
        return SWIFT_MSG_TYPE_MT700
    if "79" in tags:
        return SWIFT_MSG_TYPE_MT799
    raise ValueError("无法识别报文类型：缺少关键标签 (40A/26E/79)")


def validate_swift_message(message_type: str, tags: Dict[str, str]) -> List[str]:
    errors = []
    config = ALL_TAG_MAPS.get(message_type)
    if not config:
        errors.append(f"不支持的报文类型: {message_type}")
        return errors

    tag_map, required_tags, _ = config

    for tag in required_tags:
        if tag not in tags:
            field_name = tag_map.get(tag, tag)
            errors.append(f"缺少必填标签 :{tag}: ({field_name})")

    tag_pattern = re.compile(r"^[0-9A-Za-z]+$")
    for tag in tags:
        if not tag_pattern.match(tag):
            errors.append(f"标签格式不合法: :{tag}:")

    amount_tags = ["32B", "34B", "33B"]
    for tag in amount_tags:
        if tag in tags:
            value = tags[tag]
            amount_part = re.sub(r"^[A-Z]{3}", "", value).replace(",", "").strip()
            if amount_part:
                try:
                    float(amount_part)
                except ValueError:
                    field_name = tag_map.get(tag, tag)
                    errors.append(f"标签 :{tag}: ({field_name}) 金额字段非数字: {value}")

    return errors


def map_tags_to_fields(message_type: str, tags: Dict[str, str]) -> List[Dict[str, str]]:
    config = ALL_TAG_MAPS.get(message_type)
    if not config:
        return [{"tag": k, "field_name": k, "value": v} for k, v in tags.items()]

    tag_map, _, tag_order = config
    result = []
    seen = set()
    for tag in tag_order:
        if tag in tags:
            result.append({
                "tag": tag,
                "field_name": tag_map.get(tag, tag),
                "value": tags[tag],
            })
            seen.add(tag)
    for tag, value in tags.items():
        if tag not in seen:
            result.append({
                "tag": tag,
                "field_name": tag_map.get(tag, tag),
                "value": value,
            })
    return result


def extract_lc_number_from_tags(message_type: str, tags: Dict[str, str]) -> Optional[str]:
    if message_type == SWIFT_MSG_TYPE_MT700:
        return tags.get("20")
    elif message_type == SWIFT_MSG_TYPE_MT707:
        return tags.get("20")
    elif message_type == SWIFT_MSG_TYPE_MT799:
        return tags.get("20")
    return None


def extract_lc_data_from_mt700(tags: Dict[str, str]) -> Dict[str, Any]:
    data = {}
    if "20" in tags:
        data["lc_number"] = tags["20"]
    if "50" in tags:
        data["applicant_name"] = tags["50"]
    if "59" in tags:
        data["beneficiary_name"] = tags["59"]
    if "32B" in tags:
        amount_str = tags["32B"]
        currency_match = re.match(r"^([A-Z]{3})", amount_str)
        if currency_match:
            data["currency"] = currency_match.group(1)
        amount_part = re.sub(r"^[A-Z]{3}", "", amount_str).replace(",", "").strip()
        if amount_part:
            try:
                data["amount"] = float(amount_part)
            except ValueError:
                pass
    if "31D" in tags:
        date_str = tags["31D"].strip().split()[0] if tags["31D"].strip() else ""
        if len(date_str) == 6:
            try:
                data["expiry_date"] = _parse_swift_date(date_str)
            except ValueError:
                pass
    if "44C" in tags:
        try:
            data["latest_shipment_date"] = _parse_swift_date(tags["44C"].strip())
        except ValueError:
            pass
    if "44A" in tags:
        data["port_of_loading"] = tags["44A"]
    if "44B" in tags:
        data["port_of_discharge"] = tags["44B"]
    if "43P" in tags:
        data["partial_shipment_allowed"] = tags["43P"].strip().upper() == "ALLOWED"
    if "43T" in tags:
        data["transshipment_allowed"] = tags["43T"].strip().upper() == "ALLOWED"
    if "45A" in tags:
        data["goods_description"] = tags["45A"]
    if "47A" in tags:
        terms = tags["47A"]
        data["additional_terms"] = [t.strip() for t in terms.split("//") if t.strip()]
    if "40A" in tags:
        data["transport_mode"] = "海运"
    return data


def extract_amendment_data_from_mt707(tags: Dict[str, str]) -> Dict[str, Any]:
    data = {}
    if "20" in tags:
        data["lc_number"] = tags["20"]
    if "26E" in tags:
        data["sequence_number"] = tags["26E"]
    if "59" in tags:
        data["beneficiary_before"] = tags["59"]
    field_changes = []
    if "33B" in tags:
        field_changes.append({
            "field_name": "amount",
            "old_value": None,
            "new_value": _extract_amount_from_swift_field(tags["33B"]),
        })
    if "31D" in tags:
        date_part = tags["31D"].strip().split()[0] if tags["31D"].strip() else ""
        if len(date_part) == 6:
            try:
                field_changes.append({
                    "field_name": "expiry_date",
                    "old_value": None,
                    "new_value": _parse_swift_date(date_part).isoformat(),
                })
            except ValueError:
                pass
    if "44C" in tags:
        try:
            field_changes.append({
                "field_name": "latest_shipment_date",
                "old_value": None,
                "new_value": _parse_swift_date(tags["44C"].strip()).isoformat(),
            })
        except ValueError:
            pass
    if "44A" in tags:
        field_changes.append({
            "field_name": "port_of_loading",
            "old_value": None,
            "new_value": tags["44A"],
        })
    if "44B" in tags:
        field_changes.append({
            "field_name": "port_of_discharge",
            "old_value": None,
            "new_value": tags["44B"],
        })
    if "43P" in tags:
        field_changes.append({
            "field_name": "partial_shipment_allowed",
            "old_value": None,
            "new_value": tags["43P"].strip().upper() == "ALLOWED",
        })
    if "43T" in tags:
        field_changes.append({
            "field_name": "transshipment_allowed",
            "old_value": None,
            "new_value": tags["43T"].strip().upper() == "ALLOWED",
        })
    if "45A" in tags:
        field_changes.append({
            "field_name": "goods_description",
            "old_value": None,
            "new_value": tags["45A"],
        })
    if "47A" in tags:
        terms = tags["47A"]
        field_changes.append({
            "field_name": "additional_terms",
            "old_value": None,
            "new_value": [t.strip() for t in terms.split("//") if t.strip()],
        })
    data["field_changes"] = field_changes
    return data


def _parse_swift_date(date_str: str) -> date:
    if len(date_str) != 6:
        raise ValueError(f"SWIFT日期格式错误，应为6位YYMMDD: {date_str}")
    yy = int(date_str[:2])
    mm = int(date_str[2:4])
    dd = int(date_str[4:6])
    if yy >= 50:
        year = 1900 + yy
    else:
        year = 2000 + yy
    return date(year, mm, dd)


def _extract_amount_from_swift_field(value: str) -> Optional[float]:
    amount_part = re.sub(r"^[A-Z]{3}", "", value).replace(",", "").strip()
    if amount_part:
        try:
            return float(amount_part)
        except ValueError:
            return None
    return None
