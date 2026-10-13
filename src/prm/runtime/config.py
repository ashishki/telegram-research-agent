"""Offline configuration checks. No credentials, environment, DB or adapter startup."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
from prm.storage.postgres import StorageError, SyntheticTarget


RUNTIME_FIELDS = frozenset({'owner_ref', 'owner_chat_id', 'budget_refs', 'job_budget', 'model',
    'model_upper_bound', 'history_retention_seconds', 'model_resource_ref', 'archive_resource_ref',
    'public_web', 'public_upper_bound', 'public_search_ref', 'public_fetch_ref', 'tariff_version',
    'graph', 'github', 'canvas', 'artifact_root', 'media_root', 'local_services', 'speech', 'vision',
    'delivery', 'media_download', 'model_profiles', 'quality_profile'})
REQUIRED = frozenset({'owner_ref', 'owner_chat_id', 'budget_refs', 'job_budget'})
MODEL_FIELDS = frozenset({'provider_ref', 'connection_ref', 'endpoint', 'model', 'token_env', 'timeout_seconds', 'synthetic_http'})
SECRET_FIELDS = frozenset({'token', 'password', 'api_key', 'access_token', 'refresh_token', 'encryption_key', 'client_secret'})


@dataclass(frozen=True)
class RuntimeConfigSummary:
    schema_version: str
    selected_mode: str
    valid: bool
    configured_capabilities: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    errors: tuple[str, ...]
    observed_runtime: str = 'unknown'
    observed_storage_schema: str = 'unknown'
    observed_grants: str = 'unknown'


def load_public_json(path: str, *, limit: int) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate field')
            result[key] = value
        return result
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit: raise ValueError('bound')
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
        if not isinstance(value, dict): raise ValueError('object')
        return value
    except (OSError, ValueError, RecursionError):
        raise StorageError('invalid bounded public configuration file') from None


def _mapping(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        raise StorageError('invalid runtime configuration structure')


def _reference(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and value.strip() == value


def _credential_ref(value):
    if not isinstance(value, str) or not re.fullmatch(r'PAI_[A-Za-z0-9_]+', value):
        raise StorageError('invalid credential environment reference')


def _no_secrets(value, depth=0):
    if depth > 12: raise StorageError('runtime configuration depth exceeds bound')
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SECRET_FIELDS: raise StorageError('raw credential forbidden in runtime configuration')
            _no_secrets(item, depth + 1)
    elif isinstance(value, list):
        for item in value: _no_secrets(item, depth + 1)


def _model(value):
    _mapping(value, MODEL_FIELDS, {'provider_ref', 'connection_ref', 'endpoint', 'model'})
    if not all(_reference(value[key]) for key in ('provider_ref', 'connection_ref', 'model')):
        raise StorageError('invalid model descriptor')
    if not isinstance(value['endpoint'], str) or len(value['endpoint']) > 2048:
        raise StorageError('invalid model endpoint')
    if not value['provider_ref'].startswith('provider_') or not value['connection_ref'].startswith('connection_'):
        raise StorageError('invalid model binding references')
    url = urlsplit(value['endpoint'])
    synthetic = value.get('synthetic_http', False)
    if type(synthetic) is not bool or url.username or url.password or url.fragment or url.query:
        raise StorageError('invalid model endpoint')
    if synthetic:
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port:
            raise StorageError('invalid synthetic model endpoint')
    elif url.scheme != 'https' or not url.hostname:
        raise StorageError('invalid HTTPS model endpoint')
    if not synthetic or 'token_env' in value: _credential_ref(value.get('token_env'))
    seconds = value.get('timeout_seconds', 8)
    if type(seconds) is not int or not 1 <= seconds <= 120: raise StorageError('invalid model deadline')


def validate_runtime_config(config: dict) -> None:
    _mapping(config, RUNTIME_FIELDS, REQUIRED)
    _no_secrets(config)
    chat = config['owner_chat_id']
    if not isinstance(chat, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', chat) or int(chat) > 9223372036854775807:
        raise StorageError('invalid complete owner tuple')
    if brief_owner_ref_from_authenticated_private_tuple(chat, chat, chat) != config['owner_ref']:
        raise StorageError('runtime owner tuple differs')
    refs = config['budget_refs']
    if not isinstance(refs, list) or len(refs) not in {3, 4} or not all(_reference(x) for x in refs) or len(set(refs)) != len(refs):
        raise StorageError('invalid budget references')
    for key in ('job_budget', 'local_services'):
        if key in config and type(config[key]) is not bool: raise StorageError('invalid runtime boolean')
    retention = config.get('history_retention_seconds', 0)
    if type(retention) is not int or not 0 <= retention <= 30 * 86400: raise StorageError('invalid history retention')
    if config.get('quality_profile', 'balanced') not in {'economical', 'balanced', 'maximum'}:
        raise StorageError('invalid quality profile')
    for key in ('model_resource_ref', 'archive_resource_ref', 'public_search_ref', 'public_fetch_ref', 'tariff_version'):
        if key in config and not _reference(config[key]): raise StorageError('invalid runtime reference')
    for key in ('model_upper_bound', 'public_upper_bound'):
        if key in config and config[key] is not None and (type(config[key]) not in {int, float} or not math.isfinite(config[key]) or config[key] < 0):
            raise StorageError('invalid runtime budget bound')
    if config.get('model'): _model(config['model'])
    if config.get('model_profiles'):
        _mapping(config['model_profiles'], {'economical', 'balanced', 'maximum'})
        for roles in config['model_profiles'].values():
            _mapping(roles, {'chat', 'research', 'extraction', 'vision', 'speech', 'judge'})
            for value in roles.values(): _model(value)
        quality = config.get('quality_profile', 'balanced')
        quality = 'balanced' if quality == 'economical' else quality
        if not config['model_profiles'].get(quality, {}).get('chat'): raise StorageError('selected quality lacks chat')
        if 'balanced' not in config['model_profiles']: raise StorageError('balanced baseline profile required')
    sections = {
        'public_web': ({'token_env', 'bounds'}, {'token_env', 'bounds'}),
        'github': ({'repository_ref', 'ref', 'upper_bound', 'paths'}, {'repository_ref', 'ref', 'upper_bound'}),
        'delivery': ({'token_env', 'upper_bound', 'destination_ref', 'origin', 'synthetic'}, {'token_env', 'upper_bound', 'destination_ref'}),
        'media_download': ({'token_env', 'resource_ref', 'upper_bound', 'origin'}, {'token_env', 'resource_ref', 'upper_bound'}),
        'speech': ({'endpoint', 'upper_bound', 'resource_ref'}, {'endpoint', 'upper_bound'}),
        'vision': ({'endpoint', 'upper_bound', 'resource_ref'}, {'endpoint', 'upper_bound'}),
        'canvas': ({'token_env', 'origin', 'selection', 'connection_ref', 'institution_access_ref', 'upper_bound', 'identity_bindings'}, {'token_env', 'origin', 'selection', 'connection_ref'}),
        'graph': ({'vault_key_env', 'vault_directory', 'oauth', 'connection_ref', 'account_ref', 'upper_bound', 'mail_selection', 'calendar_selection', 'academic_sources', 'action_upper_bound'}, {'vault_key_env', 'vault_directory', 'oauth', 'connection_ref', 'account_ref'}),
    }
    for key, (allowed, required) in sections.items():
        if key in config:
            _mapping(config[key], allowed, required)
            for field in ('token_env', 'vault_key_env'):
                if field in config[key]: _credential_ref(config[key][field])
            for field in ('upper_bound', 'action_upper_bound'):
                amount = config[key].get(field)
                if amount is not None and (type(amount) not in {int, float} or not math.isfinite(amount) or amount < 0):
                    raise StorageError('invalid adapter budget bound')
    for key in ('artifact_root', 'media_root'):
        if key in config and (not isinstance(config[key], str) or not Path(config[key]).is_absolute()):
            raise StorageError('explicit absolute private artifact path required')
    if 'public_web' in config:
        from prm.public_web import PublicWebBounds
        PublicWebBounds(**config['public_web']['bounds'])
    for key in ('speech', 'vision'):
        if key in config:
            if not config.get('media_root'): raise StorageError('media root required for adapter')
            _model(config[key]['endpoint'])
    if 'graph' in config:
        _mapping(config['graph']['oauth'], {'client_id', 'tenant', 'redirect_uri', 'authority', 'graph_origin', 'synthetic'}, {'client_id', 'tenant', 'redirect_uri'})
    # Existing scope constructors are pure validators, with no network/token
    # lookup or vault creation. Unknown nested fields fail before any startup.
    for section, key, module, typename, tuple_fields, date_fields in (
        ('graph', 'mail_selection', 'prm.mail_connector', 'MailScopeSelection', ('folders', 'sender_domains'), ('since', 'until')),
        ('graph', 'calendar_selection', 'prm.schedule_connectors', 'CalendarScopeSelection', ('calendar_refs',), ('window_start', 'window_end')),
        ('canvas', 'selection', 'prm.academic_inbox', 'CanvasScopeSelection', ('course_refs',), ('window_start', 'window_end')),
    ):
        if section in config and config[section].get(key):
            from importlib import import_module
            from datetime import datetime
            value = dict(config[section][key])
            for field in tuple_fields:
                if field in value:
                    if not isinstance(value[field], list): raise StorageError('typed scope list required')
                    value[field] = tuple(value[field])
            for field in date_fields:
                if value.get(field): value[field] = datetime.fromisoformat(value[field])
            getattr(import_module(module), typename)(**value)


def check_runtime_configuration(*, mode: str, config=None, target=None, owner_ref=None, owner_chat_id=None) -> RuntimeConfigSummary:
    missing, errors, capabilities = [], [], []
    if mode == 'compatibility':
        if any(value is not None for value in (config, target, owner_ref, owner_chat_id)):
            errors.append('compatibility_refuses_durable_configuration')
        else: capabilities.append('compatibility_assistant')
    elif mode == 'durable':
        if config is None: missing.append('runtime_config')
        else:
            try:
                validate_runtime_config(config)
                if owner_ref is not None and owner_ref != config['owner_ref']: raise StorageError('owner mismatch')
                if owner_chat_id is not None and owner_chat_id != config['owner_chat_id']: raise StorageError('owner mismatch')
                capabilities.extend(['jobs', 'chat_fallback', 'archive_search'])
                if config.get('local_services'): capabilities.extend(['weekly', 'memory', 'watch'])
                for key in ('model', 'model_profiles', 'public_web', 'graph', 'github', 'canvas', 'delivery', 'media_download'):
                    if config.get(key): capabilities.append(key)
            except (StorageError, TypeError, ValueError, AttributeError): errors.append('invalid_runtime_config')
        if target is None: missing.append('synthetic_target')
        else:
            try:
                selected = SyntheticTarget.from_mapping(target)
                if selected.user != 'pa_test_app': raise StorageError('application target required')
            except (StorageError, TypeError, ValueError): errors.append('invalid_synthetic_target')
    else: errors.append('invalid_runtime_mode')
    return RuntimeConfigSummary('pa.runtime_config_summary.v1', mode, not missing and not errors,
                                tuple(capabilities), tuple(missing), tuple(errors))
