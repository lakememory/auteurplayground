from pythonosc import udp_client
import argparse
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1",
                        help="The IP address of the Ableton OSC server")
    parser.add_argument("--port", type=int, default=11000,
                        help="The port of the Ableton OSC server")
    args = parser.parse_args()

    # Initialize OSC client
    client = udp_client.SimpleUDPClient(args.ip, args.port)
    
    print("Emotion Controller Ready")
    print("Commands: 'd' for Daytime, 'n' for Nocturnal, 'q' to quit")
    
    try:
        while True:
            command = input("> ").lower().strip()
            
            if command == 'd':
                # Launch Daytime scene (Scene 1)
                print("Switching to Daytime mode...")
                client.send_message("/live/scene/fire", [0])  # Scene index is zero-based
                
            elif command == 'n':
                # Launch Nocturnal scene (Scene 2)
                print("Switching to Nocturnal mode...")
                client.send_message("/live/scene/fire", [1])  # Scene index is zero-based
                
            elif command == 'q':
                print("Quitting...")
                break
                
            else:
                print("Unknown command. Use 'd' for Daytime, 'n' for Nocturnal, 'q' to quit")
                
    except KeyboardInterrupt:
        print("\nEmotion Controller stopped.")

if __name__ == "__main__":
    main()