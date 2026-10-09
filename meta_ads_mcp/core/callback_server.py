"""Callback server for Meta Ads API authentication."""

import threading
import socket
import asyncio
import json
import logging
import webbrowser
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from typing import Dict, Any, Optional

from .utils import logger

# Global token container for communication between threads
token_container = {"token": None, "expires_in": None, "user_id": None}

# Global variables for server thread and state
callback_server_thread = None
callback_server_lock = threading.Lock()
callback_server_running = False
callback_server_port = None
callback_server_instance = None
server_shutdown_timer = None

# Timeout in seconds before shutting down the callback server
CALLBACK_SERVER_TIMEOUT = 180  # 3 minutes timeout


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Print path for debugging, without leaking an access token.
            safe_path = self.path.split("access_token=", 1)[0]
            if "access_token=" in self.path:
                safe_path += "access_token=***"
            print(f"Callback server received request: {safe_path}")
            
            if self.path.startswith("/callback"):
                self._handle_oauth_callback()
            elif self.path.startswith("/token"):
                self._handle_token()
            else:
                # If no matching path, return a 404 error
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"Error processing request: {e}")
            self.send_response(500)
            self.end_headers()
    
    def _handle_oauth_callback(self):
        """Handle OAuth callback after user authorization"""
        # Check if we're being redirected from Facebook with an authorization code
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        
        # Check for code parameter
        code = params.get('code', [None])[0]
        state = params.get('state', [None])[0]
        error = params.get('error', [None])[0]
        
        # Send 200 OK response with a simple HTML page
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        if error:
            # User denied access or other error occurred
            html = f"""
            <html>
            <head><title>Authorization Failed</title></head>
            <body>
                <h1>Authorization Failed</h1>
                <p>Error: {error}</p>
                <p>The authorization was cancelled or failed. You can close this window.</p>
            </body>
            </html>
            """
            logger.error(f"OAuth authorization failed: {error}")
        elif code:
            # Success case - we have the authorization code
            logger.info(f"Received authorization code: {code[:10]}...")
            
            # Store the authorization code temporarily
            # The auth module will exchange this for an access token
            token_container.update({
                "auth_code": code,
                "state": state,
                "timestamp": asyncio.get_event_loop().time()
            })
            
            html = """
            <html>
            <head><title>Authorization Successful</title></head>
            <body>
                <h1>✅ Authorization Successful!</h1>
                <p>You have successfully authorized the Meta Ads MCP application.</p>
                <p>You can now close this window and return to your application.</p>
                <script>
                    // Try to close the window automatically after 2 seconds
                    setTimeout(function() {
                        window.close();
                    }, 2000);
                </script>
            </body>
            </html>
            """
            logger.info("OAuth authorization successful")
        else:
            # No code or error - something unexpected happened
            # Implicit grant (response_type=token) puts the token in the URL
            # fragment, which the browser does not send to this server.
            html = """
            <html>
            <head><title>Completing authorization</title></head>
            <body>
                <h1>Completing authorization...</h1>
                <p id="status">Waiting for the Facebook token.</p>
                <script>
                    (function () {
                        var hash = window.location.hash ? window.location.hash.substring(1) : "";
                        var params = new URLSearchParams(hash);
                        var token = params.get("access_token");
                        var expires = params.get("expires_in") || "";
                        var error = params.get("error");
                        var status = document.getElementById("status");
                        if (error) {
                            status.textContent = "Authorization failed: " + error;
                            return;
                        }
                        if (!token) {
                            status.textContent = "No authorization code or token received. Please try again.";
                            return;
                        }
                        var url = "/token?access_token=" + encodeURIComponent(token)
                            + "&expires_in=" + encodeURIComponent(expires);
                        fetch(url).then(function () {
                            status.textContent = "Authorization successful. You can close this window.";
                        }).catch(function () {
                            status.textContent = "Received the token but could not deliver it to the login process.";
                        });
                    })();
                </script>
            </body>
            </html>
            """
            logger.warning("OAuth callback received without code or error; waiting for implicit-grant token")
        
        self.wfile.write(html.encode())
    
    def _handle_token(self):
        """Store an implicit-grant token, then acknowledge without echoing it."""
        params = parse_qs(urlparse(self.path).query)
        access_token = params.get("access_token", [None])[0]
        expires_in = params.get("expires_in", [None])[0]
        if access_token:
            token_container["token"] = access_token
            if expires_in and str(expires_in).isdigit():
                token_container["expires_in"] = int(expires_in)
            logger.info("Stored implicit-grant access token from callback")

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        response_data = {
            "status": "success",
            "has_token": bool(token_container.get("token")),
        }

        self.wfile.write(json.dumps(response_data).encode())
        
        # The actual token processing is now handled by the auth module
        # that imports this module and accesses token_container
    
    # Silence server logs
    def log_message(self, format, *args):
        return


def shutdown_callback_server():
    """
    Shutdown the callback server if it's running
    """
    global callback_server_thread, callback_server_running, callback_server_port, callback_server_instance, server_shutdown_timer
    
    with callback_server_lock:
        if not callback_server_running:
            print("Callback server is not running")
            return
        
        if server_shutdown_timer is not None:
            server_shutdown_timer.cancel()
            server_shutdown_timer = None
        
        try:
            if callback_server_instance:
                print("Shutting down callback server...")
                callback_server_instance.shutdown()
                callback_server_instance.server_close()
                print("Callback server shut down successfully")
            
            if callback_server_thread and callback_server_thread.is_alive():
                callback_server_thread.join(timeout=5)
                if callback_server_thread.is_alive():
                    print("Warning: Callback server thread did not shut down cleanly")
        except Exception as e:
            print(f"Error during callback server shutdown: {e}")
        finally:
            callback_server_running = False
            callback_server_thread = None
            callback_server_port = None
            callback_server_instance = None


def start_callback_server(preferred_port: int = 8080, *, strict_port: bool = False, timeout_seconds: int = CALLBACK_SERVER_TIMEOUT) -> int:
    """
    Start the callback server and return the port number it's running on.

    Args:
        preferred_port: First port to try. Login uses 8888 to match the
            redirect URI registered with Meta.
        strict_port: When True, fail if preferred_port is busy instead of
            scanning upward.
        timeout_seconds: Auto-shutdown delay.

    Returns:
        int: Port number the server is listening on

    Raises:
        Exception: If the server fails to start
    """
    global callback_server_thread, callback_server_running, callback_server_port, callback_server_instance, server_shutdown_timer
    
    # Check if callback server is disabled
    if os.environ.get("META_ADS_DISABLE_CALLBACK_SERVER"):
        raise Exception("Callback server is disabled via META_ADS_DISABLE_CALLBACK_SERVER environment variable")
    
    with callback_server_lock:
        if callback_server_running:
            print(f"Callback server already running on port {callback_server_port}")
            return callback_server_port
        
        # Find an available port
        port = preferred_port
        max_attempts = 1 if strict_port else 10
        for attempt in range(max_attempts):
            try:
                # Test if port is available
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                break
            except OSError:
                port += 1
        else:
            raise Exception(f"Could not find an available port after {max_attempts} attempts")
        
        callback_server_port = port
        
        # Start the server in a separate thread
        callback_server_thread = threading.Thread(target=server_thread, daemon=True)
        callback_server_thread.start()
        
        # Wait a moment for the server to start
        import time
        time.sleep(0.5)
        
        if not callback_server_running:
            raise Exception("Failed to start callback server")
        
        # Set up automatic shutdown timer
        def auto_shutdown():
            print(f"Callback server auto-shutdown after {timeout_seconds} seconds")
            shutdown_callback_server()
        
        server_shutdown_timer = threading.Timer(timeout_seconds, auto_shutdown)
        server_shutdown_timer.start()
        
        print(f"Callback server started on http://localhost:{port}")
        return port


def server_thread():
    """Thread function to run the callback server"""
    global callback_server_running, callback_server_instance
    
    try:
        callback_server_instance = HTTPServer(('localhost', callback_server_port), CallbackHandler)
        callback_server_running = True
        print(f"Callback server thread started on port {callback_server_port}")
        callback_server_instance.serve_forever()
    except Exception as e:
        print(f"Callback server error: {e}")
        callback_server_running = False
    finally:
        print("Callback server thread finished")
        callback_server_running = False 