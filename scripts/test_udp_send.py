"""Send test UDP packet to verify connectivity to Oculus Go."""
import socket
import time

def send_test_packet():
    """Send UDP packet to Oculus Go."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    pacific_ip = "192.168.1.57"
    test_port = 5556
    
    message = "TEST_FROM_PC:Hello_Pacific"
    
    print("=" * 60)
    print("📤 Sending test packet to Pacific")
    print("=" * 60)
    print(f"Target: {pacific_ip}:{test_port}")
    print(f"Message: {message}")
    print("=" * 60)
    
    try:
        sock.sendto(message.encode('utf-8'), (pacific_ip, test_port))
        print("✅ Packet sent successfully")
    except Exception as e:
        print(f"❌ Error sending packet: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    send_test_packet()
