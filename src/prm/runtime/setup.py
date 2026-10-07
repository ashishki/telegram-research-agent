"""Explicit synthetic schema installation; importing never migrates anything."""
from prm.storage.postgres import migrate,StorageError
from prm.storage.policy import install_policy
from prm.storage.actions import install_actions
from prm.storage.conversations import install_conversations
from prm.storage.jobs import install_jobs
from prm.runtime.scheduler import install_schedules
from prm.runtime.delivery import install_delivery
from prm.runtime.connections import install_connections
from prm.runtime.graph import install_sources
from prm.runtime.memory import install_memory
from prm.runtime.cost_cache import install_cost_cache
from prm.runtime.operations import install_operations
from prm.storage.briefs import install_briefs


def install_runtime(target,*,expected_base_version):
    if target.user!='pa_test_migrator':raise StorageError('explicit synthetic migrator target required')
    migrate(target,expected_version=expected_base_version)
    for installer in (install_policy,install_actions,install_conversations,install_jobs,install_schedules,install_delivery,install_briefs,
                      install_connections,install_sources,install_memory,install_cost_cache,install_operations):installer(target)
    return {'base_version':1,'runtime':'installed_default_off','production_migration_performed':False}
