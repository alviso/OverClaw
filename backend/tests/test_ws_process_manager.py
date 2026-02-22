"""
WebSocket RPC Tests for Process Manager
Tests workspace.processes and workspace.cleanup_processes RPC methods
"""
import asyncio
import json
import websockets
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://smart-workflow-71.preview.emergentagent.com')
WS_URL = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/gateway'
GATEWAY_TOKEN = "dev-token-change-me"


async def send_rpc(ws, method, params=None, req_id=1):
    """Send an RPC request and wait for response"""
    msg = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {}
    }
    await ws.send(json.dumps(msg))
    
    # Wait for response with matching id
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(raw)
        if data.get("id") == req_id:
            return data
        # Skip events/notifications


async def test_workspace_processes():
    """Test workspace.processes RPC method"""
    print("\n=== Testing workspace.processes RPC ===")
    
    async with websockets.connect(WS_URL) as ws:
        # Wait for welcome
        welcome = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"Got welcome: {welcome[:100]}...")
        
        # Authenticate
        auth_resp = await send_rpc(ws, "connect", {"token": GATEWAY_TOKEN}, req_id=1)
        if "error" in auth_resp:
            print(f"❌ Auth failed: {auth_resp}")
            return False
        print(f"✓ Authenticated: {auth_resp.get('result', {}).get('client_id')}")
        
        # Call workspace.processes
        resp = await send_rpc(ws, "workspace.processes", {}, req_id=2)
        
        if "error" in resp:
            print(f"❌ workspace.processes error: {resp['error']}")
            return False
        
        result = resp.get("result", {})
        processes = result.get("processes", [])
        count = result.get("count", 0)
        
        print(f"✓ workspace.processes returned {count} processes")
        for proc in processes:
            print(f"  - {proc.get('name')} (pid={proc.get('pid')}) [{proc.get('status')}]")
        
        return True


async def test_workspace_cleanup_processes():
    """Test workspace.cleanup_processes RPC method"""
    print("\n=== Testing workspace.cleanup_processes RPC ===")
    
    async with websockets.connect(WS_URL) as ws:
        # Wait for welcome
        await asyncio.wait_for(ws.recv(), timeout=5)
        
        # Authenticate
        auth_resp = await send_rpc(ws, "connect", {"token": GATEWAY_TOKEN}, req_id=1)
        if "error" in auth_resp:
            print(f"❌ Auth failed: {auth_resp}")
            return False
        
        # Call workspace.cleanup_processes
        resp = await send_rpc(ws, "workspace.cleanup_processes", {}, req_id=2)
        
        if "error" in resp:
            print(f"❌ workspace.cleanup_processes error: {resp['error']}")
            return False
        
        result = resp.get("result", {})
        ok = result.get("ok")
        removed = result.get("removed", 0)
        remaining = result.get("remaining", 0)
        
        print(f"✓ workspace.cleanup_processes returned: ok={ok}, removed={removed}, remaining={remaining}")
        return True


async def test_start_and_cleanup_zombie_process():
    """Test that starting a process with duplicate name auto-cleans dead processes"""
    print("\n=== Testing zombie process auto-cleanup ===")
    
    async with websockets.connect(WS_URL) as ws:
        # Wait for welcome
        await asyncio.wait_for(ws.recv(), timeout=5)
        
        # Authenticate
        auth_resp = await send_rpc(ws, "connect", {"token": GATEWAY_TOKEN}, req_id=1)
        if "error" in auth_resp:
            print(f"❌ Auth failed: {auth_resp}")
            return False
        
        # Start a quick process that will exit immediately
        start_resp = await send_rpc(ws, "workspace.start_process", {
            "command": "echo 'quick exit' && sleep 0.1",
            "name": "test-zombie-cleanup",
            "working_directory": "."
        }, req_id=2)
        
        if "error" in start_resp:
            print(f"❌ Failed to start process: {start_resp['error']}")
            return False
        
        result = start_resp.get("result", {})
        print(f"✓ Started process: {result.get('message', result)}")
        
        # Wait for process to exit
        await asyncio.sleep(1)
        
        # Try to start another process with the same name
        # This should work because the first one is dead and should be auto-cleaned
        start_resp2 = await send_rpc(ws, "workspace.start_process", {
            "command": "echo 'second process' && sleep 0.5",
            "name": "test-zombie-cleanup",
            "working_directory": "."
        }, req_id=3)
        
        result2 = start_resp2.get("result", {})
        if "error" in start_resp2:
            print(f"❌ Failed to start second process (zombie not cleaned): {start_resp2['error']}")
            return False
        
        print(f"✓ Second process with same name started (zombie was auto-cleaned): {result2.get('message', result2)}")
        
        # Cleanup
        await asyncio.sleep(1)
        await send_rpc(ws, "workspace.stop_process", {"name": "test-zombie-cleanup"}, req_id=4)
        
        return True


async def main():
    """Run all WebSocket RPC tests"""
    results = []
    
    try:
        results.append(("workspace.processes", await test_workspace_processes()))
    except Exception as e:
        print(f"❌ workspace.processes test failed: {e}")
        results.append(("workspace.processes", False))
    
    try:
        results.append(("workspace.cleanup_processes", await test_workspace_cleanup_processes()))
    except Exception as e:
        print(f"❌ workspace.cleanup_processes test failed: {e}")
        results.append(("workspace.cleanup_processes", False))
    
    try:
        results.append(("zombie_auto_cleanup", await test_start_and_cleanup_zombie_process()))
    except Exception as e:
        print(f"❌ zombie_auto_cleanup test failed: {e}")
        results.append(("zombie_auto_cleanup", False))
    
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    all_passed = True
    for name, passed in results:
        status = "✓ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
