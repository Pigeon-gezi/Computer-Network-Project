"""Frame-level features extracted from individual 802.11 frames."""

import numpy as np
from ..parser.mac_frame_parser import get_oui

# Known camera manufacturer OUIs (common IP camera / spy camera vendors)
CAMERA_OUIS = {
    '00:40:48': 'Hikvision', '28:ED:E0': 'Dahua', '00:1C:10': 'Hikvision',
    '00:23:35': 'Hikvision', '00:E0:4C': 'Hikvision', '4C:11:BF': 'Dahua',
    '00:0D:C5': 'Panasonic', '00:04:DA': 'Panasonic', '00:80:F0': 'Panasonic',
    '00:01:73': 'Samsung', '00:16:6B': 'Samsung', '00:23:99': 'Samsung',
    '00:0E:8F': 'Sony', '00:01:4A': 'Sony', '08:00:46': 'Sony',
    'D8:0D:17': 'TP-Link', 'B0:95:75': 'TP-Link', '70:4F:57': 'TP-Link',
    'C0:56:27': 'Belkin', '00:22:75': 'Belkin', '94:10:3E': 'Belkin',
    '00:24:A5': 'Buffalo', '00:1D:73': 'Buffalo',
    'B8:27:EB': 'Raspberry Pi', 'DC:A6:32': 'Raspberry Pi', 'E4:5F:01': 'Raspberry Pi',
    '24:0A:C4': 'ESP32', '30:AE:A4': 'ESP32', 'A4:CF:12': 'ESP32',
}


def extract_per_frame_features(frame_info):
    """Extract features from a single FrameInfo object.

    Returns dict with feature_name -> value. Non-applicable features are 0 or NaN.
    """
    feats = {}

    # Basic frame properties
    feats['frame_len'] = frame_info.frame_len
    feats['timestamp'] = frame_info.timestamp

    # Radiotap features
    feats['rssi'] = frame_info.rssi if frame_info.rssi is not None else np.nan
    feats['data_rate'] = frame_info.data_rate if frame_info.data_rate is not None else 0.0
    feats['channel_freq'] = frame_info.channel_freq if frame_info.channel_freq is not None else 0
    feats['mcs_index'] = frame_info.mcs_index if frame_info.mcs_index is not None else -1
    feats['ant_noise'] = frame_info.ant_noise if frame_info.ant_noise is not None else np.nan

    # MAC header features
    feats['frame_type'] = frame_info.frame_type if frame_info.frame_type is not None else -1
    feats['frame_subtype'] = frame_info.frame_subtype if frame_info.frame_subtype is not None else -1
    feats['to_ds'] = frame_info.to_ds if frame_info.to_ds is not None else 0
    feats['from_ds'] = frame_info.from_ds if frame_info.from_ds is not None else 0
    feats['seq_num'] = frame_info.seq_num if frame_info.seq_num is not None else -1
    feats['duration'] = frame_info.duration if frame_info.duration is not None else 0
    feats['retry_flag'] = frame_info.retry
    feats['protected_flag'] = frame_info.protected

    # QoS
    feats['qos_priority'] = frame_info.qos_priority if frame_info.qos_priority is not None else -1

    # Boolean flags (one-hot style for ML)
    feats['is_data'] = 1 if frame_info.frame_type == 2 else 0
    feats['is_mgmt'] = 1 if frame_info.frame_type == 0 else 0
    feats['is_ctrl'] = 1 if frame_info.frame_type == 1 else 0
    feats['is_qos_data'] = 1 if frame_info.is_qos_data else 0
    feats['is_uplink'] = 1 if frame_info.is_uplink else 0
    feats['is_5ghz'] = 1 if (feats['channel_freq'] > 4000) else 0

    # OUI-based features
    oui = get_oui(frame_info.sa)
    feats['sa_oui'] = oui
    feats['is_known_camera_oui'] = 1 if oui in CAMERA_OUIS else 0
    feats['is_esp32_oui'] = 1 if oui in ('24:0A:C4', '30:AE:A4', 'A4:CF:12') else 0
    feats['is_rpi_oui'] = 1 if oui in ('B8:27:EB', 'DC:A6:32', 'E4:5F:01') else 0

    # Frame size bin (qualitative size indicator)
    if feats['frame_len'] < 100:
        feats['size_bin'] = 0  # very small (ACK, CTS, Null)
    elif feats['frame_len'] < 500:
        feats['size_bin'] = 1  # small (mgmt, control)
    elif feats['frame_len'] < 1000:
        feats['size_bin'] = 2  # medium
    else:
        feats['size_bin'] = 3  # large (video data, aggregated frames)

    return feats


def extract_frame_batch(file_reader, max_frames=None):
    """Extract per-frame features for an entire pcap.
    Returns list of dicts, one per frame.
    """
    features = []
    for i, frame_info in enumerate(file_reader):
        if max_frames and i >= max_frames:
            break
        features.append(extract_per_frame_features(frame_info))
    return features


def is_camera_like_frame(feats):
    """Heuristic: does this single frame look like it came from a camera?
    Checks: large data frame, uplink, QoS, encryption, high rate.
    """
    score = 0
    if feats.get('is_data') and feats.get('is_uplink'):
        score += 1
    if feats.get('is_qos_data'):
        score += 1
    if feats.get('protected_flag'):
        score += 1
    if feats.get('frame_len', 0) > 1000:
        score += 1
    if feats.get('data_rate', 0) > 50:
        score += 1
    return score >= 3
