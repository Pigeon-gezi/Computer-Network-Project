"""Read pcap/pcapng files via PyShark or tshark + return parsed frame dicts."""

import subprocess
import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FrameInfo:
    """Normalized 802.11 frame representation."""
    timestamp: float
    frame_len: int
    # Radiotap
    rssi: Optional[float] = None
    ant_signal: Optional[int] = None
    ant_noise: Optional[int] = None
    data_rate: Optional[float] = None
    channel_freq: Optional[int] = None
    mcs_index: Optional[int] = None
    # MAC header
    frame_type: Optional[int] = None       # 0=Mgmt, 1=Ctrl, 2=Data
    frame_subtype: Optional[int] = None
    to_ds: Optional[int] = None
    from_ds: Optional[int] = None
    sa: Optional[str] = None
    da: Optional[str] = None
    ta: Optional[str] = None
    ra: Optional[str] = None
    bssid: Optional[str] = None
    seq_num: Optional[int] = None
    duration: Optional[int] = None
    retry: int = 0
    protected: int = 0
    # QoS
    qos_priority: Optional[int] = None
    # Extra
    wlan_radio_signal_percent: Optional[float] = None
    raw_frame_type_str: Optional[str] = None

    @property
    def ds_interpretation(self):
        """Return address role interpretation based on ToDS/FromDS."""
        if self.to_ds == 0 and self.from_ds == 0:
            return 'ad_hoc_or_direct'
        elif self.to_ds == 1 and self.from_ds == 0:
            return 'sta_to_ap'
        elif self.to_ds == 0 and self.from_ds == 1:
            return 'ap_to_sta'
        elif self.to_ds == 1 and self.from_ds == 1:
            return 'wds'
        return 'unknown'

    @property
    def is_data_frame(self):
        return self.frame_type == 2

    @property
    def is_qos_data(self):
        return self.frame_type == 2 and self.frame_subtype == 0x28

    @property
    def is_uplink(self):
        """Camera uplink: STA -> AP = to_ds=1, from_ds=0"""
        return self.to_ds == 1 and self.from_ds == 0


class PcapReader:
    """Read 802.11 pcap files via PyShark and return FrameInfo objects."""

    def __init__(self, use_pyshark=True, display_filter=None):
        self.use_pyshark = use_pyshark
        self.display_filter = display_filter or 'wlan'

    def read_pcap(self, pcap_path):
        """Read a pcap file and yield FrameInfo objects."""
        if self.use_pyshark:
            yield from self._read_pyshark(pcap_path)
        else:
            yield from self._read_tshark_json(pcap_path)

    def _read_pyshark(self, pcap_path):
        """Parse via PyShark."""
        import pyshark
        cap = pyshark.FileCapture(pcap_path, display_filter=self.display_filter,
                                   keep_packets=False)
        try:
            for packet in cap:
                info = self._packet_to_frameinfo(packet)
                if info is not None:
                    yield info
        finally:
            cap.close()

    def _read_tshark_json(self, pcap_path):
        """Parse via tshark JSON export (fallback)."""
        cmd = ['tshark', '-r', pcap_path, '-T', 'json']
        if self.display_filter:
            cmd.extend(['-Y', self.display_filter])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"tshark failed: {result.stderr}")

        data = json.loads(result.stdout)
        for pkt_data in data:
            info = self._json_to_frameinfo(pkt_data)
            if info is not None:
                yield info

    def _packet_to_frameinfo(self, packet):
        """Convert a PyShark packet to FrameInfo."""
        try:
            ts = float(packet.sniff_timestamp)
        except (AttributeError, ValueError):
            ts = 0.0

        frame_len = int(getattr(packet, 'length', 0))

        info = FrameInfo(timestamp=ts, frame_len=frame_len)

        # Radiotap
        if hasattr(packet, 'radiotap'):
            rt = packet.radiotap
            try:
                info.rssi = int(rt.dbm_antsignal)
            except (AttributeError, ValueError):
                try:
                    info.rssi = int(rt.ant_signal)
                except (AttributeError, ValueError):
                    pass
            try:
                info.ant_signal = int(rt.ant_signal)
            except (AttributeError, ValueError):
                pass
            try:
                info.ant_noise = int(rt.ant_noise)
            except (AttributeError, ValueError):
                pass
            try:
                info.data_rate = float(rt.datarate)
            except (AttributeError, ValueError):
                pass
            try:
                info.channel_freq = int(rt.channel_freq)
            except (AttributeError, ValueError):
                pass
            try:
                info.mcs_index = int(rt.mcs_index)
            except (AttributeError, ValueError):
                pass

        # WLAN
        if hasattr(packet, 'wlan'):
            w = packet.wlan
            try:
                info.frame_type = int(w.fc_type)
            except (AttributeError, ValueError):
                pass
            try:
                info.frame_subtype = int(w.fc_type_subtype)
            except (AttributeError, ValueError):
                pass
            try:
                info.to_ds = int(w.fc_tods)
            except (AttributeError, ValueError):
                pass
            try:
                info.from_ds = int(w.fc_fromds)
            except (AttributeError, ValueError):
                pass
            try:
                info.retry = int(w.fc_retry)
            except (AttributeError, ValueError):
                pass
            try:
                info.protected = int(w.fc_protected)
            except (AttributeError, ValueError):
                pass
            try:
                info.duration = int(w.duration)
            except (AttributeError, ValueError):
                pass
            try:
                info.sa = w.sa
            except AttributeError:
                pass
            try:
                info.da = w.da
            except AttributeError:
                pass
            try:
                info.ta = w.ta
            except AttributeError:
                pass
            try:
                info.ra = w.ra
            except AttributeError:
                pass
            try:
                info.bssid = w.bssid
            except AttributeError:
                pass
            try:
                info.seq_num = int(w.seq)
            except (AttributeError, ValueError):
                pass

            # QoS
            if hasattr(w, 'qos_priority'):
                try:
                    info.qos_priority = int(w.qos_priority)
                except (AttributeError, ValueError):
                    pass

        # WLAN radio (alternative signal source)
        if hasattr(packet, 'wlan_radio') and info.rssi is None:
            try:
                info.wlan_radio_signal_percent = float(
                    packet.wlan_radio.signal_percent)
            except (AttributeError, ValueError):
                pass

        return info

    def _json_to_frameinfo(self, pkt_data):
        """Convert tshark JSON output to FrameInfo. Simplified fallback."""
        layers = pkt_data.get('_source', {}).get('layers', {})
        ts = float(layers.get('frame', {}).get('frame.time_epoch', [0])[0])
        frame_len = int(layers.get('frame', {}).get('frame.len', [0])[0])

        info = FrameInfo(timestamp=ts, frame_len=frame_len)
        # Radiotap fields are driver-specific; extract what's available
        rt = layers.get('radiotap', {})
        for key, target in [('radiotap.dbm_antsignal', 'rssi'),
                            ('radiotap.datarate', 'data_rate'),
                            ('radiotap.channel.freq', 'channel_freq')]:
            val = rt.get(key, [None])[0]
            if val is not None:
                setattr(info, target, float(val) if target != 'channel_freq' else int(float(val)))

        # WLAN fields
        w = layers.get('wlan', {})
        field_map = {
            'wlan.fc.type': 'frame_type',
            'wlan.fc.type_subtype': 'frame_subtype',
            'wlan.fc.tods': 'to_ds',
            'wlan.fc.fromds': 'from_ds',
            'wlan.sa': 'sa', 'wlan.da': 'da',
            'wlan.bssid': 'bssid',
        }
        for key, target in field_map.items():
            val = w.get(key, [None])[0]
            if val is not None:
                if target in ('frame_type', 'frame_subtype', 'to_ds', 'from_ds', 'qos_priority'):
                    setattr(info, target, int(val))
                else:
                    setattr(info, target, val)

        return info


def pcap_info(pcap_path):
    """Print summary info about a pcap file."""
    result = subprocess.run(
        ['capinfos', pcap_path], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    # Fallback to tshark
    result = subprocess.run(
        ['tshark', '-r', pcap_path, '-q', '-z', 'io,stat,0'],
        capture_output=True, text=True)
    return result.stdout
