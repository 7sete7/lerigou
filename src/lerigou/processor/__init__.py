"""Processador de código para análise e extração de estrutura."""

from lerigou.processor.adapter import CodeToCanvasAdapter
from lerigou.processor.api_matcher import EndpointMatcher, MatchResult
from lerigou.processor.collector import CodeChunk, CodeCollector, CollectedCode
from lerigou.processor.models import APICall, CodeElement, ElementType

__all__ = [
    "APICall",
    "CodeChunk",
    "CodeElement",
    "CollectedCode",
    "CodeCollector",
    "CodeToCanvasAdapter",
    "ElementType",
    "EndpointMatcher",
    "MatchResult",
]
