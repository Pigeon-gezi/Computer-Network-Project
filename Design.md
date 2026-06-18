# 系统设计

## 整体架构

系统采用“采集层 -> 解析层 -> 特征层 -> 模型层 -> 输出层”的分层设计。原始输入是 Monitor 模式下抓取的 802.11 pcap，解析层将不同来源的 Radiotap/MAC 字段统一为结构化帧对象；特征层同时提供 frame、flow 和 device-window 三个粒度，其中最终主线是以目标 MAC 为中心的 10 秒设备窗口；模型层包含可解释规则基线与 SVM/RF 集成检测器；输出层生成可疑 MAC 排名、指标表和可视化图。

```text
Monitor / tshark / pcap
        -> Radiotap / 802.11 MAC / FrameInfo
        -> frame / flow / device-window features
        -> rules / SVM / RF / soft voting
        -> MAC ranking / suspicious camera
        -> CSV / JSON / figures / report
```

主要代码目录与职责如下：`src/capture/` 负责网卡与抓包封装，`src/parser/` 负责 Radiotap/MAC 字段解析，`src/features/` 负责三层特征与突发检测，`src/ml/` 负责规则、SVM、RF、集成和模型持久化，`src/visualization/` 负责混淆矩阵、ROC/PR、PCA、特征重要性等图表。脚本入口集中在 `scripts/`，典型流程为 `collect/extract/train/evaluate/detect`。

## 协议/算法设计

无线摄像头的可识别性来自持续视频上传行为：相对长时间的 STA 到 AP 上行、较高大帧比例、较稳定的帧间隔、QoS Data 帧、规律突发以及较高吞吐量。系统不依赖 IP 负载内容，而是只使用 802.11 空口侧可观察到的 MAC 层与物理层统计特征。

| 来源 | 字段/特征 | 作用 |
| --- | --- | --- |
| Radiotap | RSSI、data rate、channel、MCS | 反映信号强度、物理层速率和信道环境 |
| 802.11 MAC | SA/DA/TA/RA/BSSID、ToDS/FromDS | 判断有效源/目的地址、STA->AP 上行与 AP->STA 下行 |
| Frame | frame length、type/subtype、QoS、retry、protected | 区分数据/管理/控制帧，识别 QoS Data 与大帧 |
| Time series | IAT、burst count、burst density、throughput | 描述连续上传、突发规律性和传输强度 |

规则基线采用加权分数：

$$
score(x)=2\mathbb{I}(tx\_packet\_ratio\ge0.6)
+2\mathbb{I}(uplink\_packet\_ratio\ge0.5)
+2\mathbb{I}(large\_frame\_ratio\ge0.4)
+\mathbb{I}(qos\_data\_ratio\ge0.4)
+\mathbb{I}(cv\_iat\le0.8)
+\mathbb{I}(burst\_count\ge3)
+\mathbb{I}(throughput\_bps\ge10^6)
$$

默认阈值为 5 分。前三项权重最高，因为它们分别对应“设备主要在发包”“主要是 STA 到 AP 上行”“大帧比例高”，是视频上传流最核心的证据；QoS、IAT 稳定、突发和吞吐量作为辅助证据。

AI 检测器以数值特征矩阵为输入，先删除 `device_mac`、`device_oui`、`source_file`、`session_id`、窗口编号和启发式分数等高风险字段，避免模型记住设备身份；随后使用 `StandardScaler` 标准化，分别训练 SVM 和 Random Forest，最后用 soft voting 融合两个模型的概率。

未知 pcap 检测时，脚本先枚举 MAC，再对每个候选 MAC 提取 10 秒设备窗口特征。当前检测入口支持 `ml`、`rule`、`both` 三种模式：ML 模式汇总 `ml_camera_prob_mean` 和 `ml_camera_window_ratio`；规则模式汇总 `rule_score_mean`、`rule_score_max` 和 `rule_camera_window_ratio`；最终总判定字段为 `suspicious_camera`。
