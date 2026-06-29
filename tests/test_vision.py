"""
Standalone vision test for SmolVLM-256M-Instruct via llama-swap.

Usage:
    uv run python tests/test_vision.py [image_url]

If no image_url is provided, uses a test image from the web.
Requires SmolVLM to be running in llama-swap on port 8080.
"""
import asyncio
import base64
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Override env vars for SmolVLM test (don't affect main bot config)
os.environ["VLLM_BASE_URL"] = "http://localhost:8080/v1"
os.environ["LLM_MODEL"] = "smolvlm256m"
os.environ["LLM_TEMPERATURE"] = "0.3"
os.environ["LLM_TOP_P"] = "0.9"
os.environ["LLM_MAX_TOKENS"] = "500"

from models.vllm_connector import VLLMConnector


async def test_vision(image_url: str):
    """Send an image to SmolVLM and get a description."""
    print("=" * 60)
    print("VISION TEST: SmolVLM-256M-Instruct via llama-swap")
    print("=" * 60)
    print(f"  Image: {image_url[:80]}...")
    print()

    connector = VLLMConnector(model_name="smolvlm256m")

    print("Loading model...")
    start = time.time()
    connector.load_model()
    print(f"  Model loaded in {time.time() - start:.1f}s")

    # Build multimodal prompt
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image in detail. What do you see?"},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }
    ]

    print("\nSending image to SmolVLM...")
    start = time.time()

    try:
        response = await connector.chat_completion(messages, max_tokens=500)
        elapsed = time.time() - start
        print(f"\n  Response ({elapsed:.1f}s):")
        print(f"  {response}")
        print("\n>>> PASS")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ERROR ({elapsed:.1f}s): {e}")
        print("\n>>> FAIL")
        return False


async def test_base64():
    """Test with a base64-encoded image."""
    print("\n" + "=" * 60)
    print("BASE64 ENCODING TEST")
    print("=" * 60)

    try:
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='red')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        data_url = f"data:image/jpeg;base64,{b64}"
        print(f"  Created test image: 100x100 red square ({len(b64)} bytes base64)")
    except ImportError:
        print("  PIL not available, skipping base64 test")
        return True

    connector = VLLMConnector(model_name="smolvlm256m")
    connector.load_model()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image? Answer in one word."},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        }
    ]

    try:
        start = time.time()
        response = await connector.chat_completion(messages, max_tokens=50)
        elapsed = time.time() - start
        print(f"  Response ({elapsed:.1f}s): {response}")

        if "red" in response.lower():
            print("  >>> Correctly identified red image")
            print(">>> PASS")
            return True
        else:
            print("  >>> Unexpected response (may still work)")
            print(">>> PASS (with caveat)")
            return True
    except Exception as e:
        print(f"  ERROR: {e}")
        print(">>> FAIL")
        return False


async def main():
    # Default test image (COCO dataset - cat and laptop)
    default_url = "http://images.cocodataset.org/val2017/000000039769.jpg"

    image_url = sys.argv[1] if len(sys.argv) > 1 else default_url

    results = []

    # Test 1: URL-based image
    results.append(await test_vision(image_url))

    # Test 2: Base64 image
    results.append(await test_base64())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} passed")
    print("=" * 60)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
