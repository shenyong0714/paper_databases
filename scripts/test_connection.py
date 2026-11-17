#!/usr/bin/env python3
"""
Test Supabase connection and credentials.
Usage: python test_connection.py
"""
import os
import sys

print("=" * 60)
print("Supabase Connection Test")
print("=" * 60)

# Check environment variables
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

print("\n1. Environment Variables Check:")
print(f"   SUPABASE_URL: {SUPABASE_URL[:30] if SUPABASE_URL else 'NOT SET'}...")
print(f"   SUPABASE_KEY: {SUPABASE_KEY[:20] if SUPABASE_KEY else 'NOT SET'}...")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("\n❌ ERROR: Environment variables not set")
    print("   Set them with:")
    print("   export SUPABASE_URL='https://xxxxx.supabase.co'")
    print("   export SUPABASE_KEY='your-secret-key'")
    sys.exit(1)

# Test DNS resolution
print("\n2. DNS Resolution Test:")
try:
    import socket
    from urllib.parse import urlparse

    hostname = urlparse(SUPABASE_URL).hostname
    print(f"   Resolving: {hostname}")

    ip = socket.gethostbyname(hostname)
    print(f"   ✓ Resolved to: {ip}")
except Exception as e:
    print(f"   ❌ DNS resolution failed: {e}")
    print(f"   This means the URL format might be wrong")
    sys.exit(1)

# Test HTTP connection
print("\n3. HTTP Connection Test:")
try:
    import urllib.request

    test_url = f"{SUPABASE_URL}/rest/v1/"
    req = urllib.request.Request(test_url, headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    })

    response = urllib.request.urlopen(req, timeout=10)
    print(f"   ✓ Connected successfully (status: {response.status})")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    sys.exit(1)

# Test Supabase client
print("\n4. Supabase Client Test:")
try:
    from supabase import create_client, Client

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"   ✓ Client created")

    # Try to query papers table
    response = supabase.table('papers').select('arxiv_id', count='exact').limit(1).execute()
    print(f"   ✓ Database query successful")
    print(f"   Total papers in database: {response.count}")

except ImportError:
    print(f"   ⚠ supabase package not installed (but connection works)")
except Exception as e:
    print(f"   ❌ Supabase client failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ All tests passed!")
print("=" * 60)
