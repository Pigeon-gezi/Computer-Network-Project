"""Traffic burst detection for wireless camera identification.

Based on Liu et al. "Detecting wireless spy cameras via stimulating and probing"
(MobiSys 2018): wireless camera video encoding produces periodic traffic bursts
(I-frame spikes) that are distinguishable from other device traffic patterns.
"""

import numpy as np


def detect_bursts(frames, iat_threshold_ms=1.0, min_burst_packets=3):
    """Detect traffic bursts in a sorted sequence of frame feature dicts.

    A burst = contiguous frames where inter-arrival time < iat_threshold_ms.

    Args:
        frames: list of per-frame feature dicts, sorted by timestamp.
        iat_threshold_ms: max IAT within a burst (default 1ms for MAC-layer bursts).
        min_burst_packets: minimum frames in a burst.

    Returns:
        list of burst dicts:
            {'start_idx', 'end_idx', 'packet_count', 'total_bytes',
             'duration_ms', 'start_ts', 'end_ts'}
    """
    if len(frames) < min_burst_packets:
        return []

    bursts = []
    burst_start = 0

    for i in range(1, len(frames)):
        ts_curr = frames[i].get('timestamp', 0)
        ts_prev = frames[i - 1].get('timestamp', 0)
        iat_ms = (ts_curr - ts_prev) * 1000

        if iat_ms > iat_threshold_ms:
            # End of potential burst
            burst_len = i - burst_start
            if burst_len >= min_burst_packets:
                burst_frames = frames[burst_start:i]
                bursts.append(_make_burst_dict(burst_start, i - 1, burst_frames))
            burst_start = i

    # Last burst at end of frame sequence
    final_len = len(frames) - burst_start
    if final_len >= min_burst_packets:
        burst_frames = frames[burst_start:]
        bursts.append(_make_burst_dict(burst_start, len(frames) - 1, burst_frames))

    return bursts


def _make_burst_dict(start_idx, end_idx, burst_frames):
    """Build burst info dict from frame range."""
    timestamps = [f.get('timestamp', 0) for f in burst_frames]
    sizes = [f.get('frame_len', 0) for f in burst_frames]
    return {
        'start_idx': start_idx,
        'end_idx': end_idx,
        'packet_count': len(burst_frames),
        'total_bytes': sum(sizes),
        'duration_ms': (timestamps[-1] - timestamps[0]) * 1000 if len(timestamps) > 1 else 0,
        'start_ts': timestamps[0],
        'end_ts': timestamps[-1],
    }


def compute_burst_statistics(bursts):
    """Aggregate statistics from a list of detected bursts.

    Returns dict with burst-level features.
    """
    if not bursts:
        return {
            'burst_count': 0,
            'mean_burst_packets': 0.0,
            'mean_burst_bytes': 0.0,
            'mean_burst_duration_ms': 0.0,
            'mean_burst_interval_ms': 0.0,
            'std_burst_interval_ms': 0.0,
            'burst_regularity': 0.0,  # CV of inter-burst intervals
            'bursts_per_sec': 0.0,
            'burst_density': 0.0,     # avg bytes per burst / avg interval
        }

    packet_counts = [b['packet_count'] for b in bursts]
    byte_counts = [b['total_bytes'] for b in bursts]
    durations = [b['duration_ms'] for b in bursts]

    # Inter-burst intervals
    if len(bursts) > 1:
        intervals = []
        for i in range(1, len(bursts)):
            gap = (bursts[i]['start_ts'] - bursts[i - 1]['end_ts']) * 1000  # ms
            intervals.append(max(gap, 0))
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        regularity = std_interval / max(mean_interval, 1e-9)
    else:
        intervals = []
        mean_interval = 0.0
        std_interval = 0.0
        regularity = 0.0

    # Time span for density calculation
    total_span_sec = (bursts[-1]['end_ts'] - bursts[0]['start_ts']) if bursts else 1.0

    return {
        'burst_count': len(bursts),
        'mean_burst_packets': np.mean(packet_counts),
        'std_burst_packets': np.std(packet_counts),
        'mean_burst_bytes': np.mean(byte_counts),
        'std_burst_bytes': np.std(byte_counts),
        'mean_burst_duration_ms': np.mean(durations),
        'mean_burst_interval_ms': mean_interval,
        'std_burst_interval_ms': std_interval,
        'burst_regularity': regularity,
        'bursts_per_sec': len(bursts) / max(total_span_sec, 0.001),
        'burst_density': np.mean(byte_counts) / max(mean_interval, 0.001),
    }


def detect_camera_burst_pattern(burst_stats):
    """Check if burst pattern matches wireless camera characteristics.

    Camera video encoders produce periodic I-frame bursts:
    - 30fps: ~33ms interval, large I-frames every ~0.5-2s
    - Regular burst intervals (low regularity score)
    - High burst density (large bytes per burst / short interval)

    Returns (is_camera_like, confidence_score).
    """
    score = 0
    total = 0

    # Criterion 1: Has bursts at all
    total += 1
    if burst_stats['burst_count'] >= 5:
        score += 1

    # Criterion 2: High packet count per burst (aggregated video frames)
    total += 1
    if burst_stats['mean_burst_packets'] >= 5:
        score += 1
    elif burst_stats['mean_burst_packets'] >= 3:
        score += 0.5

    # Criterion 3: Regular burst intervals (low CV)
    total += 1
    regularity = burst_stats['burst_regularity']
    if regularity < 0.3:
        score += 1
    elif regularity < 0.6:
        score += 0.5

    # Criterion 4: High burst density
    total += 1
    if burst_stats['burst_density'] > 100:
        score += 1
    elif burst_stats['burst_density'] > 50:
        score += 0.5

    # Criterion 5: Non-trivial bytes per burst (video I-frames are large)
    total += 1
    if burst_stats['mean_burst_bytes'] > 10000:
        score += 1
    elif burst_stats['mean_burst_bytes'] > 5000:
        score += 0.5

    confidence = score / total if total > 0 else 0.0
    return confidence > 0.5, confidence
