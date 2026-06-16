"""Rule-based camera detector for MAC-level device-window features."""

import pandas as pd


DEFAULT_RULE_THRESHOLD = 5


RULES = [
    {
        'name': 'tx_packet_ratio_high',
        'feature': 'tx_packet_ratio',
        'op': '>=',
        'threshold': 0.6,
        'weight': 2,
        'description': 'device appears as transmitter in most frames',
    },
    {
        'name': 'uplink_packet_ratio_high',
        'feature': 'uplink_packet_ratio',
        'op': '>=',
        'threshold': 0.5,
        'weight': 2,
        'description': 'traffic is dominated by STA-to-AP uplink frames',
    },
    {
        'name': 'large_frame_ratio_high',
        'feature': 'large_frame_ratio',
        'op': '>=',
        'threshold': 0.4,
        'weight': 2,
        'description': 'many frames are large video-like data frames',
    },
    {
        'name': 'qos_data_ratio_high',
        'feature': 'qos_data_ratio',
        'op': '>=',
        'threshold': 0.4,
        'weight': 1,
        'description': 'many data frames use QoS',
    },
    {
        'name': 'iat_stable',
        'feature': 'cv_iat',
        'op': '<=',
        'threshold': 0.8,
        'weight': 1,
        'description': 'inter-arrival times are relatively stable',
        'requires_positive': 'mean_iat',
    },
    {
        'name': 'bursty_upload',
        'feature': 'burst_count',
        'op': '>=',
        'threshold': 3,
        'weight': 1,
        'description': 'window contains repeated frame bursts',
    },
    {
        'name': 'throughput_high',
        'feature': 'throughput_bps',
        'op': '>=',
        'threshold': 1_000_000,
        'weight': 1,
        'description': 'aggregate throughput exceeds 1 Mbps',
    },
]


def score_row(row, rules=None):
    """Compute an interpretable rule score for one feature row."""
    if rules is None:
        rules = RULES

    score = 0
    triggered = []
    for rule in rules:
        if _rule_matches(row, rule):
            score += rule['weight']
            triggered.append(rule['name'])
    return score, triggered


def score_dataframe(df, rules=None):
    """Return a DataFrame with rule_score and triggered_rules columns."""
    rows = []
    for _, row in df.iterrows():
        score, triggered = score_row(row, rules=rules)
        rows.append({
            'rule_score': score,
            'triggered_rules': ';'.join(triggered),
        })
    return pd.DataFrame(rows, index=df.index)


def predict_dataframe(df, threshold=DEFAULT_RULE_THRESHOLD, rules=None):
    """Return binary predictions, scores, and triggered rule names."""
    scored = score_dataframe(df, rules=rules)
    predictions = (scored['rule_score'] >= threshold).astype(int)
    return predictions, scored


def describe_rules(rules=None):
    """Return a compact human-readable rule table."""
    if rules is None:
        rules = RULES
    return pd.DataFrame(rules)


def _rule_matches(row, rule):
    if rule.get('requires_positive'):
        required_value = _value(row, rule['requires_positive'])
        if required_value <= 0:
            return False

    value = _value(row, rule['feature'])
    threshold = rule['threshold']
    if rule['op'] == '>=':
        return value >= threshold
    if rule['op'] == '<=':
        return value <= threshold
    raise ValueError(f"Unsupported rule operator: {rule['op']}")


def _value(row, feature):
    try:
        value = row.get(feature, 0)
    except AttributeError:
        value = 0
    return pd.to_numeric(pd.Series([value]), errors='coerce').fillna(0).iloc[0]
