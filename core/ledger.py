"""Durable per-game stage state, so a run survives cancellation, context loss and plugin upgrades."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

STAGES = ('intake', 'reward', 'verify', 'explore', 'oracle', 'build', 'compare', 'gate')
STATUSES = ('pending', 'running', 'passed', 'failed', 'blocked')
MODES = ('mechanics', 'faithful')
RIGHTS_BASES = ('owner', 'open-license')


class LedgerError(ValueError):
    pass


def check_rights(mode, rights):
    """'mechanics' builds new art and levels. 'faithful' reuses the game's own material, so it needs a stated basis."""
    if mode not in MODES:
        raise LedgerError(f'mode must be one of {MODES}')
    if mode == 'mechanics':
        return
    if not rights or rights.get('basis') not in RIGHTS_BASES or not rights.get('source'):
        raise LedgerError("faithful mode needs rights: {'basis': 'owner'|'open-license', 'source': <licence or proof>}")
    if rights['basis'] == 'open-license' and not rights.get('license'):
        raise LedgerError("an open-license basis must name the licence in rights['license']")


class Ledger:
    def __init__(self, path):
        self.path = Path(path)

    def create(self, game, mode, rights=None):
        check_rights(mode, rights)
        if self.path.exists():
            raise LedgerError(f'{self.path} already exists')
        self._write({'game': game, 'mode': mode, 'rights': rights, 'notes': [],
                     'stages': {s: {'status': 'pending', 'evidence': None} for s in STAGES}})

    def read(self):
        return json.loads(self.path.read_text())

    def _write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent)
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, self.path)

    def set(self, stage, status, evidence=None, note=None):
        if stage not in STAGES or status not in STATUSES:
            raise LedgerError(f'unknown stage or status: {stage}, {status}')
        state = self.read()
        if status in ('running', 'passed'):
            for earlier in STAGES[:STAGES.index(stage)]:
                if state['stages'][earlier]['status'] != 'passed':
                    raise LedgerError(f'{stage} cannot be {status}: {earlier} has not passed')
        if status == 'passed' and not evidence:
            raise LedgerError('a passed stage needs evidence')
        state['stages'][stage] = {'status': status, 'evidence': evidence}
        if note:
            state['notes'].append({'stage': stage, 'status': status, 'note': note})
        self._write(state)
        return state

    def next_stage(self):
        state = self.read()
        return next((s for s in STAGES if state['stages'][s]['status'] != 'passed'), None)
