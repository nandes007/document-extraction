import json

from evals.calibration import calibrate, render
from tests.test_run_eval import envelope, truth


def write_run(tmp_path, records: dict[str, tuple[dict, str]]):
    """records: stem -> (API response, split). Ground truth matches VALID_DOCUMENT."""
    run_dir, gt = tmp_path / "run", tmp_path / "gt"
    (run_dir / "documents").mkdir(parents=True), gt.mkdir()
    for stem, (response, split) in records.items():
        (run_dir / "documents" / f"{stem}.json").write_text(
            json.dumps({"file": f"{stem}.jpg", "response": response}))
        (gt / f"{stem}.json").write_text(json.dumps(truth(161700) | {"split": split}))
    return run_dir, gt


def by_bucket(rows):
    return {r["bucket"]: (r["fields"], r["correct"]) for r in rows}


def test_buckets_count_present_fields_on_dev_only(tmp_path):
    wrong = envelope()
    wrong["document"] = wrong["document"] | {
        "total": {"value": 999, "status": "present", "confidence": 0.6, "evidence": "999"}}
    run_dir, gt = write_run(tmp_path, {
        "a": (envelope(), "dev"),
        "b": (wrong, "dev"),
        "c": (envelope(), "test"),  # never counted
    })
    rows = by_bucket(calibrate(run_dir, gt))
    # VALID_DOCUMENT: merchant, total, payment at 0.95; date, subtotal, service,
    # tax at 0.9; discount is absent. b's total moves to 0.5-0.7.
    assert rows[">= 0.95"] == (5, 5)
    assert rows["0.9-0.95"] == (8, 8)
    assert rows["0.5-0.7"] == (1, 0)  # b's wrong total
    assert "0.5-0.7" in render(calibrate(run_dir, gt))


def test_abstained_fields_are_restored_to_their_raw_value(tmp_path):
    response = envelope()
    response["document"] = response["document"] | {
        "total": {"value": None, "status": "unreadable", "confidence": 0.3, "evidence": None}}
    response["meta"]["abstained"] = [
        {"field": "total", "reason": ["low_confidence"], "value": 161700, "confidence": 0.3}]
    run_dir, gt = write_run(tmp_path, {"a": (response, "dev")})
    assert by_bucket(calibrate(run_dir, gt))["< 0.5"] == (1, 1)
