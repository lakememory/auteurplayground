from pythonosc import udp_client
import argparse
import time
import math
import requests
import threading
import json

# Define states for better readability
STATES = {
    1: "Daytime",  # channels 1-4 up, 5-12 down
    2: "Nocturnal",  # channels 1-4 down, 6-9 up, 10-12 down
    3: "Dodgers",  # channels 1-9 down, 10 up, 11-12 down
    4: "Busy",  # channels 1-10 down, 11 up, 12 down
    5: "Empty"  # channels 1-11 down, 12 up
}

# State channel configurations
STATE_CHANNELS = {
    1: {"up": range(0, 4), "down": range(4, 12)},
    2: {"up": range(5, 9), "down": list(range(0, 5)) + list(range(9, 12))},
    3: {"up": [9], "down": list(range(0, 9)) + list(range(10, 12))},
    4: {"up": [10], "down": list(range(0, 10)) + [11]},
    5: {"up": [11], "down": range(0, 11)}
}

class EmotionController:
    def __init__(self, ip="127.0.0.1", port=11000):
        # Initialize OSC client
        self.client = udp_client.SimpleUDPClient(ip, port)
        self.current_state = None
        self.polling = False
        self.polling_thread = None
        self.polling_interval = 10  # seconds
        self.api_url = "https://sources.auteur-engineering.com/current-state"
        
    def set_volume(self, channel, value, duration=0, steps=1):
        """Set volume for a channel with optional fade duration"""
        if duration <= 0:
            # Immediate change
            self.client.send_message("/live/track/set/volume", [channel, value])
            return
            
        # Calculate fade parameters
        start_value = 0  # Assume starting from silence for simplicity
        step_time = duration / steps
        
        # Perform the fade
        for step in range(steps + 1):
            progress = step / steps
            # Use logarithmic curve for natural volume perception
            fade_value = math.pow(progress, 2) * value
            self.client.send_message("/live/track/set/volume", [channel, fade_value])
            time.sleep(step_time)
    
    def crossfade(self, fade_in_channels, fade_out_channels, duration=3.0, steps=30):
        """Perform a crossfade between sets of channels"""
        step_time = duration / steps
        
        # Perform the crossfade
        for step in range(steps + 1):
            # Calculate progress
            progress = step / steps
            
            # Logarithmic fade-out
            fade_out_value = math.pow(0.92 - progress, 2) if progress < 0.92 else 0
            
            # Logarithmic fade-in
            fade_in_value = math.pow(progress * 0.92, 2)
            
            # Apply fade-out
            for channel in fade_out_channels:
                self.client.send_message("/live/track/set/volume", [channel, fade_out_value])
            
            # Apply fade-in
            for channel in fade_in_channels:
                self.client.send_message("/live/track/set/volume", [channel, fade_in_value])
            
            # Sleep for step_time
            time.sleep(step_time)
    
    def transition_to_state(self, new_state):
        """Transition to a new state with appropriate crossfades"""
        if new_state not in STATES:
            print(f"Error: Invalid state {new_state}")
            return
            
        if self.current_state == new_state:
            print(f"Already in state {new_state} ({STATES[new_state]})")
            return
            
        print(f"Transitioning from {self.current_state or 'None'} to {new_state} ({STATES[new_state]})...")
        
        # Get channels that need to be turned up and down for the new state
        channels_up = STATE_CHANNELS[new_state]["up"]
        channels_down = STATE_CHANNELS[new_state]["down"]
        
        # If we're coming from a defined state, perform a crossfade
        if self.current_state is not None:
            current_up = STATE_CHANNELS[self.current_state]["up"]
            current_down = STATE_CHANNELS[self.current_state]["down"]
            
            # Channels that need to change (fade in or out)
            fade_in = [ch for ch in channels_up if ch in current_down]
            fade_out = [ch for ch in channels_down if ch in current_up]
            
            # Perform the crossfade between changing channels
            self.crossfade(fade_in, fade_out, duration=3.0, steps=30)
            
            # Make sure all channels are in their final state
            for channel in channels_up:
                self.set_volume(channel, 0.84)
            for channel in channels_down:
                self.set_volume(channel, 0.0)
        else:
            # First-time initialization - set all channels directly
            for channel in channels_up:
                self.set_volume(channel, 0.84)
            for channel in channels_down:
                self.set_volume(channel, 0.0)
        
        self.current_state = new_state
        print(f"Now in state {new_state} ({STATES[new_state]})")
    
    def poll_api(self):
        """Poll the API for the current state"""
        try:
            # Add query parameter 'installation=1' to the request
            params = {'installation': 1}
            response = requests.get(self.api_url, params=params, timeout=5)
            if response.status_code == 200:
                try:
                    # Parse JSON response instead of expecting plain integer
                    json_data = response.json()
                    
                    # Extract the state value from the JSON object
                    if 'state' in json_data:
                        state = int(json_data['state'])
                        if state in STATES:
                            print(f"API returned state: {state} ({STATES[state]})")
                            self.transition_to_state(state)
                        else:
                            print(f"Error: API returned invalid state: {state}")
                    else:
                        print(f"Error: API response missing 'state' field: {json_data}")
                except ValueError as e:
                    print(f"Error parsing state value: {e}")
                except json.JSONDecodeError:
                    print(f"Error: API returned invalid JSON: {response.text}")
            else:
                print(f"Error: API returned status code {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error polling API: {e}")
    
    def polling_worker(self):
        """Background worker to poll the API periodically"""
        while self.polling:
            self.poll_api()
            time.sleep(self.polling_interval)
    
    def start_polling(self):
        """Start polling the API in the background"""
        if self.polling:
            print("Already polling API")
            return
            
        self.polling = True
        self.polling_thread = threading.Thread(target=self.polling_worker)
        self.polling_thread.daemon = True
        self.polling_thread.start()
        print(f"Started polling API every {self.polling_interval} seconds")
    
    def stop_polling(self):
        """Stop polling the API"""
        if not self.polling:
            print("Not currently polling API")
            return
            
        self.polling = False
        if self.polling_thread:
            self.polling_thread.join(timeout=1.0)
        print("Stopped polling API")
    
    def set_polling_interval(self, seconds):
        """Set the polling interval"""
        try:
            seconds = float(seconds)
            if seconds < 1:
                print("Polling interval must be at least 1 second")
                return
            self.polling_interval = seconds
            print(f"Set polling interval to {seconds} seconds")
        except ValueError:
            print("Invalid polling interval")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1",
                        help="The IP address of the Ableton OSC server")
    parser.add_argument("--port", type=int, default=11000,
                        help="The port of the Ableton OSC server")
    args = parser.parse_args()

    # Initialize controller
    controller = EmotionController(args.ip, args.port)
    
    print("Advanced Emotion Controller Ready")
    print("Commands:")
    print("1-5 - Manually set state:")
    for state_num, state_name in STATES.items():
        print(f"  {state_num} - {state_name}")
    print("p   - Poll API once")
    print("a   - Start auto-polling API")
    print("s   - Stop auto-polling API")
    print("i N - Set polling interval to N seconds")
    print("q   - Quit")
    
    try:
        while True:
            command = input("> ").lower().strip()
            
            if command in ['1', '2', '3', '4', '5']:
                # Manual state transition
                controller.transition_to_state(int(command))
                
            elif command == 'p':
                # Poll API once
                print("Polling API...")
                controller.poll_api()
                
            elif command == 'a':
                # Start auto-polling
                controller.start_polling()
                
            elif command == 's':
                # Stop auto-polling
                controller.stop_polling()
                
            elif command.startswith('i '):
                # Set polling interval
                try:
                    interval = float(command[2:])
                    controller.set_polling_interval(interval)
                except ValueError:
                    print("Invalid interval. Use 'i N' where N is the number of seconds.")
                
            elif command == 'q':
                print("Quitting...")
                controller.stop_polling()
                break
                
            else:
                print("Unknown command.")
                
    except KeyboardInterrupt:
        print("\nAdvanced Emotion Controller stopped.")
        controller.stop_polling()

if __name__ == "__main__":
    main()