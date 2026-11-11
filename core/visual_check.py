"""Check sampled, unshifted 2D captures against authenticated native frames.

This checks supplied captures; the parent still verifies they came from the actual renderer.
"""
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from compare import load, sha256


def check(manifest_path, oracle_root):
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text())
        route_path = (path.parent / manifest['visual_route']).resolve()
        accepted = any(r.get('kind') in ('clear', 'heldout') and
                       (path.parent / r['reference']).resolve() == route_path
                       for r in manifest.get('routes', []))
        if not accepted:
            return ['visual_route must name an accepted clear or heldout reference route']
        route = load(route_path)
        if not route or route[max(route)].get('terminal') != 1:
            return ['visual route must reach its declared ending']
        pairs = manifest.get('visuals', [])
        frames = [p.get('f') for p in pairs]
        if any(type(f) is not int for f in frames) or len(set(frames)) != len(frames):
            return ['visual samples need distinct integer frames']
        if len(frames) < 3 or not {0, max(route)} <= set(frames) or not set(frames) <= set(route):
            return ['visual samples need reset, ending and at least one intermediate route frame']
        fields = {field for group in manifest['fields'].values() for field in group}
        problems = []
        for pair in pairs:
            f = pair['f']
            reference, rebuild = [path.parent / pair[k] for k in ('reference', 'rebuild')]
            digest = sha256(reference)
            native = [p for p in Path(oracle_root).rglob(f'{f}-{digest}.png')
                      if p.parent.name == 'frames' and sha256(p) == digest]
            if not native:
                problems.append(f'frame {f}: reference image is not a private oracle capture')
                continue
            authenticated = False
            for capture in native:
                metadata = json.loads(capture.with_suffix('.json').read_text())
                observed = metadata.get('observables', {})
                if metadata.get('f') == f and all(k in observed and k in route[f] and
                                                  observed[k] == route[f][k] for k in fields):
                    authenticated = True
                    break
            if not authenticated:
                problems.append(f'frame {f}: native capture observations differ from the selected route')
                continue
            with Image.open(reference) as a, Image.open(rebuild) as b:
                if a.size != b.size:
                    problems.append(f'frame {f}: capture dimensions differ; do not resize or shift')
                    continue
                if any('A' in image.getbands() and image.getchannel('A').getextrema() != (255, 255)
                       for image in (a, b)):
                    problems.append(f'frame {f}: captures must be opaque renderer output')
                    continue
                diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
                error = sum(ImageStat.Stat(diff).mean) / (3 * 255)
                r, g, blue = diff.split()
                histogram = ImageChops.lighter(ImageChops.lighter(r, g), blue).histogram()
                changed = sum(histogram[33:]) / (a.width * a.height)
                if error > 0.01 or changed > 0.01:
                    problems.append(f'frame {f}: visible difference (mean error {error:.4f}, changed pixels {changed:.4f})')
        return problems
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f'invalid visual evidence: {exc}']
