"""Parse 802.11 MAC frame headers and classify frame types."""

from dataclasses import dataclass, asdict
from typing import Optional


# 802.11 frame type/subtype constants
FRAME_TYPE_MGMT = 0
FRAME_TYPE_CTRL = 1
FRAME_TYPE_DATA = 2

FRAME_SUBTYPE = {
    # Management
    0x00: 'Association Request', 0x01: 'Association Response',
    0x02: 'Reassociation Request', 0x03: 'Reassociation Response',
    0x04: 'Probe Request', 0x05: 'Probe Response',
    0x08: 'Beacon', 0x0a: 'Disassociation',
    0x0b: 'Authentication', 0x0c: 'Deauthentication',
    0x0d: 'Action',
    # Control
    0x1b: 'RTS', 0x1c: 'CTS', 0x1d: 'ACK',
    0x1e: 'Block Ack Request', 0x1f: 'Block Ack',
    # Data
    0x20: 'Data', 0x21: 'Data+CF-Ack',
    0x22: 'Data+CF-Poll', 0x23: 'Data+CF-Ack+CF-Poll',
    0x24: 'Null', 0x25: 'CF-Ack', 0x26: 'CF-Poll',
    0x27: 'CF-Ack+CF-Poll',
    0x28: 'QoS Data', 0x29: 'QoS Data+CF-Ack',
    0x2a: 'QoS Data+CF-Poll', 0x2b: 'QoS Data+CF-Ack+CF-Poll',
    0x2c: 'QoS Null', 0x2e: 'QoS CF-Poll',
    0x2f: 'QoS CF-Ack+CF-Poll',
}


@dataclass
class MACFrameFields:
    """802.11 MAC header parsed fields."""
    frame_type: Optional[int] = None
    frame_subtype: Optional[int] = None
    frame_type_str: Optional[str] = None
    to_ds: int = 0
    from_ds: int = 0
    sa: Optional[str] = None
    da: Optional[str] = None
    ta: Optional[str] = None
    ra: Optional[str] = None
    bssid: Optional[str] = None
    seq_num: Optional[int] = None
    frag_num: Optional[int] = None
    duration: Optional[int] = None
    retry: int = 0
    protected: int = 0
    more_frag: int = 0
    power_mgmt: int = 0
    more_data: int = 0
    order: int = 0
    # QoS Control
    qos_tid: Optional[int] = None
    qos_priority: Optional[int] = None
    qos_ack_policy: Optional[int] = None
    # HT Control
    ht_present: int = 0

    @property
    def ds_mode(self):
        """Address interpretation mode based on ToDS/FromDS."""
        if self.to_ds == 0 and self.from_ds == 0:
            return 'ad_hoc'
        elif self.to_ds == 1 and self.from_ds == 0:
            return 'sta_to_ap'
        elif self.to_ds == 0 and self.from_ds == 1:
            return 'ap_to_sta'
        elif self.to_ds == 1 and self.from_ds == 1:
            return 'wds'
        return 'unknown'

    @property
    def is_uplink(self):
        return self.to_ds == 1 and self.from_ds == 0

    @property
    def is_downlink(self):
        return self.to_ds == 0 and self.from_ds == 1

    @property
    def is_mgmt(self):
        return self.frame_type == FRAME_TYPE_MGMT

    @property
    def is_ctrl(self):
        return self.frame_type == FRAME_TYPE_CTRL

    @property
    def is_data(self):
        return self.frame_type == FRAME_TYPE_DATA

    @property
    def is_qos_data(self):
        return self.frame_subtype in (0x28, 0x29, 0x2a, 0x2b)

    @property
    def source_address(self):
        """Get effective source address based on ToDS/FromDS."""
        if self.ds_mode == 'ad_hoc':
            return self.sa
        elif self.ds_mode == 'sta_to_ap':
            return self.sa
        elif self.ds_mode == 'ap_to_sta':
            return self.ta
        elif self.ds_mode == 'wds':
            return self.ta
        return self.sa

    @property
    def destination_address(self):
        """Get effective destination address based on ToDS/FromDS."""
        if self.ds_mode == 'ad_hoc':
            return self.da
        elif self.ds_mode == 'sta_to_ap':
            return self.ra or self.da
        elif self.ds_mode == 'ap_to_sta':
            return self.da
        elif self.ds_mode == 'wds':
            return self.ra
        return self.da

    def to_dict(self):
        d = asdict(self)
        d['ds_mode'] = self.ds_mode
        d['is_uplink'] = self.is_uplink
        d['is_downlink'] = self.is_downlink
        d['is_qos_data'] = self.is_qos_data
        return d


def parse_mac_frame(packet):
    """Parse 802.11 MAC header from a PyShark packet.
    Returns MACFrameFields. Missing fields are 0/None.
    """
    fields = MACFrameFields()

    if not hasattr(packet, 'wlan'):
        return fields

    w = packet.wlan

    # Frame control
    for attr, target, cast in [
        ('fc_type', 'frame_type', int),
        ('fc_type_subtype', 'frame_subtype', int),
        ('fc_tods', 'to_ds', int),
        ('fc_fromds', 'from_ds', int),
        ('fc_retry', 'retry', int),
        ('fc_protected', 'protected', int),
        ('fc_more_frag', 'more_frag', int),
        ('fc_pwrmgt', 'power_mgmt', int),
        ('fc_moredata', 'more_data', int),
        ('fc_order', 'order', int),
    ]:
        try:
            setattr(fields, target, cast(getattr(w, attr)))
        except (AttributeError, ValueError, TypeError):
            pass

    # Addresses
    for addr in ('sa', 'da', 'ta', 'ra', 'bssid'):
        try:
            setattr(fields, addr, getattr(w, addr))
        except AttributeError:
            pass

    # Sequence control
    try:
        fields.seq_num = int(w.seq)
    except (AttributeError, ValueError):
        pass
    try:
        fields.frag_num = int(w.frag)
    except (AttributeError, ValueError):
        pass

    # Duration
    try:
        fields.duration = int(w.duration)
    except (AttributeError, ValueError):
        pass

    # QoS Control (only in QoS Data frames)
    if fields.is_qos_data:
        try:
            fields.qos_tid = int(w.qos_tid)
        except (AttributeError, ValueError):
            pass
        try:
            fields.qos_priority = int(w.qos_priority)
        except (AttributeError, ValueError):
            pass
        try:
            fields.qos_ack_policy = int(w.qos_ack_policy)
        except (AttributeError, ValueError):
            pass

    # String name
    if fields.frame_subtype is not None:
        fields.frame_type_str = FRAME_SUBTYPE.get(fields.frame_subtype, 'Unknown')
    elif fields.frame_type is not None:
        type_names = {0: 'Management', 1: 'Control', 2: 'Data'}
        fields.frame_type_str = type_names.get(fields.frame_type, 'Unknown')

    return fields


def parse_mac_frame_from_dict(field_dict):
    """Construct MACFrameFields from a flat dict (tshark -T fields CSV)."""
    fields = MACFrameFields()
    mapping = {
        'wlan.fc.type': ('frame_type', int),
        'wlan.fc.type_subtype': ('frame_subtype', int),
        'wlan.fc.tods': ('to_ds', int),
        'wlan.fc.fromds': ('from_ds', int),
        'wlan.fc.retry': ('retry', int),
        'wlan.fc.protected': ('protected', int),
        'wlan.sa': ('sa', str), 'wlan.da': ('da', str),
        'wlan.ta': ('ta', str), 'wlan.ra': ('ra', str),
        'wlan.bssid': ('bssid', str),
        'wlan.seq': ('seq_num', int),
        'wlan.duration': ('duration', int),
        'wlan.qos.tid': ('qos_tid', int),
        'wlan.qos.priority': ('qos_priority', int),
    }
    for key, (attr, cast_fn) in mapping.items():
        val = field_dict.get(key)
        if val is not None and val != '':
            try:
                setattr(fields, attr, cast_fn(val))
            except (ValueError, TypeError):
                pass

    if fields.frame_subtype is not None:
        fields.frame_type_str = FRAME_SUBTYPE.get(fields.frame_subtype, 'Unknown')

    return fields


def get_oui(mac_address):
    """Extract OUI (first 3 bytes) from a MAC address string."""
    if not mac_address:
        return None
    parts = mac_address.replace('-', ':').split(':')
    if len(parts) >= 3:
        return ':'.join(parts[:3]).upper()
    return None
