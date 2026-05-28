"""Traffic time-series: throughput, packet rate, burst markers."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def plot_throughput_timeseries(timestamps, frame_sizes, window_sec=1.0,
                                save_path=None):
    """Plot throughput (Mbps) over time using sliding windows."""
    if len(timestamps) < 2:
        return None

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    t0 = timestamps[0]
    t_max = timestamps[-1] - t0
    n_windows = max(1, int(t_max / window_sec) + 1)
    bin_edges = np.linspace(0, n_windows * window_sec, n_windows + 1)

    # Compute throughput per window
    throughput = []
    packet_rates = []
    bin_centers = []
    for i in range(n_windows):
        t_start = i * window_sec
        t_end = (i + 1) * window_sec
        mask = (np.array(timestamps) - t0 >= t_start) & (np.array(timestamps) - t0 < t_end)
        bytes_in_window = sum(np.array(frame_sizes)[mask])
        packets_in_window = np.sum(mask)
        throughput.append(bytes_in_window * 8 / window_sec / 1e6)  # Mbps
        packet_rates.append(packets_in_window / window_sec)  # pps
        bin_centers.append(t_start + window_sec / 2)

    # Throughput subplot
    axes[0].plot(bin_centers, throughput, color='steelblue', linewidth=1)
    axes[0].fill_between(bin_centers, 0, throughput, alpha=0.2, color='steelblue')
    axes[0].set_ylabel('Throughput (Mbps)')
    axes[0].set_title('802.11 Traffic Throughput Over Time')
    axes[0].grid(True, alpha=0.3)

    # Packet rate subplot
    axes[1].plot(bin_centers, packet_rates, color='coral', linewidth=1)
    axes[1].fill_between(bin_centers, 0, packet_rates, alpha=0.2, color='coral')
    axes[1].set_ylabel('Packet Rate (pps)')
    axes[1].set_xlabel('Time (seconds)')
    axes[1].set_title('Packet Rate Over Time')
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_burst_timeline(timestamps, bursts, frame_sizes=None, save_path=None):
    """Mark detected bursts on a packet timeline."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                              gridspec_kw={'height_ratios': [3, 1]})

    t0 = timestamps[0]
    times = [t - t0 for t in timestamps]

    # Packet scatter / inter-arrival times
    if frame_sizes:
        axes[0].scatter(times, frame_sizes, s=2, alpha=0.5, c='steelblue')
        axes[0].set_ylabel('Frame Size (bytes)')
    else:
        iats = np.diff(times) * 1000
        axes[0].plot(times[1:], iats, linewidth=0.5, color='steelblue')
        axes[0].set_ylabel('Inter-Arrival Time (ms)')

    axes[0].set_title('Packet Timeline with Burst Detection')
    axes[0].grid(True, alpha=0.3)

    # Highlight bursts
    for b in bursts:
        start_t = b['start_ts'] - t0
        end_t = b['end_ts'] - t0
        axes[0].axvspan(start_t, end_t, alpha=0.3, color='red')
        axes[1].axvspan(start_t, end_t, alpha=0.5, color='red')

    # Burst indicator
    axes[1].set_ylabel('Burst')
    axes[1].set_xlabel('Time (seconds)')
    axes[1].set_ylim(0, 1)
    axes[1].set_yticks([])

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_iat_distribution_by_device(iats_by_device, save_path=None):
    """Box plot comparing inter-arrival time distributions across devices."""
    fig, ax = plt.subplots(figsize=(10, 6))
    device_names = list(iats_by_device.keys())
    data = [np.array(v) * 1000 for v in iats_by_device.values()]  # convert to ms

    bp = ax.boxplot(data, labels=device_names, patch_artist=True)
    for patch in bp['boxes']:
        patch.set_facecolor('steelblue')
        patch.set_alpha(0.6)

    ax.set_ylabel('Inter-Arrival Time (ms)')
    ax.set_title('IAT Distribution by Device')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_rssi_timeseries(timestamps, rssi_values, save_path=None):
    """Plot RSSI over time to show signal stability."""
    fig, ax = plt.subplots(figsize=(14, 5))
    t0 = timestamps[0]
    times = [t - t0 for t in timestamps]
    valid = ~np.isnan(rssi_values)
    times_v = np.array(times)[valid]
    rssi_v = np.array(rssi_values)[valid]

    ax.scatter(times_v, rssi_v, s=2, alpha=0.5, c='steelblue')
    ax.set_xlabel('Time (seconds)')
    ax.set_ylabel('RSSI (dBm)')
    ax.set_title('RSSI Over Time')
    ax.grid(True, alpha=0.3)

    # Trend line
    if len(rssi_v) > 1:
        x = np.arange(len(rssi_v))
        slope, intercept = np.polyfit(x, rssi_v, 1)
        ax.plot(times_v, slope * x + intercept, 'r-', linewidth=2,
                label=f'Trend ({slope:.3f} dBm/frame)')
        ax.legend()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig
