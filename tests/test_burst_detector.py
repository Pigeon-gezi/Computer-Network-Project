"""Tests for burst_detector module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.features.burst_detector import (
    detect_bursts, compute_burst_statistics, detect_camera_burst_pattern
)


def make_frames(timestamps, sizes=None):
    """Helper: create list of frame-like dicts from timestamps."""
    if sizes is None:
        sizes = [1500] * len(timestamps)
    return [{'timestamp': ts, 'frame_len': sz}
            for ts, sz in zip(timestamps, sizes)]


class TestDetectBursts:
    """Test burst detection algorithm."""

    def test_no_frames(self):
        bursts = detect_bursts([], iat_threshold_ms=1.0)
        assert bursts == []

    def test_too_few_frames(self):
        frames = make_frames([0.0, 0.001])
        bursts = detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3)
        assert bursts == []

    def test_single_burst(self):
        # Tight cluster = one burst
        timestamps = [0.0, 0.0005, 0.0010, 0.0015, 0.0020]
        frames = make_frames(timestamps, [1000, 1200, 1100, 1300, 1400])
        bursts = detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3)
        assert len(bursts) == 1
        assert bursts[0]['packet_count'] == 5
        assert bursts[0]['total_bytes'] == 6000
        assert bursts[0]['start_idx'] == 0
        assert bursts[0]['end_idx'] == 4

    def test_two_bursts_separated(self):
        # Two clusters with gap > 1ms
        timestamps = [
            0.0, 0.0005, 0.0010,  # burst 1
            0.100, 0.1005, 0.1010,  # burst 2
        ]
        frames = make_frames(timestamps)
        bursts = detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3)
        assert len(bursts) == 2
        assert bursts[0]['packet_count'] == 3
        assert bursts[1]['packet_count'] == 3

    def test_no_burst_when_spread_out(self):
        # All frames far apart
        timestamps = [0.0, 0.01, 0.02, 0.03, 0.04]  # 10ms IAT > 1ms threshold
        frames = make_frames(timestamps)
        bursts = detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3)
        assert bursts == []

    def test_burst_at_end(self):
        timestamps = [
            0.100, 0.200,  # gap (no burst)
            0.300, 0.3003, 0.3006, 0.3009,  # burst at end
        ]
        frames = make_frames(timestamps)
        bursts = detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3)
        assert len(bursts) == 1
        assert bursts[0]['start_idx'] == 2
        assert bursts[0]['end_idx'] == 5


class TestBurstStatistics:
    """Test burst statistics aggregation."""

    def test_empty_bursts(self):
        stats = compute_burst_statistics([])
        assert stats['burst_count'] == 0
        assert stats['mean_burst_packets'] == 0.0
        assert stats['mean_burst_bytes'] == 0.0
        assert stats['burst_regularity'] == 0.0

    def test_single_burst(self):
        bursts = [{
            'start_idx': 0, 'end_idx': 4, 'packet_count': 5,
            'total_bytes': 6000, 'duration_ms': 2.0,
            'start_ts': 0.0, 'end_ts': 0.002,
        }]
        stats = compute_burst_statistics(bursts)
        assert stats['burst_count'] == 1
        assert stats['mean_burst_packets'] == 5.0
        assert stats['mean_burst_bytes'] == 6000.0
        assert stats['mean_burst_interval_ms'] == 0.0  # only one burst

    def test_multiple_bursts_regular(self):
        bursts = [
            {'start_idx': 0, 'end_idx': 4, 'packet_count': 5,
             'total_bytes': 7000, 'duration_ms': 2.0,
             'start_ts': 0.0, 'end_ts': 0.002},
            {'start_idx': 5, 'end_idx': 9, 'packet_count': 5,
             'total_bytes': 7000, 'duration_ms': 2.0,
             'start_ts': 0.033, 'end_ts': 0.035},
            {'start_idx': 10, 'end_idx': 14, 'packet_count': 5,
             'total_bytes': 7000, 'duration_ms': 2.0,
             'start_ts': 0.066, 'end_ts': 0.068},
        ]
        stats = compute_burst_statistics(bursts)
        assert stats['burst_count'] == 3
        # Regular intervals -> low regularity score
        assert stats['burst_regularity'] < 0.1
        assert stats['bursts_per_sec'] > 0


class TestCameraBurstPattern:
    """Test camera-specific burst pattern detection."""

    def test_camera_like_pattern(self):
        stats = {
            'burst_count': 30,
            'mean_burst_packets': 8.0,
            'mean_burst_bytes': 12000.0,
            'burst_regularity': 0.1,
            'burst_density': 150.0,
        }
        is_camera, confidence = detect_camera_burst_pattern(stats)
        assert is_camera is True
        assert confidence > 0.8

    def test_non_camera_pattern(self):
        stats = {
            'burst_count': 2,
            'mean_burst_packets': 2.0,
            'mean_burst_bytes': 500.0,
            'burst_regularity': 0.9,
            'burst_density': 5.0,
        }
        is_camera, confidence = detect_camera_burst_pattern(stats)
        assert is_camera is False
        assert confidence < 0.5

    def test_edge_case_low_confidence(self):
        stats = {
            'burst_count': 5,
            'mean_burst_packets': 3.0,
            'mean_burst_bytes': 5000.0,
            'burst_regularity': 0.3,
            'burst_density': 50.0,
        }
        is_camera, confidence = detect_camera_burst_pattern(stats)
        # Borderline case — confidence should be in moderate range
        assert 0.35 <= confidence <= 0.65
