# Test script: test_control_panel.py
import requests

BASE = "http://localhost:4321"

def test_models():
    resp = requests.get(f"{BASE}/api/models/available")
    assert 'models' in resp.json()
    print("✅ Models endpoint works")

def test_audio_settings():
    resp = requests.get(f"{BASE}/api/audio/settings")
    assert 'vad_threshold' in resp.json()
    print("✅ Audio settings endpoint works")

if __name__ == "__main__":
    test_models()
    test_audio_settings()