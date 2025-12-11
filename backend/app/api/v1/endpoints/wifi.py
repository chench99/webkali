from fastapi import APIRouter, BackgroundTasks, HTTPException
import subprocess
import platform
import json
import re

# 引入攻击模块 (确保你目录下有这个文件)
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")


# ==========================================
# 1. 扫描逻辑 (Windows/Linux)
# ==========================================
def get_real_scan_results():
    """获取真实扫描结果"""
    system_type = platform.system()
    networks = []

    print(f"[*] 正在执行系统扫描... 系统: {system_type}")

    try:
        if system_type == "Windows":
            # Windows: 使用 netsh
            # 尝试多种编码防止乱码
            cmd = "netsh wlan show networks mode=bssid"
            try:
                output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
            except:
                output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')

            current_ssid = "Unknown"
            encryption = "OPEN"

            for line in output.split('\n'):
                line = line.strip()
                if line.startswith("SSID"):
                    parts = line.split(":")
                    if len(parts) > 1:
                        current_ssid = parts[1].strip()
                elif "身份验证" in line or "Authentication" in line:
                    if "WPA" in line:
                        encryption = "WPA2"
                    elif "WEP" in line:
                        encryption = "WEP"
                    else:
                        encryption = "OPEN"
                elif line.startswith("BSSID"):
                    parts = line.split(":")
                    if len(parts) > 1:
                        bssid = ":".join(parts[1:]).strip()
                        networks.append({
                            "ssid": current_ssid,
                            "bssid": bssid,
                            "channel": 1,  # Windows 难获取信道，默认1
                            "signal": -60,
                            "encryption": encryption
                        })

        else:
            # Linux: 使用 nmcli
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list"]
            output = subprocess.check_output(cmd).decode('utf-8')
            for line in output.split('\n'):
                if not line: continue
                # nmcli 格式 SSID:BSSID:CHAN:SIGNAL:SECURITY (BSSID含冒号需倒序处理)
                parts = line.split(':')
                if len(parts) >= 4:
                    sec = parts[-1]
                    bssid = ":".join(parts[-9:-3]) if len(parts) >= 9 else "Unknown"
                    ssid = line.split(bssid)[0].strip(':')
                    # 只有当 SSID 不为空时才添加
                    if ssid:
                        networks.append({
                            "ssid": ssid,
                            "bssid": bssid,
                            "channel": int(parts[-3]) if parts[-3].isdigit() else 1,
                            "signal": int(parts[-2]) if parts[-2].isdigit() else -70,
                            "encryption": sec
                        })

    except Exception as e:
        print(f"[!] 扫描出错: {e}")
        # 出错时不返回假数据，返回空列表
        return []

    return networks


# ==========================================
# 2. 接口定义 (统一暗号)
# ==========================================

# 强行把所有可能的扫描路径都指向同一个函数，防止 404
@router.post("/scan/start")
@router.get("/scan/start")
@router.post("/networks")  # 兼容旧前端
@router.get("/networks")  # 兼容旧前端
async def scan_wifi():
    """
    统一扫描接口
    """
    results = get_real_scan_results()

    return {
        "code": 200,
        "status": "success",
        "message": "扫描完成",
        "count": len(results),
        "networks": results  # 前端读取这里的 .networks
    }


# ==========================================
# 3. 攻击接口 (保持不变)
# ==========================================
@router.get("/capture/status")
async def get_status():
    return {"is_running": wifi_attacker.is_running}