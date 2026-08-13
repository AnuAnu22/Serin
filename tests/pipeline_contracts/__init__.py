"""Standing pipeline contract tests — no live services required.

These run as part of the normal ``pytest`` suite with zero external
infrastructure (no Discord, Qdrant, or llamaswap). Each file asserts on the
STRUCTURED data the pipeline assembles: which stage, which field, what content.
"""
