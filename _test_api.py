"""Quick API smoke test"""
import requests

BASE = "http://localhost:8000"

# 1. Login
resp = requests.post(f"{BASE}/auth/login", json={"username": "testuser", "password": "test123456"})
assert resp.status_code == 200, f"Login failed: {resp.text}"
token = resp.json()["access_token"]
print(f"✅ POST /auth/login — token: {token[:40]}...")

# 2. Get current user
resp = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"})
assert resp.status_code == 200, f"auth/me failed: {resp.text}"
print(f"✅ GET  /auth/me — user: {resp.json()['username']} (id={resp.json()['id']})")

# 3. List prompts
resp = requests.get(f"{BASE}/prompts/", headers={"Authorization": f"Bearer {token}"})
assert resp.status_code == 200, f"List prompts failed ({resp.status_code}): {resp.text}"
data = resp.json()
print(f"✅ GET  /prompts/ — {data['total']} prompts: {[p['name'] for p in data['prompts']]}")

# 4. Get single prompt
resp = requests.get(f"{BASE}/prompts/system", headers={"Authorization": f"Bearer {token}"})
assert resp.status_code == 200, f"Get prompt failed: {resp.text}"
p = resp.json()
print(f"✅ GET  /prompts/system — v{p['version']}: {p['content'][:60]}...")

# 5. Health check (no auth)
resp = requests.get(f"{BASE}/health")
assert resp.status_code == 200
print(f"✅ GET  /health — {resp.json()['status']}")

# 6. Swagger docs available
resp = requests.get(f"{BASE}/docs")
assert resp.status_code == 200
print(f"✅ GET  /docs — Swagger UI available")

# 7. OpenAPI schema
resp = requests.get(f"{BASE}/openapi.json")
assert resp.status_code == 200
print(f"✅ GET  /openapi.json — {len(resp.json()['paths'])} paths registered")

print("\n=== All API tests passed ===")
