from fastapi import APIRouter
from app.core.ssh_manager import ssh_client
import psutil

router = APIRouter()


# ==========================================
# 1. 系统状态监控 (修复版：增加自动重连)
# ==========================================
@router.get("/status")
async def get_system_status():
    """获取宿主机状态和 Kali 连接状态"""
    # 1. 获取本机 (Windows/Server) 资源
    cpu_usage = psutil.cpu_percent(interval=None)
    ram_usage = psutil.virtual_memory().percent

    # 2. 检查 SSH 连接状态，如果断开则尝试重连
    kali_online = False

    # 判断当前连接是否有效
    is_connected = False
    if ssh_client.client:
        try:
            if ssh_client.client.get_transport() and ssh_client.client.get_transport().is_active():
                is_connected = True
        except:
            is_connected = False

    # 如果未连接，尝试发起连接 (这就是修复的关键！)
    if not is_connected:
        try:
            print("[System] 监测到 Kali 未连接，正在尝试自动重连...")
            ssh_client.connect()
            # 连接后再次检查
            if ssh_client.client and ssh_client.client.get_transport() and ssh_client.client.get_transport().is_active():
                is_connected = True
        except Exception as e:
            print(f"[System] 自动重连失败: {e}")
            # 这里不抛出异常，以免阻塞前端获取 Host CPU 信息
            ssh_client.client = None

    kali_online = is_connected

    # 3. 如果在线，尝试获取 Kali 的负载
    kali_cpu = 0
    kali_ram = 0
    if kali_online:
        try:
            # 简单的获取 Kali 负载命令
            stdin, stdout, stderr = ssh_client.exec_command(
                "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'", timeout=2)
            k_cpu = stdout.read().decode().strip()
            kali_cpu = int(float(k_cpu)) if k_cpu else 0

            stdin, stdout, stderr = ssh_client.exec_command("free | grep Mem | awk '{print $3/$2 * 100.0}'", timeout=2)
            k_ram = stdout.read().decode().strip()
            kali_ram = int(float(k_ram)) if k_ram else 0
        except Exception as e:
            print(f"[System] 获取 Kali 负载失败: {e}")
            # 获取负载失败不代表掉线，可能只是超时
            pass

    return {
        "host": {
            "cpu": cpu_usage,
            "ram": ram_usage
        },
        "kali": {
            "online": kali_online,
            "cpu": kali_cpu,
            "ram": kali_ram
        }
    }


# ==========================================
# 2. 网卡详情获取
# ==========================================
@router.get("/interfaces")
async def get_kali_interfaces():
    """
    执行 'airmon-ng' 获取网卡列表
    """
    # 确保连接
    if not ssh_client.client:
        try:
            ssh_client.connect()
        except:
            return {"status": "error", "data": []}

    try:
        # airmon-ng 的输出包含 PHY, Interface, Driver, Chipset
        stdin, stdout, stderr = ssh_client.exec_command("airmon-ng")
        output = stdout.read().decode()

        interfaces = []
        lines = output.splitlines()

        for line in lines:
            if not line or "PHY" in line or "Interface" in line: continue
            parts = line.split('\t')
            parts = [p for p in parts if p]

            if len(parts) >= 3:
                iface_name = ""
                driver = ""
                chipset = ""

                for part in parts:
                    if part.startswith("wlan") or part.startswith("mon"):
                        iface_name = part
                        break

                if not iface_name and len(parts) > 1:
                    iface_name = parts[1]

                if len(parts) > 2: driver = parts[2]
                if len(parts) > 3: chipset = parts[3]

                if iface_name and "eth" not in iface_name and "lo" not in iface_name:
                    interfaces.append({
                        "name": iface_name,
                        "driver": driver,
                        "chipset": chipset,
                        "label": f"{iface_name}: {chipset} ({driver})"
                    })

        return {"status": "success", "data": interfaces}
    except Exception as e:
        return {"status": "error", "msg": str(e), "data": []}