#!/bin/bash
# 802.11 Monitor Mode Setup & Capture Script
# Usage: ./capture_setup.sh <interface> <output_name> [duration_sec] [channel]

INTERFACE=${1:-wlan0}
OUTPUT=${2:-capture}
DURATION=${3:-60}
CHANNEL=${4:-}

echo "[*] Killing interfering processes..."
sudo airmon-ng check kill 2>/dev/null

echo "[*] Enabling monitor mode on $INTERFACE..."
sudo airmon-ng start $INTERFACE

MON_IFACE="${INTERFACE}mon"
sleep 2

echo "[*] Verifying monitor mode on $MON_IFACE..."
iwconfig $MON_IFACE 2>/dev/null | grep -q "Mode:Monitor" && echo "    OK" || echo "    FAILED"

if [ -n "$CHANNEL" ]; then
    echo "[*] Setting channel to $CHANNEL..."
    sudo iw dev $MON_IFACE set channel $CHANNEL
fi

echo "[*] Starting capture (${DURATION}s) -> data/raw/${OUTPUT}.pcap"
sudo tshark -i $MON_IFACE -a duration:$DURATION -w "data/raw/${OUTPUT}.pcap" 2>&1

echo "[*] Capture complete."
echo "[*] Disabling monitor mode..."
sudo airmon-ng stop $MON_IFACE 2>/dev/null
sudo ifconfig $INTERFACE up
sudo systemctl restart NetworkManager 2>/dev/null || sudo service network-manager restart 2>/dev/null
echo "[*] Done."
