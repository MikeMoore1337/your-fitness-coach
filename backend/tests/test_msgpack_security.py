import gc
import tracemalloc

import msgpack
import pytest


@pytest.mark.parametrize("streaming", [False, True])
def test_invalid_map_keys_do_not_retain_decoded_values(streaming):
    assert msgpack.Unpacker.__module__ == "msgpack._cmsgpack"
    payload = msgpack.packb({42: b"x" * (1024 * 1024)})
    tracing_before = tracemalloc.is_tracing()
    if not tracing_before:
        tracemalloc.start()
    try:
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(8):
            with pytest.raises(ValueError):
                if streaming:
                    unpacker = msgpack.Unpacker()
                    unpacker.feed(payload)
                    try:
                        next(unpacker)
                    finally:
                        del unpacker
                else:
                    msgpack.unpackb(payload)
        gc.collect()
        retained = tracemalloc.get_traced_memory()[0] - before
        assert retained < 2 * 1024 * 1024
    finally:
        if not tracing_before:
            tracemalloc.stop()


def test_valid_map_still_round_trips():
    value = {"key": b"test"}
    assert msgpack.unpackb(msgpack.packb(value)) == value
