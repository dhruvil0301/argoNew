import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import os
import time

class MockDashboardNode:
    def __init__(self):
        self.robot_status = "Idle"
        self.current_position = "Base Station"
        self.battery_level = 85.0
        self.connection_status = "Connected (MOCK)"
        self.target_destination = "Base Station"
        self.distance_to_goal = 0.0
        self.motor_status = "OK"
        self.lidar_status = "Active"
        self.imu_status = "Calibrated"
        
        self.waypoint_queue = []
        self.current_goal_id = None
        
        self.waypoints = {
            0: {"name": "Base Station", "x": 0.0, "y": 0.0},
            1: {"name": "Table 1", "x": -1.5, "y": 1.5},
            2: {"name": "Table 2", "x": 1.5, "y": 1.5},
            3: {"name": "Table 3", "x": -1.5, "y": -1.5},
            4: {"name": "Table 4", "x": 1.5, "y": -1.5},
        }

    def navigate_to_waypoint(self, waypoint_id, mode='shift'):
        try:
            waypoint_id = int(waypoint_id)
        except:
            return
            
        if waypoint_id not in self.waypoints:
            print(f"Invalid waypoint: {waypoint_id}")
            return

        wp = self.waypoints[waypoint_id]

        # ================== QUEUE MODE ==================
        if mode == 'queue':
            if self.robot_status in ['Navigating', 'Paused']:
                self.waypoint_queue.append(waypoint_id)
                print(f"[OK] Queued {wp['name']} | Queue: {self.waypoint_queue}")
                
                current_name = self.waypoints.get(self.current_goal_id, {}).get('name', 'Current')
                self.target_destination = f"{current_name} (+{len(self.waypoint_queue)} queued)"
                return
            else:
                mode = 'shift'  # fallback if idle

        # ================== SHIFT MODE ==================
        if mode == 'shift':
            print(f"[SHIFT] Shift requested. Clearing queue.")
            self.waypoint_queue.clear()

        # Start new navigation
        was_navigating = (self.robot_status == "Navigating")
        
        self.current_goal_id = waypoint_id
        self.target_destination = wp["name"]
        
        if len(self.waypoint_queue) > 0:
            self.target_destination += f" (+{len(self.waypoint_queue)} queued)"
            
        self.robot_status = "Navigating"
        self.distance_to_goal = 5.0
        print(f"[NAV] Navigating to {wp['name']}")

        # Start movement thread only if not already running
        if not was_navigating:
            threading.Thread(target=self.fake_movement, daemon=True).start()

    def fake_movement(self):
        print("[MOVE] Movement thread started")
        
        while self.robot_status in ["Navigating", "Paused"]:
            if self.distance_to_goal > 0 and self.robot_status == "Navigating":
                time.sleep(1)
                self.distance_to_goal = max(0.0, self.distance_to_goal - 1.0)
                
            elif self.distance_to_goal <= 0 and self.robot_status == "Navigating":
                self.distance_to_goal = 0.0
                self.current_position = self.waypoints[self.current_goal_id]["name"]
                print(f"[OK] Reached {self.current_position}")

                if len(self.waypoint_queue) > 0:
                    next_wp = self.waypoint_queue.pop(0)
                    print(f"-> Next in queue: {self.waypoints[next_wp]['name']} | Remaining: {self.waypoint_queue}")
                    
                    # Continue to next waypoint
                    self.current_goal_id = next_wp
                    wp_name = self.waypoints[next_wp]["name"]
                    self.target_destination = wp_name
                    if len(self.waypoint_queue) > 0:
                        self.target_destination += f" (+{len(self.waypoint_queue)} queued)"
                    self.distance_to_goal = 5.0
                else:
                    self.robot_status = "Idle"
                    self.current_goal_id = None
                    self.target_destination = "Base Station"
                    print("[IDLE] All goals completed. Robot Idle.")
                    break
            else:
                time.sleep(0.5)  # Paused
                
        print("[MOVE] Movement thread ended")

    def pause_navigation(self):
        if self.robot_status == "Navigating":
            self.robot_status = "Paused"
            print("[PAUSE] Navigation paused")

    def emergency_stop(self):
        self.robot_status = "Emergency Stop"
        self.waypoint_queue.clear()
        self.current_goal_id = None
        self.distance_to_goal = 0.0
        self.target_destination = "Base Station"
        print("[STOP] EMERGENCY STOP")

    def get_state(self):
        return {
            "robotStatus": self.robot_status,
            "currentPosition": self.current_position,
            "batteryLevel": round(self.battery_level, 1),
            "connectionStatus": self.connection_status,
            "targetDestination": self.target_destination,
            "distanceToGoal": round(self.distance_to_goal, 2),
            "motorStatus": self.motor_status,
            "lidarStatus": self.lidar_status,
            "imuStatus": self.imu_status,
            "currentGoalId": self.current_goal_id,
            "waypointQueue": self.waypoint_queue.copy()
        }


dashboard_node = MockDashboardNode()

class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/api/state':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                state = dashboard_node.get_state()
                self.wfile.write(json.dumps(state).encode())
                
            elif self.path in ['/', '/dashboard.html', '']:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                html_path = os.path.join(script_dir, 'dashboard.html')
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                try:
                    with open(html_path, 'rb') as f:
                        self.wfile.write(f.read())
                except FileNotFoundError:
                    error_msg = f"dashboard.html not found at: {html_path}"
                    print(f"[ERROR] {error_msg}")
                    self.send_error(404, error_msg)
            else:
                # Serve static files relative to the script directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                clean_path = self.path.lstrip('/')
                file_path = os.path.join(script_dir, clean_path)
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    self.send_response(200)
                    if file_path.endswith('.png'):
                        self.send_header('Content-type', 'image/png')
                    elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                        self.send_header('Content-type', 'image/jpeg')
                    elif file_path.endswith('.webp'):
                        self.send_header('Content-type', 'image/webp')
                    elif file_path.endswith('.svg'):
                        self.send_header('Content-type', 'image/svg+xml')
                    elif file_path.endswith('.css'):
                        self.send_header('Content-type', 'text/css')
                    elif file_path.endswith('.js'):
                        self.send_header('Content-type', 'application/javascript')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass # Client disconnected during response
        except Exception as e:
            print(f"Error in do_GET: {e}")
            
    def do_POST(self):
        try:
            if self.path == '/api/command':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                command = json.loads(post_data.decode())
                cmd_type = command.get('command')
                
                if cmd_type == 'navigate':
                    waypoint_id = command.get('waypoint')
                    mode = command.get('mode', 'shift')
                    dashboard_node.navigate_to_waypoint(waypoint_id, mode)
                elif cmd_type == 'pause':
                    dashboard_node.pause_navigation()
                elif cmd_type == 'emergency_stop':
                    dashboard_node.emergency_stop()
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            else:
                self.send_response(404)
                self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass # Client disconnected during response
        except Exception as e:
            print(f"Error in do_POST: {e}")
            
    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"Error in do_OPTIONS: {e}")
        
    def log_message(self, format, *args):
        pass


def run_http_server():
    server = ThreadingHTTPServer(('0.0.0.0', 8080), DashboardHTTPHandler)
    print("[OK] MOCK Dashboard server running on http://0.0.0.0:8080")
    print("Open browser -> http://localhost:8080")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == '__main__':
    run_http_server()