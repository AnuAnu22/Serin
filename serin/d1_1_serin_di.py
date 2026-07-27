"""Root DI container — holds singletons created during startup, and owns
every factory function gateway code needs to construct pipeline/state
objects without importing pipeline/state modules directly.

Zero exceptions to Gateway Isolation (Rule 5), including the composition
root (PipelineInitializer). A composition root still needs to know HOW to
build things — that's unavoidable, it's the one file whose job is
building the system — but it doesn't need to import the pipeline/state
modules ITSELF to do that. This module is the seam: it imports
pipeline/state code (that's legal — d1_1_serin_di.py is not itself
inside gateway/, it's root-level), and exposes factory functions that
gateway code calls instead of importing the classes directly. The
distinction that matters: "gateway code knows how to call a factory" is
fine; "gateway code imports and directly instantiates pipeline classes"
is exactly what Rule 5 exists to prevent, since that's what makes
pipeline code hard to test, hard to swap, and hard to reason about in
isolation from Discord.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_3_mention_translator import (
        MentionTranslator,
    )
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_4_core_manager import (
        EnhancedMessageManagerV3,
    )
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_3_ingest_sync.d4_2_sync_crawler import (
        MessageCrawler,
    )
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_3_remember_qdrant import (
        QdrantMemorySystem,
    )
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_4_sync_monitor import (
        MemorySyncMonitor,
    )
    from serin.d1_4_config_base.d2_3_core_logger import LoggerProtocol

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


# --- Factories for classes the composition root constructs ---
# These exist so PipelineInitializer (and anything else in gateway/) can
# build pipeline/state objects by calling a factory here instead of
# importing the class directly. The import happens ONCE, inside this
# function body, in the one module whose job is to own that seam.

def create_mention_translator(client: Any) -> MentionTranslator:
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_1_ingest_context.d4_3_mention_translator import (
        MentionTranslator,
    )
    return MentionTranslator(client)


def create_qdrant_memory_system(data_dir: str, qdrant_host: str, qdrant_port: int) -> QdrantMemorySystem:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_3_remember_qdrant import (
        QdrantMemorySystem,
    )
    return QdrantMemorySystem(data_dir=data_dir, qdrant_host=qdrant_host, qdrant_port=qdrant_port)


def create_message_crawler(
    client: Any, memory_system: Any, background_processor: Any, mention_translator: Any,
) -> MessageCrawler:
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_3_ingest_sync.d4_2_sync_crawler import (
        MessageCrawler,
    )
    return MessageCrawler(client, memory_system, background_processor, mention_translator)


def create_sync_monitor(
    memory_system: Any, background_processor: Any, message_crawler: Any,
) -> MemorySyncMonitor:
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_4_sync_monitor import (
        MemorySyncMonitor,
    )
    return MemorySyncMonitor(memory_system, background_processor, message_crawler)


def create_message_manager(
    client: Any, mention_translator: Any, memory_system: Any, voice_output_manager: Any = None,
) -> EnhancedMessageManagerV3:
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_4_core_manager import (
        EnhancedMessageManagerV3,
    )
    return EnhancedMessageManagerV3(
        client, mention_translator, memory_system, voice_output_manager=voice_output_manager,
    )


def build_message_pipeline(**kwargs: Any) -> MessagePipeline:
    """Thin pass-through to MessagePipeline.build(**kwargs) — the pipeline
    stays in charge of its own construction signature; this function
    exists purely so gateway code doesn't import MessagePipeline itself."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )
    return MessagePipeline.build(**kwargs)


def get_thinking_filter_instance() -> Any:
    from serin.d1_3_state_core.d2_3_model_system.d3_5_model_helpers.d6_1_thinking_filter import (
        get_thinking_filter,
    )
    return get_thinking_filter()


# --- Response generator: module-level state + pure functions ---
# response_generator.py holds a couple of module-level globals
# (discord_client, llama) that gateway code needs to set once at startup
# and read from during voice audio processing. A plain attribute-poke
# from gateway code into a pipeline module is exactly what Rule 5
# forbids; these wrapper functions are the seam instead — gateway calls
# set_response_generator_client(...) / get_llama_connector(), and only
# this file ever imports response_generator directly.

def set_response_generator_client(client: Any) -> None:
    import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator as rg
    rg.discord_client = client


async def initialize_llama_connector() -> None:
    import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator as rg
    await rg.initialize_llama()


def get_llama_connector() -> Any:
    import serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator as rg
    return rg.llama


def get_response_generator_fn() -> Any:
    """The get_response_natural function itself, for passing into
    MessagePipeline.build(response_generator=...)."""
    from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
        get_response_natural,
    )
    return get_response_natural


def build_voice_system_prompt() -> str:
    from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
        build_natural_system_prompt,
    )
    result: str = build_natural_system_prompt()
    return result


# --- db_protect: exception types + protector access ---
# Exception classes are a lower-risk category than live objects/functions
# (they carry no runtime state to synchronize), but "no exceptions" means
# treating them the same way as everything else here: gateway code
# catches them via these re-exports rather than importing the state-layer
# module directly.

def get_database_validation_error_type() -> type[Exception]:
    from serin.d1_3_state_core.d2_1_db_protect import DatabaseValidationError
    return DatabaseValidationError


def get_database_recovery_error_type() -> type[Exception]:
    from serin.d1_3_state_core.d2_1_db_protect import DatabaseRecoveryError
    return DatabaseRecoveryError


def create_database_protector(data_dir: str) -> Any:
    from serin.d1_3_state_core.d2_1_db_protect import DatabaseProtector
    return DatabaseProtector(data_dir)


def get_database_protector_instance() -> Any:
    from serin.d1_3_state_core.d2_1_db_protect import get_database_protector
    return get_database_protector()


# --- Voice pipeline's cross-layer call into the message pipeline ---

async def process_voice_input(manager: Any, **kwargs: Any) -> Any:
    """Thin pass-through so gateway voice code doesn't import the
    pipeline's message-processing entry point directly."""
    from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_5_message_process import (
        process_voice_input as _process_voice_input,
    )
    return await _process_voice_input(manager, **kwargs)
