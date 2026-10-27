"""TiresIAs: the rotary cache follows the device (upstream kept it on the first one)."""
import pytest
import torch

from model.module import RotaryPositionalEmbedding


def test_cache_recomputed_when_device_changes():
    rope = RotaryPositionalEmbedding(8)
    q = torch.randn(1, 2, 5, 8)
    rope(q, q)                                             # cache on cpu
    rope.cos_cached = rope.cos_cached.to("meta")           # as if computed on another device
    rope.sin_cached = rope.sin_cached.to("meta")
    a, _ = rope(q, q)                                      # upstream: device mismatch here
    assert a.device == q.device


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="needs Apple MPS")
def test_cpu_then_mps():
    rope = RotaryPositionalEmbedding(8)
    q = torch.randn(1, 2, 5, 8)
    ref, _ = rope(q, q)
    rope = rope.to("mps")
    out, _ = rope(q.to("mps"), q.to("mps"))
    assert torch.allclose(out.cpu(), ref, atol=1e-5)
