import subprocess
import time
import requests
import os
import csv
import glob
import sys
import shutil

# ================= 配置区域 =================
# C2 地址 (部署时通常由 Server 自动通过 sed 注入，这里留空或写默认)
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
# 临时文件存放目录
TMP_DIR = "/tmp/kali_c2_scan"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 工具函数 =================
def get_c2_ip():
    """获取回连的 C2 IP 地址"""
    if FIXED_C2_IP: return FIXED_C2_IP
    # 尝试获取默认网关作为 Host IP (适用于 NAT 模式)
    try:
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway: return gateway
    except:
        pass
    return "127.0.0.1"


def run_cmd(cmd):
    """执行 Shell 命令并返回输出"""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def cleanup_files(prefix):
    """清理 airodump 生成的临时文件"""
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass


def check_monitor_mode(iface):
    """检查网卡是否为监听模式"""
    try:
        info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in info:
            return True
    except:
        pass
    return False


def ensure_monitor_mode(iface):
    """确保网卡进入监听模式 (自动处理 airmon-ng)"""
    if check_monitor_mode(iface):
        return iface

    print(f"[*] 正在将 {iface} 开启为监听模式...")
    run_cmd("airmon-ng check kill")  # 杀掉干扰进程
    run_cmd(f"airmon-ng start {iface}")

    # 检查名称是否变更为 iface + 'mon'
    possible_names = [iface, f"{iface}mon"]
    for name in possible_names:
        if os.path.exists(f"/sys/class/net/{name}") and check_monitor_mode(name):
            return name
    return iface


def get_interfaces():
    """获取系统网卡列表"""
    interfaces = []
    sys_path = "/sys/class/net"
    if not os.path.exists(sys_path): return []

    for iface in os.listdir(sys_path):
        if iface == 'lo' or not os.path.exists(f"{sys_path}/{iface}/wireless"):
            # 有些网卡可能没有 wireless 目录但确实是无线的 (如 USB)，这里做个简单的过滤
            # 生产环境建议用 iw dev 确认
            if "wiphy" not in run_cmd(f"iw dev {iface} info"):
                continue

        mode = "Monitor" if check_monitor_mode(iface) else "Managed"
        interfaces.append({
            "name": iface,
            "display": f"{iface} [{mode}]",
            "mode": mode
        })
    return interfaces


# ================= 核心逻辑：CSV 解析 =================
def parse_airodump_csv(csv_path):
    """
    解析 airodump-ng 的 CSV 文件。
    文件结构分为两部分：
    1. AP 列表 (BSSID, ESSID, Channel, Encryption...)
    2. 空行
    3. Station 列表 (Station MAC, BSSID, Power...)
    """
    networks = []
    clients = []

    # 辅助字典：统计每个 AP 下的客户端数量 {BSSID: count}
    client_counts = {}

    if not os.path.exists(csv_path):
        return [], []

    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.readlines()

        # 分割上下两部分
        ap_section = []
        station_section = []
        is_station_part = False

        for line in content:
            line = line.strip()
            if not line: continue

            if line.startswith("Station MAC"):
                is_station_part = True
                continue

            if is_station_part:
                station_section.append(line)
            else:
                ap_section.append(line)

        # 1. 解析 Station 部分 (为了统计人数)
        if station_section:
            reader = csv.reader(station_section)
            for row in reader:
                if len(row) < 6: continue
                # CSV 格式: Station MAC, First time seen, Last time seen, Power, # packets, BSSID, Probed ESSIDs
                st_mac = row[0].strip()
                power = row[3].strip()
                packets = row[4].strip()
                bssid = row[5].strip()

                # 过滤未关联的客户端
                if bssid and "not associated" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1

                clients.append({
                    "mac": st_mac,
                    "bssid": bssid,
                    "signal": int(power) if power.lstrip('-').isdigit() else -100,
                    "packets": int(packets) if packets.isdigit() else 0
                })

        # 2. 解析 AP 部分
        # 跳过头部 (BSSID, First time seen...)
        start_idx = 0
        for i, line in enumerate(ap_section):
            if line.startswith("BSSID"):
                start_idx = i + 1
                break

        if start_idx < len(ap_section):
            reader = csv.reader(ap_section[start_idx:])
            for row in reader:
                if len(row) < 14: continue
                # CSV 格式: BSSID, ..., Channel, ..., Privacy, ..., Power, ..., ESSID
                bssid = row[0].strip()
                channel = int(row[3].strip()) if row[3].strip().isdigit() else 0
                encryption = row[5].strip()
                power = row[8].strip()
                ssid = row[13].strip()

                if not ssid: ssid = "<Hidden>"

                networks.append({
                    "bssid": bssid,
                    "ssid": ssid,
                    "channel": channel,
                    "encryption": encryption,
                    "signal": int(power) if power.lstrip('-').isdigit() else -100,
                    "client_count": client_counts.get(bssid, 0)  # 绑定在线人数
                })

    except Exception as e:
        print(f"[-] 解析 CSV 出错: {e}")

    return networks, clients


# ================= 任务执行逻辑 =================
def task_scan(iface):
    """执行全频段扫描"""
    print(f"[*] 执行全频段扫描: {iface}")
    mon_iface = ensure_monitor_mode(iface)

    prefix = f"{TMP_DIR}/scan_result"
    cleanup_files(prefix)

    # --band abg: 扫描 2.4GHz 和 5GHz
    # --write: 写入文件
    # output-format csv: 只生成 CSV
    cmd = [
        "timeout", "10s",
        "airodump-ng",
        "--band", "abg",
        "--write", prefix,
        "--output-format", "csv",
        mon_iface
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 解析结果
    csv_file = f"{prefix}-01.csv"
    networks, _ = parse_airodump_csv(csv_file)

    cleanup_files(prefix)
    return networks


def task_monitor(iface, bssid, channel):
    """执行定向监听 (持续运行直到任务取消)"""
    print(f"[*] 执行定向监听: {bssid} (CH: {channel})")
    mon_iface = ensure_monitor_mode(iface)

    # 锁定信道 (先用 iwconfig 锁一下，airodump 也会锁)
    os.system(f"iwconfig {mon_iface} channel {channel}")

    prefix = f"{TMP_DIR}/monitor_target"
    cleanup_files(prefix)

    # 启动后台进程
    cmd = [
        "airodump-ng",
        "--bssid", bssid,
        "--channel", str(channel),
        "--write", prefix,
        "--output-format", "csv",
        mon_iface
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"

    try:
        while True:
            time.sleep(2)  # 每2秒读取一次

            # 1. 检查心跳，看任务是否被后端取消
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=3).json()
                if res.get("task") != "monitor_target":
                    print("[*] 收到停止指令")
                    break
            except:
                pass

            # 2. 解析实时 CSV
            csv_file = f"{prefix}-01.csv"
            if os.path.exists(csv_file):
                _, clients = parse_airodump_csv(csv_file)

                # 过滤出只属于目标 BSSID 的客户端 (虽然 airodump 加了 --bssid 过滤，但保险起见)
                target_clients = [c for c in clients if c['bssid'] == bssid]

                if target_clients:
                    # 回传数据
                    try:
                        requests.post(f"{base_url}/callback", json={
                            "type": "monitor_update",
                            "data": target_clients
                        })
                    except:
                        pass
    finally:
        proc.terminate()
        cleanup_files(prefix)


# ================= 主循环 =================
def main():
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"
    print(f"[*] Agent 启动，C2 地址: {base_url}")

    last_reg_time = 0

    while True:
        try:
            # 1. 定期注册网卡 (每10秒)
            if time.time() - last_reg_time > 10:
                ifaces = get_interfaces()
                requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces})
                last_reg_time = time.time()

            # 2. 心跳获取任务
            res = requests.get(f"{base_url}/agent/heartbeat", timeout=5).json()
            task = res.get("task")
            params = res.get("params", {})

            if task == "scan":
                # 执行扫描
                nets = task_scan(params.get("interface", "wlan0"))
                # 回传结果
                requests.post(f"{base_url}/callback", json={
                    "type": "scan_result",
                    "networks": nets
                })

            elif task == "monitor_target":
                # 进入监听阻塞循环
                task_monitor(
                    params.get("interface", "wlan0"),
                    params.get("bssid"),
                    params.get("channel")
                )

        except KeyboardInterrupt:
            break
        except Exception as e:
            # print(f"[-] Loop Error: {e}")
            pass

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()