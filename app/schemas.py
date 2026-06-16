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
    source: str
    is_removed: bool
    removal_reason: Optional[str] = None

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
    auto_conclusion: Optional[str] = None
    final_conclusion: Optional[str] = None
    total_discrepancies: int
    critical_count: int
    minor_count: int
    presentation_date: date
    review_status: str
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
    auto_conclusion: Optional[str] = None
    final_conclusion: Optional[str] = None
    total_discrepancies: int
    critical_count: int
    minor_count: int
    presentation_date: date
    review_status: str
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


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"


class ReviewAction(str, Enum):
    CONFIRM = "confirm"
    OVERRULE = "overrule"
    ADD_DISCREPANCY = "add_discrepancy"
    REMOVE_DISCREPANCY = "remove_discrepancy"


class ReviewerCreate(BaseModel):
    employee_id: str
    name: str
    department: str


class ReviewerResponse(BaseModel):
    id: int
    employee_id: str
    name: str
    department: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewAssignmentResponse(BaseModel):
    id: int
    audit_record_id: int
    reviewer_id: int
    reviewer_name: Optional[str] = None
    claimed_at: datetime
    expires_at: datetime
    completed_at: Optional[datetime] = None
    is_expired: bool

    class Config:
        from_attributes = True


class ReviewClaimRequest(BaseModel):
    employee_id: str


class DiscrepancyCreateRequest(BaseModel):
    discrepancy_type: str
    severity: str
    document_type: Optional[str] = None
    description: str
    lc_clause_reference: Optional[str] = None


class DiscrepancyRemoveRequest(BaseModel):
    discrepancy_id: int
    removal_reason: str


class ReviewOverruleRequest(BaseModel):
    new_conclusion: str
    overruled_reason: str


class ReviewCompleteRequest(BaseModel):
    action: ReviewAction
    overrule_data: Optional[ReviewOverruleRequest] = None
    add_discrepancies: Optional[List[DiscrepancyCreateRequest]] = None
    remove_discrepancies: Optional[List[DiscrepancyRemoveRequest]] = None
    remarks: Optional[str] = None


class ReviewOpinionResponse(BaseModel):
    id: int
    audit_record_id: int
    reviewer_id: int
    reviewer_name: Optional[str] = None
    action_type: str
    overruled_reason: Optional[str] = None
    new_conclusion: Optional[str] = None
    remarks: Optional[str] = None
    review_duration_seconds: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditRecordWithReviewResponse(AuditRecordResponse):
    review_status: str
    auto_conclusion: Optional[str] = None
    final_conclusion: Optional[str] = None
    active_assignment: Optional[ReviewAssignmentResponse] = None
    review_opinions: List[ReviewOpinionResponse] = []


class ReviewerStatsResponse(BaseModel):
    reviewer_id: int
    reviewer_name: str
    employee_id: str
    start_date: date
    end_date: date
    total_reviewed: int
    confirm_count: int
    confirm_rate: float
    overrule_count: int
    avg_review_duration_seconds: float
    total_review_duration_seconds: int


class TransferType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


class TransferStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class BackToBackStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class ConflictStatus(str, Enum):
    NORMAL = "normal"
    CONFLICT = "conflict"


class TransferCreate(BaseModel):
    lc_number: str
    second_beneficiary_name: str
    transfer_amount: float
    transfer_type: TransferType


class TransferConfirmRequest(BaseModel):
    action: str


class TransferResponse(BaseModel):
    id: int
    original_lc_id: int
    transfer_number: str
    second_beneficiary_name: str
    transfer_amount: float
    transfer_type: str
    status: str
    confirmation_time: Optional[datetime] = None
    inherited_terms: Optional[Dict[str, Any]] = None
    sequence_number: int
    created_at: datetime

    class Config:
        from_attributes = True


class TransferDetailResponse(TransferResponse):
    original_lc: LetterOfCreditResponse


class BackToBackDocumentRequirementCreate(BaseModel):
    document_type: str
    original_copies: int = 0
    copy_copies: int = 0


class BackToBackDocumentRequirementResponse(BaseModel):
    id: int
    document_type: str
    original_copies: int
    copy_copies: int

    class Config:
        from_attributes = True


class BackToBackLCCreate(BaseModel):
    lc_number: str
    beneficiary_name: str
    applicant_name: str
    issuing_bank: str
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
    document_requirements: List[BackToBackDocumentRequirementCreate]


class BackToBackLCResponse(BaseModel):
    id: int
    original_lc_id: int
    back_to_back_number: str
    beneficiary_name: str
    applicant_name: str
    issuing_bank: str
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
    document_requirements: List[BackToBackDocumentRequirementResponse]
    status: str
    conflict_status: str
    conflict_details: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BackToBackLCDetailResponse(BackToBackLCResponse):
    original_lc: LetterOfCreditResponse


class LcAvailableAmountResponse(BaseModel):
    lc_number: str
    original_amount: float
    total_transferred_amount: float
    total_back_to_back_amount: float
    remaining_available_amount: float
    transfers: List[TransferResponse]
    back_to_back_lcs: List[BackToBackLCResponse]


class LcTransferBackToBackSummaryResponse(BaseModel):
    lc_number: str
    transfers: List[TransferResponse]
    back_to_back_lcs: List[BackToBackLCResponse]


class AlertType(str, Enum):
    SHIPMENT = "shipment"
    PRESENTATION = "presentation"
    EXPIRY = "expiry"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"


class AlertResponse(BaseModel):
    id: int
    alert_number: str
    lc_id: int
    alert_type: str
    trigger_date: date
    target_date: date
    remaining_days: int
    status: str
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AlertAcknowledgeRequest(BaseModel):
    acknowledged_by: str


class AlertStatsResponse(BaseModel):
    alert_type: str
    count: int


class FreezeType(str, Enum):
    SHIPMENT_EXPIRED = "shipment_expired"
    PRESENTATION_EXPIRED = "presentation_expired"
    EXPIRY_EXPIRED = "expiry_expired"
    MANUAL = "manual"


class FreezeStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"


class FreezeRecordResponse(BaseModel):
    id: int
    freeze_number: str
    lc_id: int
    freeze_type: str
    reason: str
    status: str
    frozen_at: datetime
    released_at: Optional[datetime] = None
    released_by: Optional[str] = None
    release_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FreezeReleaseRequest(BaseModel):
    released_by: str
    release_reason: str


class SwiftMessageType(str, Enum):
    MT700 = "MT700"
    MT707 = "MT707"
    MT799 = "MT799"


class SwiftSendStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class SwiftMessageGenerateRequest(BaseModel):
    message_type: SwiftMessageType
    lc_number: str
    narrative: Optional[str] = None


class SwiftMessageResponse(BaseModel):
    id: int
    message_number: str
    message_type: str
    lc_number: str
    lc_id: Optional[int] = None
    raw_message: str
    status: str
    sent_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SwiftParseRequest(BaseModel):
    raw_message: str


class SwiftParsedField(BaseModel):
    tag: str
    field_name: str
    value: str


class SwiftParseResponse(BaseModel):
    message_type: str
    lc_number: Optional[str] = None
    fields: List[SwiftParsedField]
    created_resource_id: Optional[int] = None
    created_resource_type: Optional[str] = None
    missing_fields: List[str] = []


class PartyRole(str, Enum):
    ISSUING_BANK = "issuing_bank"
    ADVISING_BANK = "advising_bank"
    BENEFICIARY = "beneficiary"
    APPLICANT = "applicant"


class EventType(str, Enum):
    LC_CREATED = "lc_created"
    SUBMISSION_CREATED = "submission_created"
    SUBMISSION_REVIEWED = "submission_reviewed"
    AMENDMENT_CREATED = "amendment_created"
    AMENDMENT_ACCEPTED = "amendment_accepted"
    AMENDMENT_REJECTED = "amendment_rejected"
    ALERT_GENERATED = "alert_generated"
    FREEZE_CREATED = "freeze_created"
    FREEZE_RELEASED = "freeze_released"
    TRANSFER_CREATED = "transfer_created"
    BACK_TO_BACK_CREATED = "back_to_back_created"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class PartyCreate(BaseModel):
    name: str
    role: PartyRole
    contact: str


class PartyResponse(BaseModel):
    id: int
    name: str
    role: str
    contact: str
    created_at: datetime

    class Config:
        from_attributes = True


class PartySubscriptionResponse(BaseModel):
    id: int
    party_id: int
    event_type: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SubscriptionUpdate(BaseModel):
    event_type: EventType
    is_active: bool


class SubscriptionBatchUpdate(BaseModel):
    subscriptions: List[SubscriptionUpdate]


class NotificationResponse(BaseModel):
    id: int
    notification_number: str
    party_id: int
    party_name: Optional[str] = None
    event_type: str
    lc_id: int
    lc_number: Optional[str] = None
    event_summary: str
    event_ref_id: Optional[str] = None
    status: str
    read_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationMarkReadRequest(BaseModel):
    notification_ids: List[int]


class NotificationArchiveRequest(BaseModel):
    notification_ids: List[int]


class LCEventStreamResponse(BaseModel):
    id: int
    event_type: str
    event_summary: str
    event_ref_id: Optional[str] = None
    lc_id: int
    party_id: Optional[int] = None
    party_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
