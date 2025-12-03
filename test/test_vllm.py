import os
from openai import OpenAI


def test_vllm_connectivity():
    base_url = os.getenv("LLM_BASE_URL", "http://172.19.88.128:8000/v1")
    client = OpenAI(base_url=base_url, api_key=os.getenv("LLM_API_KEY", "unused"))

    models = client.models.list()
    assert hasattr(models, 'data'), "Models response missing 'data'"
    assert len(models.data) >= 1, "No models available on vLLM endpoint"

    model_id = models.data[0].id
    res = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "Say ok"}],
        max_tokens=4,
        temperature=0
    )
    assert res.choices[0].message.content, "No content generated"


