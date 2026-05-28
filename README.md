# 802.11 MAC 层分析与设备识别

> 计算机网络 CS3611 大作业 · 题目四 · 完整 AI 方案 (25分)

## 项目简介

本项目通过 **Monitor 模式** 抓取 802.11 WiFi 帧，解析 Radiotap + MAC 头部字段，提取多层级流量特征，使用 **SVM + Random Forest 集成模型** 对无线设备进行分类识别。重点应用场景为**隐藏无线摄像头检测**。

### 技术栈

- **抓包**: tshark / aircrack-ng (Linux, Monitor 模式 WiFi 网卡)
- **解析**: PyShark + scapy
- **ML**: scikit-learn (SVM, Random Forest, VotingClassifier)
- **可视化**: matplotlib + seaborn
- **语言**: Python 3

### 参考文献

- Liu T, et al. *Detecting wireless spy cameras via stimulating and probing.* MobiSys 2018.
- Zhang X, et al. *CamLoPA: A hidden wireless camera localization framework via signal propagation path analysis.* IEEE S&P 2025.

---

## 项目架构

```
project/
├── README.md
├── requirements.txt                  # Python 依赖
├── capture_setup.sh                  # Monitor 模式 + 抓包 一键脚本
│
├── data/
│   ├── raw/                          # 原始 pcap 文件
│   ├── processed/                    # 提取的特征 CSV + 评估结果 JSON
│   ├── models/                       # 训练好的模型 (.joblib) + 元数据
│   └── labels.csv                    # 设备 MAC -> 类型 标签 (训练用)
│
├── src/                              # 核心源代码
│   ├── capture/                      # [层1] 抓包
│   │   ├── monitor_setup.py          #   WiFi 网卡检测, Monitor 模式切换, 信道锁定
│   │   └── capture_session.py        #   tshark 封装: 定时/定包/实时回调/字段批量导出
│   │
│   ├── parser/                       # [层2] 报文解析
│   │   ├── pcap_reader.py            #   PyShark / tshark JSON 双后端解析, FrameInfo 数据结构
│   │   ├── radiotap_parser.py        #   Radiotap 头: RSSI, data_rate, channel, MCS, 距离估算
│   │   └── mac_frame_parser.py       #   802.11 MAC 帧: ToDS/FromDS 地址解析, 帧类型/子类型, QoS
│   │
│   ├── features/                     # [层3] 特征工程
│   │   ├── per_frame_features.py     #   帧级特征: size, RSSI, type, flags, OUI (20+ 维)
│   │   ├── per_flow_features.py      #   流级特征: IAT 统计, 方向比, RSSI 方差, 摄像头启发式评分
│   │   ├── burst_detector.py         #   突发检测: 基于 IAT 阈值的突发识别 + 摄像头模式匹配
│   │   ├── feature_selector.py       #   特征重要性排序 (RF Gini), PCA 降维, 摄像头特征集
│   │   └── feature_extractor.py      #   总调度器: pcap → 三级特征 (帧/流/窗口) → DataFrame
│   │
│   ├── ml/                           # [层4] 机器学习
│   │   ├── dataset.py                #   数据集构建: 标准化, 标签编码, 训练/测试拆分
│   │   ├── svm_classifier.py         #   SVM: RBF/poly kernel, GridSearchCV (C, gamma)
│   │   ├── rf_classifier.py          #   RF: n_estimators, max_depth 网格搜索
│   │   ├── model_evaluator.py        #   评估: 混淆矩阵, F1/Precision/Recall, ROC AUC, 二分类检测
│   │   ├── model_persistence.py      #   模型/定标器/元数据 保存与加载 (joblib + JSON)
│   │   └── ensemble.py               #   集成: VotingClassifier soft voting, 权重优化
│   │
│   └── visualization/                # [层5] 可视化
│       ├── frame_plots.py            #   帧类型饼图, 大小/RSSI/速率分布直方图, 信道使用
│       ├── traffic_plots.py          #   吞吐量/包率时序图, 突发时间线, RSSI 时序+趋势
│       ├── feature_plots.py          #   特征相关热力图, PCA 散点图, 特征重要性条形图
│       └── result_plots.py           #   混淆矩阵 (原始+归一化), ROC 曲线, PR 曲线, 检测摘要
│
├── scripts/                          # CLI 入口脚本
│   ├── collect_training_data.py      #   引导式数据采集 (按设备类型标注)
│   ├── extract_features.py           #   特征提取 (单文件/批量, 支持 labels.csv)
│   ├── train_model.py                #   模型训练 (多分类/二分类, 自动选择最佳模型)
│   ├── run_detector.py               #   设备检测 (pcap/特征输入, 摄像头告警)
│   └── evaluate_model.py             #   完整评估 + 图表报告生成
│
└── tests/                            # 单元测试 (53 个)
    ├── test_pcap_reader.py           #   FrameInfo 数据结构 + PcapReader
    ├── test_radiotap_parser.py       #   RadiotapFields + CSV 解析
    ├── test_burst_detector.py        #   突发检测 + 摄像头模式识别
    ├── test_feature_extractor.py     #   帧级/流级特征 + 摄像头启发式
    └── test_ml_pipeline.py           #   Dataset, SVM, RF, Ensemble, 评估, 持久化
```

### 数据流

```
WiFi Monitor 模式
       │
       ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│ tshark 抓包  │───▶│ PyShark 逐帧解析  │───▶│ 三级特征提取         │
│ → .pcap 文件 │    │ Radiotap + MAC   │    │ 帧级 → 流级 → 窗口级 │
└──────────────┘    └──────────────────┘    └──────────┬──────────┘
                                                       │
                                                       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐
│ 设备类型标签     │◀───│ Ensemble 投票     │◀───│ StandardScaler│
│ camera/phone/.. │    │ SVM + RF (soft)   │    │ 特征标准化    │
└──────────────────┘    └──────────────────┘    └──────────────┘
```

---

## 特征体系

### 帧级特征 (20+ 维)

从每一帧 802.11 报文中提取:

| 特征 | 来源 | 用途 |
|------|------|------|
| `rssi` | radiotap.dbm_antsignal | 信号强度 (dBm) |
| `data_rate` | radiotap.datarate | PHY 速率 (Mbps) |
| `channel_freq` | radiotap.channel.freq | 2.4/5 GHz 判断 |
| `mcs_index` | radiotap.mcs.index | MCS 速率等级 |
| `frame_len` | frame.len | 帧大小 (视频帧 ~1400B) |
| `frame_type` | wlan.fc.type | 管理/控制/数据 |
| `frame_subtype` | wlan.fc.type_subtype | QoS Data / Beacon / ACK |
| `to_ds / from_ds` | wlan.fc | 方向 (上行/下行) |
| `seq_num` | wlan.seq | 序列号 (连续→突发) |
| `retry / protected` | wlan.fc | 重传/加密标志 |
| `qos_priority` | wlan.qos.priority | QoS 优先级 (视频=高) |
| `sa_oui` | wlan.sa 前三字节 | 厂商指纹 |

### 流级特征 (按 SA→DA 聚合)

| 类别 | 关键特征 |
|------|---------|
| **帧大小** | mean/std/min/max/median, large_frame_ratio |
| **到达间隔 (IAT)** | mean/std/cv_iat, 规律性指标 |
| **方向** | uplink_ratio (摄像头 ~0.9+) |
| **信号** | mean/std/rssi_range/rssi_trend |
| **帧类型** | data/mgmt/ctrl ratio, qos_data_ratio |
| **加密/重传** | protected_ratio, retry_ratio |
| **吞吐量** | throughput_bps, packet_count, total_bytes |

### 突发特征 (核心创新点)

基于 Liu et al. (MobiSys 2018) 的流量突发检测算法:

```
IAT < 1ms 的连续帧 → 突发
突发特征: 数量 / 平均包数 / 大小 / 间隔 / 规律性(CV) / 密度
```

摄像头典型模式: 规律突发 (~33ms 间隔), 高密度, 大 I-frame 突发

---

## 设备分类体系

| 类别 | 典型 MAC 行为 | 关键区分特征 |
|------|-------------|------------|
| `wireless_camera` | 持续 QoS Data 上行, 大帧, 规律 IAT | large_frame_ratio↑, uplink_ratio↑, burst_regularity↓, qos_data_ratio↑ |
| `smartphone` | 混合流量, Probe Request, RSSI 方差大 | mgmt_frame_ratio↑, rssi_variance↑, burst_regularity↑ |
| `laptop` | 突发流量, 高总量 | throughput↑, packet_count↑, mean_frame_size 中等 |
| `iot_sensor` | 低频小帧, 长休眠 | packet_count↓, mean_frame_size↓, burst_count↓ |
| `access_point` | Beacon 主导, Management 为主 | mgmt_frame_ratio↑↑, data_frame_ratio↓ |

---

## 使用流程

### 环境准备

```bash
# 安装系统依赖 (Ubuntu/Debian)
sudo apt install tshark aircrack-ng wireless-tools

# 安装 Python 依赖
pip install -r requirements.txt

# 验证 Monitor 模式支持
python scripts/collect_training_data.py --detect
```

### 第一步: 采集训练数据

为每种设备类型采集 5-10 分钟流量:

```bash
# 确保 WiFi 网卡处于 Monitor 模式
sudo bash capture_setup.sh wlan0

# 分别采集不同设备
python scripts/collect_training_data.py \
    -i wlan0mon -d wireless_camera -t 300 \
    -n "手机IP摄像头模式, 720p流"

python scripts/collect_training_data.py \
    -i wlan0mon -d smartphone -t 300 \
    -n "日常手机使用"

python scripts/collect_training_data.py \
    -i wlan0mon -d laptop -t 300 \
    -n "笔记本网页浏览"

# 查看已采集的会话
python scripts/collect_training_data.py --list
```

### 第二步: 特征提取

```bash
# 批量提取所有 pcap 的特征 (与标签关联)
python scripts/extract_features.py \
    -d data/raw/ \
    -l data/labels.csv \
    -o data/processed/features.csv

# 或对单个文件提取
python scripts/extract_features.py \
    -i data/raw/camera_20240101_120000.pcap \
    -o data/processed/camera_features.csv
```

### 第三步: 训练模型

```bash
# 多分类模式 (识别所有设备类型)
python scripts/train_model.py \
    -f data/processed/features.csv \
    -o data/models/

# 二分类模式 (仅检测摄像头 vs 非摄像头)
python scripts/train_model.py \
    -f data/processed/features.csv \
    -o data/models/ \
    --binary-camera
```

### 第四步: 运行检测

```bash
# 对未知 pcap 文件进行设备识别
python scripts/run_detector.py \
    -p data/raw/unknown_capture.pcap \
    -m data/models/

# 摄像头专项检测 (二分类)
python scripts/run_detector.py \
    -p data/raw/unknown_capture.pcap \
    -m data/models/ \
    --binary-detection \
    --min-confidence 0.6

# 使用预提取的特征
python scripts/run_detector.py \
    -f data/processed/unknown_features.csv \
    -m data/models/
```

### 第五步: 评估 & 报告

```bash
# 生成完整评估报告和图表
python scripts/evaluate_model.py \
    -f data/processed/features.csv \
    -m data/models/ \
    -o report/figures/ \
    --report

# 二分类评估
python scripts/evaluate_model.py \
    -f data/processed/features.csv \
    -m data/models/ \
    --binary
```

### 运行测试

```bash
python -m pytest tests/ -v                    # 全部 53 个测试
python -m pytest tests/ -v -k "burst"         # 仅突发检测相关
python -m pytest tests/ -v -k "ml"            # 仅 ML 流水线
```

---

## 注意事项

### 硬件要求

- **必须**拥有一块支持 Monitor 模式的 WiFi 网卡
- **必须**在 Linux 环境下运行 (Windows WSL2 不支持 Monitor 模式)
- 推荐网卡芯片: Atheros AR9271, Ralink RT3070, Realtek RTL8812AU, Intel AX200 (部分支持)

### 环境要求

- `tshark` 需要 root 权限才能抓包, 所有涉及抓包的命令都需要 `sudo`
- 首次使用 Wireshark/tshark 时可能需要配置: `sudo dpkg-reconfigure wireshark-common` 并允许非 root 用户抓包

### 数据采集建议

- **设备距离**: 保持目标设备距抓包网卡 2-5 米, 避免信号过强饱和
- **环境控制**: 尽量在 WiFi 干扰较小的环境采集, 关闭不必要的 WiFi 设备
- **信道固定**: 建议锁定到目标 AP 所在信道 (`-c` 参数), 避免跳频丢失帧
- **标签准确性**: 确保 `labels.csv` 中的 session_id 与 pcap 文件名前缀匹配

### 摄像头模拟方案

如果没有真实无线摄像头, 可使用以下替代方案:

1. **手机 IP 摄像头**: Android 安装 "IP Webcam" APP, iPhone 使用 "EpocCam"
2. **ESP32-CAM**: 低成本 WiFi 摄像头模块 (~30元)
3. **笔记本摄像头推流**: 使用 `ffmpeg` 将摄像头推流到本地 RTMP 服务器
4. **公开数据集**: 搜索 "802.11 wireless camera pcap dataset"

### 模型性能说明

- 数据集越大越平衡, 模型效果越好 (建议每种设备 >5 分钟流量)
- 不同环境下的 WiFi 特征可能有分布偏移, 建议在目标环境中采集训练数据
- RF 输出的特征重要性可用于报告的实验分析章节

### 常见问题

| 问题 | 解决方法 |
|------|---------|
| `tshark: No such device` | 检查网卡名: `iw dev` 或 `iwconfig` |
| `Permission denied` | 需要 `sudo` 运行 tshark 抓包命令 |
| 特征提取后 DataFrame 为空 | 检查 pcap 是否包含 802.11 帧 (非以太网帧) |
| RSSI 字段缺失 | 不同驱动报告不同 radiotap 字段, 代码已做优雅降级 |
| PyShark 导入报错 | 检查 tshark 是否正确安装: `tshark --version` |
| 训练准确率低 | 增加训练数据量, 检查设备标签是否正确, 调整 `--cv` 参数 |

---

## 评分对应

| 评分项 | 对应实现 | 分值 |
|--------|---------|------|
| Monitor 抓包 + pcap 分析 | `capture/` + `parser/` 层 | 基础 15分 |
| RSSI 分析 + 设备识别 | `features/` 流级特征 + RSSI 统计 | 进阶 +10分 |
| SVM/RF 设备分类 | `ml/` 集成模型 + GridSearchCV 调参 | AI +25分 |
| 可视化 + 报告 | `visualization/` + `scripts/evaluate_model.py` | 完整呈现 |
| 测试覆盖 | `tests/` 53 个单元测试 | 代码质量保证 |

---

## 许可证

本项目为课程作业, 仅供学习参考。
