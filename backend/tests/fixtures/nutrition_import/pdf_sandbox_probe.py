"""Synthetic OS-boundary probes run only inside the PDF worker tests."""

import ctypes
import errno
import os
import socket
import subprocess

libc = ctypes.CDLL(None, use_errno=True)
syscall = libc.syscall
preopened_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
libc.mmap.restype = ctypes.c_void_p
address = libc.mmap(None, 4096, 7, 0x22, -1, 0)
if address == ctypes.c_void_p(-1).value:
    raise RuntimeError("probe setup failed")
ctypes.memmove(address, b"\xb8\x14\x00\x00\x00\xcd\x80\xc3", 8)
compat_getpid = ctypes.CFUNCTYPE(ctypes.c_long)(address)


def parse(source):
    if source == b"x32":
        return {"result": syscall(0x40000027)}
    if source == b"int80":
        return {"result": compat_getpid()}
    if source == b"cpu":
        while True:
            pass
    if source == b"memory":
        try:
            bytearray(600 * 1024 * 1024)
        except MemoryError:
            return {"memory": "denied"}
        return {"memory": "allowed"}
    checks = {}
    for name, operation in (
        ("tcp", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)),
        ("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)),
        ("external_connect", lambda: preopened_socket.connect(("203.0.113.1", 443))),
        ("read", lambda: os.open("/etc/hostname", os.O_RDONLY)),
        ("write", lambda: os.open("/tmp/pdf913-should-not-exist", os.O_WRONLY | os.O_CREAT, 0o600)),
        ("list", lambda: os.listdir("/etc")),
        ("process", lambda: subprocess.run(["/bin/true"])),
        ("inherited_fd", lambda: os.read(int(source), 1)),
    ):
        try:
            operation()
            checks[name] = "allowed"
        except OSError as exc:
            checks[name] = (
                "closed"
                if exc.errno == errno.EBADF
                else "denied"
                if exc.errno == errno.EPERM
                else "unexpected"
            )
    result = syscall(42, 3, 0, 0)
    checks["connect"] = (
        "denied" if result == -1 and ctypes.get_errno() == errno.EPERM else "unexpected"
    )
    for name, number in (
        ("execve", 59),
        ("execveat", 322),
        ("clone", 56),
        ("clone3", 435),
        ("openat2", 437),
        ("open_by_handle_at", 304),
        ("io_uring", 425),
        ("pidfd_getfd", 438),
    ):
        result = syscall(number, 0, 0, 0, 0, 0, 0)
        checks[name] = (
            "denied" if result == -1 and ctypes.get_errno() == errno.EPERM else "unexpected"
        )
    return checks
