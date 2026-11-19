"""The benchmark numbers have to come from a run, not from a comment."""

from app.benchmark.runner import run_benchmark


def test_benchmark_matches_ground_truth():
    result = run_benchmark()
    assert result["project_count"] == 8
    assert result["bug_count"] == 12
    assert result["detection_rate"] == 1.0
    assert result["fix_success_rate"] == 1.0
    assert result["false_positive_count"] == 0
    assert all(project["fixed"] for project in result["projects"])
