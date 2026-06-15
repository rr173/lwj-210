from datetime import date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from app.models import LetterOfCredit, Document, AuditRecord, Discrepancy


EPSILON = 0.01


class AuditResult:
    def __init__(self):
        self.discrepancies: List[Dict[str, Any]] = []

    def add(self, discrepancy_type: str, severity: str, document_type: Optional[str],
            description: str, lc_clause_reference: Optional[str] = None):
        self.discrepancies.append({
            "discrepancy_type": discrepancy_type,
            "severity": severity,
            "document_type": document_type,
            "description": description,
            "lc_clause_reference": lc_clause_reference
        })


class AuditEngine:
    def __init__(self, lc: LetterOfCredit, documents: List[Document], presentation_date: date):
        self.lc = lc
        self.documents = documents
        self.presentation_date = presentation_date
        self.result = AuditResult()
        self.doc_map = {d.document_type: d for d in documents}

    def _get_doc_content(self, doc_type: str) -> Optional[Dict[str, Any]]:
        doc = self.doc_map.get(doc_type)
        return doc.content if doc else None

    def _names_similar(self, name1: str, name2: str) -> Tuple[bool, bool]:
        if not name1 or not name2:
            return False, False
        n1 = name1.strip()
        n2 = name2.strip()
        if n1 == n2:
            return True, False
        if n1.lower() == n2.lower():
            return True, True
        if n1.replace(" ", "").lower() == n2.replace(" ", "").lower():
            return True, True
        return False, False

    def _amount_less_than(self, a: float, b: float) -> bool:
        return (b - a) > EPSILON

    def check_completeness(self):
        for req in self.lc.document_requirements:
            doc_type = req.document_type
            submitted = self.doc_map.get(doc_type)

            if not submitted:
                self.result.add(
                    "completeness", "critical", doc_type,
                    f"缺少信用证要求的单据: {doc_type}, 需要{req.original_copies}正{req.copy_copies}副",
                    "单据要求清单"
                )
                continue

            if submitted.original_copies_submitted < req.original_copies:
                severity = "critical" if req.original_copies > 0 and submitted.original_copies_submitted == 0 else "minor"
                self.result.add(
                    "completeness", severity, doc_type,
                    f"{doc_type}正本份数不足: 提交{submitted.original_copies_submitted}份, 要求{req.original_copies}份",
                    "单据要求清单"
                )

            if submitted.copy_copies_submitted < req.copy_copies:
                self.result.add(
                    "completeness", "minor", doc_type,
                    f"{doc_type}副本份数不足: 提交{submitted.copy_copies_submitted}份, 要求{req.copy_copies}份",
                    "单据要求清单"
                )

    def check_amount(self):
        invoice = self._get_doc_content("invoice")
        if invoice:
            invoice_amount = invoice.get("total_amount", 0)
            if self._amount_less_than(self.lc.amount, invoice_amount):
                self.result.add(
                    "amount", "critical", "invoice",
                    f"发票总金额{invoice_amount}{self.lc.currency}超过信用证金额{self.lc.amount}{self.lc.currency}",
                    "信用证金额条款"
                )

        insurance = self._get_doc_content("insurance")
        if insurance and invoice:
            insurance_amount = insurance.get("insurance_amount", 0)
            invoice_amount = invoice.get("total_amount", 0)
            min_insurance = round(invoice_amount * 1.1, 2)

            has_110_clause = any("110%" in term or "1.1" in term for term in self.lc.additional_terms)

            if self._amount_less_than(insurance_amount, min_insurance):
                severity = "critical" if has_110_clause else "minor"
                self.result.add(
                    "amount", severity, "insurance",
                    f"保险金额{insurance_amount}低于发票金额110%({min_insurance})",
                    "附加条款-保险金额" if has_110_clause else "UCP600默认规则"
                )

            if insurance.get("currency") and invoice.get("currency"):
                if insurance["currency"] != invoice["currency"]:
                    self.result.add(
                        "amount", "minor", "insurance",
                        f"保险币种{insurance['currency']}与发票币种{invoice['currency']}不一致",
                        "信用证币种条款"
                    )

    def check_date(self):
        invoice = self._get_doc_content("invoice")
        bl = self._get_doc_content("bill_of_lading")
        insurance = self._get_doc_content("insurance")

        if invoice:
            inv_date_str = invoice.get("invoice_date")
            if inv_date_str:
                inv_date = date.fromisoformat(inv_date_str) if isinstance(inv_date_str, str) else inv_date_str
                if inv_date > self.presentation_date:
                    self.result.add(
                        "date", "critical", "invoice",
                        f"发票日期{inv_date}晚于交单日期{self.presentation_date}",
                        "UCP600第14条"
                    )

        shipment_date = None
        if bl:
            ship_date_str = bl.get("shipment_date")
            if ship_date_str:
                shipment_date = date.fromisoformat(ship_date_str) if isinstance(ship_date_str, str) else ship_date_str
                if shipment_date > self.lc.latest_shipment_date:
                    self.result.add(
                        "date", "critical", "bill_of_lading",
                        f"提单装船日期{shipment_date}晚于信用证最迟装运日期{self.lc.latest_shipment_date}",
                        "最迟装运日期条款"
                    )

        if self.presentation_date > self.lc.latest_presentation_date:
            self.result.add(
                "date", "critical", None,
                f"交单日期{self.presentation_date}晚于信用证最迟交单日期{self.lc.latest_presentation_date}",
                "最迟交单日期条款"
            )

        if shipment_date:
            if self.presentation_date > shipment_date + timedelta(days=21):
                self.result.add(
                    "date", "critical", None,
                    f"交单日期{self.presentation_date}晚于装船日期后21天({shipment_date + timedelta(days=21)})",
                    "UCP600第14条c款"
                )

            if insurance:
                ins_date_str = insurance.get("issue_date")
                if ins_date_str:
                    ins_date = date.fromisoformat(ins_date_str) if isinstance(ins_date_str, str) else ins_date_str
                    if ins_date > shipment_date:
                        self.result.add(
                            "date", "critical", "insurance",
                            f"保险投保日期{ins_date}晚于装船日期{shipment_date}",
                            "UCP600第28条e款"
                        )

        if self.presentation_date > self.lc.expiry_date:
            self.result.add(
                "date", "critical", None,
                f"交单日期{self.presentation_date}晚于信用证到期日{self.lc.expiry_date}",
                "信用证到期日条款"
            )

    def check_party(self):
        invoice = self._get_doc_content("invoice")
        bl = self._get_doc_content("bill_of_lading")

        if invoice:
            inv_beneficiary = invoice.get("beneficiary", "")
            match, has_diff = self._names_similar(inv_beneficiary, self.lc.beneficiary_name)
            if not match:
                self.result.add(
                    "party", "critical", "invoice",
                    f"发票受益人'{inv_beneficiary}'与信用证受益人'{self.lc.beneficiary_name}'不一致",
                    "信用证受益人条款"
                )
            elif has_diff:
                self.result.add(
                    "party", "minor", "invoice",
                    f"发票受益人名称存在拼写/大小写/空格差异: '{inv_beneficiary}' vs '{self.lc.beneficiary_name}'",
                    "信用证受益人条款"
                )

            inv_applicant = invoice.get("applicant", "")
            match, has_diff = self._names_similar(inv_applicant, self.lc.applicant_name)
            if not match:
                self.result.add(
                    "party", "minor", "invoice",
                    f"发票申请人'{inv_applicant}'与信用证申请人'{self.lc.applicant_name}'不一致",
                    "信用证申请人条款"
                )
            elif has_diff:
                self.result.add(
                    "party", "minor", "invoice",
                    f"发票申请人名称存在拼写/大小写/空格差异: '{inv_applicant}' vs '{self.lc.applicant_name}'",
                    "信用证申请人条款"
                )

        if bl:
            bl_shipper = bl.get("shipper", "")
            match, has_diff = self._names_similar(bl_shipper, self.lc.beneficiary_name)
            shipper_otherwise = any("托运人" in term and "受益人" not in term for term in self.lc.additional_terms)
            if not shipper_otherwise and not match:
                self.result.add(
                    "party", "minor", "bill_of_lading",
                    f"提单托运人'{bl_shipper}'与信用证受益人'{self.lc.beneficiary_name}'不一致",
                    "UCP600默认规则"
                )
            elif not shipper_otherwise and has_diff:
                self.result.add(
                    "party", "minor", "bill_of_lading",
                    f"提单托运人名称存在拼写/大小写/空格差异: '{bl_shipper}' vs '{self.lc.beneficiary_name}'",
                    "UCP600默认规则"
                )

    def check_goods(self):
        invoice = self._get_doc_content("invoice")
        lc_goods = self.lc.goods_description.strip()

        if invoice:
            inv_goods_norm = invoice.get("goods_description", "").strip()
            lc_goods_norm = lc_goods.strip()

            if inv_goods_norm and inv_goods_norm != lc_goods_norm:
                match_space = inv_goods_norm.replace(" ", "").replace(",", "").lower() == lc_goods_norm.replace(" ", "").replace(",", "").lower()
                if not match_space:
                    self.result.add(
                        "goods", "critical", "invoice",
                        f"发票货物描述与信用证不匹配: 发票'{inv_goods_norm}' vs 信用证'{lc_goods_norm}'",
                        "信用证货物描述条款"
                    )
                else:
                    self.result.add(
                        "goods", "minor", "invoice",
                        f"发票货物描述存在空格/标点/大小写差异",
                        "信用证货物描述条款"
                    )

            goods_list = invoice.get("goods", [])
            doc_types_to_check = ["bill_of_lading", "packing_list", "insurance", "origin_cert", "inspection_cert"]

            main_product_name = ""
            if goods_list and isinstance(goods_list, list) and len(goods_list) > 0:
                main_product_name = goods_list[0].get("name", "").lower()

            if not main_product_name:
                main_product_words = lc_goods_norm.lower().split()
                if "cif" in main_product_words:
                    main_product_words = main_product_words[:main_product_words.index("cif")]
                elif "cfr" in main_product_words:
                    main_product_words = main_product_words[:main_product_words.index("cfr")]
                elif "fob" in main_product_words:
                    main_product_words = main_product_words[:main_product_words.index("fob")]
                main_product_name = " ".join([w for w in main_product_words if w])

            for doc_type in doc_types_to_check:
                doc_content = self._get_doc_content(doc_type)
                if doc_content:
                    doc_goods = doc_content.get("goods_description", "").strip()
                    if doc_goods and main_product_name:
                        doc_lower = doc_goods.lower()
                        main_words = main_product_name.split()
                        contradiction_count = 0
                        total_check = 0
                        for kw in main_words:
                            if len(kw) > 3:
                                total_check += 1
                                if kw not in doc_lower:
                                    contradiction_count += 1
                        if total_check > 0 and contradiction_count == total_check:
                            self.result.add(
                                "goods", "minor", doc_type,
                                f"{doc_type}货物描述'{doc_goods}'与发票存在潜在矛盾",
                                "UCP600第14条e款"
                            )

    def check_transport(self):
        bl = self._get_doc_content("bill_of_lading")
        if not bl:
            return

        bl_port_load = bl.get("port_of_loading", "").strip()
        lc_port_load = self.lc.port_of_loading.strip()
        if bl_port_load.lower() != lc_port_load.lower():
            self.result.add(
                "transport", "critical", "bill_of_lading",
                f"提单装港'{bl_port_load}'与信用证装港'{lc_port_load}'不一致",
                "信用证装运港条款"
            )

        bl_port_disch = bl.get("port_of_discharge", "").strip()
        lc_port_disch = self.lc.port_of_discharge.strip()
        if bl_port_disch.lower() != lc_port_disch.lower():
            self.result.add(
                "transport", "critical", "bill_of_lading",
                f"提单卸港'{bl_port_disch}'与信用证卸港'{lc_port_disch}'不一致",
                "信用证目的港条款"
            )

        if not self.lc.transshipment_allowed:
            bl_transshipment = bl.get("transshipment", False)
            remarks = bl.get("remarks", "")
            has_trans_marker = bl_transshipment == True or "转运" in remarks or "TRANSSHIP" in remarks.upper()
            if has_trans_marker:
                self.result.add(
                    "transport", "critical", "bill_of_lading",
                    "提单显示转运标记，但信用证禁止转运",
                    "信用证转运条款"
                )

        if not self.lc.partial_shipment_allowed:
            bl_packages = bl.get("packages", 0) or bl.get("quantity", 0)
            invoice = self._get_doc_content("invoice")
            if invoice:
                inv_qty = 0
                goods_list = invoice.get("goods", [])
                if goods_list and isinstance(goods_list, list):
                    for item in goods_list:
                        inv_qty += item.get("quantity", 0)
                if inv_qty > 0 and bl_packages > 0:
                    if bl_packages < inv_qty * 0.90:
                        self.result.add(
                            "transport", "critical", "bill_of_lading",
                            f"提单件数{bl_packages}明显少于发票数量{inv_qty},疑似分批装运但信用证禁止分批",
                            "信用证分批装运条款"
                        )

    def check_special_terms(self):
        has_insurance_110_checked = False

        for idx, term in enumerate(self.lc.additional_terms):
            term_lower = term.lower()

            if "指示抬头" in term or "to order" in term_lower:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    consignee = bl.get("consignee", "")
                    if "to order" not in consignee.lower() and "指示" not in consignee:
                        self.result.add(
                            "special", "critical", "bill_of_lading",
                            f"提单收货人'{consignee}'未做成指示抬头(TO ORDER)",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if "空白背书" in term or "blank endorsed" in term_lower:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    endorsement = bl.get("endorsement", "")
                    if "blank" not in endorsement.lower() and "空白" not in endorsement:
                        self.result.add(
                            "special", "minor", "bill_of_lading",
                            "提单未按要求做成空白背书",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if "运费预付" in term or "freight prepaid" in term_lower:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    freight = bl.get("freight_term", "")
                    if "prepaid" not in freight.lower() and "预付" not in freight:
                        self.result.add(
                            "special", "critical", "bill_of_lading",
                            f"提单运费条款'{freight}'未显示运费预付",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if "运费到付" in term or "freight collect" in term_lower:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    freight = bl.get("freight_term", "")
                    if "collect" not in freight.lower() and "到付" not in freight:
                        self.result.add(
                            "special", "critical", "bill_of_lading",
                            f"提单运费条款'{freight}'未显示运费到付",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if "清洁提单" in term or "clean" in term_lower:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    clean = bl.get("clean", True)
                    remarks = bl.get("remarks", "")
                    if not clean or ("瑕疵" in remarks or "damaged" in remarks.lower()):
                        self.result.add(
                            "special", "critical", "bill_of_lading",
                            f"提单含有不清洁批注: {remarks}",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if ("110%" in term or "1.1" in term) and not has_insurance_110_checked:
                has_insurance_110_checked = True

            if "一切险" in term or "all risks" in term_lower:
                insurance = self._get_doc_content("insurance")
                if insurance:
                    risks = insurance.get("risks", "")
                    if "all risks" not in risks.lower() and "一切险" not in risks:
                        self.result.add(
                            "special", "minor", "insurance",
                            f"保险险别'{risks}'未包含一切险",
                            f"附加条款第{idx + 1}条: {term}"
                        )

            if "通知方" in term:
                bl = self._get_doc_content("bill_of_lading")
                if bl:
                    notify = bl.get("notify_party", "")
                    if not notify:
                        self.result.add(
                            "special", "minor", "bill_of_lading",
                            "提单未填写通知方信息",
                            f"附加条款第{idx + 1}条: {term}"
                        )

    def run_audit(self) -> Tuple[str, List[Dict[str, Any]]]:
        self.check_completeness()
        self.check_amount()
        self.check_date()
        self.check_party()
        self.check_goods()
        self.check_transport()
        self.check_special_terms()

        discrepancies = self.result.discrepancies
        total = len(discrepancies)
        critical_count = sum(1 for d in discrepancies if d["severity"] == "critical")
        minor_count = sum(1 for d in discrepancies if d["severity"] == "minor")

        if total == 0:
            conclusion = "compliant"
        elif critical_count == 0 and minor_count <= 2:
            conclusion = "minor_discrepancy"
        else:
            conclusion = "discrepant"

        return conclusion, discrepancies
