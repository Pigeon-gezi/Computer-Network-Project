# 基于 802.11 空口帧特性的无线摄像头检测系统

本仓库是计算机网络课程大作业“基于空口帧特性识别的摄像头检测系统”的实现。系统通过外置 WiFi 网卡的 Monitor 模式被动抓取 802.11 空口帧，解析 Radiotap 与 MAC 层字段，按 MAC 地址聚合设备级流量画像，并用规则方法和机器学习方法识别疑似无线摄像头。

## 功能概览

- 空口帧采集：支持 Monitor 模式、固定信道、固定时长抓包，输出 `.pcap` 原始数据。
- 字段解析与特征提取：提取源/目的 MAC、ToDS/FromDS、RSSI、速率、信道、帧长、帧类型、QoS、重传、加密标志等字段。
- MAC 级画像：推荐使用 `device-window` 模式，以“一个 MAC 在一个时间窗口内的统计画像”为一条样本。
- 规则判定 baseline：基于上行占比、长帧比例、QoS 比例、吞吐率、突发性等规则打分，并输出混淆矩阵。
- AI 分类：支持 SVM、RandomForest 和集成模型，提供二分类摄像头检测与多分类设备识别。
- 未知场景检测：对未标注 pcap 自动枚举候选 MAC，逐个建立 MAC 画像，输出疑似摄像头 MAC 排名。
- 实验审计：提供泄露检查脚本，检查身份字段、时间字段、session 划分和单特征过强问题。

## 项目结构

```text
.
├── scripts/
│   ├── capture_monitor.sh          # Monitor mode + 信道锁定 + tshark 抓包
│   ├── label_capture.py            # 从 pcap 中辅助选择 MAC 并写入 labels.csv
│   ├── extract_features.py         # flow / device-window 特征提取
│   ├── train_model.py              # SVM/RF/Ensemble 训练
│   ├── evaluate_model.py           # AI 模型评估与图表生成
│   ├── evaluate_rules.py           # 规则 baseline 评估
│   ├── detect_unknown_pcap.py      # 未标注 pcap 的 MAC 级摄像头检测
│   └── audit_leakage.py            # 数据泄露与划分审计
├── src/
│   ├── parser/                     # pcap、Radiotap、802.11 MAC 字段解析
│   ├── features/                   # 帧级、flow 级、MAC-window 级特征
│   ├── ml/                         # Dataset、SVM、RF、规则 baseline、评估、持久化
│   └── visualization/              # 混淆矩阵、ROC/PR、特征图、PCA 等图表
├── data/
│   ├── raw/                        # 原始 pcap，默认不进 Git
│   ├── processed/                  # 特征 CSV，默认不进 Git
│   └── models/                     # 模型文件，默认不进 Git
├── report/                         # 评估图表与报告输出
├── tests/                          # 单元测试
├── VMWARE_UBUNTU_SETUP.md          # VMware + Ubuntu + 网卡抓包操作手册
└── Task_clean.md                   # 任务要求文本
```

## 环境要求

抓包必须在 Linux 环境中进行，推荐 Ubuntu 22.04 虚拟机加支持 Monitor 模式的 USB WiFi 网卡。Windows/WSL 通常不能完成真实 802.11 Monitor 抓包。

系统依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-pip git tshark aircrack-ng wireless-tools net-tools
```

Python 依赖：

```bash
pip3 install -r requirements.txt
```

详细虚拟机和网卡配置见 [VMWARE_UBUNTU_SETUP.md](VMWARE_UBUNTU_SETUP.md)。

## 推荐工作流

### 1. 抓包

示例接口名为 `wlx6c1ff790462a`，信道以实际热点信道为准：

```bash
bash scripts/capture_monitor.sh \
  -i wlx6c1ff790462a \
  -o data/raw/train/wireless_camera_001.pcap \
  -t 60 \
  -c 6
```

建议目录：

```text
data/raw/train/        干净训练 session
data/raw/test/         独立 final test session
data/raw/mixed_test/   未标注混合场景，用于演示检测
data/raw/scratch/      临时抓包
```

### 2. 标注目标 MAC

训练和测试集的 `device-window` 特征需要知道每份 pcap 的目标设备 MAC：

```bash
python3 scripts/label_capture.py \
  -p data/raw/train/wireless_camera_001.pcap \
  -d wireless_camera \
  -n "camera live view"
```

`data/labels.csv` 格式：

```csv
device_mac,device_type,session_id,notes,timestamp
aa:bb:cc:dd:ee:ff,wireless_camera,wireless_camera_001,camera live view,2026-06-18T10:00:00
11:22:33:44:55:66,tablet,tablet_001,tablet streaming,2026-06-18T10:10:00
```

`session_id` 使用文件名前缀匹配。比如 `wireless_camera_001` 会匹配 `wireless_camera_001.pcap`。

### 3. 提取 MAC-window 特征

训练集：

```bash
python3 scripts/extract_features.py \
  -d data/raw/train \
  -l data/labels.csv \
  -o data/processed/train_device_window_features.csv \
  --level device-window \
  --window 10
```

测试集：

```bash
python3 scripts/extract_features.py \
  -d data/raw/test \
  -l data/labels.csv \
  -o data/processed/test_device_window_features.csv \
  --level device-window \
  --window 10
```

`--window` 可以按实验需要调整。窗口越短样本越多，但单条画像更噪；窗口越长画像更稳定，但样本更少。

### 4. 数据审计

训练前建议检查是否存在身份泄露、时间泄露或同一 pcap 的窗口被拆到训练和测试两边：

```bash
python3 scripts/audit_leakage.py \
  -f data/processed/train_device_window_features.csv \
  --positive-label wireless_camera \
  --group-col source_file
```

重点关注：

- `device_mac`、`device_oui`、`source_file` 不应进入模型特征。
- `window_idx`、`window_start`、`camera_heuristic_score` 不应进入模型特征。
- 使用 `--group-col source_file` 时，同一个 pcap 不应同时出现在 train/test。

### 5. 训练 AI 模型

推荐训练二分类摄像头检测器，并按 pcap 文件分组划分内部验证集：

```bash
python3 scripts/train_model.py \
  -f data/processed/train_device_window_features.csv \
  -o data/models \
  --binary-camera \
  --cv 2 \
  --group-col source_file
```

实现中默认排除了身份字段、时间字段和规则分数字段，避免模型直接学习 MAC、OUI、文件名或人工规则分数。

### 6. 评估 AI 模型

独立测试集评估：

```bash
python3 scripts/evaluate_model.py \
  -f data/processed/test_device_window_features.csv \
  -m data/models \
  --binary \
  --external-test \
  -o report/final_device_window_test
```

输出包括混淆矩阵、归一化混淆矩阵、ROC 曲线、PR 曲线、PCA 图、特征重要性图和评估 JSON。

### 7. 评估规则 baseline

规则法用于满足基础任务中的“建立判决依据”，也用于与 AI 模型对比：

```bash
python3 scripts/evaluate_rules.py \
  -f data/processed/test_device_window_features.csv \
  -o report/rule_baseline_test \
  --positive-label wireless_camera \
  --threshold 5
```

规则分数依据包括：

- 发送包占比高
- 上行包占比高
- 长帧比例高
- QoS 数据帧比例高
- 包间隔相对稳定
- burst 数量较多
- 吞吐率较高

输出包括 `rule_predictions.csv`、`rules.csv`、`rule_metrics.json`、规则法混淆矩阵和归一化混淆矩阵。

### 8. 未知 pcap 现场检测

对未标注混合 pcap 自动枚举 MAC 并输出疑似摄像头。支持三种方法：

ML 模型检测：
```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  --method ml \
  -m data/models \
  --window 10 \
  --top-macs 20 \
  --min-frames 100 \
  --min-source-frames 10 \
  --camera-threshold 0.6 \
  -o data/processed/unknown_scene_detection.csv
```

规则 baseline 检测，不需要模型目录：

```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  --method rule \
  --window 10 \
  --top-macs 20 \
  --min-frames 100 \
  --min-source-frames 10 \
  --rule-threshold 5 \
  --rule-window-ratio-threshold 0.5 \
  -o data/processed/unknown_scene_rule_detection.csv
```

同时输出 ML 与规则结果：

```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  --method both \
  -m data/models \
  --window 10 \
  --top-macs 20 \
  --camera-threshold 0.6 \
  --rule-threshold 5 \
  -o data/processed/unknown_scene_both_detection.csv
```

输出字段包括：

```text
mac
total_frames
source_frames
data_source_frames
window_count
ml_camera_prob_mean / rule_score_mean
ml_camera_window_ratio / rule_camera_window_ratio
suspicious_camera
关键特征均值
```

ML 模式下，`ml_camera_prob_mean` 是该 MAC 多个窗口的平均摄像头概率；`ml_camera_window_ratio` 是被模型判为摄像头的窗口占比。规则模式下，`rule_score_mean` 是平均规则分数；`rule_camera_window_ratio` 是规则判为摄像头的窗口占比。`suspicious_camera` 会综合当前启用方法的结果，偏向候选发现而不是最终定罪。

## 关键实现说明

### 为什么采用 MAC-level device-window

任务要求“按 MAC 地址进行聚合统计，形成设备级流量画像”。因此正式实验使用 `device-window`：每一行样本对应一个目标 MAC 在一个时间窗口内的统计特征，而不是一个 flow 或一整份 pcap。

### 如何区分上下行

代码使用 802.11 MAC 头中的 `ToDS/FromDS` 字段判断方向：

```text
ToDS=1, FromDS=0  -> STA 到 AP，视为上行
ToDS=0, FromDS=1  -> AP 到 STA，视为下行
```

摄像头作为 WiFi STA 上传视频时，通常表现为持续的 STA->AP 数据帧。

### 规则法和 AI 法的关系

规则法是独立 baseline，不作为 AI 模型输入。`camera_heuristic_score`、`is_known_camera_oui` 等高风险字段已从训练特征中排除。这样可以在报告中公平比较：

```text
规则判定 baseline vs SVM vs RandomForest vs Ensemble
```

### 数据泄露控制

当前训练流程做了以下控制：

- 排除 `device_mac`、`device_oui`、`source_file`、`session_id` 等身份字段。
- 排除 `window_idx`、`window_start` 等时间/位置字段。
- 排除 `camera_heuristic_score` 和 `is_known_camera_oui`。
- 通过 `--group-col source_file` 避免同一 pcap 的多个窗口同时进入训练集和内部测试集。
- 提供 `audit_leakage.py` 检查单特征过强、身份字段和 split overlap。

### AUC 与 F1 的区别

AUC 衡量概率排序能力，F1 衡量固定决策阈值下的分类结果。因此可能出现 AUC 很高但 F1 下降的情况，说明模型排序较好，但当前阈值或决策边界不是最优。

## 数据采集建议

- 每类至少采集多个独立 pcap，尽量覆盖不同时间、位置、距离和信道条件。
- 不要让类别和环境强绑定，例如不要只在热点 A 采摄像头、只在热点 B 采非摄像头。
- 需要困难负样本：视频通话、直播推流、云盘上传、大文件上传等。
- 需要困难正样本：低码率摄像头、画面静止、不同型号摄像头、不同距离和网络环境。
- 单个 WiFi 网卡同一时刻只能监听一个信道，不能同时抓 2.4 GHz 和 5 GHz。
- 手机作为热点时，热点手机自身通过蜂窝上传云盘不经过 WiFi 空口；应让另一台设备连接热点并上传。

## 常用命令速查

```bash
# 抓包
bash scripts/capture_monitor.sh -i wlx6c1ff790462a -o data/raw/test.pcap -t 60 -c 6

# 查看 pcap 中源 MAC 排名
tshark -r data/raw/test.pcap -Y "wlan.fc.type == 2" -T fields -e wlan.sa | sort | uniq -c | sort -nr | head

# 标注
python3 scripts/label_capture.py -p data/raw/train/camera_001.pcap -d wireless_camera

# 提取 device-window 特征
python3 scripts/extract_features.py -d data/raw/train -l data/labels.csv -o data/processed/train_device_window_features.csv --level device-window --window 10

# 训练
python3 scripts/train_model.py -f data/processed/train_device_window_features.csv -o data/models --binary-camera --cv 2 --group-col source_file

# AI 评估
python3 scripts/evaluate_model.py -f data/processed/test_device_window_features.csv -m data/models --binary --external-test -o report/final_device_window_test

# 规则法评估
python3 scripts/evaluate_rules.py -f data/processed/test_device_window_features.csv -o report/rule_baseline_test --positive-label wireless_camera --threshold 5

# 未知 pcap 检测：ML
python3 scripts/detect_unknown_pcap.py -p data/raw/mixed_test/unknown_scene.pcap --method ml -m data/models --window 10 --top-macs 20 -o data/processed/unknown_scene_detection.csv

# 未知 pcap 检测：规则法
python3 scripts/detect_unknown_pcap.py -p data/raw/mixed_test/unknown_scene.pcap --method rule --window 10 --top-macs 20 --rule-threshold 5 -o data/processed/unknown_scene_rule_detection.csv
```

## 测试

```bash
python -m pytest tests/ -v
```

测试覆盖解析、特征提取、burst 检测、机器学习管线、模型评估与持久化等基础逻辑。

## Git 数据管理

`.gitignore` 默认忽略：

```text
data/raw/*
data/processed/*
data/models/*
*.pcap
*.pcapng
*.joblib
__pycache__/
*.pyc
```

大文件 pcap、特征 CSV 和训练模型建议保留在本地或云盘，不直接提交到 GitHub。

## 任务要求对应关系

| 任务要求 | 当前实现 |
| --- | --- |
| 空口帧获取 | `scripts/capture_monitor.sh`，支持 monitor mode、信道锁定、固定时长抓包 |
| 字段分析 | `src/parser/` 与 `src/features/`，解析 Radiotap 与 802.11 MAC 字段 |
| MAC 聚合画像 | `--level device-window`，按 MAC 与时间窗口聚合 |
| 规则判决 | `src/ml/rule_baseline.py` 与 `scripts/evaluate_rules.py` |
| 指标评估 | `scripts/evaluate_model.py`、`scripts/evaluate_rules.py` 输出混淆矩阵、F1、误报率、漏报率 |
| AI 扩展 | SVM、RandomForest、Ensemble 摄像头检测 |
| 现场演示 | `scripts/detect_unknown_pcap.py` 对未知 pcap 输出候选摄像头 MAC |

## 许可证

本项目为课程作业，仅供学习与实验展示使用。
