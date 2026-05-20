import os
import time
import subprocess
import pytest
import httpx

@pytest.mark.timeout(120)
def test_end_to_end_orchestrator_integration():
    """
    Spawns the Orchestrator on the host in development mode,
    creates a session (which spawns a real agent-workspace-mcp container),
    calls tools via the gateway proxy, and terminates the session.
    """
    # 1. Define configuration environment variables
    env = os.environ.copy()
    env["ORCHESTRATOR_MODE"] = "development"
    env["ORCHESTRATOR_API_KEY"] = "integration-secret-key"
    env["AGENT_IMAGE"] = "agent-workspace-mcp:latest"
    env["BASE_WORKSPACE_DIR"] = "/tmp/mcp-workspaces-integration"
    
    # 2. Spin up Uvicorn Orchestrator server in the background
    port = 49123
    log_file = open("/tmp/orchestrator.log", "w")
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "orchestrator.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd="/home/martin/projects/agent-workspace-mcp/.worktrees/http-transport/services/orchestrator",
        env=env,
        stdout=log_file,
        stderr=log_file
    )
    
    # Wait for server to boot up
    time.sleep(3)
    
    gateway_url = f"http://127.0.0.1:{port}"
    headers = {"Authorization": "Bearer integration-secret-key"}
    
    session_id = None
    
    import queue
    import threading
    import json

    try:
        # 3. Initialize dynamic session
        print("\n[E2E] Requesting new isolated workspace session...")
        with httpx.Client() as client:
            res = client.post(f"{gateway_url}/api/sessions", headers=headers, timeout=20.0)
            assert res.status_code == 200, f"Failed: {res.text}"
            session_data = res.json()
            session_id = session_data["session_id"]
            print(f"[E2E] Session successfully created: {session_id}")
            
            # Let the spawned agent container finish booting and starting Uvicorn
            print("[E2E] Waiting for agent container warmup...")
            time.sleep(3)
            
            try:
                # Verify listed in sessions
                list_res = client.get(f"{gateway_url}/api/sessions", headers=headers)
                assert list_res.status_code == 200
                active_sessions = list_res.json()
                assert any(s["session_id"] == session_id for s in active_sessions)
                
                # Start SSE background consumer
                sse_events = queue.Queue()
                stop_sse = threading.Event()
                
                def consume_sse():
                    try:
                        with httpx.Client(timeout=None) as sse_client:
                            with sse_client.stream("GET", f"{gateway_url}/mcp/{session_id}/sse", headers=headers) as stream:
                                current_event = None
                                for line in stream.iter_lines():
                                    if stop_sse.is_set():
                                        break
                                    if not line:
                                        continue
                                    if line.startswith("event:"):
                                        current_event = line.replace("event:", "").strip()
                                    elif line.startswith("data:"):
                                        data = line.replace("data:", "").strip()
                                        sse_events.put({"event": current_event, "data": data})
                                        current_event = None
                    except Exception as e:
                        print(f"[E2E] SSE stream thread error: {e}")
                
                sse_thread = threading.Thread(target=consume_sse, daemon=True)
                sse_thread.start()
                
                # Wait for endpoint event
                print("[E2E] Waiting for endpoint event on SSE stream...")
                endpoint_event = None
                for _ in range(50):
                    try:
                        ev = sse_events.get(timeout=0.2)
                        if ev["event"] == "endpoint":
                            endpoint_event = ev
                            break
                    except queue.Empty:
                        continue
                        
                assert endpoint_event is not None, "Failed to receive endpoint event from SSE stream"
                post_endpoint = endpoint_event["data"]
                post_url = f"{gateway_url}{post_endpoint}"
                print(f"[E2E] Discovered target POST URL: {post_url}")
                
                # 3.5. Perform MCP Initialization Handshake
                print("[E2E] Performing MCP initialization handshake...")
                init_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "integration-test-client",
                            "version": "1.0.0"
                        }
                    },
                    "id": 0
                }
                init_res = client.post(post_url, headers=headers, json=init_payload, timeout=20.0)
                assert init_res.status_code in [200, 202], f"Init POST Failed: {init_res.text}"
                
                # Wait for initialize response on SSE stream
                init_response_event = None
                for _ in range(50):
                    try:
                        ev = sse_events.get(timeout=0.2)
                        if ev["event"] == "message":
                            data = json.loads(ev["data"])
                            if data.get("id") == 0:
                                init_response_event = data
                                break
                    except queue.Empty:
                        continue
                assert init_response_event is not None, "Failed to receive initialize response"
                print("[E2E] Received initialize response, sending initialized notification...")
                
                # Send initialized notification
                initialized_payload = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                initialized_res = client.post(post_url, headers=headers, json=initialized_payload, timeout=20.0)
                assert initialized_res.status_code in [200, 202], f"Initialized Notification Failed: {initialized_res.text}"
                print("[E2E] Initialization complete.")
    
                # 4. Proxy JSON-RPC Tool Call: write_file
                print("[E2E] Calling write_file tool via proxy gateway...")
                rpc_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "write_file",
                        "arguments": {
                            "filepath": "hello.txt",
                            "content": "Hello from Multi-Tenant E2E integration test!"
                        }
                    },
                    "id": 1
                }
                
                rpc_res = client.post(post_url, headers=headers, json=rpc_payload, timeout=20.0)
                assert rpc_res.status_code in [200, 202], f"POST Failed: {rpc_res.text}"
                
                # Wait for response on SSE stream
                rpc_response_event = None
                for _ in range(50):
                    try:
                        ev = sse_events.get(timeout=0.2)
                        if ev["event"] == "message":
                            data = json.loads(ev["data"])
                            if data.get("id") == 1:
                                rpc_response_event = data
                                break
                    except queue.Empty:
                        continue
                        
                assert rpc_response_event is not None, "Failed to receive write_file response from SSE stream"
                assert "error" not in rpc_response_event, f"RPC returned error: {rpc_response_event}"
                print("[E2E] write_file execution successful.")
                
                # 5. Proxy JSON-RPC Tool Call: run_bash
                print("[E2E] Calling run_bash tool via proxy gateway...")
                rpc_payload_bash = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "run_bash",
                        "arguments": {
                            "command": "cat hello.txt"
                        }
                    },
                    "id": 2
                }
                
                rpc_res_bash = client.post(post_url, headers=headers, json=rpc_payload_bash, timeout=20.0)
                assert rpc_res_bash.status_code in [200, 202]
                
                # Wait for response on SSE stream
                rpc_response_bash_event = None
                for _ in range(50):
                    try:
                        ev = sse_events.get(timeout=0.2)
                        if ev["event"] == "message":
                            data = json.loads(ev["data"])
                            if data.get("id") == 2:
                                rpc_response_bash_event = data
                                break
                    except queue.Empty:
                        continue
                        
                assert rpc_response_bash_event is not None, "Failed to receive run_bash response from SSE stream"
                assert "error" not in rpc_response_bash_event
                
                content = rpc_response_bash_event["result"]["content"][0]["text"]
                assert "Hello from Multi-Tenant E2E" in content, f"Unexpected content: {content}"
                print(f"[E2E] run_bash output: {content.strip()}")
            except AssertionError as ae:
                print("--- AGENT CONTAINER LOGS ON FAILURE ---")
                try:
                    logs_proc = subprocess.run(["docker", "logs", f"mcp-agent-{session_id}"], capture_output=True, text=True)
                    print("STDOUT:", logs_proc.stdout)
                    print("STDERR:", logs_proc.stderr)
                except Exception as e:
                    print(f"Failed to fetch docker logs: {e}")
                print("--- ORCHESTRATOR LOG ON FAILURE ---")
                try:
                    with open("/tmp/orchestrator.log", "r") as f:
                        print(f.read())
                except Exception as e:
                    print(f"Failed to read orchestrator log: {e}")
                raise ae
            
            # Stop background SSE consumer
            stop_sse.set()
            sse_thread.join(timeout=1.0)
            
    finally:
        # 6. Tear down session
        if session_id and proc.poll() is None:
            print("[E2E] Terminating session and cleaning up...")
            try:
                with httpx.Client() as client:
                    del_res = client.delete(f"{gateway_url}/api/sessions/{session_id}", headers=headers, timeout=20.0)
                    assert del_res.status_code == 200
                    print("[E2E] Workspace cleanly pruned.")
            except Exception as e:
                print(f"[E2E] Cleanup request failed: {e}")
                
        # Stop Uvicorn server
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
