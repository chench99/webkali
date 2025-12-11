import subprocess
import time
import requests
import os
import csv
import glob
import sys
import socket
import re
import shutil

# ================= 配置区域 =================
# 部署时后端会自动注入 IP，手动测试请填入 Windows IP
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

# 确保临时目录存在
if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 基础工具函数 =================

def get_c2_ip():
    """智能探测 C2 服务器 IP"""
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        # 探测默认网关
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


def get_driver_name(iface):
    """获取网卡驱动/芯片名称 (用于前端友好显示)"""
    # 方法1: 使用 ethtool 获取驱动名
    try:
        driver = subprocess.check_output(f"ethtool -i {iface} | grep driver", shell=True).decode().split(":")[1].strip()
    except:
        driver = "Unknown"

    # 方法2: 尝试获取更详细的 USB/PCI 设备名 (高级)
    # 简单处理：如果 ethtool 拿到的是 usb 桥接，尝试读 usb ID
    return driver


def check_monitor_mode(iface):
    """检查指定网卡是否已经是监听模式"""
    try:
        iw_info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in iw_info:
            return True
    except:
        pass
    return False


# ================= 核心：智能网卡管理 =================

def get_smart_interfaces():
    """
    智能获取网卡列表
    格式: { "name": "wlan0", "display": "rtl88xxau (wlan0)", "mode": "Monitor" }
    """
    interfaces = []
    # 列出所有网络接口
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []

    for iface in os.listdir(sys_cls_net):
        # 排除非无线网卡 (检查是否有 wireless 目录或 phy80211)
        if iface == "lo" or iface.startswith("eth") or iface.startswith("docker"):
            continue

        # 进一步确认是否为无线设备
        if not os.path.exists(f"{sys_cls_net}/{iface}/wireless") and not os.path.exists(
                f"{sys_cls_net}/{iface}/phy80211"):
            # 某些现代驱动可能不创建 wireless 目录，尝试用 iw dev 确认
            if not run_cmd(f"iw dev {iface} info"):
                continue

        # 1. 获取驱动名称 (e.g., rtl88xxau)
        driver = get_driver_name(iface)

        # 2. 获取当前模式
        mode = "Monitor" if check_monitor_mode(iface) else "Managed"

        # 3. 构造友好名称
        # 前端显示格式: "驱动名 (接口名)" -> "rtl88xxau (wlan0)"
        display_name = f"{driver} ({iface})"
        if mode == "Monitor":
            display_name = f"🔥 {driver} ({iface})"

        interfaces.append({
            "name": iface,
            "display": display_name,
            "mode": mode,
            "is_wireless": True
        })

    return interfaces


def ensure_monitor_mode(original_iface):
    """
    【智能核心】
    1. 检查网卡是否为监听模式
    2. 如果不是，自动开启 airmon-ng
    3. 自动识别开启后的新名称 (如 wlan0 -> wlan0mon)
    """
    print(f"[*] 正在检查网卡状态: {original_iface}")

    # 1. 如果已经是监听模式，直接返回
    if check_monitor_mode(original_iface):
        print(f"[+] {original_iface} 已经是监听模式")
        return original_iface

    # 2. 尝试开启监听模式
    print(f"[*] 正在尝试开启监听模式: {original_iface} ...")

    # 先杀掉干扰进程 (可选，根据稳定性需求)
    run_cmd("airmon-ng check kill")

    # 启动 airmon-ng
    output = run_cmd(f"airmon-ng start {original_iface}")

    # 3. 智能捕获新名称
    # airmon-ng 输出通常包含: "monitor mode enabled on [phy0]wlan0mon"
    # 我们重新扫描所有网卡，找到那个驱动相同且处于 Monitor 模式的网卡

    # 简单策略：检查常见的更名规则
    potential_names = [original_iface, f"{original_iface}mon", "mon0"]

    # 重新获取一次系统网卡列表
    current_ifaces = os.listdir("/sys/class/net")

    # 优先在列表中找
    for name in current_ifaces:
        # 如果名字匹配，且处于 monitor 模式
        if name in potential_names or name.startswith(original_iface):
            if check_monitor_mode(name):
                print(f"[+] 成功开启监听模式! 新接口名: {name}")
                return name

    # 如果没找到改名规律，就遍历所有网卡找一个 Monitor 模式的
    for name in current_ifaces:
        if check_monitor_mode(name):
            print(f"[+] 找到可用监听接口: {name}")
            return name

    print("[-] 开启监听模式失败，将尝试使用原接口")
    return original_iface


# ================= 业务功能函数 =================

def parse_airodump_csv(csv_path):
    """解析 CSV 数据"""
    clients = []
    try:
        if not os.path.exists(csv_path): return []
        # 防止文件锁，复制一份读取
        tmp_read = csv_path + ".read"
        shutil.copy(csv_path, tmp_read)

        with open(tmp_read, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        start_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("Station MAC"):
                start_idx = i
                break

        if start_idx != -1:
            reader = csv.reader(lines[start_idx + 1:])
            for row in reader:
                if len(row) < 6: continue
                clients.append({
                    'mac': row[0].strip(),
                    'power': row[3].strip(),
                    'packets': row[4].strip(),
                    'bssid': row[5].strip(),
                    'probed': row[6].strip() if len(row) > 6 else ""
                })
    except:
        pass
    return clients


def perform_scan_airodump(iface):
    """
    使用 airodump-ng 进行快速扫描 (替代 nmcli)
    因为我们要开监听模式，nmcli 可能会失效，统一用 airodump 更稳
    """
    networks = []
    print(f"[*] 使用 airodump-ng 扫描 (接口: {iface})")

    prefix = f"{TMP_DIR}/scan_result"
    # 扫描 5 秒
    cmd = ["timeout", "5s", "airodump-ng", "--write", prefix, "--output-format", "csv", iface]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    csv_file = f"{prefix}-01.csv"
    if os.path.exists(csv_file):
        try:
            with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                # 跳过空行和非 AP 行
                for row in reader:
                    if not row or len(row) < 14: continue
                    if row[0].strip() == "BSSID": continue  # 标题行
                    if row[0].strip() == "Station MAC": break  # 到了客户端部分，停止

                    ssid = row[13].strip()
                    if not ssid: ssid = "<Hidden>"

                    networks.append({
                        "ssid": ssid,
                        "bssid": row[0].strip(),
                        "channel": int(row[3].strip()),
                        "signal": int(row[8].strip()),
                        "encryption": row[5].strip(),
                        "vendor": "Unknown"
                    })
        except Exception as e:
            print(f"[-] 解析扫描结果失败: {e}")

    # 清理
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass

    return networks


def run_monitor_task(task_type, params, original_iface):
    """执行持续监听任务"""
    # 1. 【智能切换】确保进入监听模式，并获取正确名称
    mon_iface = ensure_monitor_mode(original_iface)

    # 清理旧文件
    for f in glob.glob(f"{TMP_DIR}/*"):
        try:
            os.remove(f)
        except:
            pass

    prefix = f"{TMP_DIR}/output"
    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]

    if task_type == 'monitor_target':
        bssid = params.get('bssid')
        channel = params.get('channel')
        # 必须先切信道
        run_cmd(f"iwconfig {mon_iface} channel {channel}")
        cmd.extend(["--bssid", bssid, "--channel", str(channel)])
        print(f"[*] 启动定向监听: {bssid} on {mon_iface} (CH {channel})")

    elif task_type == 'deep_scan':
        print(f"[*] 启动深度全网扫描: {mon_iface}")
        # 深度扫描不加过滤

    cmd.append(mon_iface)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csv_file = f"{prefix}-01.csv"

    # 获取 C2 URL
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    try:
        while True:
            # 检查任务状态
            try:
                r = requests.get(f"{base_url}/agent/heartbeat", timeout=2)
                remote_task = r.json().get("task")
                if remote_task == "idle" or remote_task != task_type:
                    print("[*] 收到停止/变更指令")
                    break
            except:
                pass

            clients = parse_airodump_csv(csv_file)
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
        print("[*] 监听任务结束")


# ================= 主程序 =================

def main():
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    os.environ['no_proxy'] = '*'

    print(f"[*] Smart Agent v6.0 Started. C2: {base_url}")

    # 首次注册
    try:
        ifaces = get_smart_interfaces()
        requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=5)
        print(f"[+] 注册成功，发现 {len(ifaces)} 个无线接口")
    except:
        print("[-] 注册失败，进入离线重试循环")

    while True:
        try:
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            # 每次心跳都更新一下网卡状态 (因为可能刚刚开了 Monitor 模式，名字变了)
            # 这样前端能看到网卡名字变成了 "🔥 rtl88xxau (wlan0mon)"
            current_ifaces = get_smart_interfaces()
            if current_ifaces:
                requests.post(f"{base_url}/register_agent", json={"interfaces": current_ifaces})

            if task == "scan":
                iface = params.get("interface")
                # 智能切换模式扫描
                mon_iface = ensure_monitor_mode(iface)
                res = perform_scan_airodump(mon_iface)
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": res})

            elif task in ["monitor_target", "deep_scan"]:
                iface = params.get("interface")
                if not iface and current_ifaces: iface = current_ifaces[0]["name"]
                # 进入阻塞式监听
                run_monitor_task(task, params, iface)

            elif task == "idle":
                pass

        except Exception as e:
            # print(f"[!] Loop Error: {e}")
            pass

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()