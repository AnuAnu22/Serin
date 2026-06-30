from __future__ import annotations

from typing import TYPE_CHECKING

from serin.core.logger import logger
from serin.messaging.context import MessageContext
from serin.messaging.stages import PipelineStage

if TYPE_CHECKING:
    from serin.messaging.context import PipelineDeps


class ActiveSearchStage(PipelineStage):
    async def _run(self, ctx: MessageContext, deps: PipelineDeps) -> None:
        if not deps.active_search:
            return

        logger.info("Entering Thinking Loop...")
        max_loops = 2
        loop_count = 0
        accumulated_results = ""

        while loop_count < max_loops:
            needs_search, query, reason = await deps.active_search.analyze_need_to_search(
                user_message=ctx.user_messages[-1]['content'],
                recent_context=ctx.formatted_context,
                previous_results=accumulated_results if loop_count > 0 else None
            )

            if not needs_search or not query:
                logger.info(f"Thinking complete: No further search needed ({reason})")
                break

            logger.info(f"Thought (Iter {loop_count + 1}): search for '{query}' ({reason})")

            new_results = deps.memory.search_memories(
                query=query,
                user_id=ctx.primary_user_id,
                n_results=3
            )
            logger.info(f"Found {len(new_results)} results")

            if new_results:
                ctx.formatted_context += f"\n\n--- ACTIVE RECALL (Iteration {loop_count + 1}) ---\n"
                ctx.formatted_context += f"Query: {query}\n"
                for mem in new_results:
                    ts = (mem.get('timestamp') or '')[:10]
                    ctx.formatted_context += f"- {mem['content']} (from {ts})\n"

                accumulated_results += f"\nResults for '{query}':\n"
                for mem in new_results:
                    ts = (mem.get('timestamp') or '')[:10]
                    accumulated_results += f"- {mem['content']} (from {ts})\n"

                ctx.active_search_results.extend(new_results)
            else:
                logger.info("   (No results found)")
                accumulated_results += f"\nResults for '{query}': None found.\n"

            loop_count += 1
