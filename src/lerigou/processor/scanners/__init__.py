"""Scanners para encontrar endpoints e padrões em repositórios."""

from lerigou.processor.scanners.fastapi import EndpointInfo, FastAPIScanner

__all__ = ["FastAPIScanner", "EndpointInfo"]
