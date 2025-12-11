from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import subprocess
import psutil
import re
import platform
import sys

# 引入攻击模块
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")


# ==========================================
# 1. 辅助函数：Windows 真实扫描解析
# ==========================================
def scan_windows_real():
    """
    [Windows] 使用 netsh 获取真实 WiFi 列表
    """
    networks = []
    try:
        # 执行 Windows 原生扫描命令
        # 注意：这需要你的电脑有无线网卡且已开启 WiFi
        cmd = "netsh wlan show networks mode=bssid"
        # 编码设为 gb18030 兼容中文系统
        output = subprocess.check_output(cmd, shell=True).decode('gb18030', errors='ignore')

        current_ssid = "Unknown"
        current_encryption = "OPEN"

        # 简单的文本解析
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("SSID"):
                # 获取 SSID (例如: SSID 1 : CMCC)
                parts = line.split(":")
                if len(parts) > 1:
                    current_ssid = parts[1].strip()
            elif line.startswith("身份验证") or line.startswith("Authentication"):
                if "WPA" in line:
                    current_encryption = "WPA2"
                elif "WEP" in line:
                    current_encryption = "WEP"
                else:
                    current_encryption = "OPEN"
            elif line.startswith("BSSID"):
                # 获取 BSSID (MAC 地址)
                parts = line.split(":")
                if len(parts) > 1:
                    bssid = ":".join(parts[1:]).strip()
                    # 获取信号强度 (需要下一行，这里简化处理，默认为 -60)
                    # 存入列表
                    networks.append({
                        "ssid": current_ssid,
                        "bssid": bssid,
                        "channel": 1,  # Windows netsh 很难直接获取信道，暂置 1
                        "signal": -60,
                        "encryption": current_encryption
                    })
    except subprocess.CalledProcessError:
        print("[!] Windows 扫描失败: 没有找到无线网卡或 WiFi 未开启")
        return []
    except Exception as e:
        print(f"[!] Windows 扫描未知错误: {e}")
        return []

    return networks


def get_real_interface_name():
    """
    获取真实的无线网卡名称
    """
    stats = psutil.net_if_stats()
    # 关键词匹配真实网卡
    keywords = ["wlan", "wireless", "wi-fi", "无线"]

    for iface in stats.keys():
        # 排除掉 VMware/VirtualBox 等虚拟网卡
        if any(k in iface.lower() for k in keywords) and "vmware" not in iface.lower():
            return iface

    return None


# ==========================================
# 2. 核心 API 路由
# ==========================================

# --- [关键修复] 将接口改为 /networks 以匹配前端请求 ---
@router.get("/networks")
async def scan_networks():
    """
    获取真实 WiFi 列表
    """
    system_type = platform.system()
    real_interface = get_real_interface_name()

    # 1. 严格检查：如果没有网卡，直接报错，不给假数据
    if not real_interface:
        # 如果你在 Windows 上但 psutil 没识别出名字，通常系统默认叫 "Wi-Fi"
        if system_type == "Windows":
            real_interface = "Wi-Fi"
        else:
            # 如果真的找不到，返回空列表或者错误提示
            print("[!] 错误: 未检测到物理无线网卡")
            return {
                "status": "error",
                "message": "未检测到物理无线网卡 (No Physical WiFi Adapter Found)",
                "networks": []
            }

    print(f"[*] 正在使用真实网卡 [{real_interface}] 进行扫描...")

    results = []
    if system_type == "Windows":
        # 执行 Windows 真实扫描
        results = scan_windows_real()
    else:
        # Linux / Kali 真实扫描 (nmcli)
        try:
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list"]
            output = subprocess.check_output(cmd).decode('utf-8')
            for line in output.split('\n'):
                if not line: continue
                parts = line.split(':')
                if len(parts) >= 4:
                    # 简单解析
                    sec = parts[-1]
                    bssid = ":".join(parts[-9:-3]) if len(parts) >= 9 else "Unknown"
                    ssid = line.split(bssid)[0].strip(':')
                    results.append({
                        "ssid": ssid, "bssid": bssid, "encryption": sec, "signal": -50, "channel": 6
                    })
        except:
            print("[!] Linux 扫描失败，请确保安装了 nmcli")

    return {
        "status": "success",
        "interface": real_interface,
        "count": len(results),
        "networks": results
    }


# --- 其他接口保持不变 ---
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_capture(config: AttackConfig, background_tasks: BackgroundTasks):
    if wifi_attacker.is_running:
        raise HTTPException(status_code=409, detail="任务运行中")
    background_tasks.add_task(wifi_attacker.run_attack_cycle, config.bssid, config.channel, config.attack_type)
    return {"status": "started"}


@router.post("/capture/stop")
async def stop_capture():
    wifi_attacker.is_running = False
    return {"status": "stopped"}


@router.get("/capture/status")
async def get_status():
    return {"is_running": wifi_attacker.is_running, "handshake_captured": wifi_attacker.handshake_captured}