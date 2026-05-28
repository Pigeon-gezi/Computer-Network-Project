"""Tests for pcap_reader module.

Run: python -m pytest tests/test_pcap_reader.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.parser.pcap_reader import FrameInfo, PcapReader


class TestFrameInfo:
    """Test FrameInfo dataclass properties."""

    def test_ds_interpretation_ad_hoc(self):
        fi = FrameInfo(timestamp=0.0, frame_len=100, to_ds=0, from_ds=0)
        assert fi.ds_interpretation == 'ad_hoc_or_direct'

    def test_ds_interpretation_sta_to_ap(self):
        fi = FrameInfo(timestamp=0.0, frame_len=100, to_ds=1, from_ds=0)
        assert fi.ds_interpretation == 'sta_to_ap'
        assert fi.is_uplink is True

    def test_ds_interpretation_ap_to_sta(self):
        fi = FrameInfo(timestamp=0.0, frame_len=100, to_ds=0, from_ds=1)
        assert fi.ds_interpretation == 'ap_to_sta'

    def test_is_data_frame(self):
        fi_data = FrameInfo(timestamp=0.0, frame_len=100, frame_type=2)
        assert fi_data.is_data_frame is True

        fi_mgmt = FrameInfo(timestamp=0.0, frame_len=100, frame_type=0)
        assert fi_mgmt.is_data_frame is False

    def test_is_qos_data(self):
        fi_qos = FrameInfo(timestamp=0.0, frame_len=100, frame_type=2,
                           frame_subtype=0x28)
        assert fi_qos.is_qos_data is True

        fi_data = FrameInfo(timestamp=0.0, frame_len=100, frame_type=2,
                            frame_subtype=0x20)
        assert fi_data.is_qos_data is False

    def test_default_values(self):
        fi = FrameInfo(timestamp=0.0, frame_len=0)
        assert fi.rssi is None
        assert fi.frame_type is None
        assert fi.to_ds is None
        assert fi.retry == 0
        assert fi.protected == 0


class TestPcapReader:
    """Test PcapReader class."""

    def test_init_default(self):
        reader = PcapReader()
        assert reader.use_pyshark is True
        assert reader.display_filter == 'wlan'

    def test_init_custom_filter(self):
        reader = PcapReader(use_pyshark=False, display_filter='wlan.data')
        assert reader.use_pyshark is False
        assert reader.display_filter == 'wlan.data'

    def test_read_nonexistent_file(self):
        reader = PcapReader()
        with pytest.raises(Exception):
            list(reader.read_pcap('/tmp/nonexistent_xyz.pcap'))
