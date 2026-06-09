#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash scripts/capture_monitor.sh -i <interface> -o <output.pcap> [-t seconds] [-c channel] [--restore]

Example:
  bash scripts/capture_monitor.sh -i wlx6c1ff790462a -o data/raw/test_capture.pcap -t 60 -c 6
  bash scripts/capture_monitor.sh -i wlx6c1ff790462a -o data/raw/test_capture.pcap -t 60 -c 6 --restore

Notes:
  - iw/ip operations use sudo.
  - tshark runs as the current user, which matches dumpcap/wireshark group setup.
EOF
}

INTERFACE=""
OUTPUT=""
DURATION="60"
CHANNEL=""
RESTORE="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interface)
            INTERFACE="${2:-}"
            shift 2
            ;;
        -o|--output)
            OUTPUT="${2:-}"
            shift 2
            ;;
        -t|--duration)
            DURATION="${2:-}"
            shift 2
            ;;
        -c|--channel)
            CHANNEL="${2:-}"
            shift 2
            ;;
        --restore)
            RESTORE="1"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 2
            ;;
    esac
done

if [[ -z "$INTERFACE" || -z "$OUTPUT" ]]; then
    usage
    exit 2
fi

if ! command -v tshark >/dev/null 2>&1; then
    echo "ERROR: tshark not found. Install it with: sudo apt install tshark" >&2
    exit 1
fi

OUT_DIR="$(dirname "$OUTPUT")"
mkdir -p "$OUT_DIR"

echo "[*] Stopping processes that may interfere with monitor mode..."
sudo airmon-ng check kill >/dev/null 2>&1 || true

echo "[*] Enabling monitor mode on $INTERFACE..."
sudo ip link set "$INTERFACE" down
sudo iw dev "$INTERFACE" set type monitor
sudo ip link set "$INTERFACE" up

if [[ -n "$CHANNEL" ]]; then
    echo "[*] Locking channel to $CHANNEL..."
    sudo iw dev "$INTERFACE" set channel "$CHANNEL"
fi

echo "[*] Capturing ${DURATION}s on $INTERFACE -> $OUTPUT"
tshark -i "$INTERFACE" -a "duration:$DURATION" -w "$OUTPUT"

echo "[*] Capture complete."
ls -lh "$OUTPUT"

if [[ "$RESTORE" == "1" ]]; then
    echo "[*] Restoring $INTERFACE to managed mode..."
    sudo ip link set "$INTERFACE" down
    sudo iw dev "$INTERFACE" set type managed
    sudo ip link set "$INTERFACE" up
    sudo systemctl restart NetworkManager || true
    echo "[*] Restore complete."
fi

