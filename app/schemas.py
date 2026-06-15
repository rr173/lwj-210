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


class FeeTier(str, Enum):
    STANDARD = "standard"
    PREFERRED = "preferred"
    VIP = "vip"


class FeeType(str, Enum):
    FIRST_SUBMISSION = "first_submission"
    RESUBMISSION = "resubmission"


class FeeStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"


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
    fee_tier: FeeTier = FeeTier.STANDARD
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
    fee_tier: str
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
    original_submission_id: str
    resubmission_round: int
    modification_remark: Optional[str] = None
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
    original_submission_id: str
    resubmission_round: int
    modification_remark: Optional[str] = None
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


class SubmissionResubmitRequest(BaseModel):
    new_submission_id: str
    modification_remark: str = Field(..., min_length=1, description="修改说明，必须说明本次修改了哪些内容")
    presentation_date: date
    documents: List[DocumentSubmit]


class SubmissionHistoryResponse(BaseModel):
    original_submission_id: str
    lc_number: str
    total_rounds: int
    max_allowed_rounds: int
    current_conclusion: str
    history: List[AuditRecordResponse]


class AmendmentStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AmendableField(str, Enum):
    AMOUNT = "amount"
    LATEST_SHIPMENT_DATE = "latest_shipment_date"
    LATEST_PRESENTATION_DATE = "latest_presentation_date"
    EXPIRY_DATE = "expiry_date"
    PORT_OF_LOADING = "port_of_loading"
    PORT_OF_DISCHARGE = "port_of_discharge"
    PARTIAL_SHIPMENT_ALLOWED = "partial_shipment_allowed"
    TRANSSHIPMENT_ALLOWED = "transshipment_allowed"
    GOODS_DESCRIPTION = "goods_description"
    ADDITIONAL_TERMS = "additional_terms"


class FieldChange(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any


class AmendmentCreate(BaseModel):
    lc_number: str
    field_changes: List[FieldChange]


class AmendmentResponse(BaseModel):
    id: int
    lc_id: int
    amendment_number: str
    sequence_number: int
    status: str
    field_changes: List[FieldChange]
    acceptance_time: Optional[datetime] = None
    expiry_time: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class AmendmentSnapshotResponse(BaseModel):
    amendment_number: str
    status: str
    before: dict
    after: Optional[dict] = None


class AmendmentActionRequest(BaseModel):
    action: str


class LcWithAmendmentsResponse(LetterOfCreditResponse):
    amendments: List[AmendmentResponse] = []


class FeeRecordResponse(BaseModel):
    id: int
    fee_number: str
    lc_id: int
    submission_id: str
    audit_record_id: int
    fee_type: str
    fee_tier: str
    base_fee: float
    per_doc_fee: float
    document_count: int
    document_fee_total: float
    total_amount: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class LcFeeSummaryResponse(BaseModel):
    lc_number: str
    fee_tier: str
    fee_records: List[FeeRecordResponse]
    total_amount: float
    confirmed_amount: float
    pending_amount: float


class FeeTierSummary(BaseModel):
    fee_tier: str
    record_count: int
    total_amount: float
    confirmed_amount: float
    pending_amount: float


class FeeSummaryResponse(BaseModel):
    start_date: date
    end_date: date
    total_records: int
    grand_total: float
    by_tier: List[FeeTierSummary]
