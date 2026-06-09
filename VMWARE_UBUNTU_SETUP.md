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

对抓到的 pcap 提取特征：

```bash
python3 scripts/extract_features.py \
  -i data/raw/test_capture.pcap \
  -o data/processed/test_features.csv
```

如果已经有多个带标签 pcap，可以批量提取：

```bash
python3 scripts/extract_features.py \
  -d data/raw \
  -l data/labels.csv \
  -o data/processed/features.csv
```

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

## 10. 训练和检测

训练多分类模型：

```bash
python3 scripts/train_model.py \
  -f data/processed/features.csv \
  -o data/models
```

训练摄像头二分类模型：

```bash
python3 scripts/train_model.py \
  -f data/processed/features.csv \
  -o data/models \
  --binary-camera
```

运行检测：

```bash
python3 scripts/run_detector.py \
  -p data/raw/test_capture.pcap \
  -m data/models
```

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
