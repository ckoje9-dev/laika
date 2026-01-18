"""DXF 파싱 파이프라인."""

from . import parse1_node, parse2_node, dxf_parse  # noqa: F401


async def dxf_parse2(*args, **kwargs):  # noqa: D401
    """parse2_node.run 래퍼: RQ kwargs 호환."""
    return await parse2_node.run(*args, **kwargs)
