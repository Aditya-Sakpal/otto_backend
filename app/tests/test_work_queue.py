"""Unit tests for work-queue section-count assembly (pure, no DB)."""
from types import SimpleNamespace

from app.services.work_queue_service import build_section_counts


def _group(n):
    return SimpleNamespace(items=list(range(n)))


def test_counts_sum_task_groups():
    counts = build_section_counts([_group(3), _group(2)], unresolved=[1, 2], leads=[1])
    assert counts.tasks == 5
    assert counts.unresolved_appointments == 2
    assert counts.pending_leads == 1


def test_empty_everything():
    counts = build_section_counts([], [], [])
    assert counts.tasks == 0
    assert counts.unresolved_appointments == 0
    assert counts.pending_leads == 0


def test_none_inputs_are_safe():
    counts = build_section_counts(None, None, None)
    assert counts.tasks == 0
    assert counts.unresolved_appointments == 0
    assert counts.pending_leads == 0


def test_only_tasks():
    counts = build_section_counts([_group(4)], [], [])
    assert counts.tasks == 4
    assert counts.unresolved_appointments == 0
    assert counts.pending_leads == 0


def test_only_unresolved():
    counts = build_section_counts([], [1, 2, 3], [])
    assert counts.tasks == 0
    assert counts.unresolved_appointments == 3


def test_only_leads():
    counts = build_section_counts([], [], [1, 2])
    assert counts.pending_leads == 2
    assert counts.tasks == 0
