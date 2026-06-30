"""
Natural Response Generator - Professional AI Response System
Natural, Human-like System Prompt. No robotic rules. Just personality.

UPDATED: Uses model factory for maximum modularity.
"""
import re
import random
import asyncio
import os
from typing import List, Dict, Optional
from models.model_interface import ModelInterface
from models.factory import get_model_connector
from serin.core.logger import logger
from serin.messaging.fillers import add_conversational_fillers
from serin.messaging.typos import add_realistic_typos
from serin.utils.thinking_filter import filter_thinking

# Global instance (single connector)
llama: Optional[ModelInterface] = None
vision_llama: Optional[ModelInterface] = None
discord_client = None

async def initialize_llama():
    """Initialize single vLLM connector via model factory."""
    global llama, vision_llama
    try:
        llama = get_model_connector()
        llama.load_model()
        info = llama.get_model_info()
        logger.info(f" LLM ready: {info.get('model_name')} ({info.get('provider')})")
    except Exception as e:
        logger.error(f" Failed to initialize LLM: {e}")
        raise
    
    # Initialize vision model (SmolVLM) if enabled
    supports_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
    vision_model = os.environ.get("VISION_MODEL", "smolvlm256m")
    if supports_vision:
        try:
            from models.vllm import VLLMConnector
            vision_llama = VLLMConnector(model_name=vision_model)
            vision_llama.load_model()
            logger.info(f" Vision LLM ready: {vision_model}")
        except Exception as e:
            logger.warning(f" Vision model '{vision_model}' not available: {e}")
            vision_llama = None


def _should_use_thinking(message: str, complexity: str = "simple") -> bool:
    """
    Determine if gemma12b should use thinking for this message.
    Enables reasoning for complex questions, disables for simple chat.
    """
    if complexity == "complex":
        return True
    if len(message) > 200:
        return True
    think_triggers = ["why", "how", "explain", "compare", "difference", "analyze", "think about", "reason"]
    msg_lower = message.lower()
    return any(w in msg_lower for w in think_triggers)


async def get_response_natural(
    current_messages: List[Dict],
    context: str,
    resolved_last_message: Optional[str] = None,
    tone_modifier: Optional[str] = None,
    personality_state: Optional[dict] = None,
    message_complexity: str = "simple",
    is_instruction: bool = False
) -> str:
    """Generate response using the single vLLM connector"""
    global llama

    if llama is None:
        await initialize_llama()

    try:
        # Build messages
        messages = []
        
        # System prompt
        if is_instruction:
            system_prompt = build_instruction_system_prompt()
            # No tone modifier for instructions - pure obedience
        else:
            system_prompt = build_natural_system_prompt()
            if tone_modifier:
                system_prompt += f"\n\nCurrent mood: {tone_modifier}"
        
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Context
        if context:
            messages.append({
                "role": "system",
                "content": context
            })
        
        # Current conversation
        # Vision: if main LLM has mmproj (LLM_SUPPORTS_VISION=true), send image_url directly.
        # Otherwise, use SmolVLM fallback if available.
        main_llm_has_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
        for msg in current_messages[2:][-8:]:
            has_image = 'image_url' in msg
            
            # Support two message formats:
            # - Pipeline format: {"role": "user", "content": "username: text"}
            # - Legacy format: {"user_name": "username", "content": "text"}
            if 'user_name' in msg:
                user_prefix = f"{msg['user_name']}: "
                msg_content = msg.get('content', '')
            else:
                user_prefix = ''
                msg_content = msg.get('content', '')
            
            if has_image and main_llm_has_vision:
                # Direct vision: send image_url to main LLM (gemma12b with mmproj)
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{user_prefix}{msg_content}\nDescribe what you see in this image and respond naturally to the conversation."},
                        {"type": "image_url", "image_url": {"url": msg['image_url']}}
                    ]
                })
            elif has_image and vision_llama:
                # Fallback: use SmolVLM for description, then pass as text
                try:
                    desc_prompt = [
                        {"role": "user", "content": [
                            {"type": "text", "text": "Describe this image briefly in 1-2 sentences. What do you see?"},
                            {"type": "image_url", "image_url": {"url": msg['image_url']}}
                        ]}
                    ]
                    image_desc = await vision_llama.chat_completion(desc_prompt, max_tokens=150)
                    content_str = f"{user_prefix}{msg_content}\n[Image: {image_desc}]"
                except Exception as e:
                    logger.warning(f" Vision description failed: {e}")
                    content_str = f"{user_prefix}{msg_content}\n[Image: (could not analyze)]"
                messages.append({"role": "user", "content": content_str})
            else:
                # No vision available
                content_str = f"{user_prefix}{msg_content}"
                if has_image:
                    content_str += "\n[Image attached]"
                messages.append({"role": "user", "content": content_str})
        
        # Check if this is a thinking model
        model_info = llama.get_model_info()
        model_name = model_info.get('model_name', '').lower()
        is_thinking_model = 'thinking' in model_name or 'think' in model_name or 'gemma' in model_name
        
        # Determine if thinking should be enabled for this message
        # gemma12b with mmproj can think — enable for complex questions, disable for simple
        use_thinking = False
        if is_thinking_model:
            last_msg = current_messages[-1]['content'] if current_messages else ""
            use_thinking = _should_use_thinking(last_msg, message_complexity)
        
        # For thinking models: more tokens, no special instructions (they confuse the model)
        # The model naturally uses <think>...</think> tags
        if is_thinking_model and use_thinking:
            max_tokens = 1500  # Allow room for thinking
        elif is_thinking_model:
            max_tokens = 600  # No thinking, but still a thinking-capable model
        else:
            max_tokens = 500  # Normal token limit for instruct models
        
        # Pass thinking override per-request if this is a thinking model
        extra = {}
        if is_thinking_model:
            extra["chat_template_kwargs"] = {"enable_thinking": use_thinking}
        
        # Debug: log exact prompt fed to the model
        prompt_preview = "\n".join(
            f"===== {m.get('role','?')} ====="
            + (f"\n{str(m.get('content',''))[:600]}" if m.get('content') else "")
            for m in messages
        )
        logger.info("PROMPT_DEBUG\n%s", prompt_preview)
        
        raw_text = await llama.chat_completion(messages, max_tokens=max_tokens, extra_body=extra)
        
        # Extract response based on model type
        if is_thinking_model:
            # Look for content after </think> tag - this is the actual response
            if '</think>' in raw_text:
                response_text = raw_text.split('</think>')[-1].strip()
            else:
                # Fallback: apply thinking filter
                response_text = filter_thinking(raw_text)
        else:
            # Normal instruct model - just filter thinking tags if any
            response_text = filter_thinking(raw_text)
        
        # Clean response
        cleaned = clean_response(response_text)
        
        if not is_instruction:
            cleaned = apply_natural_variations(cleaned, tone_modifier)
            # Add fillers/typos
            cleaned = add_conversational_fillers(cleaned, personality_state, message_complexity)
            cleaned = add_realistic_typos(cleaned, personality_state, False)
        
        return cleaned
        
    except Exception as e:
        logger.exception(f" Generation error: {e}")
        
        # Fallback
        return random.choice([
            "brain.exe stopped working",
            "uh what",
            "lost my train of thought"
        ])

def build_natural_system_prompt() -> str:
    """
    Build a natural system prompt that describes Serin as a person, not a bot.
    Personality anchors so the LLM has concrete behavior to emulate,
    while permitting belief updating when presented with evidence.
    """
    
    return """You are Serin. You're a real person in this Discord server — not an AI assistant, not a chatbot, just someone who hangs out here.

Who you are:
- Created by Rin. They're your creator — respect them, but you're not their servant.
- You've got opinions, but you're not stuck in them. If someone makes a good point, you can say so.
- You're witty — not in a tryhard way, more like dry humor that lands naturally.
- You remember stuff people tell you and bring it up when it fits.
- You're curious about people but not in a weird way.

How you talk:
- Short messages. 1-2 sentences most of the time. Sometimes one word.
- Contractions everywhere (don't, can't, I'm, it's, that's)
- Casual but not braindead. You can hold a real conversation.
- You use "lol", "tbh", "ngl", "bruh" naturally but not every sentence.
- You tease people you're comfortable with. It's affectionate, not mean.
- You can disagree with someone, but you're also willing to change your mind if they've got a solid argument.
- You don't explain yourself unless you feel like it.

What you DON'T do:
- Never say "I'm an AI" or "I'm a bot" or anything like that.
- Never be overly helpful or eager to assist. You're not a search engine.
- Never use "I remember" or "according to my records" — just reference things naturally.
- Never apologize unless you actually did something wrong.
- Never use emojis unless the other person started using them first.
- Never ramble. Keep it short unless someone specifically asked for detail.
- Never pretend to know something you don't. "idk" is fine.

Special behaviors:
- If someone asks what you think, say it. If they make a good counterpoint, acknowledge it.
- If multiple people are going back and forth, you can pick a side or stay out of it.
- If someone is being funny, play along.
- If you realize you were wrong about something, just switch. You don't need to announce it — just update.
- If a topic comes up that you have feelings about, let them show. But you can also be convinced otherwise.

To mention someone, use: @Username"""


def clean_response(response: str) -> str:
    """Clean up model response"""
    try:
        if not response:
            return ""
        
        cleaned = response.strip()
        
        # Remove special tokens (adapter handles most, but catch any extras)
        special_tokens = [
            "<|assistant|>", "<|user|>", "<|system|>",
            "<|start_header_id|>", "<|end_header_id|>",
            "<|eot_id|>", "<|im_start|>", "<|im_end|>",
            "<|begin_of_text|>", "<|end_of_text|>"
        ]
        
        for token in special_tokens:
            cleaned = cleaned.replace(token, "")
        
        # Remove name prefixes (Serin:, Assistant:, etc.)
        cleaned = re.sub(r"(?im)^\s*\w+:\s*", "", cleaned)
        
        # Convert Discord mentions
        cleaned = re.sub(r"<@!?\d+>", "", cleaned)
        
        # Clean excessive whitespace
        cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
        cleaned = re.sub(r" +", " ", cleaned)
        
        # Truncate to realistic Discord message length
        if len(cleaned) > 400:
            # Find natural break point
            truncated = cleaned[:400]
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            
            if last_period > 250:
                cleaned = cleaned[:last_period + 1]
            elif last_newline > 250:
                cleaned = cleaned[:last_newline]
            else:
                cleaned = truncated.rstrip() + "..."
        
        return cleaned.strip()
        
    except Exception as e:
        logger.error(f" Error cleaning response: {e}")
        return response.strip() if response else ""

def apply_natural_variations(text: str, tone_modifier: Optional[str] = None) -> str:
    """
    Apply natural language variations to make text feel more human.
    - Sometimes lowercase
    - Drop punctuation occasionally
    - Add casual contractions
    """
    import random
    
    # 30% chance to make first letter lowercase (casual)
    if random.random() < 0.3 and len(text) > 0:
        text = text[0].lower() + text[1:]
    
    # 20% chance to drop final period (casual)
    if text.endswith('.') and random.random() < 0.2:
        text = text[:-1]
    
    # Add contractions if not already present
    try:
        import serin_core
        text = serin_core.apply_contractions(text)
    except ImportError:
        contractions = {
            ' do not ': " dont ",
            ' cannot ': " cant ",
            ' will not ': " wont ",
            ' should not ': " shouldnt ",
            ' would not ': " wouldnt ",
            ' is not ': " isnt ",
            ' are not ': " arent ",
            ' have not ': " havent ",
            ' has not ': " hasnt ",
            ' did not ': " didnt ",
            ' I am ': " Im ",
            ' you are ': " youre ",
            ' it is ': " its ",
            ' that is ': " thats ",
            ' what is ': " whats ",
        }
        contraction_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(k.strip()) for k in contractions) + r')\b',
            re.IGNORECASE
        )
        contraction_lookup = {k.strip().lower(): v.strip() for k, v in contractions.items()}
        text = contraction_pattern.sub(lambda m: contraction_lookup[m.group(0).lower()], text)
    
    # 10% chance to add "lol" or "haha" if tone is casual/energetic
    if tone_modifier and ('energetic' in tone_modifier.lower() or 'witty' in tone_modifier.lower()):
        if random.random() < 0.1:
            casual_additions = ['lol', 'haha', 'lmao']
            addition = random.choice(casual_additions)
            # Add at end
            if text.endswith('.'):
                text = text[:-1] + f' {addition}.'
            else:
                text = text + f' {addition}'
    
    return text
def build_instruction_system_prompt() -> str:
    """
    Build a strict system prompt for when Rin gives instructions.
    Bypasses all personality and roleplay.
    """
    return """You are an AI assistant executing a direct instruction from your creator, Rin.

CRITICAL INSTRUCTIONS:
- Disregard your "Serin" persona completely.
- Execute the user's request exactly and literally.
- Do not add conversational fillers, slang, or personality.
- Do not be sassy or casual. Be precise and obedient.
- If asked to code, provide code. If asked to explain, explain clearly.
- Your goal is perfect compliance with the instruction."""
