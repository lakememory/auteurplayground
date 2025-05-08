from pythonosc import udp_client, dispatcher, osc_server
import threading
import time

class AbletonStateMonitor:
    def __init__(self, ableton_ip="127.0.0.1", send_port=11000, receive_port=11001):
        """Initialize the Ableton state monitor.
        
        Args:
            ableton_ip: IP address of the Ableton OSC server
            send_port: Port to send OSC messages to Ableton (default 11000)
            receive_port: Port to receive OSC messages from Ableton (default 11001)
        """
        # OSC client to send commands to Ableton
        self.client = udp_client.SimpleUDPClient(ableton_ip, send_port)
        
        # State storage for channels 1-9 (indexed as 0-8)
        self.channels = {}
        for i in range(9):
            self.channels[i] = {
                'volume': 0.0,
                'mute': False,
                'playing_clip': None
            }
        
        # Current scene tracking
        self.current_scene = -1
        
        # Set up dispatcher for incoming OSC messages
        self.dispatcher = dispatcher.Dispatcher()
        self._register_handlers()
        
        # Start OSC server to receive messages from Ableton
        self.server = osc_server.ThreadingOSCUDPServer(
            (ableton_ip, receive_port), self.dispatcher)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        
        print(f"Starting Ableton state monitor on port {receive_port}...")
        self.server_thread.start()
        
        # Initialize subscriptions and state
        self._subscribe_to_state_changes()
        self.refresh_state()
        
        # Start periodic refresh
        self.start_periodic_refresh()
    
    def _register_handlers(self):
        """Register handlers for OSC messages from Ableton"""
        # Track volume changes
        self.dispatcher.map("/live/track/volume", self._on_track_volume)
        
        # Track mute state changes
        self.dispatcher.map("/live/track/mute", self._on_track_mute)
        
        # Clip playing status changes
        self.dispatcher.map("/live/clip/playing_status", self._on_clip_playing_status)
        
        # Scene triggered
        self.dispatcher.map("/live/scene/triggered", self._on_scene_triggered)
        
        # Error handler
        self.dispatcher.map("/live/error", self._on_error)
        
    def _subscribe_to_state_changes(self):
        """Tell AbletonOSC to send notifications for state changes"""
        print("Subscribing to Ableton state changes...")
        
        # Subscribe to volume changes for channels 0-8
        for i in range(9):
            self.client.send_message("/live/track/volume/listen", [i, 1])
            self.client.send_message("/live/track/mute/listen", [i, 1])
        
        # Subscribe to clip playing status for all clips
        self.client.send_message("/live/clip/playing_status/listen", [1])
        
        # Subscribe to scene triggers
        self.client.send_message("/live/scene/triggered/listen", [1])
        
    def refresh_state(self):
        """Request a full state refresh from Ableton"""
        print("Refreshing full Ableton state...")
        
        # Get volume for channels 0-8
        for i in range(9):
            self.client.send_message("/live/track/get/volume", [i])
            self.client.send_message("/live/track/get/mute", [i])
            
            # Get playing clip for this track
            self.client.send_message("/live/track/get/playing_slot_index", [i])
    
    def start_periodic_refresh(self, interval=10.0):
        """Start a periodic full state refresh"""
        def refresh_loop():
            while True:
                time.sleep(interval)
                self.refresh_state()
        
        refresh_thread = threading.Thread(target=refresh_loop)
        refresh_thread.daemon = True
        refresh_thread.start()
        print(f"Periodic state refresh enabled (every {interval} seconds)")
    
    # --- Handler methods ---
    
    def _on_track_volume(self, address, *args):
        """Handle track volume change messages"""
        if len(args) >= 2:
            track_index, volume = args[0], args[1]
            
            # Only process channels 0-8
            if 0 <= track_index < 9:
                old_volume = self.channels[track_index].get('volume', 0)
                self.channels[track_index]['volume'] = volume
                
                # Convert to dB for more readable output
                db_value = "-inf" if volume == 0 else f"{20 * math.log10(volume):.1f}"
                
                print(f"Channel {track_index+1} volume: {db_value} dB (raw: {volume:.3f})")
    
    def _on_track_mute(self, address, *args):
        """Handle track mute change messages"""
        if len(args) >= 2:
            track_index, mute_state = args[0], bool(args[1])
            
            # Only process channels 0-8
            if 0 <= track_index < 9:
                self.channels[track_index]['mute'] = mute_state
                print(f"Channel {track_index+1} mute: {mute_state}")
    
    def _on_clip_playing_status(self, address, *args):
        """Handle clip playing status change messages"""
        if len(args) >= 3:
            track_index, clip_index, playing = args[0], args[1], bool(args[2])
            
            # Only process channels 0-8
            if 0 <= track_index < 9:
                if playing:
                    self.channels[track_index]['playing_clip'] = clip_index
                    print(f"Channel {track_index+1} playing clip {clip_index+1}")
                elif self.channels[track_index]['playing_clip'] == clip_index:
                    self.channels[track_index]['playing_clip'] = None
                    print(f"Channel {track_index+1} stopped playing clip {clip_index+1}")
    
    def _on_scene_triggered(self, address, *args):
        """Handle scene triggered messages"""
        if args:
            scene_index = args[0]
            self.current_scene = scene_index
            print(f"Scene {scene_index+1} triggered")
    
    def _on_error(self, address, *args):
        """Handle error messages from AbletonOSC"""
        print(f"Ableton OSC Error: {' '.join(str(arg) for arg in args)}")
    
    # --- Public methods ---
    
    def get_channel_state(self, channel_index):
        """Get the state of a specific channel (1-9)"""
        # Convert from 1-based to 0-based indexing
        index = channel_index - 1
        if 0 <= index < 9:
            return self.channels[index]
        return None
    
    def get_all_channels_state(self):
        """Get the state of all channels"""
        return self.channels
    
    def get_current_scene(self):
        """Get the currently playing scene index"""
        return self.current_scene
    
    def print_current_state(self):
        """Print a formatted summary of the current state"""
        print("\n=== CURRENT ABLETON STATE ===")
        print(f"Active Scene: {self.current_scene + 1 if self.current_scene >= 0 else 'None'}")
        print("\nChannel States:")
        
        for i in range(9):
            vol = self.channels[i]['volume']
            db_value = "-inf" if vol == 0 else f"{20 * math.log10(vol):.1f}"
            
            clip = self.channels[i]['playing_clip']
            clip_str = f"Clip {clip + 1}" if clip is not None else "None"
            
            mute = "Muted" if self.channels[i]['mute'] else "Unmuted"
            
            print(f"  Channel {i+1}: Volume: {db_value} dB, Playing: {clip_str}, {mute}")
        print("===========================\n")


# Example usage
if __name__ == "__main__":
    import math  # For dB conversion
    
    # Create the monitor
    monitor = AbletonStateMonitor()
    
    # Simple command line interface
    print("\nAbleton State Monitor")
    print("Commands:")
    print("  state  - Print current state")
    print("  refresh - Force state refresh")
    print("  q      - Quit")
    
    try:
        while True:
            cmd = input("> ").strip().lower()
            
            if cmd == "state":
                monitor.print_current_state()
            elif cmd == "refresh":
                monitor.refresh_state()
            elif cmd == "q":
                break
            else:
                print("Unknown command")
    
    except KeyboardInterrupt:
        print("\nShutting down state monitor...")