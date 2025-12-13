import subprocess
import time
import requests
import os
import csv
import glob
import sys
import shutil

# ================= 配置区域 =================
FIXED_C2_IP = ""  # 部署时会自动注入
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 基础工具函数 =================

def get_c2_ip():
    """智能获取 C2 地址"""
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway: return gateway
    except:
        pass
    return "127.0.0.1"


def run_cmd(cmd):
    try:
        # 使用 check_output 捕获输出
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def check_monitor_mode(iface):
    """检查网卡是否为监听模式"""
    try:
        iw_info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in iw_info: return True
    except:
        pass
    return False


def ensure_monitor_mode(original_iface):
    """确保进入监听模式，返回实际接口名"""
    if check_monitor_mode(original_iface): return original_iface

    print(f"[*] 开启监听模式: {original_iface}")
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {original_iface}")

    # 查找可能变更为 wlan0mon 的新名称
    for name in os.listdir("/sys/class/net"):
        if (name.startswith(original_iface) or "mon" in name) and check_monitor_mode(name):
            return name
    return original_iface


def get_smart_interfaces():
    """获取网卡列表回传给 C2"""
    interfaces = []
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []

    for iface in os.listdir(sys_cls_net):
        if iface in ["lo"] or iface.startswith(("eth", "docker", "veth")): continue
        # 简单过滤非无线网卡
        if not os.path.exists(f"{sys_cls_net}/{iface}/wireless") and not os.path.exists(
                f"{sys_cls_net}/{iface}/phy80211"):
            continue

        driver = "Unknown"
        try:
            driver = subprocess.check_output(f"ethtool -i {iface} | grep driver", shell=True).decode().split(":")[
                1].strip()
        except:
            pass

        mode = "Monitor" if check_monitor_mode(iface) else "Managed"
        interfaces.append({
            "name": iface,
            "display": f"{'🔥 ' if mode == 'Monitor' else ''}{driver} ({iface})",
            "mode": mode,
            "is_wireless": True
        })
    return interfaces


def cleanup_files(prefix):
    """清理临时 CSV 文件"""
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass


# ================= 核心升级：双频扫描与深度解析 =================

def parse_csv_dual_section(csv_path):
    """
    [核心升级] 解析 airodump-ng 的 CSV。
    该 CSV 包含两部分，中间由空行分隔：
    1. Access Points (BSSID, ESSID, ...)
    2. Stations (MAC, BSSID, Power, ...)
    """
    networks = []
    client_counts = {}  # { bssid: count }
    clients_details = []

    if not os.path.exists(csv_path): return [], []

    try:
        # 为了防止文件被写入时读取报错，建议先读入内存
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        ap_lines = []
        station_lines = []
        is_station_section = False

        for line in lines:
            line = line.strip()
            if not line: continue  # 跳过空行

            if line.startswith("Station MAC"):
                is_station_section = True
                continue  # 跳过 Station 表头

            if is_station_section:
                station_lines.append(line)
            else:
                ap_lines.append(line)

        # 1. 解析 Station 部分，统计人数
        if station_lines:
            reader = csv.reader(station_lines)
            for row in reader:
                if len(row) < 6: continue
                # Station CSV 格式: MAC, First seen, Last seen, Power, # packets, BSSID, Probed ESSIDs
                st_mac = row[0].strip()
                power = row[3].strip()
                packets = row[4].strip()
                bssid = row[5].strip()

                # 统计人数 (排除未关联的)
                if bssid and bssid != "(not associated)":
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1

                # 记录详细信息 (用于 monitor 模式)
                clients_details.append({
                    "mac": st_mac,
                    "power": power,
                    "packets": packets,
                    "bssid": bssid
                })

        # 2. 解析 AP 部分
        # 跳过第一行表头 (BSSID, First time seen...)
        if len(ap_lines) > 0:
            # 找到表头索引，防止 csv 文件头部有垃圾数据
            header_idx = -1
            for i, l in enumerate(ap_lines):
                if l.startswith("BSSID"):
                    header_idx = i
                    break

            if header_idx != -1 and len(ap_lines) > header_idx + 1:
                reader = csv.reader(ap_lines[header_idx + 1:])
                for row in reader:
                    if len(row) < 14: continue

                    bssid = row[0].strip()
                    channel_str = row[3].strip()
                    encrypt = row[5].strip()
                    signal_str = row[8].strip()
                    ssid = row[13].strip()

                    try:
                        channel = int(channel_str)
                    except:
                        channel = 0

                    try:
                        signal = int(signal_str)
                    except:
                        signal = -100

                    if not ssid: ssid = "<Hidden>"

                    networks.append({
                        "bssid": bssid,
                        "ssid": ssid,
                        "channel": channel,
                        "signal": signal,
                        "encryption": encrypt,
                        "band": "5G" if channel > 14 else "2.4G",  # 简单频段判断
                        "clientCount": client_counts.get(bssid, 0)  # [NEW] 绑定人数
                    })

    except Exception as e:
        print(f"[-] CSV Parse Error: {e}")

    return networks, clients_details


def perform_scan_airodump(iface):
    """[C2任务] 普通扫描 (覆盖 2.4/5G)"""
    print(f"[*] 执行普通扫描 (15s): {iface} [Band: 2.4/5G]")
    prefix = f"{TMP_DIR}/scan_result"
    cleanup_files(prefix)

    # [NEW] 添加 --band abg 支持 5G
    cmd = [
        "timeout", "15s",
        "airodump-ng",
        "--band", "abg",
        "--write", prefix,
        "--output-format", "csv",
        iface
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    csv_file = f"{prefix}-01.csv"
    networks, _ = parse_csv_dual_section(csv_file)

    cleanup_files(prefix)
    return networks


def run_monitor_task(task_type, params, original_iface):
    """[C2任务] 持续监听/深度扫描"""
    mon_iface = ensure_monitor_mode(original_iface)
    prefix = f"{TMP_DIR}/monitor_output"
    cleanup_files(prefix)

    # 构造命令
    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]

    if task_type == 'monitor_target':
        bssid = params.get('bssid')
        channel = params.get('channel')
        # 切信道防止漏包
        run_cmd(f"iwconfig {mon_iface} channel {channel}")
        cmd.extend(["--bssid", bssid, "--channel", str(channel)])
        print(f"[*] 锁定监听: {bssid} (CH {channel})")

    elif task_type == 'deep_scan':
        print(f"[*] 启动全网深度扫描")
        cmd.extend(["--band", "abg"])  # 全频段

    cmd.append(mon_iface)

    # 启动后台进程
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csv_file = f"{prefix}-01.csv"

    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    try:
        # 循环回传数据
        while True:
            # 1. 检查 C2 停止信号
            try:
                r = requests.get(f"{base_url}/agent/heartbeat", timeout=2)
                if r.json().get("task") != task_type:
                    print("[*] 收到停止指令")
                    break
            except:
                pass

            # 2. 解析数据
            _, clients = parse_csv_dual_section(csv_file)

            # 3. 回传数据
            if clients:
                update_type = 'monitor_update' if task_type == 'monitor_target' else 'deep_update'
                try:
                    requests.post(f"{base_url}/callback", json={
                        "type": update_type,
                        "data": clients
                    })
                except:
                    pass

            time.sleep(2)
    finally:
        if proc: proc.terminate()
        cleanup_files(prefix)


# ================= 主入口 =================

def main():
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    os.environ['no_proxy'] = '*'  # 防止代理干扰内网通信

    print(f"[*] Kali Agent v2.0 (5G Support) -> {base_url}")

    # 上线注册
    try:
        requests.post(f"{base_url}/register_agent", json={"interfaces": get_smart_interfaces()}, timeout=3)
    except:
        pass

    while True:
        try:
            # 心跳轮询
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            if task == "scan":
                iface = params.get("interface")
                mon_iface = ensure_monitor_mode(iface)

                # 执行扫描
                nets = perform_scan_airodump(mon_iface)

                # 回传
                requests.post(f"{base_url}/callback", json={
                    "type": "scan_result",
                    "networks": nets
                })

            elif task in ["monitor_target", "deep_scan"]:
                # 进入持续监听循环 (会阻塞直到任务结束)
                iface = params.get("interface")
                run_monitor_task(task, params, iface)

            elif task == "idle":
                # 空闲时偶尔更新网卡状态
                if int(time.time()) % 10 == 0:
                    requests.post(f"{base_url}/register_agent", json={"interfaces": get_smart_interfaces()})

        except Exception as e:
            print(f"[!] Loop Error: {e}")
            time.sleep(3)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()