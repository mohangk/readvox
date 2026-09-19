"""Public fingerprints of the exact privately approved historical selection.

The manifest digest binds cloud identities without publishing those identities.
Reference digests independently bind the selected recording bytes. Edited source
manifests or recordings remain importable but do not inherit historical approval.
"""
import hashlib
import json
from pathlib import Path

APPROVED_RUN = '20260913T043114Z-0f3d936a'
APPROVED_MANIFEST_SHA256 = '530d1dccc92aa788c7b405c636791664a33193907811715d2972097b6cd635e4'
APPROVED_REFERENCE_SHA256 = {16: '8181b87c115c1ea8aada90e00ef5da9c979847e1f06de5cedd1fe0170d1485b4', 11: '1d128ef51544d18474bd678e36aed4e468a6db11a6c0ef098880c5072e5a30a1', 6: '143445ee763925bd4a06a7424b38a710eb521be674cbf02027486f14c2ef459a', 1: 'fc34a5d0b7a83d85c461a4a8934da7421aee6dbe10ab8ed24f1b4e7a6395604f'}


def is_approved_legacy(source: Path, original: dict) -> bool:
    """Check exact manifest and reference bytes, without cloud access or writes."""
    try:
        raw = source.read_bytes()
        if (hashlib.sha256(raw).hexdigest() != APPROVED_MANIFEST_SHA256
                or json.loads(raw) != original or original.get('run_id') != APPROVED_RUN):
            return False
        voices = original.get('voices', [])
        if len(voices) != len(APPROVED_REFERENCE_SHA256) or {v.get('number') for v in voices} != set(APPROVED_REFERENCE_SHA256):
            return False
        root = source.resolve().parent.parent if source.resolve().parent.name == APPROVED_RUN else source.resolve().parent
        run_root = (root / APPROVED_RUN).resolve()
        for voice in voices:
            relative = Path(voice['reference_audio'])
            reference = (root / relative).resolve()
            if (relative.is_absolute() or not reference.is_relative_to(run_root)
                    or hashlib.sha256(reference.read_bytes()).hexdigest() != APPROVED_REFERENCE_SHA256[voice['number']]):
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False
