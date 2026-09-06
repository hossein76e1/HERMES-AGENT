#!/usr/bin/env python3
"""Test registration endpoint and capture error"""
import traceback
import sys

# Patch sys.stderr to capture all output
class TeeWriter:
    def __init__(self):
        self.buffer = []
    def write(self, s):
        self.buffer.append(s)
    def flush(self):
        pass

old_stderr = sys.stderr
sys.stderr = TeeWriter()

try:
    from fastapi.testclient import TestClient
    from api import app
    
    # Reset stderr to terminal for our output
    sys.stderr = old_stderr
    
    client = TestClient(app, raise_server_exceptions=False)
    
    r = client.post('/api/auth/register', json={
        'email': 'testerr@test.com',
        'password': 'test123',
        'full_name': 'Error Test'
    })
    print(f"Status: {r.status_code}")
    print(f"Body: {r.json()}")
    
    # Also check captured stderr
    captured = ''.join(sys.stderr.buffer if hasattr(sys.stderr, 'buffer') else [])
    if captured:
        print(f"\nCaptured errors:\n{captured[:2000]}")
        
except Exception as e:
    sys.stderr = old_stderr
    print(f"Exception: {e}")
    traceback.print_exc()
    sys.stderr = old_stderr
