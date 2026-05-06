"""
Watch Party Synchronization Module
Allows two Stremio RPC ATV instances to sync playback state.

Architecture:
  - One user hosts the party (acts as relay server on a configurable port)
  - Other users connect to the host IP
  - All play/pause/seek events are broadcast to peers
"""

import logging
import threading
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable
import requests

logger = logging.getLogger("stremio-rpc")


class WatchPartyServer:
    """Lightweight HTTP relay server for hosting a watch party"""
    
    def __init__(self, port: int = 5467, on_command: Optional[Callable] = None):
        self.port = port
        self.on_command = on_command
        self.server: Optional[HTTPServer] = None
        self.running = False
        self.peers = []  # List of connected peer IPs
        self.last_state = {}
        
    def start(self):
        if self.running:
            return
            
        handler = self._make_handler()
        self.server = HTTPServer(("0.0.0.0", self.port), handler)
        self.running = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        logger.info(f"[WatchParty] Server started on port {self.port}")
        
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.running = False
            logger.info("[WatchParty] Server stopped")
    
    def broadcast_state(self, state: dict):
        """Send state update to all connected peers"""
        self.last_state = state
        for peer in self.peers[:]:
            try:
                requests.post(
                    f"http://{peer}:{self.port}/party/sync",
                    json=state,
                    timeout=2
                )
            except Exception:
                logger.warning(f"[WatchParty] Peer {peer} unreachable, removing")
                self.peers.remove(peer)
    
    def _make_handler(self):
        server_ref = self
        
        class PartyHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress default HTTP logging
                
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(content_length)) if content_length else {}
                
                if self.path == "/party/join":
                    peer_ip = self.client_address[0]
                    if peer_ip not in server_ref.peers:
                        server_ref.peers.append(peer_ip)
                        logger.info(f"[WatchParty] Peer joined: {peer_ip}")
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "joined", "current_state": server_ref.last_state}).encode())
                    
                elif self.path == "/party/sync":
                    # Received sync command from peer or host
                    if server_ref.on_command:
                        server_ref.on_command(body)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                    
                elif self.path == "/party/leave":
                    peer_ip = self.client_address[0]
                    if peer_ip in server_ref.peers:
                        server_ref.peers.remove(peer_ip)
                        logger.info(f"[WatchParty] Peer left: {peer_ip}")
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"left"}')
                else:
                    self.send_response(404)
                    self.end_headers()
                    
            def do_GET(self):
                if self.path == "/party/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "peers": len(server_ref.peers),
                        "state": server_ref.last_state
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
        
        return PartyHandler


class WatchPartyClient:
    """Client that connects to a watch party host"""
    
    def __init__(self, on_command: Optional[Callable] = None):
        self.host_url = ""
        self.connected = False
        self.on_command = on_command
        self.local_server: Optional[WatchPartyServer] = None
        
    def join(self, host_ip: str, port: int = 5467):
        """Join a watch party hosted by another user"""
        self.host_url = f"http://{host_ip}:{port}"
        
        try:
            res = requests.post(f"{self.host_url}/party/join", json={}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                self.connected = True
                logger.info(f"[WatchParty] Joined party at {host_ip}:{port}")
                
                # Start local listener for incoming sync commands
                # Bug 15: Avoid port collision by using port + 1 for local listener
                self.local_server = WatchPartyServer(port=port + 1, on_command=self.on_command)
                self.local_server.start()
                
                # Apply current state from host
                if data.get("current_state") and self.on_command:
                    self.on_command(data["current_state"])
                    
                return True
        except Exception as e:
            logger.error(f"[WatchParty] Join failed: {e}")
            
        return False
    
    def leave(self):
        if self.connected and self.host_url:
            try:
                requests.post(f"{self.host_url}/party/leave", json={}, timeout=2)
            except Exception:
                pass
            self.connected = False
            if self.local_server:
                self.local_server.stop()
            logger.info("[WatchParty] Left party")
    
    def send_state(self, state: dict):
        """Send our state to the host for broadcast"""
        if not self.connected or not self.host_url:
            return
        try:
            requests.post(f"{self.host_url}/party/sync", json=state, timeout=2)
        except Exception:
            pass


class WatchPartyManager:
    """Unified manager that handles both hosting and joining"""
    
    def __init__(self, config: dict, controller_ref=None):
        self.enabled = config.get("watch_party_enabled", False)
        self.mode = config.get("watch_party_mode", "off")  # "host", "client", "off"
        self.port = config.get("watch_party_port", 5467)
        self.host_ip = config.get("watch_party_host_ip", "")
        self.controller = controller_ref
        
        self.server: Optional[WatchPartyServer] = None
        self.client: Optional[WatchPartyClient] = None
        self._last_broadcast = {}
    
    def start(self):
        if not self.enabled or self.mode == "off":
            return
            
        if self.mode == "host":
            self.server = WatchPartyServer(
                port=self.port,
                on_command=self._handle_remote_command
            )
            self.server.start()
            
        elif self.mode == "client":
            self.client = WatchPartyClient(on_command=self._handle_remote_command)
            self.client.join(self.host_ip, self.port)
    
    def stop(self):
        if self.server:
            self.server.stop()
        if self.client:
            self.client.leave()
    
    def broadcast(self, action: str, position_ms: int = 0):
        """Called from monitor loop on state changes"""
        state = {"action": action, "position": position_ms, "ts": time.time()}
        
        # Deduplicate
        if state.get("action") == self._last_broadcast.get("action"):
            if abs(state.get("position", 0) - self._last_broadcast.get("position", 0)) < 5000:
                return
        self._last_broadcast = state
        
        if self.mode == "host" and self.server:
            self.server.broadcast_state(state)
        elif self.mode == "client" and self.client:
            self.client.send_state(state)
    
    def _handle_remote_command(self, state: dict):
        """Handle incoming sync command from peer"""
        if not self.controller:
            return
            
        action = state.get("action")
        position = state.get("position", 0)
        
        logger.info(f"[WatchParty] Received: {action} @ {position}ms")
        
        if action == "play":
            self.controller.play()
        elif action == "pause":
            self.controller.pause()
        elif action == "seek":
            self.controller.seek_to(position, current_ms=0)

    @property
    def peer_count(self):
        if self.server:
            return len(self.server.peers)
        return 1 if (self.client and self.client.connected) else 0
