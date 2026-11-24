"""Which device the extraction models run on, and how many lanes run at once."""

from __future__ import annotations

import os

from src.config import EXTRACTION_DEVICE


def resolve_device(configured: str | None = None):
    """Map ``DOCMIND_DEVICE`` (auto|cpu|cuda|mps) to a Docling AcceleratorDevice.

    ``auto`` picks CUDA, then Apple MPS, then CPU. Returns (device, is_gpu).
    """
    from docling.datamodel.accelerator_options import AcceleratorDevice

    choice = (configured or EXTRACTION_DEVICE or "auto").lower()
    if choice == "cpu":
        return AcceleratorDevice.CPU, False
    if choice == "cuda":
        return AcceleratorDevice.CUDA, True
    if choice == "mps":
        return AcceleratorDevice.MPS, True
    try:
        import torch

        if torch.cuda.is_available():
            return AcceleratorDevice.CUDA, True
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return AcceleratorDevice.MPS, True
    except Exception:
        pass
    return AcceleratorDevice.CPU, False


def cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))  # respects container CPU limits on Linux
    except AttributeError:
        try:
            import psutil

            return len(psutil.Process().cpu_affinity())
        except Exception:
            return os.cpu_count() or 1


def lanes() -> int:
    """Parallel extraction lanes, each with its own models and one thread.

    On two CPU cores, two single-threaded lanes read table pages 35% and
    scanned pages 29% faster than one lane with two threads (measured in M4).
    A GPU runs one lane. Override with ``DOCMIND_EXTRACT_LANES``.
    """
    configured = os.getenv("DOCMIND_EXTRACT_LANES", "auto").lower()
    if configured != "auto":
        return max(1, int(configured))
    _, is_gpu = resolve_device()
    if is_gpu:
        return 1
    return max(1, min(4, cpu_count()))


def threads_per_lane() -> int:
    """Torch threads per lane: the CPU cores shared out, never more.

    ``DOCMIND_NUM_THREADS`` can lower it but not raise it past the share:
    on a 2-core box, 2 lanes x 8 threads (an old .env default) ran about 2x
    slower than 2 lanes x 1 thread, because 16 busy threads fought for 2 cores.
    """
    _, is_gpu = resolve_device()
    share = 4 if is_gpu else max(1, cpu_count() // lanes())
    configured = os.getenv("DOCMIND_NUM_THREADS")
    if configured:
        return max(1, min(int(configured), share))
    return share
