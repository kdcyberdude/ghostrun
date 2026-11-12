"""Default to the tested recipe, disclose overrides, and measure before longer work."""
from ghostrun_security import child_env

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

BASELINE_PATH = Path(__file__).with_name('training-baseline.json')
BASELINE = json.loads(BASELINE_PATH.read_text())
PREFLIGHT_ITERS = 3
PREFLIGHT_SECONDS = 180


class PolicyError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PolicyError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(args, smoke=False):
    defaults = {**BASELINE['settings'], **BASELINE['runtime']}
    parser = Parser(allow_abbrev=False, add_help=False)
    for key, value in defaults.items():
        parser.add_argument('--' + key.replace('_', '-'), type=type(value), default=value)
    settings = vars(parser.parse_args(args))
    for key, value in settings.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise PolicyError(f'{key} must be finite')
        if isinstance(value, (int, float)) and value < 0:
            raise PolicyError(f'{key} must be non-negative')
    for key in ('envs_per_game', 'minibatch_envs', 'infer_chunk', 'obs_slots', 'steps', 'epochs', 'core'):
        if settings[key] < 1:
            raise PolicyError(f'{key} must be positive')
    changed = {k: {'baseline': v, 'requested': settings[k]} for k, v in BASELINE['settings'].items()
               if settings[k] != v}
    return settings, changed


def argv(settings):
    return [item for k, v in settings.items() for item in ('--' + k.replace('_', '-'), str(v))]


def hardware():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=uuid,name,memory.total',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, env=child_env())
        rows = result.stdout.strip().splitlines()
        if len(rows) != 1:
            raise PolicyError('training preflight requires one visible GPU')
        uuid, name, memory = [x.strip() for x in rows[0].split(',')]
        return {'uuid': uuid, 'name': name, 'memory_mib': int(memory)}
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise PolicyError(f'cannot measure GPU hardware: {exc}') from exc


def resource_evidence(game, source):
    """Record optional measured reasons for an override without adding an approval gate."""
    if not source:
        return None
    run = Path(source).resolve()
    if run.parent != (game.ref / 'runs').resolve():
        raise PolicyError('adjustment evidence must be an owned run directory')
    plan_path = run / 'training-policy.json'
    plan = json.loads(plan_path.read_text())
    log = run / 'stdout.log'
    text = log.read_text()
    rows_path = run / 'metrics.jsonl'
    rows = [json.loads(x) for x in rows_path.read_text().splitlines() if x] if rows_path.exists() else []
    oom = 'out of memory' in text.lower()
    compiler = any(x in text for x in ('BackendCompilerFailed', 'torch._dynamo.exc', 'ptxas fatal', 'nvcc fatal'))
    peak = max((r.get('mem_gb', 0) for r in rows), default=0) * 1e9 / 1048576
    return {'run': str(run), 'source_phase': plan['phase'], 'hardware': plan['hardware'],
            'out_of_memory': oom, 'compiler_failure': compiler,
            'peak_memory_mib': peak, 'stdout_sha256': digest(log),
            'metrics_sha256': digest(rows_path) if rows_path.exists() else None}


def plan(game, settings, changed, smoke=False, evidence=None, note=None):
    model_hash = digest(game.engine / 'rl/model.py')
    if model_hash != BASELINE['model_sha256']:
        changed = {**changed, 'model_source': {'baseline': BASELINE['model_sha256'], 'requested': model_hash}}
    gpu = None if settings['device'] == 'cpu' else hardware()
    adjustment = resource_evidence(game, evidence)
    return {'baseline': BASELINE['id'], 'baseline_sha256': digest(BASELINE_PATH),
            'phase': 'smoke' if smoke else 'preflight', 'settings': settings,
            'recipe': 'custom' if changed else 'recommended', 'model_sha256': model_hash,
            'hardware': gpu, 'adjustments': changed, 'adjustment_evidence': adjustment,
            'recipe_note': note or ('Explicit argument/source override; no reason supplied.' if changed else 'Tested Mario default.'),
            'notice': 'Using a custom recipe. Explain the differences and reason to the user; this is not the tested Mario recipe.' if changed else
                      'Using the tested Mario recipe.'}


def throughput(run, prior, current):
    """A tiny/smaller-model run cannot qualify a different production configuration."""
    if not prior or prior['phase'] == 'smoke' or any(prior.get(k) != current.get(k)
            for k in ('baseline_sha256', 'hardware', 'model_sha256')):
        return None
    if any(prior['settings'][k] != current['settings'][k] for k in BASELINE['settings']):
        return None
    run = Path(run)
    path = run / 'metrics.jsonl'
    rows = [json.loads(x) for x in path.read_text().splitlines() if x] if path.exists() else []
    if any(any(k in (g.get('ends') or {}) for k in ('fault', 'emulator_fault'))
           for r in rows for g in (r.get('games') or {}).values()):
        raise PolicyError('preflight reported emulator faults')
    if any(not math.isfinite(r[k]) for r in rows for k in ('pg', 'v', 'ent', 'kl', 'gnorm') if k in r):
        raise PolicyError('preflight reported non-finite training metrics')
    if not (run / 'CLEAN_EXIT').exists() or not (run / 'ckpt_rank0_latest.pt').exists():
        return None
    if len(rows) < PREFLIGHT_ITERS:
        return None
    speeds = [r.get('sps', 0) for r in rows[1:PREFLIGHT_ITERS]]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in speeds):
        raise PolicyError('preflight did not produce valid measured throughput')
    return {'run': str(run), 'metrics_sha256': digest(path), 'steady_decisions_per_second': statistics.median(speeds),
            'samples': speeds, 'note': 'Measured throughput; this does not prove learning.'}


def bounded(settings):
    settings = dict(settings)
    settings['total_iters'] = min(settings['total_iters'] or PREFLIGHT_ITERS, PREFLIGHT_ITERS)
    settings['time_limit'] = min(settings['time_limit'] or PREFLIGHT_SECONDS, PREFLIGHT_SECONDS)
    return settings
