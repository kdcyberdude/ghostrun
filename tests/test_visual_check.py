import json

from PIL import Image
import pytest

from compare import sha256
import visual_check


@pytest.fixture
def evidence(tmp_path):
    native = tmp_path / 'private' / 'session' / 'frames'
    native.mkdir(parents=True)
    rows = [dict(f=f, player_x=f, terminal=int(f == 3)) for f in range(4)]
    route = tmp_path / 'clear.jsonl'
    route.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    pairs = []
    for f in (0, 1, 3):
        reference, rebuild = tmp_path / f'native-{f}.png', tmp_path / f'rebuild-{f}.png'
        image = Image.new('RGB', (8, 8), (30 + f, 60, 90))
        image.save(reference)
        image.save(rebuild)
        capture = native / f'{f}-{sha256(reference)}.png'
        capture.write_bytes(reference.read_bytes())
        capture.with_suffix('.json').write_text(json.dumps({'f': f, 'observables': rows[f]}))
        pairs.append(dict(f=f, reference=reference.name, rebuild=rebuild.name))
    manifest = dict(visual_route=route.name, routes=[dict(kind='clear', reference=route.name)],
                    fields={'player': {'player_x': 2}, 'outcome': {'terminal': 0}}, visuals=pairs)
    path = tmp_path / 'completion.json'
    path.write_text(json.dumps(manifest))
    return path, tmp_path / 'private', manifest


def save(path, manifest):
    path.write_text(json.dumps(manifest))


def test_matching_native_samples_pass(evidence):
    path, native, _ = evidence
    assert visual_check.check(path, native) == []


@pytest.mark.parametrize('frames', [[0, 3], [1, 2, 3], [0, 1, 2], [0, 1, 4], [0, 1, 1, 3]])
def test_requires_distinct_reset_middle_and_ending_frames(evidence, frames):
    path, native, manifest = evidence
    manifest['visuals'] = [dict(manifest['visuals'][0], f=f) for f in frames]
    save(path, manifest)
    assert visual_check.check(path, native)


def test_reference_must_be_an_accepted_complete_route(evidence):
    path, native, manifest = evidence
    manifest['routes'][0]['kind'] = 'death-recovery'
    save(path, manifest)
    assert 'accepted clear or heldout' in visual_check.check(path, native)[0]


def test_untrusted_native_image_rejected(evidence):
    path, native, manifest = evidence
    Image.new('RGB', (8, 8), 'white').save(path.parent / manifest['visuals'][0]['reference'])
    assert 'not a private oracle capture' in visual_check.check(path, native)[0]


@pytest.mark.parametrize('size,color', [((16, 16), (30, 60, 90)), ((8, 8), (0, 0, 0))])
def test_scaled_or_blank_output_rejected(evidence, size, color):
    path, native, manifest = evidence
    Image.new('RGB', size, color).save(path.parent / manifest['visuals'][0]['rebuild'])
    assert visual_check.check(path, native)


def test_tiny_color_noise_is_accepted(evidence):
    path, native, manifest = evidence
    Image.new('RGB', (8, 8), (31, 61, 91)).save(path.parent / manifest['visuals'][0]['rebuild'])
    assert visual_check.check(path, native) == []


@pytest.mark.parametrize('observed', [{'player_x': 900, 'terminal': 0}, {'terminal': 0}])
def test_capture_metadata_must_match_route_measurements(evidence, observed):
    path, native, _ = evidence
    metadata = next(native.rglob('0-*.json'))
    metadata.write_text(json.dumps({'f': 0, 'observables': observed}))
    assert 'observations differ' in visual_check.check(path, native)[0]


def test_transparent_capture_rejected(evidence):
    path, native, manifest = evidence
    Image.new('RGBA', (8, 8), (30, 60, 90, 0)).save(path.parent / manifest['visuals'][0]['rebuild'])
    assert 'opaque' in visual_check.check(path, native)[0]
