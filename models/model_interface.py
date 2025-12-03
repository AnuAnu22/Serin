"""
Abstract Model Interface - Base class for all LLM connectors.
This ensures any model backend can be swapped without changing bot code.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class ModelInterface(ABC):
    """
    Abstract interface that all model connectors must implement.
    This allows swapping between LM Studio, vLLM, Safetensors, OpenAI, etc.
    """
    
    @abstractmethod
    def load_model(
        self,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None
    ):
        """
        Initialize and load the model.
        
        Args:
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling threshold (0.0-1.0)
        
        Raises:
            RuntimeError: If model fails to load
        """
        pass
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Generate chat completion response.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate
            stop: Stop sequences
            **kwargs: Additional model-specific parameters
        
        Returns:
            Generated text response
        
        Raises:
            RuntimeError: If generation fails
        """
        pass
    
    @abstractmethod
    async def send_input(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Generate completion from prompt (legacy support).
        
        Args:
            prompt: Input prompt
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate
            stop: Stop sequences
            **kwargs: Additional parameters
        
        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Dict containing:
                - model_name: str
                - model_type: str (llama, qwen, etc.)
                - provider: str (lmstudio, vllm, etc.)
                - temperature: float
                - max_tokens: int
        """
        pass
    
    def blocking_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Blocking version of chat_completion (optional to implement).
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError("Blocking chat completion not implemented for this connector")
    
    def blocking_send_input(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Blocking version of send_input (optional to implement).
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError("Blocking send input not implemented for this connector")
