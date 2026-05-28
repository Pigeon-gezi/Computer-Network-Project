"""Parse radiotap headers from 802.11 frames."""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RadiotapFields:
    """Standard radiotap header fields."""
    rssi: Optional[float] = None               # dBm signal strength
    ant_signal: Optional[int] = None            # Raw signal (alternative to RSSI)
    ant_noise: Optional[int] = None             # Noise floor
    data_rate: Optional[float] = None           # PHY data rate in Mbps
    channel_freq: Optional[int] = None          # Center frequency in MHz
    channel_flags: Optional[int] = None         # Channel flags (0x00a0 = 5GHz)
    mcs_index: Optional[int] = None             # MCS index (HT/VHT)
    mcs_known: Optional[int] = None             # MCS known flags
    flags: Optional[int] = None                 # Radiotap present flags
    tsft: Optional[int] = None                  # MAC timestamp
    antenna: Optional[int] = None               # Antenna index

    @property
    def is_5ghz(self):
        """Check if frame is on 5GHz band."""
        if self.channel_freq and self.channel_freq > 4000:
            return True
        return False

    @property
    def estimated_distance_m(self):
        """Very rough distance estimate based on free-space path loss.
        Assumes TX power ~20dBm. Accuracy is low but useful for relative comparison.
        """
        if self.rssi is None:
            return None
        # Free-space path loss: FSPL = 20log10(d) + 20log10(f) - 27.55
        # Assuming f = 2437 MHz (ch 6), TX power = 20 dBm
        tx_power = 20
        freq_mhz = self.channel_freq or 2437
        fspl = tx_power - self.rssi  # approximate path loss
        if fspl <= 0:
            return 0.1
        # d = 10^((fspl - 20log10(f) + 27.55) / 20)
        import math
        d = 10 ** ((fspl - 20 * math.log10(freq_mhz) + 27.55) / 20)
        return round(d, 2)

    def to_dict(self):
        d = asdict(self)
        d['is_5ghz'] = self.is_5ghz
        d['estimated_distance_m'] = self.estimated_distance_m
        return d


def parse_radiotap(packet):
    """Extract radiotap fields from a PyShark packet.
    Returns RadiotapFields. Missing fields are None.
    """
    fields = RadiotapFields()

    if not hasattr(packet, 'radiotap'):
        return fields

    rt = packet.radiotap

    # RSSI (preferred: dbm_antsignal)
    for attr, target in [
        ('dbm_antsignal', 'rssi'),
        ('ant_signal', 'ant_signal'),
        ('ant_noise', 'ant_noise'),
        ('datarate', 'data_rate'),
        ('channel_freq', 'channel_freq'),
        ('channel_flags', 'channel_flags'),
        ('mcs_index', 'mcs_index'),
        ('mcs_known', 'mcs_known'),
        ('flags', 'flags'),
        ('tsft', 'tsft'),
        ('antenna', 'antenna'),
    ]:
        try:
            val = getattr(rt, attr)
            if target in ('rssi', 'data_rate'):
                setattr(fields, target, float(val))
            elif target in ('ant_noise',):
                setattr(fields, target, int(val) if val else None)
            else:
                setattr(fields, target, int(val) if val is not None else None)
        except (AttributeError, ValueError, TypeError):
            pass

    # If dbm_antsignal unavailable, try ant_signal as RSSI
    if fields.rssi is None and fields.ant_signal is not None:
        # Some drivers report RSSI in ant_signal; apply typical offset
        # This is heuristic and driver-dependent
        fields.rssi = float(fields.ant_signal)

    return fields


def parse_radiotap_from_dict(field_dict):
    """Construct RadiotapFields from a flat dict (e.g., tshark -T fields CSV)."""
    fields = RadiotapFields()
    mapping = {
        'radiotap.dbm_antsignal': ('rssi', float),
        'radiotap.ant_signal': ('ant_signal', int),
        'radiotap.ant_noise': ('ant_noise', int),
        'radiotap.datarate': ('data_rate', float),
        'radiotap.channel.freq': ('channel_freq', int),
        'radiotap.mcs.index': ('mcs_index', int),
    }
    for key, (attr, cast_fn) in mapping.items():
        val = field_dict.get(key)
        if val is not None and val != '':
            try:
                setattr(fields, attr, cast_fn(val))
            except (ValueError, TypeError):
                pass
    return fields
