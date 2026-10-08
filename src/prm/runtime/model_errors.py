"""Safe provider error classification; a response never authorizes blind retry."""
from prm.storage.postgres import StorageError
from llm.client import LLMOutcomeUnknown
from dataclasses import dataclass
from llm.client import LLMCompletionReceipt


@dataclass(frozen=True)
class ModelAccountingReceipt(LLMCompletionReceipt):
    accounting_status: str = 'unconfirmed'
    attempt_ref: str = ''
    operation_refs: tuple = ()
    retry_allowed: bool = False


class ModelPreparationUnknown(StorageError):
    def __init__(self,attempt_ref,operation_refs):
        super().__init__('model preparation is unconfirmed; transport was not attempted; do not retry automatically')
        self.attempt_ref=attempt_ref;self.operation_refs=tuple(operation_refs)
        self.retry_allowed=False;self.external_call_attempted=False;self.reason_kind='preparation_unknown'


class ModelAccountingUnconfirmed(StorageError):
    def __init__(self,receipt):
        super().__init__('model reply accepted; durable accounting status unavailable; do not retry')
        self.receipt=receipt;self.attempt_ref=receipt.attempt_ref;self.operation_refs=receipt.operation_refs
        self.accounting_status='unconfirmed';self.retry_allowed=False


@dataclass(frozen=True)
class AcceptedMediaReceipt:
    model: str
    text: str
    duration_ms: int
    delivery_outcome: str = 'accepted'
    external_call_attempted: bool = True
    usage_recorded: bool = False
    estimated_cost_usd: None = None


class MediaAccountingUnconfirmed(StorageError):
    def __init__(self,receipt,result,attempt_ref,operation_refs):
        super().__init__('media response accepted; cost accounting is unconfirmed; do not retry')
        self.receipt=receipt;self.result=result
        self.attempt_ref=attempt_ref;self.operation_refs=tuple(operation_refs)
        self.retry_allowed=False;self.reason_kind='accepted_accounting_unconfirmed'


class MediaOutcomeUnknown(LLMOutcomeUnknown):
    def __init__(self,receipt,attempt_ref,operation_refs):
        super().__init__(receipt)
        self.args=('selected media provider outcome is unknown; do not retry automatically',)
        self.attempt_ref=attempt_ref;self.operation_refs=tuple(operation_refs)
        self.retry_allowed=False;self.reason_kind='provider_outcome_unknown'


class ModelProviderRejected(StorageError):
    def __init__(self,status_code):
        super().__init__('selected model provider rejected the request')
        self.status_code=status_code;self.reason_kind='provider_rejected';self.retry_allowed=False


class ModelResponseInvalid(StorageError):
    def __init__(self):
        super().__init__('selected model provider returned an invalid response')
        self.reason_kind='invalid_provider_response';self.retry_allowed=False


DEFINITIVE_REJECTIONS=frozenset({400,401,403,404,405,422,429})
