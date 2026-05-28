"""Tests for feature_extractor module — integration test with synthetic data."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pytest

from src.features.per_frame_features import extract_per_frame_features, is_camera_like_frame
from src.features.per_flow_features import (
    group_frames_into_flows, extract_flow_features, _camera_heuristic
)
from src.parser.pcap_reader import FrameInfo
from src.parser.mac_frame_parser import get_oui


def make_frame_info(timestamp=0.0, frame_len=1500, frame_type=2,
                    frame_subtype=0x28, to_ds=1, from_ds=0, rssi=-45,
                    sa='aa:bb:cc:dd:ee:ff', da='11:22:33:44:55:66',
                    data_rate=65.0, retry=0, protected=1,
                    qos_priority=4):
    """Create a FrameInfo with camera-like characteristics."""
    return FrameInfo(
        timestamp=timestamp, frame_len=frame_len,
        rssi=rssi, data_rate=data_rate,
        frame_type=frame_type, frame_subtype=frame_subtype,
        to_ds=to_ds, from_ds=from_ds,
        sa=sa, da=da, retry=retry, protected=protected,
        qos_priority=qos_priority,
    )


class TestPerFrameFeatures:
    """Test frame-level feature extraction."""

    def test_extract_camera_like_frame(self):
        fi = make_frame_info()
        feats = extract_per_frame_features(fi)

        assert feats['frame_len'] == 1500
        assert feats['rssi'] == -45.0
        assert feats['data_rate'] == 65.0
        assert feats['is_data'] == 1
        assert feats['is_qos_data'] == 1
        assert feats['is_uplink'] == 1
        assert feats['protected_flag'] == 1
        assert feats['size_bin'] == 3  # large

    def test_extract_mgmt_frame(self):
        fi = FrameInfo(timestamp=0.0, frame_len=200, frame_type=0,
                       frame_subtype=0x08, sa='aa:bb:cc:dd:ee:ff')
        feats = extract_per_frame_features(fi)
        assert feats['is_data'] == 0
        assert feats['is_mgmt'] == 1
        assert feats['frame_len'] == 200

    def test_is_camera_like_frame_true(self):
        feats = extract_per_frame_features(make_frame_info())
        assert is_camera_like_frame(feats) is True

    def test_is_camera_like_frame_false(self):
        fi = FrameInfo(timestamp=0.0, frame_len=50, frame_type=1,  # ACK
                       sa='aa:bb:cc:dd:ee:ff')
        feats = extract_per_frame_features(fi)
        assert is_camera_like_frame(feats) is False

    def test_sa_oui_extraction(self):
        fi = make_frame_info(sa='b8:27:eb:01:02:03')
        feats = extract_per_frame_features(fi)
        assert feats['sa_oui'] == 'B8:27:EB'
        assert feats['is_rpi_oui'] == 1

    def test_unknown_oui(self):
        fi = make_frame_info(sa='ff:ee:dd:cc:bb:aa')
        feats = extract_per_frame_features(fi)
        assert feats['is_known_camera_oui'] == 0
        assert feats['is_esp32_oui'] == 0


class TestPerFlowFeatures:
    """Test flow-level feature aggregation."""

    def test_group_frames_into_flows(self):
        # Create frames from same SA to same DA
        frames = []
        for i in range(10):
            feats = extract_per_frame_features(make_frame_info(timestamp=i * 0.01))
            feats['sa'] = 'aa:bb:cc:dd:ee:01'
            feats['da'] = '11:22:33:44:55:01'
            frames.append(feats)

        flows = group_frames_into_flows(frames, timeout_sec=5.0)
        assert len(flows) == 1
        assert len(flows[0]) == 10

    def test_group_split_by_timeout(self):
        frames = []
        # First 5: cluster within 1s
        for i in range(5):
            feats = extract_per_frame_features(make_frame_info(timestamp=i * 0.01))
            feats['sa'] = 'aa:bb:cc:dd:ee:01'
            feats['da'] = '11:22:33:44:55:01'
            frames.append(feats)
        # Gap > 5s
        for i in range(5):
            feats = extract_per_frame_features(make_frame_info(timestamp=10.0 + i * 0.01))
            feats['sa'] = 'aa:bb:cc:dd:ee:01'
            feats['da'] = '11:22:33:44:55:01'
            frames.append(feats)

        flows = group_frames_into_flows(frames, timeout_sec=5.0)
        assert len(flows) == 2

    def test_extract_flow_features_camera(self):
        frames = []
        for i in range(100):
            feats = extract_per_frame_features(
                make_frame_info(timestamp=i * 0.01, frame_len=1400))
            feats['sa'] = 'aa:bb:cc:dd:ee:01'
            feats['da'] = '11:22:33:44:55:01'
            frames.append(feats)

        flow_feats = extract_flow_features(frames)

        assert flow_feats['packet_count'] == 100
        assert flow_feats['mean_frame_size'] > 1300
        assert flow_feats['data_frame_ratio'] == 1.0
        assert flow_feats['qos_data_ratio'] == 1.0
        assert flow_feats['uplink_ratio'] == 1.0
        assert flow_feats['protected_ratio'] == 1.0
        # Camera heuristic score should be high
        assert flow_feats['camera_heuristic_score'] >= 7

    def test_camera_heuristic_high(self):
        feats = {
            'mean_frame_size': 1400,
            'large_frame_ratio': 0.9,
            'uplink_ratio': 0.95,
            'qos_data_ratio': 0.8,
            'protected_ratio': 1.0,
            'cv_iat': 0.2,
            'mean_iat': 30,
            'mean_data_rate': 65,
        }
        score = _camera_heuristic(feats)
        assert score >= 8
