"""Safe provider error classification; a response never authorizes blind retry."""
from prm.storage.postgres import StorageError


class ModelProviderRejected(StorageError):
    def __init__(self,status_code):
        super().__init__('selected model provider rejected the request')
        self.status_code=status_code;self.reason_kind='provider_rejected';self.retry_allowed=False


class ModelResponseInvalid(StorageError):
    def __init__(self):
        super().__init__('selected model provider returned an invalid response')
        self.reason_kind='invalid_provider_response';self.retry_allowed=False


DEFINITIVE_REJECTIONS=frozenset({400,401,403,404,405,422,429})
