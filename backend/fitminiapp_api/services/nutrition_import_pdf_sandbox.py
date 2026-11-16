"""Fail-closed syscall allowlist for the dedicated PDF adapter process."""

from __future__ import annotations

import ctypes
import errno
import os
import platform

_ALLOW = 0x7FFF0000
_ERRNO = 0x00050000
_SYSCALLS = (
    "read",
    "write",
    "close",
    "fstat",
    "lseek",
    "brk",
    "mmap",
    "mprotect",
    "munmap",
    "mremap",
    "madvise",
    "futex",
    "clock_gettime",
    "getrandom",
    "getpid",
    "gettid",
    "rt_sigaction",
    "rt_sigprocmask",
    "rt_sigreturn",
    "sigaltstack",
    "sched_yield",
    "nanosleep",
    "restart_syscall",
    "exit",
    "exit_group",
)


def install_pdf_sandbox() -> None:
    """Close inherited descriptors and deny every syscall not needed by the parser."""
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("PDF sandbox unsupported")
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise RuntimeError("PDF sandbox unavailable")
    context = library.seccomp_init(_ERRNO | errno.EPERM)
    if not context:
        raise RuntimeError("PDF sandbox unavailable")
    for name in _SYSCALLS:
        number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
        if number < 0 or library.seccomp_rule_add(context, _ALLOW, number, 0) != 0:
            raise RuntimeError("PDF sandbox unavailable")
    for entry in os.listdir("/proc/self/fd"):
        fd = int(entry)
        if fd > 2:
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
    if library.seccomp_load(context) != 0:
        raise RuntimeError("PDF sandbox unavailable")
