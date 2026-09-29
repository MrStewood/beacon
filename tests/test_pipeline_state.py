"""Supervisor state: escalated candidates must not be re-queued for rebuild.

Regression for the build→review→escalate livelock: an investigation whose
candidate was moved to leads/needs_human_review/ was still counted as
"needs candidate", so every loop step rebuilt it, re-reviewed it, and
escalated it again forever.
"""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import supervisor as sup


def _wire(monkeypatch, tmp_path, escalated: bool) -> None:
    inv_zip = tmp_path / "investigations" / "40744"
    inv_zip.mkdir(parents=True)
    inv_zip.joinpath("40744-foo-pantry.json").write_text(json.dumps({
        "complete": True,
        "candidate_id": "laurel-foo-pantry-123",
        "lead": {"name": "Foo Pantry", "category": "food",
                 "source_url": "https://foo.example/org"},
        "pass_b": {},
        "summary": {},
    }))

    approved = tmp_path / "approved"
    approved.mkdir()
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    human = tmp_path / "needs_human_review"
    human.mkdir()
    if escalated:
        human.joinpath("laurel-foo-pantry-123.yaml").write_text(yaml.dump({
            "candidate_id": "laurel-foo-pantry-123",
            "resource": {"name": "Foo Pantry"},
        }))

    monkeypatch.setattr(sup, "BEACON_ROOT", tmp_path)
    monkeypatch.setattr(sup, "INVESTIGATIONS_DIR", tmp_path / "investigations")
    monkeypatch.setattr(sup, "APPROVED_DIR", approved)
    monkeypatch.setattr(sup, "REJECTED_DIR", rejected)
    monkeypatch.setattr(sup, "CANDIDATES_DIR", candidates)
    monkeypatch.setattr(sup, "HUMAN_REVIEW_DIR", human)


def test_escalated_investigation_is_not_rebuilt(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, escalated=True)

    inv = sup._read_investigations()

    assert inv["needs_candidate"] == 0, "escalated investigation was re-queued for rebuild"
    assert sup._read_needs_human()["count"] == 1


def test_clean_investigation_still_needs_candidate(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, escalated=False)

    inv = sup._read_investigations()

    assert inv["needs_candidate"] == 1
    assert inv["items"][0]["name"] == "Foo Pantry"
    assert sup._read_needs_human()["count"] == 0
