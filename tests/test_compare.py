import json

import pytest

from evals import compare, run_eval
from tests.test_run_eval import envelope, truth
from tests.test_schema import VALID_DOCUMENT

FILES = ["a.jpg", "b.jpg", "c.jpg"]


@pytest.fixture
def gt(tmp_path, monkeypatch):
    """Ground truth that VALID_DOCUMENT matches on every field."""
    directory = tmp_path / "gt"
    directory.mkdir()
    for name in FILES:
        (directory / f"{name.split('.')[0]}.json").write_text(json.dumps(truth(161700)))
    monkeypatch.setattr(run_eval, "GROUND_TRUTH", directory)
    return directory


def make_run(root, name, changes=None, files=FILES):
    """A saved run folder. `changes` maps a file to field overrides."""
    documents = root / name / "documents"
    documents.mkdir(parents=True)
    for file in files:
        response = envelope()
        response["document"] = VALID_DOCUMENT | (changes or {}).get(file, {})
        record = {"file": file, "http_status": 200, "wall_seconds": 1.0,
                  "response": response}
        (documents / f"{file.split('.')[0]}.json").write_text(json.dumps(record))
    return root / name


def run(baseline, candidate, *extra):
    return compare.main([str(baseline), str(candidate), *extra])


WRONG_TOTAL = {"total": {"value": 1, "status": "present", "confidence": 0.9, "evidence": "1"}}
INVENTED_DISCOUNT = {"discount": {"value": 500, "status": "present",
                                  "confidence": 0.9, "evidence": "500"}}


def test_identical_runs_pass_with_no_flips(tmp_path, gt, capsys):
    a, b = make_run(tmp_path, "a"), make_run(tmp_path, "b")
    assert run(a, b) == 0
    out = capsys.readouterr().out
    assert "regressions (0)" in out and "fixes (0)" in out
    assert "measures run-to-run noise" in out  # same model and prompt on both


def test_one_field_turning_wrong_fails_and_is_listed(tmp_path, gt, capsys):
    a, b = make_run(tmp_path, "a"), make_run(tmp_path, "b", {"b.jpg": WRONG_TOTAL})
    assert run(a, b, "--json") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["regressions"] == [{
        "file": "b.jpg", "field": "total", "before": "correct", "after": "wrong_value",
        "value_before": 161700, "value_after": 1,
    }]
    assert result["reasons"] == ["total accuracy dropped"]


def test_a_fix_alone_passes(tmp_path, gt, capsys):
    a, b = make_run(tmp_path, "a", {"b.jpg": WRONG_TOTAL}), make_run(tmp_path, "b")
    assert run(a, b, "--json") == 0
    result = json.loads(capsys.readouterr().out)
    assert [f["field"] for f in result["fixes"]] == ["total"]
    assert result["regressions"] == []


def test_one_more_hallucination_fails(tmp_path, gt, capsys):
    a, b = make_run(tmp_path, "a"), make_run(tmp_path, "b", {"a.jpg": INVENTED_DISCOUNT})
    assert run(a, b, "--json") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["candidate"]["hallucinated"] == result["baseline"]["hallucinated"] + 1
    assert "hallucinations rose" in result["reasons"]


def test_document_in_one_run_only_is_listed_and_not_counted(tmp_path, gt, capsys):
    # c.jpg is wrong in the baseline but missing from the candidate: dropping
    # it must not count as a fix, and it must be named.
    a = make_run(tmp_path, "a", {"c.jpg": WRONG_TOTAL})
    b = make_run(tmp_path, "b", files=["a.jpg", "b.jpg"])
    assert run(a, b, "--json") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["only_in_baseline"] == ["c.jpg"]
    assert result["shared_documents"] == 2
    assert result["fixes"] == []


def test_compare_writes_no_scorecard(tmp_path, gt):
    a, b = make_run(tmp_path, "a"), make_run(tmp_path, "b")
    run(a, b)
    assert not (a / "scorecard.json").exists() and not (b / "scorecard.json").exists()


def test_missing_run_folder_exits_2(tmp_path, gt):
    assert run(make_run(tmp_path, "a"), tmp_path / "nope") == 2


def test_bad_arguments_exit_2():
    with pytest.raises(SystemExit) as exc:
        compare.main(["only-one"])
    assert exc.value.code == 2
