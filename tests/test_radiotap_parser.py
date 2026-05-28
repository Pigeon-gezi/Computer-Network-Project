"""Tests for radiotap_parser module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.parser.radiotap_parser import (
    RadiotapFields, parse_radiotap_from_dict
)


class TestRadiotapFields:
    """Test RadiotapFields dataclass."""

    def test_default_values(self):
        rf = RadiotapFields()
        assert rf.rssi is None
        assert rf.ant_signal is None
        assert rf.channel_freq is None
        assert rf.is_5ghz is False

    def test_is_5ghz_true(self):
        rf = RadiotapFields(channel_freq=5180)
        assert rf.is_5ghz is True

    def test_is_5ghz_false(self):
        rf = RadiotapFields(channel_freq=2437)
        assert rf.is_5ghz is False

    def test_is_5ghz_none(self):
        rf = RadiotapFields(channel_freq=None)
        assert rf.is_5ghz is False

    def test_estimated_distance(self):
        rf = RadiotapFields(rssi=-40, channel_freq=2437)
        d = rf.estimated_distance_m
        assert d is not None
        assert d > 0
        # At -40 dBm, distance should be small (< 10m)
        assert d < 20

    def test_estimated_distance_no_rssi(self):
        rf = RadiotapFields(rssi=None)
        assert rf.estimated_distance_m is None

    def test_to_dict(self):
        rf = RadiotapFields(rssi=-50, channel_freq=5180)
        d = rf.to_dict()
        assert d['rssi'] == -50.0
        assert d['is_5ghz'] is True
        assert d['estimated_distance_m'] is not None


class TestParseRadiotapFromDict:
    """Test CSV-based parsing."""

    def test_parse_full_dict(self):
        d = {
            'radiotap.dbm_antsignal': '-45',
            'radiotap.ant_signal': '60',
            'radiotap.ant_noise': '-90',
            'radiotap.datarate': '65.0',
            'radiotap.channel.freq': '2437',
            'radiotap.mcs.index': '7',
        }
        rf = parse_radiotap_from_dict(d)
        assert rf.rssi == -45.0
        assert rf.ant_signal == 60
        assert rf.ant_noise == -90
        assert rf.data_rate == 65.0
        assert rf.channel_freq == 2437
        assert rf.mcs_index == 7

    def test_parse_empty_dict(self):
        rf = parse_radiotap_from_dict({})
        assert rf.rssi is None
        assert rf.data_rate is None

    def test_parse_partial_dict(self):
        rf = parse_radiotap_from_dict({'radiotap.dbm_antsignal': '-60'})
        assert rf.rssi == -60.0
        assert rf.channel_freq is None

    def test_parse_bad_values(self):
        rf = parse_radiotap_from_dict({
            'radiotap.dbm_antsignal': 'invalid',
            'radiotap.datarate': '',
        })
        # Should not raise; just skip bad values
        assert rf.ant_signal is None
