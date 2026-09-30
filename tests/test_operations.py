import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT = Path(__file__).resolve().parents[1]

def test_operations_records():
    config = json.loads((ROOT / 'operations/config.json').read_text())
    Draft202012Validator(json.loads((ROOT / 'schema/operations.schema.json').read_text()), format_checker=FormatChecker()).validate(config)
    validator = Draft202012Validator(json.loads((ROOT / 'schema/lead.schema.json').read_text()), format_checker=FormatChecker())
    ids = set()
    for path in (ROOT / 'operations/leads').glob('*.json'):
        lead = json.loads(path.read_text())
        validator.validate(lead)
        assert lead['lead_id'] == path.stem
        assert lead['lead_id'] not in ids
        ids.add(lead['lead_id'])
        for history in lead['history_paths']:
            assert (ROOT / history).is_file()
        if lead['status'] == 'published':
            assert lead['resource_id']
        if lead['status'] == 'candidate':
            assert lead['candidate_id']
    assert ids
