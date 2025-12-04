try:
    from transformers import BlipProcessor, BlipForConditionalGeneration
    print("Transformers available")
except ImportError as e:
    print(f"Transformers NOT available: {e}")
