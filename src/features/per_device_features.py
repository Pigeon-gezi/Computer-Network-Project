"""Device/MAC-level feature aggregation over time windows."""

import numpy as np

from .burst_detector import detect_bursts, compute_burst_statistics
from .per_frame_features import CAMERA_OUIS
from ..parser.mac_frame_parser import get_oui


def extract_device_window_features(frame_features, target_mac, window_sec=30.0,
                                   burst_iat_threshold_ms=1.0,
                                   min_burst_packets=3):
    """Aggregate frames involving target_mac into per-window device profiles."""
    target_mac = normalize_mac(target_mac)
    frames = [
        f for f in frame_features
        if normalize_mac(f.get('sa')) == target_mac
        or normalize_mac(f.get('da')) == target_mac
    ]
    if not frames:
        return []

    frames = sorted(frames, key=lambda f: f.get('timestamp', 0))
    t0 = frames[0].get('timestamp', 0)
    windows = {}
    for frame in frames:
        win_idx = int((frame.get('timestamp', t0) - t0) / window_sec)
        windows.setdefault(win_idx, []).append(frame)

    rows = []
    for win_idx, win_frames in sorted(windows.items()):
        row = extract_device_features(
            win_frames,
            target_mac,
            burst_iat_threshold_ms=burst_iat_threshold_ms,
            min_burst_packets=min_burst_packets,
        )
        if row:
            row['window_idx'] = win_idx
            row['window_start'] = t0 + win_idx * window_sec
            row['window_sec'] = window_sec
            rows.append(row)
    return rows


def extract_device_features(frames, target_mac, burst_iat_threshold_ms=1.0,
                            min_burst_packets=3):
    """Aggregate all frames involving target_mac into one device profile."""
    if not frames:
        return {}

    target_mac = normalize_mac(target_mac)
    frames = sorted(frames, key=lambda f: f.get('timestamp', 0))
    n = len(frames)

    row = {
        'device_mac': target_mac,
        'device_oui': get_oui(target_mac),
    }
    row['is_known_camera_oui'] = 1 if row['device_oui'] in CAMERA_OUIS else 0

    timestamps = np.array([f.get('timestamp', 0) for f in frames], dtype=float)
    sizes = np.array([f.get('frame_len', 0) for f in frames], dtype=float)
    duration = float(timestamps[-1] - timestamps[0]) if n > 1 else 0.0

    row['packet_count'] = n
    row['duration_sec'] = duration
    row['total_bytes'] = float(sizes.sum())
    row['throughput_bps'] = float(row['total_bytes'] * 8 / max(duration, 0.001))

    row.update(_size_stats(sizes))
    row.update(_iat_stats(timestamps))
    row.update(_direction_stats(frames, target_mac))
    row.update(_rssi_stats(frames))
    row.update(_rate_stats(frames))
    row.update(_frame_type_stats(frames))

    tx_frames = [f for f in frames if normalize_mac(f.get('sa')) == target_mac]
    burst_frames = tx_frames if tx_frames else frames
    bursts = detect_bursts(
        sorted(burst_frames, key=lambda f: f.get('timestamp', 0)),
        iat_threshold_ms=burst_iat_threshold_ms,
        min_burst_packets=min_burst_packets,
    )
    row.update(compute_burst_statistics(bursts))
    row['camera_heuristic_score'] = _device_camera_heuristic(row)

    return row


def _size_stats(sizes):
    n = len(sizes)
    return {
        'mean_frame_size': float(np.mean(sizes)),
        'std_frame_size': float(np.std(sizes)),
        'min_frame_size': float(np.min(sizes)),
        'max_frame_size': float(np.max(sizes)),
        'median_frame_size': float(np.median(sizes)),
        'large_frame_ratio': float(np.sum(sizes > 1000) / n),
        'small_frame_ratio': float(np.sum(sizes < 100) / n),
    }


def _iat_stats(timestamps):
    if len(timestamps) <= 1:
        return {
            'mean_iat': 0.0,
            'std_iat': 0.0,
            'min_iat': 0.0,
            'max_iat': 0.0,
            'median_iat': 0.0,
            'cv_iat': 0.0,
        }

    iats = np.diff(timestamps) * 1000
    mean_iat = float(np.mean(iats))
    std_iat = float(np.std(iats))
    return {
        'mean_iat': mean_iat,
        'std_iat': std_iat,
        'min_iat': float(np.min(iats)),
        'max_iat': float(np.max(iats)),
        'median_iat': float(np.median(iats)),
        'cv_iat': std_iat / max(mean_iat, 1e-9),
    }


def _direction_stats(frames, target_mac):
    n = len(frames)
    tx_frames = [
        f for f in frames if normalize_mac(f.get('sa')) == target_mac
    ]
    rx_frames = [
        f for f in frames if normalize_mac(f.get('da')) == target_mac
    ]
    tx_bytes = sum(f.get('frame_len', 0) for f in tx_frames)
    rx_bytes = sum(f.get('frame_len', 0) for f in rx_frames)
    total_bytes = tx_bytes + rx_bytes

    uplink_frames = [
        f for f in tx_frames
        if f.get('to_ds', 0) == 1 and f.get('from_ds', 0) == 0
    ]
    downlink_frames = [
        f for f in rx_frames
        if f.get('to_ds', 0) == 0 and f.get('from_ds', 0) == 1
    ]
    uplink_bytes = sum(f.get('frame_len', 0) for f in uplink_frames)
    downlink_bytes = sum(f.get('frame_len', 0) for f in downlink_frames)
    ds_bytes = uplink_bytes + downlink_bytes

    return {
        'tx_packet_count': len(tx_frames),
        'rx_packet_count': len(rx_frames),
        'tx_packet_ratio': len(tx_frames) / n,
        'rx_packet_ratio': len(rx_frames) / n,
        'tx_bytes_ratio': tx_bytes / max(total_bytes, 1),
        'rx_bytes_ratio': rx_bytes / max(total_bytes, 1),
        'uplink_packet_count': len(uplink_frames),
        'downlink_packet_count': len(downlink_frames),
        'uplink_packet_ratio': len(uplink_frames) / n,
        'downlink_packet_ratio': len(downlink_frames) / n,
        'uplink_bytes_ratio': uplink_bytes / max(ds_bytes, 1),
        'downlink_bytes_ratio': downlink_bytes / max(ds_bytes, 1),
    }


def _rssi_stats(frames):
    rssi = [
        f.get('rssi') for f in frames
        if not np.isnan(f.get('rssi', np.nan))
    ]
    if not rssi:
        return {
            'mean_rssi': 0.0,
            'std_rssi': 0.0,
            'min_rssi': 0.0,
            'max_rssi': 0.0,
            'rssi_range': 0.0,
            'rssi_trend': 0.0,
        }

    rssi = np.array(rssi, dtype=float)
    if len(rssi) > 2:
        x = np.arange(len(rssi))
        slope, _ = np.polyfit(x, rssi, 1)
    else:
        slope = 0.0
    return {
        'mean_rssi': float(np.mean(rssi)),
        'std_rssi': float(np.std(rssi)),
        'min_rssi': float(np.min(rssi)),
        'max_rssi': float(np.max(rssi)),
        'rssi_range': float(np.max(rssi) - np.min(rssi)),
        'rssi_trend': float(slope),
    }


def _rate_stats(frames):
    rates = [
        f.get('data_rate', 0) for f in frames
        if f.get('data_rate', 0) > 0
    ]
    if not rates:
        return {'mean_data_rate': 0.0, 'max_data_rate': 0.0}
    return {
        'mean_data_rate': float(np.mean(rates)),
        'max_data_rate': float(np.max(rates)),
    }


def _frame_type_stats(frames):
    n = len(frames)
    return {
        'data_frame_ratio': _ratio(frames, 'is_data', n),
        'mgmt_frame_ratio': _ratio(frames, 'is_mgmt', n),
        'ctrl_frame_ratio': _ratio(frames, 'is_ctrl', n),
        'qos_data_ratio': _ratio(frames, 'is_qos_data', n),
        'retry_ratio': _ratio(frames, 'retry_flag', n),
        'protected_ratio': _ratio(frames, 'protected_flag', n),
    }


def _ratio(frames, key, n):
    return sum(1 for f in frames if f.get(key, 0) == 1) / max(n, 1)


def _device_camera_heuristic(row):
    score = 0
    if row.get('tx_packet_ratio', 0) > 0.6:
        score += 2
    if row.get('uplink_packet_ratio', 0) > 0.5:
        score += 2
    if row.get('large_frame_ratio', 0) > 0.4:
        score += 2
    if row.get('qos_data_ratio', 0) > 0.4:
        score += 1
    if row.get('cv_iat', 999) < 0.8 and row.get('mean_iat', 0) > 0:
        score += 1
    if row.get('burst_count', 0) >= 3:
        score += 1
    if row.get('throughput_bps', 0) > 1e6:
        score += 1
    return score


def normalize_mac(value):
    if value is None:
        return ''
    return str(value).strip().lower()
