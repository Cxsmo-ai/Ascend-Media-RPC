import asyncio
import logging
import socket
import threading
from typing import List, Optional, Dict

logger = logging.getLogger("stremio-rpc")

try:
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False


class MDNSListener:
    """Listens for Android TV devices advertised via mDNS/Zeroconf."""

    def __init__(self):
        self.devices: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def add_service(self, zc, service_type, name):
        try:
            info = zc.get_service_info(service_type, name)
            if info:
                addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
                if addresses:
                    with self._lock:
                        self.devices[name] = {
                            "name": name,
                            "host": addresses[0],
                            "port": info.port,
                            "properties": {k.decode(): v.decode() if isinstance(v, bytes) else v
                                          for k, v in info.properties.items()},
                        }
                    logger.info(f"mDNS: Found device {name} at {addresses[0]}")
        except Exception as e:
            logger.debug(f"mDNS: Error processing service {name}: {e}")

    def remove_service(self, zc, service_type, name):
        with self._lock:
            self.devices.pop(name, None)

    def update_service(self, zc, service_type, name):
        self.add_service(zc, service_type, name)

    def get_devices(self) -> List[Dict]:
        with self._lock:
            return list(self.devices.values())


class ADBDiscovery:
    def __init__(self, port: int = 5555, use_mdns: bool = True):
        self.port = port
        self.use_mdns = use_mdns and HAS_ZEROCONF
        self._mdns_listener: Optional[MDNSListener] = None
        self._zeroconf: Optional[object] = None
        self._browser: Optional[object] = None

    def start_mdns(self):
        """Start mDNS/Zeroconf discovery for Android TV devices."""
        if not self.use_mdns or not HAS_ZEROCONF:
            return
        try:
            self._mdns_listener = MDNSListener()
            self._zeroconf = Zeroconf()
            # Android TV devices advertise via _adb-tls-connect._tcp.local.
            self._browser = ServiceBrowser(
                self._zeroconf,
                ["_adb-tls-connect._tcp.local.", "_androidtvremote2._tcp.local."],
                self._mdns_listener,
            )
            logger.info("mDNS discovery started")
        except Exception as e:
            logger.warning(f"mDNS discovery failed to start: {e}")

    def stop_mdns(self):
        if self._zeroconf:
            try:
                self._zeroconf.close()
            except Exception:
                pass
            self._zeroconf = None

    def get_mdns_devices(self) -> List[Dict]:
        if self._mdns_listener:
            return self._mdns_listener.get_devices()
        return []

    async def scan_network(self) -> List[str]:
        # Try mDNS first
        mdns_devices = self.get_mdns_devices()
        if mdns_devices:
            return [d["host"] for d in mdns_devices]

        # Fall back to brute-force port scan
        local_ip = self._get_local_ip()
        if not local_ip:
            return []

        subnet = ".".join(local_ip.split(".")[:3])
        tasks = []

        # Scan 1-254
        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            tasks.append(self._check_port(ip, self.port))

        results = await asyncio.gather(*tasks)
        return [ip for ip in results if ip]

    def _get_local_ip(self) -> Optional[str]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    async def _check_port(self, ip: str, port: int) -> Optional[str]:
        writer = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=0.2
            )
            return ip

        except Exception:
            return None

        finally:
            if writer is not None:
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
                except Exception:
                    pass
