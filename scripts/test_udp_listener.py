"""Test UDP listener to verify broadcast reception on port 5556."""
import socket
import time

def test_udp_listener():
    """Listen for UDP broadcasts on port 5556."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', 5556))
    sock.settimeout(1.0)
    
    print("=" * 60)
    print("🔍 UDP Listener Test")
    print("=" * 60)
    print(f"Listening on 0.0.0.0:5556 for UDP broadcasts")
    print(f"Expecting messages from: 192.168.1.57 (Pacific/Oculus Go)")
    print(f"Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                print(f"📥 Received from {addr[0]}:{addr[1]}")
                print(f"   Message: {message}")
                print(f"   Bytes: {len(data)}")
            except socket.timeout:
                print(".", end="", flush=True)
                continue
    except KeyboardInterrupt:
        print("\n\n✅ Test complete")
    finally:
        sock.close()

if __name__ == "__main__":
    test_udp_listener()
