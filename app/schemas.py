from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from enum import Enum


class TransportMode(str, Enum):
    SEA = "海运"
    AIR = "空运"
    MULTIMODAL = "多式联运"


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    CNY = "CNY"


class DocumentType(str, Enum):
    INVOICE = "invoice"
    BILL_OF_LADING = "bill_of_lading"
    PACKING_LIST = "packing_list"
    INSURANCE = "insurance"
    ORIGIN_CERT = "origin_cert"
    INSPECTION_CERT = "inspection_cert"


class DiscrepancyType(str, Enum):
    COMPLETENESS = "completeness"
    AMOUNT = "amount"
    DATE = "date"
    PARTY = "party"
    GOODS = "goods"
    TRANSPORT = "transport"
    SPECIAL = "special"


class Severity(str, Enum):
    CRITICAL = "critical"
    MINOR = "minor"


class Conclusion(str, Enum):
    COMPLIANT = "compliant"
    MINOR_DISCREPANCY = "minor_discrepancy"
    DISCREPANT = "discrepant"


class DocumentRequirementCreate(BaseModel):
    document_type: str
    original_copies: int = 0
    copy_copies: int = 0


class DocumentRequirementResponse(BaseModel):
    id: int
    document_type: str
    original_copies: int
    copy_copies: int

    class Config:
        from_attributes = True


class LetterOfCreditCreate(BaseModel):
    lc_number: str
    issuing_bank: str
    beneficiary_name: str
    applicant_name: str
    currency: Currency
    amount: float
    latest_shipment_date: date
    latest_presentation_date: date
    expiry_date: date
    transport_mode: TransportMode
    port_of_loading: str
    port_of_discharge: str
    partial_shipment_allowed: bool = False
    transshipment_allowed: bool = False
    goods_description: str
    additional_terms: List[str] = []
    document_requirements: List[DocumentRequirementCreate]


class LetterOfCreditResponse(BaseModel):
    id: int
    lc_number: str
    issuing_bank: str
    beneficiary_name: str
    applicant_name: str
    currency: str
    amount: float
    latest_shipment_date: date
    latest_presentation_date: date
    expiry_date: date
    transport_mode: str
    port_of_loading: str
    port_of_discharge: str
    partial_shipment_allowed: bool
    transshipment_allowed: bool
    goods_description: str
    additional_terms: List[str]
    document_requirements: List[DocumentRequirementResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentSubmit(BaseModel):
    lc_number: str
    submission_id: str
    document_type: str
    original_copies_submitted: int = 0
    copy_copies_submitted: int = 0
    content: Dict[str, Any]


class DocumentResponse(BaseModel):
    id: int
    lc_id: int
    submission_id: str
    document_type: str
    original_copies_submitted: int
    copy_copies_submitted: int
    content: Dict[str, Any]

    class Config:
        from_attributes = True


class SubmissionSubmit(BaseModel):
    lc_number: str
    submission_id: str
    presentation_date: date
    documents: List[DocumentSubmit]


class DiscrepancyResponse(BaseModel):
    id: int
    discrepancy_type: str
    severity: str
    document_type: Optional[str] = None
    description: str
    lc_clause_reference: Optional[str] = None

    class Config:
        from_attributes = True


class AuditRecordResponse(BaseModel):
    id: int
    lc_id: int
    submission_id: str
    conclusion: str
    total_discrepancies: int
    critical_count: int
    minor_count: int
    presentation_date: date
    discrepancies: List[DiscrepancyResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditRecordDetailResponse(BaseModel):
    id: int
    lc_id: int
    submission_id: str
    conclusion: str
    total_discrepancies: int
    critical_count: int
    minor_count: int
    presentation_date: date
    discrepancies: List[DiscrepancyResponse]
    created_at: datetime
    lc: LetterOfCreditResponse
    documents: List[DocumentResponse]


class DiscrepancyStatsResponse(BaseModel):
    discrepancy_type: str
    count: int


class BeneficiaryDiscrepancyRateResponse(BaseModel):
    beneficiary_name: str
    total_audits: int
    total_discrepancies: int
    discrepancy_rate: float
