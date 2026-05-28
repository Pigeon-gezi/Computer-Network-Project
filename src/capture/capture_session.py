"""tshark capture wrapper supporting timed, count-based, and live modes."""

import subprocess
import os
import signal
import threading


class CaptureSession:
    """Manages a tshark 802.11 monitor-mode capture session."""

    def __init__(self, interface, output_dir='data/raw/'):
        self.interface = interface
        self.output_dir = output_dir
        self._process = None
        self._stop_event = threading.Event()

    def capture_duration(self, duration_sec, output_name, channel=None,
                         display_filter=None):
        """Capture for a fixed duration in seconds."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f"{output_name}.pcap")

        cmd = ['tshark', '-i', self.interface,
               '-a', f'duration:{duration_sec}',
               '-w', output_path]

        if display_filter:
            cmd.extend(['-Y', display_filter])

        # Channel locking via iw if specified
        if channel is not None:
            from .monitor_setup import set_channel
            set_channel(self.interface, channel)

        subprocess.run(cmd, check=True)
        return output_path

    def capture_packet_count(self, count, output_name, display_filter=None):
        """Capture a fixed number of packets."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f"{output_name}.pcap")

        cmd = ['tshark', '-i', self.interface,
               '-c', str(count),
               '-w', output_path]

        if display_filter:
            cmd.extend(['-Y', display_filter])

        subprocess.run(cmd, check=True)
        return output_path

    def start_background_capture(self, output_name, display_filter=None):
        """Start capture in background. Use stop_capture() to end."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, f"{output_name}.pcap")

        cmd = ['tshark', '-i', self.interface, '-w', output_path]
        if display_filter:
            cmd.extend(['-Y', display_filter])

        self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        return output_path

    def stop_capture(self):
        """Stop a background capture gracefully."""
        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGINT)
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

    def capture_live(self, callback, display_filter=None, packet_count=None):
        """Capture with a Python callback per packet via PyShark.
        callback(packet) is called for each captured packet.
        Set packet_count to limit, or None for indefinite.
        """
        import pyshark

        cap = pyshark.LiveCapture(interface=self.interface,
                                   display_filter=display_filter)
        count = 0
        for packet in cap.sniff_continuously():
            if self._stop_event.is_set():
                break
            callback(packet)
            count += 1
            if packet_count and count >= packet_count:
                break

    def capture_live_async(self, callback, display_filter=None):
        """Start live capture in a background thread."""
        self._stop_event.clear()
        thread = threading.Thread(
            target=self.capture_live,
            args=(callback, display_filter),
            daemon=True
        )
        thread.start()
        return thread

    def stop_live(self):
        """Signal live capture to stop."""
        self._stop_event.set()

    def export_fields_csv(self, pcap_path, fields, output_csv=None):
        """Fast bulk export of specified fields from pcap to CSV via tshark.
        fields: list of tshark field names, e.g. ['radiotap.dbm_antsignal', 'wlan.sa']
        """
        if output_csv is None:
            output_csv = pcap_path.replace('.pcap', '') + '_fields.csv'

        field_args = []
        for f in fields:
            field_args.extend(['-e', f])

        cmd = ['tshark', '-r', pcap_path, '-T', 'fields',
               '-E', 'header=y', '-E', 'separator=,',
               '-E', 'quote=d', '-E', 'occurrence=f',
               *field_args]

        with open(output_csv, 'w') as f:
            subprocess.run(cmd, stdout=f, check=True)

        return output_csv
