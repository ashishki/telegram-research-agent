"""Explicit per-role quality profiles, retaining the measured baseline."""
from prm.storage.postgres import StorageError

ROLES=frozenset({'chat','research','extraction','vision','speech','judge'})
QUALITIES=frozenset({'economical','balanced','maximum'})


class ModelProfiles:
    def __init__(self,profiles,*,baseline='balanced',comparison_receipts=None):
        if baseline not in QUALITIES or baseline not in profiles:raise StorageError('explicit baseline profile required')
        if set(profiles)-QUALITIES or any(set(value)-ROLES for value in profiles.values()):raise StorageError('unsupported explicit model profile or role')
        self.profiles,self.baseline,self.comparisons=profiles,baseline,dict(comparison_receipts or {})
    def select(self,*,role,quality='balanced',manual_model=None):
        if role not in ROLES or quality not in QUALITIES:raise StorageError('explicit supported workload role and quality required')
        chosen=quality
        if quality=='economical' and not self.comparisons.get(role,{}).get('quality_non_regressed'):
            chosen=self.baseline
        endpoint=self.profiles.get(chosen,{}).get(role)
        if endpoint is None:raise StorageError('configured workload model unavailable; no implicit provider fallback')
        if manual_model is not None:
            matches=[value[role] for value in self.profiles.values() if role in value and value[role].model==manual_model]
            if len(matches)!=1:raise StorageError('manual model selection must identify one configured endpoint')
            endpoint=matches[0]
        return endpoint
