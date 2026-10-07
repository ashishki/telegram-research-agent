"""Keep media validation before preparation and all later failures non-retryable."""
from datetime import datetime,timezone
import hashlib
import time
from llm.client import LLMCompletionReceipt
from prm.storage.postgres import StorageError
from .model_errors import MediaOutcomeUnknown,MediaAccountingUnconfirmed,AcceptedMediaReceipt,ModelProviderRejected,ModelResponseInvalid


def read_bounded_media(asset,path,*,maximum,signatures):
    if asset.is_expired(datetime.now(timezone.utc)) or asset.mime_type not in signatures or path.is_symlink():
        raise StorageError('current allowlisted media file required')
    with path.open('rb') as source:content=source.read(maximum+1)
    if (not 0<len(content)<=maximum or len(content)!=asset.size_bytes
        or not content.startswith(signatures[asset.mime_type]) or hashlib.sha256(content).hexdigest()!=asset.sha256):
        raise StorageError('bounded media identity changed')
    return content


def execute_fenced_media(registry,reservation,transport,record,*,attempt_ref,model,http_attempted):
    """Retain the durable fence even if usage accounting loses its acknowledgment.

    Rejections and invalid replies keep their typed, non-retryable reason. All
    other failures after preparation carry an unknown receipt and fence refs.
    Bookkeeping never masks a non-retryable transport failure with a raw error.
    """
    started=time.monotonic();outcome='unknown';failure=None
    operations=(reservation.operation_ref,)
    def fenced(error):
        if isinstance(error,(ModelProviderRejected,ModelResponseInvalid)):
            error.attempt_ref=attempt_ref;error.operation_refs=operations
            return error
        receipt=LLMCompletionReceipt(text='',model=model,input_tokens=0,output_tokens=0,
            estimated_cost_usd=None,duration_ms=int((time.monotonic()-started)*1000),attempts=1,
            usage_recorded=False,external_call_attempted=http_attempted(),delivery_outcome='unknown')
        return MediaOutcomeUnknown(receipt,attempt_ref,operations)
    try:
        result=registry.execute_reserved((reservation,),transport);outcome='accepted'
    except Exception as error:
        failure=fenced(error)
        if isinstance(error,ModelProviderRejected):outcome='rejected'
    try:record(outcome,int((time.monotonic()-started)*1000))
    except Exception as error:
        if failure is None:
            receipt=AcceptedMediaReceipt(model=model,text=result if isinstance(result,str) else result['text'],
                duration_ms=int((time.monotonic()-started)*1000),external_call_attempted=http_attempted())
            failure=MediaAccountingUnconfirmed(receipt,result,attempt_ref,operations)
    if failure is not None:raise failure from None
    return result
