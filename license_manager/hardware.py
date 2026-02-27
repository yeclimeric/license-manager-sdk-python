import hashlib
import json
import logging
import os
import platform
import socket
import subprocess
import uuid
from typing import List, Tuple, Dict, Optional


class HardwareProvider:
    """Abstracts hardware fingerprint collection."""
    def fingerprint(self) -> Tuple[str, Dict[str, str]]:
        raise NotImplementedError


class DefaultHardwareProvider(HardwareProvider):
    """
    Collects host-agnostic identifiers.
    Supported field names (case-insensitive):
      - mac: first non-loopback MAC address (default)
      - hostname: OS host name (default)
      - cpu: CPU model / brand string (best-effort)
      - memory: total physical memory capacity (best-effort)
    """
    def __init__(self, fields: Optional[List[str]] = None):
        if not fields:
            self.fields = ["mac", "hostname"]
        else:
            self.fields = [f.strip().lower() for f in fields if f.strip()]
            if not self.fields:
                self.fields = ["mac", "hostname"]

    def fingerprint(self) -> Tuple[str, Dict[str, str]]:
        data: Dict[str, str] = {}
        for field in self.fields:
            if field == "hostname":
                data["hostname"] = self._get_hostname()
            elif field == "mac":
                mac = self._get_mac()
                if mac:
                    data["mac"] = mac
            elif field == "cpu":
                cpu = self._get_cpu()
                if cpu:
                    data["cpu"] = cpu
            elif field == "memory":
                mem = self._get_memory()
                if mem:
                    data["memory"] = mem
                    
        # Deterministic serialization
        keys = sorted(data.keys())
        builder = []
        for k in keys:
            val = str(data[k]).lower()
            builder.append(f"{k}={val};")
            
        full_string = "".join(builder)
        hash_sum = hashlib.sha256(full_string.encode('utf-8')).hexdigest()
        return hash_sum, data

    def _get_hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def _get_mac(self) -> str:
        try:
            # uuid.getnode() returns MAC of the first active interface 
            # or a random 48-bit number if not found (has multicast bit set)
            node = uuid.getnode()
            if (node >> 40) % 2 == 0:  # Not a random MAC
                mac = ':'.join(('%012x' % node)[i:i+2] for i in range(0, 12, 2))
                return mac.lower()
            return ""
        except Exception:
            return ""

    def _get_cpu(self) -> str:
        system = platform.system().lower()
        try:
            if system == "linux":
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.lower().startswith("model name"):
                            return line.split(":")[1].strip()
            elif system == "darwin":
                return self._cmd_output(["sysctl", "-n", "machdep.cpu.brand_string"])
            elif system == "windows":
                wmic_out = self._cmd_output(["wmic", "cpu", "get", "Name"])
                if wmic_out and "name" not in wmic_out.lower():
                    return wmic_out
                # Fallback
                env_proc = os.getenv("PROCESSOR_IDENTIFIER")
                if env_proc:
                    return env_proc
        except Exception:
            pass
        
        return platform.processor() or platform.machine()

    def _get_memory(self) -> str:
        system = platform.system().lower()
        try:
            if system == "linux":
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.lower().startswith("memtotal"):
                            parts = line.split()
                            if len(parts) >= 2:
                                val_kb = int(parts[1])
                                return self._format_bytes(val_kb * 1024)
            elif system == "darwin":
                out = self._cmd_output(["sysctl", "-n", "hw.memsize"])
                if out:
                    return self._format_bytes(int(out))
            elif system == "windows":
                out = self._cmd_output(["wmic", "computersystem", "get", "TotalPhysicalMemory"])
                if out:
                    return self._format_bytes(int(out))
        except Exception:
            pass
        return ""

    def _cmd_output(self, cmd: List[str]) -> str:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode('utf-8')
            lines = [line.strip() for line in out.split('\n') if line.strip()]
            for line in lines:
                lower_line = line.lower()
                if "name" in lower_line or "totalphysicalmemory" in lower_line:
                    continue
                return line
            return ""
        except Exception:
            return ""

    def _format_bytes(self, b: int) -> str:
        kb = 1024
        mb = 1024 * kb
        gb = 1024 * mb
        if b >= gb:
            return f"{b // gb}GB"
        elif b >= mb:
            return f"{b // mb}MB"
        elif b >= kb:
            return f"{b // kb}KB"
        else:
            return f"{b}B"
