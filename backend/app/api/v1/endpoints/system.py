from fastapi import APIRouter
from app.core.ssh_manager import ssh_client
import psutil

router = APIRouter()


# ==========================================
# 1. 系统状态监控 (修复版：自动重连)
# ==========================================
@router.get("/status")
async def get_system_status():
    """获取宿主机状态和 Kali 连接状态"""
    # 1. 获取 Windows/宿主机 资源
    cpu_usage = psutil.cpu_percent(interval=None)
    ram_usage = psutil.virtual_memory().percent

    # 2. 【核心修复】检查 SSH，如果没连上，立即尝试连接！
    kali_online = False

    # 先判断当前连接是否活跃
    is_active = False
    if ssh_client.client:
        try:
            transport = ssh_client.client.get_transport()
            if transport and transport.is_active():
                is_active = True
        except:
            pass

    # 如果不活跃，说明断了或者还没连，执行重连
    if not is_active:
        # print("[System] 检测到 SSH 未连接，正在尝试自动重连...") # 调试时可开启
        try:
            ssh_client.connect()
            # 连完再检查一次
            if ssh_client.client and ssh_client.client.get_transport() and ssh_client.client.get_transport().is_active():
                is_active = True
        except Exception as e:
            # 连不上就打印个简单的错误，别报错给前端
            print(f"[System] 自动重连尝试失败: {str(e)}")
            ssh_client.client = None

    kali_online = is_active

    # 3. 获取 Kali 内部负载 (仅当连接成功时)
    kali_cpu = 0
    kali_ram = 0
    if kali_online:
        try:
            # 此时连接已建立，执行命令获取 Kali 的 CPU/内存
            # timeout=2 防止卡死
            stdin, stdout, stderr = ssh_client.exec_command(
                "grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'",
                timeout=2
            )
            k_cpu = stdout.read().decode().strip()
            kali_cpu = int(float(k_cpu)) if k_cpu else 0

            stdin, stdout, stderr = ssh_client.exec_command(
                "free | grep Mem | awk '{print $3/$2 * 100.0}'",
                timeout=2
            )
            k_ram = stdout.read().decode().strip()
            kali_ram = int(float(k_ram)) if k_ram else 0
        except Exception:
            pass  # 获取负载失败不影响在线状态

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
    # 同样加上重连保护
    if not ssh_client.client:
        try:
            ssh_client.connect()
        except:
            return {"status": "error", "data": []}

    try:
        stdin, stdout, stderr = ssh_client.exec_command("airmon-ng")
        output = stdout.read().decode()

        interfaces = []
        lines = output.splitlines()

        for line in lines:
            if not line or "PHY" in line or "Interface" in line: continue
            parts = [p for p in line.split('\t') if p]

            if len(parts) >= 3:
                iface_name = ""
                driver = ""
                chipset = ""

                for part in parts:
                    if part.startswith("wlan") or part.startswith("mon"):
                        iface_name = part;
                        break

                if not iface_name and len(parts) > 1: iface_name = parts[1]
                if len(parts) > 2: driver = parts[2]
                if len(parts) > 3: chipset = parts[3]

                if iface_name and "eth" not in iface_name:
                    interfaces.append({
                        "name": iface_name,
                        "driver": driver,
                        "chipset": chipset,
                        "label": f"{iface_name}: {chipset} ({driver})"
                    })

        return {"status": "success", "data": interfaces}
    except Exception as e:
        return {"status": "error", "msg": str(e), "data": []}