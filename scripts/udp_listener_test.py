"""Test UDP broadcast reception from Android APK"""
import socket
import time

# Bind to UDP port 5556 (same as VR discovery)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(('', 5556))
sock.settimeout(2.0)

print("🔍 Listening for UDP packets on port 5556...")
print("📱 Make sure your Android APK is running and on WiFi!")
print("⏱️  Waiting 60 seconds for broadcasts...")
print()

start_time = time.time()
packet_count = 0

while time.time() - start_time < 60:
    try:
        data, addr = sock.recvfrom(1024)
        packet_count += 1
        message = data.decode('utf-8', errors='ignore')
        print(f"✅ Packet #{packet_count} from {addr[0]}:{addr[1]}")
        print(f"   Content: {message[:100]}")
        print()
    except socket.timeout:
        elapsed = int(time.time() - start_time)
        print(f"⏳ {elapsed}s elapsed, {packet_count} packets received...", end='\r')

sock.close()
print()
print(f"✨ Test complete: {packet_count} packets received in 60 seconds")

if packet_count == 0:
    print()
    print("❌ NO PACKETS RECEIVED! Possible issues:")
    print("   1. Android APK is not running")
    print("   2. APK is not on same WiFi network")
    print("   3. Router has AP isolation enabled (blocks device-to-device)")
    print("   4. Windows Firewall is blocking UDP port 5556")
    print("   5. APK broadcast code is not working")
