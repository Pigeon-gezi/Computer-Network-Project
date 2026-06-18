# 展演代码问答材料

本文整理展演时可能被问到的代码层面问题。回答时建议先讲任务目标，再落到具体脚本或模块。

## 项目整体

### Q1：这个系统完整流程是什么？

A：流程是：外置 WiFi 网卡进入 Monitor 模式，在固定信道抓取 802.11 空口帧，保存为 pcap；之后用 tshark/PyShark 解析 Radiotap 和 MAC 层字段；再按 MAC 地址和时间窗口聚合成设备画像；最后分别用规则法和机器学习模型判断是否为摄像头。现场演示时可以直接输入一份未知 pcap，输出候选摄像头 MAC。

### Q2：主要代码入口有哪些？

A：

- `scripts/capture_monitor.sh`：抓包。
- `scripts/label_capture.py`：辅助标注 pcap 中的目标 MAC。
- `scripts/extract_features.py`：提取 flow 或 device-window 特征。
- `scripts/train_model.py`：训练 SVM、RandomForest 和集成模型。
- `scripts/evaluate_model.py`：评估 AI 模型。
- `scripts/evaluate_rules.py`：评估规则 baseline。
- `scripts/detect_unknown_pcap.py`：对未标注 pcap 枚举 MAC 并检测疑似摄像头。

### Q3：为什么正式实验使用 `device-window`，不是 flow？

A：任务要求是“按 MAC 地址聚合统计，形成设备级流量画像”。flow 只描述一段 SA->DA 流，容易把同一设备拆成很多局部片段；`device-window` 则表示“某个 MAC 在一个时间窗口内的整体行为”，更符合摄像头检测任务，也更适合输出可疑 MAC。

## 抓包与 802.11 解析

### Q4：为什么必须用 Linux 和 Monitor 模式？

A：普通网卡 managed 模式只能看到本机收发的网络包，不能被动监听周围 802.11 空口帧。Monitor 模式可以抓到指定信道上的 802.11 帧和 Radiotap 信息。Windows/WSL 通常无法稳定支持 USB WiFi 网卡的 Monitor 模式，因此使用 Ubuntu 虚拟机。

### Q5：怎么确定抓包信道？

A：先在 managed 模式下扫描目标热点：

```bash
iwlist wlx6c1ff790462a scan | grep -A 12 'ESSID:"热点名"'
```

看到 `Channel` 或 DS Parameter Set 后，抓包时用 `-c` 锁定该信道。锁错信道会导致抓不到目标设备的数据帧。

### Q6：能不能同时抓 2.4 GHz 和 5 GHz？

A：单个 WiFi 网卡同一时刻只能监听一个信道，不能同时抓 2.4 GHz 和 5 GHz。要么固定一个信道采集，要么使用两个网卡分别锁定两个信道。轮询信道会漏包，不适合分析连续视频流。

### Q7：如何判断上行和下行？

A：看 802.11 MAC 头的 `ToDS/FromDS`：

```text
ToDS=1, FromDS=0  -> STA 到 AP，上行
ToDS=0, FromDS=1  -> AP 到 STA，下行
```

无线摄像头上传视频时通常表现为持续 STA->AP 数据帧。

## 特征工程

### Q8：提取了哪些关键特征？

A：主要包括帧长统计、长帧比例、包间隔 IAT、上下行比例、发送/接收比例、RSSI、物理层速率、QoS 数据帧比例、加密/重传比例、吞吐率、burst 数量和 burst 密度等。

### Q9：为什么摄像头会有可识别特征？

A：无线摄像头通常持续上传视频流，因此相对普通终端更容易出现大帧比例高、上行占比高、吞吐率稳定、QoS 数据帧多、包间隔较连续和突发模式较稳定等特征。

### Q10：为什么不能直接把 MAC 或 OUI 喂给模型？

A：这样会变成设备身份识别，而不是摄像头行为识别。例如训练集中某个 MAC 永远是摄像头，模型可能只记住这个 MAC。当前 `Dataset.prepare()` 默认排除了 `device_mac`、`device_oui`、`source_file`、`session_id` 等字段。

### Q11：为什么排除 `camera_heuristic_score`？

A：它是人工规则分数，本身已经包含摄像头判断逻辑。如果把它喂给 ML 模型，模型可能只是学习规则分数，而不是学习原始统计特征。因此规则分数只作为 baseline 独立评估，不作为 AI 模型输入。

## 规则 baseline

### Q12：规则法是怎么判定的？

A：规则法在 `src/ml/rule_baseline.py` 中实现。它按特征触发加权得分，例如发送包占比高 +2、上行包占比高 +2、长帧比例高 +2、QoS 比例高 +1、IAT 稳定 +1、burst 多 +1、吞吐率高 +1。总分达到阈值，默认 `5`，就判为摄像头。

### Q13：规则法和 ML 的关系是什么？

A：规则法是基础任务要求的可解释判决依据，ML 是扩展方法。两者独立评估，用相同测试集输出混淆矩阵、F1、误报率和漏报率，便于对比。

### Q14：规则阈值为什么是 5？

A：这是一个保守的经验阈值，要求至少满足多个强摄像头特征，而不是单一特征触发。若误报多可以提高到 6，若漏报多可以降低到 4。展演中可以说明阈值可通过验证集调优。

## 机器学习

### Q15：训练了哪些模型？

A：主要训练 SVM、RandomForest，并构建 soft-voting 集成模型。二分类模式下目标是 `wireless_camera` vs `non_wireless_camera`，多分类模式也支持区分手机、平板、摄像头等类别。

### Q16：为什么要使用 `--group-col source_file`？

A：一个 pcap 会产生多个时间窗口。如果随机按行切分，同一份 pcap 的相邻窗口可能同时进入训练和测试，造成 session 泄露。`--group-col source_file` 保证同一 pcap 只出现在训练或测试一边。

### Q17：为什么还要做分层分组划分？

A：普通 group split 只能保证文件不重叠，不能保证类别比例。当前实现用近似分层分组方法，让 train/test 的类别比例更接近整体分布，同时保持 pcap 不交叉。

### Q18：为什么有时 F1 下降但 AUC 还是 1.00？

A：AUC 衡量概率排序能力，F1 衡量固定阈值下的分类结果。如果所有正样本概率都高于负样本，AUC 可以是 1；但默认阈值或模型 hard prediction 仍可能让少数样本分错，导致 F1 下降。

### Q19：为什么模型分数经常满分？是否有泄露？

A：早期确实发现过风险，包括时间字段、规则分数和 row-level split。现在已经排除高风险字段并使用分组划分。如果仍满分，更可能是当前数据集太干净、设备和场景太少、摄像头与非摄像头行为差异过大。需要通过新设备、跨环境和困难负样本验证泛化。

## 未知 pcap 检测

### Q20：`detect_unknown_pcap.py` 和 `run_detector.py` 有什么区别？

A：`run_detector.py` 是旧的通用预测脚本，主要对已有 feature CSV 或 flow-level pcap 做分类。`detect_unknown_pcap.py` 是现场演示脚本，不需要 labels.csv，会自动枚举 pcap 中的 MAC，逐个提取 device-window 特征，并按 MAC 聚合输出疑似摄像头。它支持 `--method ml`、`--method rule` 和 `--method both`，可以只跑 ML、只跑规则 baseline，或同时输出两者。

### Q21：未知检测时为什么要先筛选 top MAC？

A：复杂环境中 pcap 可能出现很多 AP、广播、路由器和低频设备。逐个 MAC 做 window 特征提取会很慢。`--top-macs`、`--min-frames`、`--min-source-frames` 用于先过滤掉几乎无关的 MAC。

### Q22：`min-frames` 和 `min-source-frames` 是什么？

A：`min-frames` 是该 MAC 在 pcap 的任意地址字段中出现的最低帧数；`min-source-frames` 是该 MAC 作为 `wlan.sa` 出现的最低次数。后者接近“主动发送”过滤，但严格上行还要看 `ToDS/FromDS`，真正上行比例在 device-window 特征里计算。

### Q23：ML 模式为什么用平均概率或窗口占比两个条件？

A：未知检测是在 MAC 级别做候选发现。`ml_camera_prob_mean` 表示整体概率强度，`ml_camera_window_ratio` 表示多个窗口预测的一致性。两者用 OR 是偏召回的策略，避免漏掉持续被判为摄像头但概率校准偏低的 MAC。若要更严格，可以提高阈值或改为 AND。

### Q24：未知 pcap 能不能不用 ML，只用规则法检测？

A：可以。`detect_unknown_pcap.py --method rule` 会跳过模型加载，只枚举 MAC、提取 device-window 特征，然后调用规则 baseline 打分。输出包含 `rule_score_mean`、`rule_score_max`、`rule_camera_window_ratio`、`rule_common_triggers` 和 `rule_suspicious_camera`，适合展示基础任务中的规则判定逻辑。

## 数据与实验设计

### Q25：是否必须所有数据来自同一个 WiFi 环境？

A：不必须。任务要求在不同环境下评估鲁棒性。但不能让类别和环境绑定，例如所有摄像头都来自热点 A、所有非摄像头都来自热点 B。更好的设计是每个环境都采摄像头和非摄像头。

### Q26：什么是困难负样本？

A：会表现出类似摄像头上行行为的非摄像头设备，例如手机视频通话、直播推流、云盘上传、笔记本上传大文件。这些样本能检验模型是否只是识别“大上行流”，而不是摄像头。

### Q27：作为热点的手机自己上传云盘能当 WiFi 上行样本吗？

A：不能很好地作为 WiFi 上行样本。热点手机自己用蜂窝网络上传不经过 WiFi 空口。应该让另一台设备连接该热点并上传云盘，这样空口中才有 STA->AP 的 WiFi 上行帧。

### Q28：为什么 pcap 很多帧，特征样本却很少？

A：`device-window` 是按时间窗口聚合的。例如 60 秒 pcap、10 秒窗口，单个目标 MAC 最多大约生成 6 条样本。帧数多说明每个窗口里统计更稳定，不等于样本行数多。

## 代码质量与可解释性

### Q29：如何证明没有明显数据泄露？

A：使用 `scripts/audit_leakage.py` 检查模型实际使用的特征列、身份字段是否进入模型、同一 `source_file` 是否跨 train/test、单特征 AUC 是否异常接近 1。训练代码默认排除高风险列，并支持分组划分。

### Q30：如何看模型关注了哪些特征？

A：`evaluate_model.py` 会输出 RandomForest 重要性 Top 10，并单独列出摄像头领域特征的 rank。报告中的 `feature_importance.png` 可用于说明模型主要依赖哪些统计特征。

### Q31：规则法的混淆矩阵在哪里？

A：运行 `scripts/evaluate_rules.py` 后，在输出目录中生成：

```text
rule_confusion_matrix.png
rule_confusion_matrix_norm.png
rule_metrics.json
rule_predictions.csv
```

### Q32：如果现场检测误报怎么办？

A：可以提高 `--camera-threshold`、提高 `--window-ratio-threshold`、提高候选 MAC 的 `--min-frames`，或者在训练集中加入更多困难负样本。展演时应说明该系统输出的是“候选可疑 MAC”，最终可结合规则指标和人工确认。

### Q33：如果现场检测漏报怎么办？

A：先确认是否锁定正确 WiFi 信道、目标设备是否连接该热点、抓包时长是否足够、候选 MAC 是否被 `min-frames` 过滤。必要时降低 `--min-frames`、`--min-source-frames` 或 `--camera-threshold`。

### Q34：这个项目最大的局限是什么？

A：最大的局限是泛化依赖数据覆盖。不同摄像头型号、码率、网络环境、距离和非摄像头上行行为都可能改变特征分布。因此实验报告应同时给出当前数据集结果和对未见设备/困难负样本的讨论。

## 展演建议回答模板

### 如果被问“你们到底识别的是摄像头还是大流量上传？”

A：基础特征确实围绕上行视频流，包括长帧、持续上行、QoS 和突发规律，所以困难负样本如视频会议和文件上传很关键。我们通过规则 baseline、AI 模型、未见设备测试和困难负样本来区分“摄像头类持续视频上传”与普通大流量上传。当前系统输出的是可疑 MAC 候选，而不是法律意义上的确定判断。

### 如果被问“为什么不用 IP/TCP/应用层？”

A：任务要求是空口帧和 802.11 MAC 层分析。Monitor 模式下即使数据帧加密，也能看到 Radiotap 和 MAC 层统计信息，例如帧长、方向、速率、RSSI、时间间隔和 QoS 标志。本项目正是利用这些不解密也可获得的侧信道特征。

### 如果被问“现场怎么演示？”

A：先让摄像头和普通终端连接同一热点，确认信道；用 `capture_monitor.sh` 抓 60 秒 pcap；然后运行 `detect_unknown_pcap.py`，脚本会列出 pcap 中候选 MAC、每个 MAC 的摄像头概率和可疑标记；最后把输出 MAC 与摄像头真实 MAC 对比。
