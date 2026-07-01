"""
Model Adapter - Handles format differences between model families.
Detects model type and applies correct chat format, stop tokens, etc.
"""
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from serin.state.logger import logger


class ModelDetector:
    """Automatically detect model family from model name"""

    @staticmethod
    def detect_type(model_name: str) -> str:
        """
        Detect model type from name.

        Args:
            model_name: Model identifier

        Returns:
            Model type: llama, qwen, deepseek, gemma, phi, mistral, gpt, claude
        """
        if not model_name:
            return "llama"  # Default

        name_lower = model_name.lower()

        # Check model families
        if "qwen" in name_lower:
            return "qwen"
        elif "deepseek" in name_lower:
            return "deepseek"
        elif "gemma" in name_lower:
            return "gemma"
        elif "phi" in name_lower:
            return "phi"
        elif "mistral" in name_lower:
            return "mistral"
        elif "gpt" in name_lower or "chatgpt" in name_lower:
            return "gpt"
        elif "claude" in name_lower:
            return "claude"
        elif "llama" in name_lower or "llama3" in name_lower or "llama-3" in name_lower:
            return "llama"
        else:
            # Default to llama for unknown models
            logger.warning(f" Unknown model type '{model_name}', defaulting to llama format")
            return "llama"


# Model-specific configurations
MODEL_CONFIG = {
    "llama": {
        "stop_tokens": ["<|eot_id|>", "<|end_of_text|>"],
        "strip_tokens": ["<|start_header_id|>", "<|end_header_id|>", "<|begin_of_text|>"],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    },
    "qwen": {
        "stop_tokens": ["<|im_end|>", "<|endoftext|>"],
        "strip_tokens": ["<|im_start|>"],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<thought>.*?</thought>',
        ]
    },
    "deepseek": {
        "stop_tokens": ["</s>", "<|end|>"],
        "strip_tokens": ["<|system|>", "<|user|>", "<|assistant|>"],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'\[Reasoning\].*?\[/Reasoning\]',
            r'<reasoning>.*?</reasoning>',
        ]
    },
    "gemma": {
        "stop_tokens": ["<end_of_turn>", "<eos>"],
        "strip_tokens": ["<start_of_turn>", "<bos>"],
        "thinking_patterns": [
            # Gemma 4 uses <|channel>thought ... <channel|> for reasoning.
            # When served via llama.cpp --jinja, thinking goes to reasoning_content.
            # These patterns catch leaked thinking tokens in content.
            r'<\|channel\|>thought\n.*?\n<channel\|>',
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    },
    "phi": {
        "stop_tokens": ["<|end|>", "<|endoftext|>"],
        "strip_tokens": ["<|system|>", "<|user|>", "<|assistant|>"],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    },
    "mistral": {
        "stop_tokens": ["</s>", "[/INST]"],
        "strip_tokens": ["[INST]", "[/INST]"],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    },
    "gpt": {
        "stop_tokens": [],  # GPT API handles this
        "strip_tokens": [],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    },
    "claude": {
        "stop_tokens": [],  # Claude API handles this
        "strip_tokens": [],
        "thinking_patterns": [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
        ]
    }
}


class ModelAdapter:
    """
    Adapter that handles model-specific formatting and token management.
    Makes any model work with the same bot code.
    """

    def __init__(self, model_name: str) -> None:
        """
        Initialize adapter for specific model.

        Args:
            model_name: Name/identifier of the model
        """
        self.model_name = model_name
        self.model_type = ModelDetector.detect_type(model_name)
        self.config = MODEL_CONFIG.get(self.model_type, MODEL_CONFIG["llama"])

        logger.info(f" Model adapter initialized: {self.model_type} ({model_name})")

    def format_messages(self, messages: list[dict]) -> list[dict]:
        """
        Format messages for specific model.
        For OpenAI-compatible APIs, this returns messages as-is.
        For raw model inference, this would convert to model-specific format.

        Args:
            messages: Standard message format [{"role": "system/user/assistant", "content": "..."}]

        Returns:
            Formatted messages (for OpenAI API, unchanged; for others, converted)
        """
        # For OpenAI-compatible APIs (LM Studio, vLLM, etc.), no conversion needed
        # The API server handles the model-specific formatting
        return messages

    def clean_response(self, response: str) -> str:
        """
        Clean model-specific tokens and artifacts from response.

        Args:
            response: Raw model output

        Returns:
            Cleaned response text
        """
        if not response:
            return ""

        cleaned = response

        # Step 1: Strip model-specific tokens
        for token in self.config["strip_tokens"]:
            cleaned = cleaned.replace(token, "")

        # Step 2: Strip thinking tags (model-specific patterns)
        for pattern in self.config["thinking_patterns"]:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)

        # Step 3: Strip common artifacts
        # Remove name prefixes (Serin:, Assistant:, etc.)
        cleaned = re.sub(r"(?im)^\s*\w+:\s*", "", cleaned)

        # Step 4: Clean excessive whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
        cleaned = re.sub(r' +', ' ', cleaned)

        # Step 5: Strip leading/trailing whitespace
        cleaned = cleaned.strip()

        return cleaned

    def get_stop_tokens(self) -> list[str]:
        """
        Get stop tokens for this model.

        Returns:
            List of stop token strings
        """
        return self.config["stop_tokens"]

    def get_thinking_patterns(self) -> list[str]:
        """
        Get thinking tag patterns for this model.

        Returns:
            List of regex patterns for thinking tags
        """
        return self.config["thinking_patterns"]

    def supports_system_role(self) -> bool:
        """
        Check if model supports system role in chat.

        Returns:
            True if system role is supported
        """
        # Most modern models support system role
        # Only very old models might not
        return True

    def get_model_type(self) -> str:
        """
        Get detected model type.

        Returns:
            Model type string
        """
        return self.model_type
