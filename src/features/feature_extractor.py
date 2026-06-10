"""Central feature extraction orchestrator: pcap -> per-flow feature DataFrame."""

import os
import numpy as np
import pandas as pd
from tqdm import tqdm

from .per_frame_features import extract_per_frame_features
from .per_flow_features import group_frames_into_flows, extract_flow_features
from .burst_detector import detect_bursts, compute_burst_statistics
from ..parser.pcap_reader import PcapReader


class FeatureExtractor:
    """Orchestrates full feature extraction pipeline from pcap files.

    Usage:
        extractor = FeatureExtractor(window_duration_sec=10.0)
        df = extractor.extract_from_pcap('capture.pcap')
    """

    def __init__(self, window_duration_sec=10.0, flow_timeout_sec=5.0,
                 burst_iat_threshold_ms=1.0, min_burst_packets=3,
                 show_progress=False):
        self.window_duration = window_duration_sec
        self.flow_timeout = flow_timeout_sec
        self.burst_iat_threshold = burst_iat_threshold_ms
        self.min_burst_packets = min_burst_packets
        self.show_progress = show_progress

    def extract_from_pcap(self, pcap_path, max_frames=None, show_progress=None):
        """Full pipeline: pcap file -> per-flow feature DataFrame.

        Returns DataFrame where each row is one flow (SA->DA).
        """
        progress = self.show_progress if show_progress is None else show_progress
        pcap_name = os.path.basename(pcap_path)

        # Step 1: Parse pcap -> per-frame features
        all_frames = self._read_frames(pcap_path, max_frames=max_frames,
                                       show_progress=progress,
                                       desc=f"Reading {pcap_name}")

        if not all_frames:
            return pd.DataFrame()

        # Step 2: Extract per-frame features
        frame_features = []
        frame_iter = tqdm(all_frames, desc=f"Frame features {pcap_name}",
                          unit='frame', disable=not progress)
        for fi in frame_iter:
            feats = extract_per_frame_features(fi)
            feats['sa'] = fi.sa or 'unknown'
            feats['da'] = fi.da or 'unknown'
            frame_features.append(feats)

        # Step 3: Group into flows
        flows = group_frames_into_flows(frame_features, self.flow_timeout)

        # Step 4: Extract per-flow features + burst stats
        all_flow_features = []
        flow_iter = tqdm(flows, desc=f"Flow features {pcap_name}",
                         unit='flow', disable=not progress)
        for flow_frames in flow_iter:
            flow_feats = extract_flow_features(flow_frames)

            # Sort by timestamp for burst detection
            sorted_frames = sorted(flow_frames, key=lambda f: f['timestamp'])
            bursts = detect_bursts(sorted_frames, self.burst_iat_threshold,
                                   self.min_burst_packets)
            burst_stats = compute_burst_statistics(bursts)

            combined = {**flow_feats, **burst_stats}
            all_flow_features.append(combined)

        # Step 5: Build DataFrame
        df = pd.DataFrame(all_flow_features)

        # Drop non-numeric identifier columns from feature set
        self.identifier_cols = ['sa', 'da', 'sa_oui']
        self.feature_cols = [c for c in df.columns
                             if c not in self.identifier_cols]

        return df

    def extract_from_pcap_batch(self, pcap_dir, label_map=None, max_frames=None,
                                show_progress=None):
        """Extract features from all pcap files in a directory.

        Args:
            pcap_dir: directory containing .pcap/.pcapng files
            label_map: optional dict {filename_prefix: device_label}
                       e.g. {'camera_session1': 'wireless_camera'}

        Returns DataFrame with device labels if label_map is provided.
        """
        progress = self.show_progress if show_progress is None else show_progress
        all_dfs = []
        pcap_files = [
            fname for fname in sorted(os.listdir(pcap_dir))
            if fname.endswith(('.pcap', '.pcapng'))
        ]
        file_iter = tqdm(pcap_files, desc="PCAP files", unit='file',
                         disable=not progress)
        for fname in file_iter:
            path = os.path.join(pcap_dir, fname)
            df = self.extract_from_pcap(path, max_frames=max_frames,
                                        show_progress=progress)
            if df.empty:
                continue

            # Try to match label
            if label_map:
                for prefix, label in label_map.items():
                    if fname.startswith(prefix):
                        df['device_type'] = label
                        break
                else:
                    df['device_type'] = 'unknown'
            df['source_file'] = fname
            all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()

        result = pd.concat(all_dfs, ignore_index=True)
        return result

    def get_feature_matrix(self, flow_df):
        """Extract numeric feature matrix X from flow DataFrame.
        Fills NaN, drops non-numeric columns.
        """
        numeric_cols = flow_df[self.feature_cols].select_dtypes(
            include=[np.number]).columns.tolist()
        X = flow_df[numeric_cols].copy()
        # Fill NaN with column median (or 0 if all NaN)
        X = X.fillna(X.median())
        X = X.fillna(0)
        # Replace inf
        X = X.replace([np.inf, -np.inf], 0)
        return X

    def extract_window_features(self, pcap_path, window_sec=None, show_progress=None):
        """Extract features per time window (for MAC-agnostic analysis).

        Returns DataFrame of window-level features.
        """
        progress = self.show_progress if show_progress is None else show_progress
        pcap_name = os.path.basename(pcap_path)
        if window_sec is None:
            window_sec = self.window_duration

        all_frames = self._read_frames(pcap_path, show_progress=progress,
                                       desc=f"Reading windows {pcap_name}")
        if not all_frames:
            return pd.DataFrame()

        frame_features = []
        frame_iter = tqdm(all_frames, desc=f"Window frame features {pcap_name}",
                          unit='frame', disable=not progress)
        for fi in frame_iter:
            feats = extract_per_frame_features(fi)
            feats['sa'] = fi.sa or 'unknown'
            feats['da'] = fi.da or 'unknown'
            frame_features.append(feats)

        if not frame_features:
            return pd.DataFrame()

        # Slice into windows
        t0 = frame_features[0]['timestamp']
        windows = {}
        for feats in frame_features:
            win_idx = int((feats['timestamp'] - t0) / window_sec)
            if win_idx not in windows:
                windows[win_idx] = []
            windows[win_idx].append(feats)

        window_rows = []
        window_items = sorted(windows.items())
        window_iter = tqdm(window_items, desc=f"Window features {pcap_name}",
                           unit='window', disable=not progress)
        for win_idx, win_frames in window_iter:
            row = _extract_window_features(win_frames, win_idx, t0, window_sec)
            window_rows.append(row)

        return pd.DataFrame(window_rows)

    def _read_frames(self, pcap_path, max_frames=None, show_progress=False,
                     desc="Reading frames"):
        reader = PcapReader()
        frames = []
        frame_iter = tqdm(reader.read_pcap(pcap_path), desc=desc, unit='frame',
                          disable=not show_progress)
        for i, frame in enumerate(frame_iter):
            if max_frames is not None and i >= max_frames:
                break
            frames.append(frame)
        return frames


def _extract_window_features(window_frames, win_idx, t0, window_sec):
    """Extract aggregate features for a single time window."""
    row = {'window_idx': win_idx, 'time_start': t0 + win_idx * window_sec}
    n = len(window_frames)

    # Unique sources/destinations
    sources = set(f.get('sa', 'unknown') for f in window_frames)
    dests = set(f.get('da', 'unknown') for f in window_frames)
    row['unique_sources'] = len(sources)
    row['unique_destinations'] = len(dests)

    # Traffic volume
    row['total_traffic_volume'] = sum(f.get('frame_len', 0) for f in window_frames)
    row['packet_count'] = n

    # Frame type distribution
    data_ratio = sum(1 for f in window_frames if f.get('is_data', 0) == 1) / n
    mgmt_ratio = sum(1 for f in window_frames if f.get('is_mgmt', 0) == 1) / n
    ctrl_ratio = sum(1 for f in window_frames if f.get('is_ctrl', 0) == 1) / n
    row['data_frame_ratio'] = data_ratio
    row['mgmt_frame_ratio'] = mgmt_ratio
    row['ctrl_frame_ratio'] = ctrl_ratio

    # Dominant source
    sa_counts = {}
    for f in window_frames:
        sa = f.get('sa', 'unknown')
        sa_counts[sa] = sa_counts.get(sa, 0) + 1
    if sa_counts:
        dominant_sa, dominant_count = max(sa_counts.items(), key=lambda x: x[1])
        row['dominant_source_ratio'] = dominant_count / n
        row['dominant_sa'] = dominant_sa
    else:
        row['dominant_source_ratio'] = 0
        row['dominant_sa'] = 'unknown'

    # Source entropy (diversity metric)
    total = sum(sa_counts.values())
    probs = [c / total for c in sa_counts.values()]
    entropy = -sum(p * np.log2(p) for p in probs if p > 0)
    row['source_entropy'] = entropy

    # Mean RSSI
    rssi_vals = [f.get('rssi', np.nan) for f in window_frames
                 if not np.isnan(f.get('rssi', np.nan))]
    if rssi_vals:
        row['mean_global_rssi'] = np.mean(rssi_vals)
        row['max_global_rssi'] = np.max(rssi_vals)
    else:
        row['mean_global_rssi'] = row['max_global_rssi'] = 0.0

    # Uplink ratio
    row['uplink_ratio'] = sum(1 for f in window_frames
                               if f.get('is_uplink', 0) == 1) / n

    # QoS ratio
    row['qos_ratio'] = sum(1 for f in window_frames
                            if f.get('is_qos_data', 0) == 1) / n

    return row
