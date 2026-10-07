"""Prepare exact-code candidate inventory; evidence is never inferred from code."""
import hashlib
import json
from pathlib import Path
import subprocess


def prepare_candidate(repository,*,evidence=()):
    repository=Path(repository).resolve()
    head=subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'],text=True).strip()
    matrix=json.loads((repository/'docs/design/PAI.requirements.json').read_text())
    inventory=[]
    for pattern in ('src/prm/runtime/*.py','src/prm/storage/*.py','tests/test_pai_*.py'):
        for path in sorted(repository.glob(pattern)):
            inventory.append({'path':str(path.relative_to(repository)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    accepted=[entry for entry in evidence if entry.get('head_sha')==head and entry.get('status')=='observed_pass']
    proven={entry['spec_id'] for entry in accepted if 'spec_id' in entry}
    return {'schema_version':1,'head_sha':head,'status':'candidate_unverified','inventory':inventory,
            'spec_sha256':matrix['spec_sha256'],'requirements':[{'spec_id':entry['spec_id'],'case_name':entry['case_name'],
                'evidence':'observed_pass' if entry['spec_id'] in proven else 'pending'} for entry in matrix['requirements']],
            'scenarios':matrix['scenarios'],'gates':{'synthetic_acceptance':'pending','load_recovery':'pending','independent_review':'pending',
                'actual_providers':'pending_scoped_access','human_visual_usefulness':'pending','production':'not_authorized','owner_completion':'pending'}}


def completion_allowed(candidate,*,human_acceptance_ref=None):
    # A draft package cannot be promoted by changing one boolean or a count.
    if not human_acceptance_ref:return False
    return (candidate.get('status')=='accepted_by_workflow' and all(row['evidence']=='observed_pass' for row in candidate['requirements'])
            and all(value in {'observed_pass','accepted'} for value in candidate['gates'].values()))
