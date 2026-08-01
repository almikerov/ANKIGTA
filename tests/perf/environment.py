"""The machine a benchmark run happened on.

Ticket 30 asks for measurements on a documented Windows 4-core/16 GiB/SSD
environment with MTA and Anki. No harness can make a machine be that one, and
one that quietly asserts it is would report a pass from a laptop on battery.

So the run records what it actually ran on, states which of the documented
facts it could confirm, and leaves the rest named as unconfirmed. A number
measured somewhere else is still a number; it is just not the number the ticket
asks for, and the report has to say which it is.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field


#: The documented envelope, from the ticket.
REQUIRED_OS = "Windows"
REQUIRED_CORES = 4
REQUIRED_MEMORY_GIB = 16


@dataclass(frozen=True)
class MachineFacts:
    operating_system: str
    release: str
    processor: str
    logical_cores: int | None
    memory_gib: float | None
    python_version: str
    #: Facts the ticket names that this run could not establish, e.g. that the
    #: database lives on an SSD, or that MTA and Anki were both installed.
    unconfirmed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def matches_reference_envelope(self) -> bool:
        return (
            self.operating_system == REQUIRED_OS
            and self.logical_cores is not None
            and self.logical_cores >= REQUIRED_CORES
            and self.memory_gib is not None
            and self.memory_gib >= REQUIRED_MEMORY_GIB
        )

    def payload(self) -> dict[str, object]:
        return {
            "operatingSystem": self.operating_system,
            "release": self.release,
            "processor": self.processor,
            "logicalCores": self.logical_cores,
            "memoryGiB": self.memory_gib,
            "pythonVersion": self.python_version,
            "matchesReferenceEnvelope": self.matches_reference_envelope,
            "unconfirmed": list(self.unconfirmed),
        }


def _memory_gib() -> float | None:
    """Total physical memory, or `None` when this platform will not say.

    Read through the standard library only. A benchmark that needs a third
    party package to describe the machine is a benchmark that stops running the
    day that package is not installed.
    """
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError):
            return None
        return round(pages * page_size / 1024**3, 2)
    if sys.platform == "win32":
        import ctypes

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / 1024**3, 2)
    return None


def describe_machine(*, mta_server_root: str | None = None) -> MachineFacts:
    unconfirmed: list[str] = [
        # Whether the database sits on an SSD is not readable without asking
        # the platform about the specific device, and a wrong answer here would
        # be worse than an absent one.
        "storage_is_ssd",
        # Anki itself is never launched by an automated check: the companion
        # add-on writes to a real collection, which is the owner's data.
        "anki_desktop_installed",
    ]
    if mta_server_root is None:
        unconfirmed.append("mta_server_available")
    return MachineFacts(
        operating_system=platform.system(),
        release=platform.release(),
        processor=platform.processor() or platform.machine(),
        logical_cores=os.cpu_count(),
        memory_gib=_memory_gib(),
        python_version=platform.python_version(),
        unconfirmed=tuple(unconfirmed),
    )


def disk_free_gib(path: str) -> float | None:
    try:
        return round(shutil.disk_usage(path).free / 1024**3, 2)
    except OSError:
        return None
