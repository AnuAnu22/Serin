"""Root DI container — holds singletons created during startup."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.ingest.context.mention_translator import (
        MentionTranslator,
    )
    from serin.d1_1_pipeline_flow.ingest.core.manager import EnhancedMessageManagerV3
    from serin.d1_1_pipeline_flow.ingest.sync.crawler import MessageCrawler
    from serin.d1_1_pipeline_flow.remember.qdrant import QdrantMemorySystem
    from serin.d1_3_state_core.logger import LoggerProtocol

_logger: LoggerProtocol | None = None
_mention_translator: MentionTranslator | None = None
_message_manager: EnhancedMessageManagerV3 | None = None
_crawler: MessageCrawler | None = None
_qdrant: QdrantMemorySystem | None = None


def init_root(
    logger: LoggerProtocol,
) -> None:
    global _logger
    _logger = logger


def get_logger() -> LoggerProtocol:
    if _logger is None:
        raise RuntimeError("Root not initialized")
    return _logger


def set_mention_translator(obj: MentionTranslator) -> None:
    global _mention_translator
    _mention_translator = obj


def get_mention_translator() -> MentionTranslator:
    if _mention_translator is None:
        raise RuntimeError("MentionTranslator not initialized")
    return _mention_translator


def set_message_manager(obj: EnhancedMessageManagerV3) -> None:
    global _message_manager
    _message_manager = obj


def get_message_manager() -> EnhancedMessageManagerV3:
    if _message_manager is None:
        raise RuntimeError("MessageManager not initialized")
    return _message_manager


def set_crawler(obj: MessageCrawler) -> None:
    global _crawler
    _crawler = obj


def get_crawler() -> MessageCrawler:
    if _crawler is None:
        raise RuntimeError("Crawler not initialized")
    return _crawler


def set_qdrant(obj: QdrantMemorySystem) -> None:
    global _qdrant
    _qdrant = obj


def get_qdrant() -> QdrantMemorySystem:
    if _qdrant is None:
        raise RuntimeError("Qdrant not initialized")
    return _qdrant
