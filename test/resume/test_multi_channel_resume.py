"""Multi-channel resume helpers and cursor parity tests.

These tests cover the per-channel common-resume-plane logic that keeps
multi-channel sequential stacks resuming at whole plane-pair boundaries.
"""

from __future__ import annotations

from lightsheet.resume import ResumeManifest
from lightsheet.resume.probe import _common_resume_plane


def _manifest(cursors: dict[str, dict[str, int]]) -> ResumeManifest:
    return ResumeManifest(
        uuid="test-uuid",
        state="in_progress",
        n_planes=10,
        stack_starting_plane=0.0,
        stack_ending_plane=90.0,
        stack_step=10.0,
        save_mode="stitch",
        wavelengths=[555, 640],
        multi_channel=True,
        created_at="2026-09-08T00:00:00+00:00",
        cursors=cursors,
    )


def test_common_resume_plane_uses_minimum_channel_count() -> None:
    """The common resume plane is the minimum per-channel safe count."""
    manifest = _manifest({"hdf5": {"ch0": 4, "ch1": 4}})
    probes = {"hdf5": {"ch0": 4, "ch1": 4}}
    common, torn_tail = _common_resume_plane(manifest, probes)
    assert common == 4
    assert torn_tail is False


def test_common_resume_plane_detects_torn_tail() -> None:
    """A channel ahead of the common signals a torn final plane-pair."""
    manifest = _manifest({"hdf5": {"ch0": 5, "ch1": 4}})
    probes = {"hdf5": {"ch0": 5, "ch1": 4}}
    common, torn_tail = _common_resume_plane(manifest, probes)
    assert common == 4
    assert torn_tail is True


def test_common_resume_plane_respects_observed_count() -> None:
    """The safe count per channel is the minimum of cursor and observed."""
    manifest = _manifest({"hdf5": {"ch0": 5, "ch1": 4}})
    probes = {"hdf5": {"ch0": 3, "ch1": 3}}
    common, torn_tail = _common_resume_plane(manifest, probes)
    assert common == 3
    assert torn_tail is False


def test_common_resume_plane_across_hdf5_and_zarr() -> None:
    """The common plane is the minimum across all formats and channels."""
    manifest = _manifest(
        {
            "hdf5": {"ch0": 5, "ch1": 4},
            "zarr": {"store": 3},
        }
    )
    probes = {
        "hdf5": {"ch0": 5, "ch1": 4},
        "zarr": {"store": 3},
    }
    common, torn_tail = _common_resume_plane(manifest, probes)
    assert common == 3
    assert torn_tail is True


def test_common_resume_plane_no_cursors_returns_zero() -> None:
    """A fresh manifest with no cursors resumes from plane zero."""
    manifest = _manifest({})
    common, torn_tail = _common_resume_plane(manifest, {})
    assert common == 0
    assert torn_tail is False
