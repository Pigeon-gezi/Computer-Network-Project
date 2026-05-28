"""Flow-level features: aggregations over frames sharing the same SA->DA pair.

A "flow" is a unidirectional stream from a specific source MAC to a
specific destination MAC, within a time window (activity timeout resets).
"""

import numpy as np
from .per_frame_features import CAMERA_OUIS, get_oui


# Timeout to split flows (seconds of inactivity = new flow)
FLOW_TIMEOUT_SEC = 5.0


def group_frames_into_flows(frame_features, timeout_sec=FLOW_TIMEOUT_SEC):
    """Group per-frame feature dicts into flows by (sa, da).

    Each frame feature dict must contain: 'sa' key (MAC string) and 'timestamp' key.
    Returns list of lists: [[frame_dict, ...], ...]
    """
    if not frame_features:
        return []

    # Map sa -> list of indices
    sa_groups = {}
    for i, feats in enumerate(frame_features):
        sa = feats.get('sa', 'unknown')
        if sa not in sa_groups:
            sa_groups[sa] = []
        sa_groups[sa].append(i)

    all_flows = []
    for sa, indices in sa_groups.items():
        # Split by da within the same SA
        da_subgroups = {}
        for idx in indices:
            da = frame_features[idx].get('da', 'unknown')
            if da not in da_subgroups:
                da_subgroups[da] = []
            da_subgroups[da].append(idx)

        for da, flow_indices in da_subgroups.items():
            flow_indices.sort(key=lambda i: frame_features[i]['timestamp'])
            # Split by timeout
            current_flow = []
            for j, idx in enumerate(flow_indices):
                if current_flow and j > 0:
                    prev_ts = frame_features[flow_indices[j - 1]]['timestamp']
                    curr_ts = frame_features[idx]['timestamp']
                    if curr_ts - prev_ts > timeout_sec:
                        all_flows.append([frame_features[i] for i in current_flow])
                        current_flow = []
                current_flow.append(idx)
            if current_flow:
                all_flows.append([frame_features[i] for i in current_flow])

    return all_flows


def extract_flow_features(flow_frames):
    """Extract aggregated features from a flow (list of per-frame feature dicts).

    Returns dict with flow-level features.
    """
    if not flow_frames:
        return {}

    feats = {}
    n = len(flow_frames)

    # Source identity
    feats['sa'] = flow_frames[0].get('sa', 'unknown')
    feats['da'] = flow_frames[0].get('da', 'unknown')
    feats['sa_oui'] = get_oui(feats['sa'])

    # Time span
    timestamps = [f['timestamp'] for f in flow_frames]
    feats['duration_sec'] = max(timestamps) - min(timestamps) if n > 1 else 0.0

    # Packet count and throughput
    feats['packet_count'] = n
    total_bytes = sum(f.get('frame_len', 0) for f in flow_frames)
    feats['total_bytes'] = total_bytes
    feats['throughput_bps'] = (total_bytes * 8) / max(feats['duration_sec'], 0.001)

    # Frame size statistics
    sizes = [f.get('frame_len', 0) for f in flow_frames]
    feats['mean_frame_size'] = np.mean(sizes)
    feats['std_frame_size'] = np.std(sizes)
    feats['min_frame_size'] = np.min(sizes)
    feats['max_frame_size'] = np.max(sizes)
    feats['median_frame_size'] = np.median(sizes)

    # Size distribution (fraction of large frames > 1000 bytes)
    large_frames = sum(1 for s in sizes if s > 1000)
    small_frames = sum(1 for s in sizes if s < 100)
    feats['large_frame_ratio'] = large_frames / n
    feats['small_frame_ratio'] = small_frames / n

    # Inter-arrival time statistics
    if n > 1:
        iats = np.diff(timestamps)
        feats['mean_iat'] = np.mean(iats) * 1000  # ms
        feats['std_iat'] = np.std(iats) * 1000
        feats['min_iat'] = np.min(iats) * 1000
        feats['max_iat'] = np.max(iats) * 1000
        feats['median_iat'] = np.median(iats) * 1000
        # Coefficient of variation = regularity metric
        feats['cv_iat'] = feats['std_iat'] / max(feats['mean_iat'], 1e-9)
    else:
        feats['mean_iat'] = feats['std_iat'] = feats['min_iat'] = feats['max_iat'] = 0.0
        feats['median_iat'] = feats['cv_iat'] = 0.0

    # Direction ratio: uplink fraction
    uplink_count = sum(1 for f in flow_frames if f.get('is_uplink', 0) == 1)
    feats['uplink_ratio'] = uplink_count / n

    # RSSI statistics
    rssi_vals = [f['rssi'] for f in flow_frames if not np.isnan(f.get('rssi', np.nan))]
    if rssi_vals:
        feats['mean_rssi'] = np.mean(rssi_vals)
        feats['std_rssi'] = np.std(rssi_vals)
        feats['min_rssi'] = np.min(rssi_vals)
        feats['max_rssi'] = np.max(rssi_vals)
        feats['rssi_range'] = feats['max_rssi'] - feats['min_rssi']
        # RSSI trend (linear regression slope)
        if len(rssi_vals) > 2:
            x = np.arange(len(rssi_vals))
            slope, _ = np.polyfit(x, rssi_vals, 1)
            feats['rssi_trend'] = slope
        else:
            feats['rssi_trend'] = 0.0
    else:
        feats['mean_rssi'] = feats['std_rssi'] = feats['min_rssi'] = feats['max_rssi'] = 0.0
        feats['rssi_range'] = feats['rssi_trend'] = 0.0

    # Frame type distribution
    data_count = sum(1 for f in flow_frames if f.get('is_data', 0) == 1)
    mgmt_count = sum(1 for f in flow_frames if f.get('is_mgmt', 0) == 1)
    ctrl_count = sum(1 for f in flow_frames if f.get('is_ctrl', 0) == 1)
    feats['data_frame_ratio'] = data_count / n
    feats['mgmt_frame_ratio'] = mgmt_count / n
    feats['ctrl_frame_ratio'] = ctrl_count / n

    # QoS
    qos_count = sum(1 for f in flow_frames if f.get('is_qos_data', 0) == 1)
    feats['qos_data_ratio'] = qos_count / n

    # Retry / Protected
    retry_count = sum(1 for f in flow_frames if f.get('retry_flag', 0) == 1)
    prot_count = sum(1 for f in flow_frames if f.get('protected_flag', 0) == 1)
    feats['retry_ratio'] = retry_count / n
    feats['protected_ratio'] = prot_count / n

    # Data rate statistics
    rates = [f.get('data_rate', 0) for f in flow_frames if f.get('data_rate', 0) > 0]
    if rates:
        feats['mean_data_rate'] = np.mean(rates)
        feats['max_data_rate'] = np.max(rates)
    else:
        feats['mean_data_rate'] = feats['max_data_rate'] = 0.0

    # Channel
    channels = [f.get('channel_freq', 0) for f in flow_frames if f.get('channel_freq', 0) > 0]
    feats['is_5ghz'] = 1 if any(c > 4000 for c in channels) else 0

    # OUI flag
    feats['is_known_camera_oui'] = 1 if feats.get('sa_oui') in CAMERA_OUIS else 0

    # Camera heuristic score
    feats['camera_heuristic_score'] = _camera_heuristic(feats)

    return feats


def _camera_heuristic(feats):
    """Compute a camera-likeness score from flow features. Range 0-10."""
    score = 0
    if feats.get('mean_frame_size', 0) > 1000:
        score += 2
    if feats.get('large_frame_ratio', 0) > 0.5:
        score += 2
    if feats.get('uplink_ratio', 0) > 0.7:
        score += 2
    if feats.get('qos_data_ratio', 0) > 0.5:
        score += 1
    if feats.get('protected_ratio', 0) > 0.5:
        score += 1
    if feats.get('cv_iat', 999) < 0.5 and feats.get('mean_iat', 0) > 0:
        score += 1
    if feats.get('mean_data_rate', 0) > 50:
        score += 1
    return score
