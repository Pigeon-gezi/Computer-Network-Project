# VMware + Ubuntu 网络抓包环境配置手册

本文用于从零配置一个 Ubuntu 虚拟机，用来运行本仓库的 802.11 空口帧抓包、特征提取和摄像头检测代码。

当前 USB WiFi 网卡接口名：

```text
wlx6c1ff790462a
```

## 1. 虚拟机建议配置

推荐配置：

```text
VMware: Workstation Pro / Player
Ubuntu: 22.04 LTS Desktop
Disk: 30 GB
Memory: 4-8 GB
CPU: 2-4 cores
Network Adapter: NAT
USB Controller: USB 3.0 / USB 3.1
Installation: Minimal installation
```

安装 Ubuntu 时：

```text
Use Active Directory: 不勾选
Location Services: 关闭
Download updates while installing Ubuntu: 可不勾选
Install third-party software: 可勾选
```

用户名建议使用小写英文或数字，例如：

```text
username: cnlab
```

密码需要记住，后续运行 `sudo` 命令会频繁使用。

## 2. 安装系统依赖

进入 Ubuntu 后打开终端：

```bash
sudo apt update
sudo apt install -y python3 python3-pip git tshark aircrack-ng wireless-tools net-tools
```

安装 `tshark` 时如果提示：

```text
Should non-superusers be able to capture packets?
```

可以选择 `Yes`。不过本实验抓 802.11 空口帧时通常仍建议使用 `sudo`。

## 3. 将 USB WiFi 网卡连接到虚拟机

在 VMware 中连接 USB 网卡：

```text
VM > Removable Devices > USB WiFi 网卡 > Connect
```

如果是 VMware Player，入口可能是：

```text
Player > Removable Devices > USB WiFi 网卡 > Connect
```

也可以点击 VMware 窗口右下角的 USB 图标连接设备。

连接后，在 Ubuntu 中检查：

```bash
lsusb
iw dev
iwconfig
```

如果看到 `wlx6c1ff790462a`，说明 USB 网卡已进入虚拟机。

## 4. 测试 Monitor Mode

先关闭可能干扰 monitor mode 的进程：

```bash
sudo airmon-ng check kill
```

第一次运行时可能看到类似：

```text
Failed to stop avahi-daemon, please stop it on your own.
Killing these processes:
    PID Name
    809 wpa_supplicant
   3129 avahi-daemon
```

这通常不是严重错误。再次运行没有输出，通常表示干扰进程已经被处理。

由于当前接口名 `wlx6c1ff790462a` 已经很长，不建议依赖 `airmon-ng` 自动创建 `xxxmon` 接口名。更稳妥的方式是直接把当前接口切换为 monitor 类型：

```bash
sudo ip link set wlx6c1ff790462a down
sudo iw dev wlx6c1ff790462a set type monitor
sudo ip link set wlx6c1ff790462a up
iwconfig
```

如果 `iwconfig` 输出中看到：

```text
wlx6c1ff790462a  Mode:Monitor
```

说明 monitor mode 成功。

锁定信道，例如信道 6：

```bash
sudo iw dev wlx6c1ff790462a set channel 6
```

## 5. 手动抓包测试

在项目根目录运行：

```bash
mkdir -p data/raw
sudo tshark -i wlx6c1ff790462a -a duration:60 -w data/raw/test_capture.pcap
```

检查是否生成文件：

```bash
ls -lh data/raw/test_capture.pcap
```

如果文件大小明显大于 0，说明抓包成功。

## 6. 使用一键抓包脚本

当前环境中，`tshark` 已配置为普通用户可抓包。因此推荐使用本仓库的封装脚本：

```bash
bash scripts/capture_monitor.sh \
  -i wlx6c1ff790462a \
  -o data/raw/test_capture.pcap \
  -t 60 \
  -c 6
```

这个脚本会自动完成：

```text
1. 停止干扰 monitor mode 的进程
2. 将 wlx6c1ff790462a 切换到 monitor mode
3. 锁定信道
4. 使用普通用户运行 tshark 抓包
5. 输出 pcap 文件大小
```

如果希望抓包结束后自动恢复 managed 模式和 NetworkManager：

```bash
bash scripts/capture_monitor.sh \
  -i wlx6c1ff790462a \
  -o data/raw/test_capture.pcap \
  -t 60 \
  -c 6 \
  --restore
```

## 7. 使用项目 Python 脚本抓包

项目中的 Python 采集逻辑会优先使用 `iw` 将网卡切到 monitor mode，适合当前这种长接口名：

```bash
python3 scripts/collect_training_data.py --detect
```

采集一段标注为摄像头的数据：

```bash
sudo python3 scripts/collect_training_data.py \
  -i wlx6c1ff790462a \
  -d wireless_camera \
  -t 60 \
  -c 6 \
  -n "test wireless camera capture"
```

注意：`capture_setup.sh` 会默认拼接 `mon` 后缀，当前接口名较长时可能不稳定。因此当前机器上优先使用 `collect_training_data.py` 或手动 `tshark` 抓包。

## 8. 安装 Python 依赖并提取特征

进入项目目录后：

```bash
pip3 install -r requirements.txt
```

### 特征级别选择

当前特征提取支持两种级别：

```text
flow           默认模式；每条样本是一个 SA -> DA flow
device-window  推荐正式实验使用；每条样本是目标 MAC 在一个时间窗口内的设备画像
```

课程任务强调“按 MAC 地址聚合统计，形成设备级流量画像”。因此正式训练和报告建议优先使用：

```text
--level device-window
```

flow 模式仍适合调试、对比和快速检查。

### labels.csv 要求

`device-window` 模式必须依赖真实设备 MAC。`data/labels.csv` 格式：

```csv
device_mac,device_type,session_id,notes,timestamp
aa:bb:cc:dd:ee:ff,wireless_camera,wireless_camera_001,camera live view,2026-06-15T10:00:00
11:22:33:44:55:66,tablet,tablet_001,tablet streaming,2026-06-15T10:10:00
```

`session_id` 仍支持前缀匹配，例如：

```text
tablet_ -> tablet_001.pcap, tablet_002.pcap, ...
```

但在 `device-window` 模式下，`device_mac` 不能是 `unknown`，否则脚本无法知道应该聚合哪个 MAC，会跳过对应 pcap。

### 推荐数据目录

建议把正式数据和临时数据分开：

```text
data/raw/train/        干净单目标训练 session
data/raw/test/         独立 final test session
data/raw/mixed_test/   混合设备演示场景
data/raw/scratch/      临时抓包，不进训练
```

临时测试包、信道检查包、未确认标签的 pcap 不要放进 `train/`。

### 推荐：MAC 窗口级特征

训练集：

```bash
python3 scripts/extract_features.py \
  -d data/raw/train \
  -l data/labels.csv \
  -o data/processed/train_device_window_features.csv \
  --level device-window \
  --window 30
```

测试集：

```bash
python3 scripts/extract_features.py \
  -d data/raw/test \
  -l data/labels.csv \
  -o data/processed/test_device_window_features.csv \
  --level device-window \
  --window 30
```

窗口长度建议：

```text
--window 30  默认推荐；单条设备画像更稳定
--window 15  样本更多，但每条画像更短、更噪
```

`device-window` 内部会按 `labels.csv` 中的 `device_mac` 聚合：

```text
sa == device_mac 或 da == device_mac
```

并输出目标设备在窗口内的上下行比例、帧长、IAT、RSSI、突发等 MAC 画像特征。

该模式会优先使用普通用户权限运行：

```text
tshark -T fields
```

并在 tshark 阶段用目标 MAC 做过滤，因此通常比 PyShark 逐包读取更快。这里不使用 `sudo`，需要确保前面已经完成普通用户 `tshark/dumpcap` 权限配置。

### flow 模式仍可用

flow 模式每条样本是一个单向 flow，适合调试和对比：

```bash
python3 scripts/extract_features.py \
  -d data/raw/train \
  -l data/labels.csv \
  -o data/processed/train_flow_features.csv \
  --level flow \
  --mac-filter endpoint
```

flow 模式下 `--mac-filter` 可选：

```text
none         不过滤，旧行为
source       只保留 sa == device_mac，适合可疑上传源分析
destination  只保留 da == device_mac
endpoint     保留 sa == device_mac 或 da == device_mac，适合设备相关 flow 对比
```

推荐：

```text
flow 训练对比：--mac-filter endpoint
可疑上传源分析：--mac-filter source
device-window 模式：不需要 --mac-filter
```

如果同时指定：

```bash
--level device-window --mac-filter endpoint
```

不会破坏结果，但 `--mac-filter` 不参与 `device-window` 逻辑，容易造成误解。`device-window` 总是按 `device_mac` 做设备级聚合。

### 单文件调试

对单个 pcap 做 flow 特征提取：

```bash
python3 scripts/extract_features.py \
  -i data/raw/test_capture.pcap \
  -o data/processed/test_features.csv
```

### 训练数据占比检查

训练前建议检查类别、session 和 MAC 占比，避免某个设备或某个 pcap 贡献过多样本：

```bash
python3 - <<'PY'
import pandas as pd

df = pd.read_csv('data/processed/train_device_window_features.csv')

print('\n[device_type]')
print(df['device_type'].value_counts())
print((df['device_type'].value_counts(normalize=True) * 100).round(2).astype(str) + '%')

if 'source_file' in df.columns:
    print('\n[source_file, device_type]')
    print(df.groupby(['source_file', 'device_type']).size().sort_values(ascending=False))

mac_col = 'device_mac' if 'device_mac' in df.columns else 'sa'
if mac_col in df.columns:
    print(f'\n[{mac_col}]')
    print(df[mac_col].value_counts())
    print((df[mac_col].value_counts(normalize=True) * 100).round(2).astype(str) + '%')
PY
```

如果某个 MAC 或某个 `source_file` 占比过高，模型可能更容易学习该 session 的环境特征，而不是设备类别特征。正式实验建议让每类有多个 session，并尽量避免单个 session 占主导。

## 9. 标注采集样本

抓包完成后，可以用脚本自动统计 pcap 中的数据帧源 MAC，并追加标签到 `data/labels.csv`：

```bash
python3 scripts/label_capture.py \
  -p data/raw/wireless_camera_001.pcap \
  -d wireless_camera \
  -n "phone hotspot camera live view"
```

脚本会列出候选源 MAC，例如：

```text
  1. aa:bb:cc:dd:ee:ff    30000 frames
  2. 11:22:33:44:55:66     8000 frames
```

输入序号即可写入：

```text
data/labels.csv
```

如果已经知道目标 MAC：

```bash
python3 scripts/label_capture.py \
  -p data/raw/wireless_camera_001.pcap \
  -d wireless_camera \
  -m aa:bb:cc:dd:ee:ff \
  -n "known camera mac"
```

如果确认候选第一名就是目标设备，可以自动选择第一名：

```bash
python3 scripts/label_capture.py \
  -p data/raw/wireless_camera_001.pcap \
  -d wireless_camera \
  -y \
  -n "auto select top source mac"
```

默认 `session_id` 会使用 pcap 文件名去掉扩展名。例如：

```text
data/raw/wireless_camera_001.pcap -> session_id = wireless_camera_001
```

## 10. 训练、评估和未知场景检测

推荐训练二分类摄像头检测模型：

```bash
python3 scripts/train_model.py \
  -f data/processed/train_device_window_features.csv \
  -o data/models \
  --binary-camera \
  --cv 2 \
  --group-col source_file
```

此时 `train_model.py` 内部会从训练集里再切出一部分作为 validation / internal test。`--group-col source_file` 表示按 pcap 文件分组划分，避免同一份 pcap 的多个时间窗口同时进入训练集和内部测试集。

使用独立测试集做最终评估：

```bash
python3 scripts/evaluate_model.py \
  -f data/processed/test_device_window_features.csv \
  -m data/models \
  --binary \
  --external-test \
  -o report/final_device_window_test
```

`--external-test` 表示整份输入 CSV 都是 final held-out test，不再随机切分。

### 未知 pcap 检测模式

正式演示时更常见的输入是一份未标注的现场 pcap。此时不应该依赖 `labels.csv`，而是让程序枚举 pcap 中出现的 MAC，逐个建立 device-window 画像，再用训练好的 `camera_detector` 判断哪些 MAC 疑似摄像头。

推荐使用：

```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  -m data/models \
  --window 10 \
  --top-macs 20 \
  --min-frames 100 \
  --min-source-frames 10 \
  --camera-threshold 0.6 \
  -o data/processed/unknown_scene_detection.csv
```

该脚本会输出：

```text
1. pcap 中出现频率较高的候选 MAC
2. 每个候选 MAC 的窗口数、帧数、摄像头概率
3. 被判定为 suspicious_camera 的 MAC
4. 关键指标均值，例如 large_frame_ratio、mean_frame_size、uplink_packet_ratio
```

参数含义：

```text
--top-macs 20
    只检测候选排名前 20 的 MAC，避免复杂环境下运行过慢。
    设置为 0 表示检测所有满足阈值的 MAC。

--min-frames 100
    候选 MAC 至少要在 100 个帧中出现过。
    只要该 MAC 出现在 sa/da/ta/ra/bssid 任一地址字段中，就计入 total_frames。

--min-source-frames 10
    候选 MAC 至少要作为 wlan.sa 出现 10 次。
    这不是严格的上行帧数，只是快速排除几乎不主动发送的 MAC。
    真正的上行比例会在 device-window 特征中通过 uplink_packet_ratio 等字段计算。

--camera-threshold 0.6
    如果某个 MAC 的平均摄像头概率超过该阈值，则标记为 suspicious_camera。
```

如果抓包时间较短，候选 MAC 被过滤掉，可以适当放宽：

```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  -m data/models \
  --top-macs 0 \
  --min-frames 30 \
  --min-source-frames 5 \
  -o data/processed/unknown_scene_detection.csv
```

如果现场 MAC 很多、运行太慢，可以提高阈值：

```bash
python3 scripts/detect_unknown_pcap.py \
  -p data/raw/mixed_test/unknown_scene.pcap \
  -m data/models \
  --top-macs 10 \
  --min-frames 500 \
  --min-source-frames 50
```

`scripts/run_detector.py` 是旧的通用预测脚本，主要用于对已提取的 feature CSV 或 flow-level pcap 做分类。当前正式演示推荐使用 `scripts/detect_unknown_pcap.py`，因为它针对未标注 pcap 自动枚举 MAC，并按 MAC 聚合输出候选摄像头。

## 11. 恢复普通联网

运行 `airmon-ng check kill` 或切换 monitor mode 后，Ubuntu 虚拟机里的普通 WiFi/网络管理服务可能被停止。需要恢复时：

```bash
sudo ip link set wlx6c1ff790462a down
sudo iw dev wlx6c1ff790462a set type managed
sudo ip link set wlx6c1ff790462a up
sudo systemctl restart NetworkManager
```

如果仍不恢复，直接重启虚拟机通常最快。

## 12. 常见问题

查看网卡是否进入虚拟机：

```bash
lsusb
iw dev
iwconfig
```

查看 monitor mode 是否成功：

```bash
iwconfig
```

查看 pcap 是否包含 802.11 帧：

```bash
tshark -r data/raw/test_capture.pcap -c 5
```

如果抓不到包，优先检查：

```text
1. USB 网卡是否连接到虚拟机，而不是 Windows 主机
2. 网卡是否支持 monitor mode
3. 是否锁定到了目标 WiFi 所在信道
4. 是否使用了 sudo
5. VMware USB Controller 是否启用 USB 3.0 / 3.1
```

### device-window 输出为空

常见原因：

```text
1. labels.csv 中 device_mac 是 unknown
2. 设备启用了随机 MAC，labels.csv 记录的 MAC 和 pcap 中实际 MAC 不一致
3. pcap 没抓到目标热点信道
4. session_id 前缀没有匹配到 pcap 文件名
```

可以用下面命令检查 pcap 中的源 MAC：

```bash
tshark -r data/raw/train/tablet_001.pcap \
  -Y "wlan.fc.type == 2" \
  -T fields -e wlan.sa | sort | uniq -c | sort -nr | head
```

### device-window 样本数变少

这是正常现象。`device-window` 是按时间窗口聚合：

```text
一个 pcap 的一个目标 MAC 每 30 秒 -> 一条样本
```

如果样本太少，可以调小窗口：

```bash
--window 15
```

但窗口越短，单条设备画像越不稳定。

### 混合数据怎么用

混合 pcap 不建议直接放进 `train/`。推荐用途：

```text
mixed_test/ 中用于演示和最终鲁棒性测试
```

如果要把混合 pcap 用于训练，必须依赖 MAC 级标签和 device-window 聚合，不能把整份 pcap 简单标成一个类别。

### 类别名称显示

训练和评估会保存并使用类别名，例如：

```text
non_wireless_camera
wireless_camera
tablet
```

不会只显示数字编码。
