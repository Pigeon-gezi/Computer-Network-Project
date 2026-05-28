"""Frame-level visualization: type distribution, size histogram, RSSI distribution."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend


def plot_frame_type_distribution(frame_types, subtype_names=None, save_path=None):
    """Pie chart of frame types (Management/Control/Data)."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Main types
    type_counts = {0: 0, 1: 0, 2: 0}
    for ft in frame_types:
        if ft in type_counts:
            type_counts[ft] += 1

    labels = ['Management (0)', 'Control (1)', 'Data (2)']
    sizes = [type_counts[0], type_counts[1], type_counts[2]]
    colors = ['#ff9999', '#66b3ff', '#99ff99']

    axes[0].pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                startangle=90)
    axes[0].set_title('802.11 Frame Type Distribution')

    # Size histogram by type
    axes[1].set_title('Frame Size Distribution')
    axes[1].set_xlabel('Frame Size (bytes)')
    axes[1].set_ylabel('Count')

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_rssi_distribution(rssi_values, labels=None, save_path=None):
    """Histogram/KDE of RSSI distribution, optionally grouped by device type."""
    fig, ax = plt.subplots(figsize=(10, 6))

    if labels is not None:
        for label in set(labels):
            mask = np.array(labels) == label
            ax.hist(np.array(rssi_values)[mask], bins=30, alpha=0.5,
                    label=str(label), density=True)
        ax.legend()
    else:
        ax.hist(rssi_values, bins=40, color='steelblue', edgecolor='white',
                density=True)

    ax.set_xlabel('RSSI (dBm)')
    ax.set_ylabel('Density')
    ax.set_title('RSSI Distribution')
    ax.axvline(x=-50, color='green', linestyle='--', alpha=0.5, label='Strong')
    ax.axvline(x=-70, color='orange', linestyle='--', alpha=0.5, label='Medium')
    ax.axvline(x=-85, color='red', linestyle='--', alpha=0.5, label='Weak')

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_frame_size_histogram(frame_sizes, by_type=None, save_path=None):
    """Histogram of frame sizes, optionally split by type."""
    fig, ax = plt.subplots(figsize=(10, 6))

    if by_type is not None:
        for type_val in sorted(set(by_type)):
            mask = np.array(by_type) == type_val
            type_name = {0: 'Management', 1: 'Control', 2: 'Data'}.get(type_val, str(type_val))
            ax.hist(np.array(frame_sizes)[mask], bins=50, alpha=0.5,
                    label=type_name)
        ax.legend()
    else:
        ax.hist(frame_sizes, bins=60, color='steelblue', edgecolor='white')

    ax.set_xlabel('Frame Size (bytes)')
    ax.set_ylabel('Count')
    ax.set_title('802.11 Frame Size Distribution')

    # Mark typical ranges
    ax.axvspan(0, 100, alpha=0.1, color='gray', label='ACK/CTS/Null')
    ax.axvspan(1000, 1550, alpha=0.1, color='green', label='Video Data')

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_data_rate_distribution(data_rates, save_path=None):
    """Histogram of PHY data rates."""
    fig, ax = plt.subplots(figsize=(10, 5))
    rates = [r for r in data_rates if r > 0]
    ax.hist(rates, bins=50, color='teal', edgecolor='white')
    ax.set_xlabel('Data Rate (Mbps)')
    ax.set_ylabel('Count')
    ax.set_title('PHY Data Rate Distribution')
    ax.axvline(x=np.mean(rates) if rates else 0, color='red', linestyle='--',
               label=f'Mean: {np.mean(rates):.1f} Mbps' if rates else '')
    if rates:
        ax.legend()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig


def plot_channel_usage(channel_freqs, save_path=None):
    """Bar chart of WiFi channel usage."""
    fig, ax = plt.subplots(figsize=(12, 5))
    from collections import Counter
    counts = Counter(ch for ch in channel_freqs if ch > 0)
    channels = sorted(counts.keys())
    values = [counts[ch] for ch in channels]
    bars = ax.bar(range(len(channels)), values, color='steelblue')
    ax.set_xticks(range(len(channels)))
    ax.set_xticklabels([str(ch) for ch in channels], rotation=45)
    ax.set_xlabel('Channel Frequency (MHz)')
    ax.set_ylabel('Frame Count')
    ax.set_title('WiFi Channel Usage')
    # Color 5GHz differently
    for i, ch in enumerate(channels):
        if ch > 4000:
            bars[i].set_color('orange')
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig
