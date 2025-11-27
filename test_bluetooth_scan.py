"""Quick Bluetooth scan test to verify bleak/Windows permissions."""
import asyncio
import logging
from bleak import BleakScanner

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def scan_test():
    logger.info("🔍 Starting 10-second Bluetooth scan...")
    logger.info("📱 Make sure your Lovense devices are ON and nearby")
    
    def callback(device, advertisement_data):
        logger.info(f"  Found: {device.name or 'Unknown'} ({device.address}) RSSI={advertisement_data.rssi}")
        if advertisement_data.service_uuids:
            logger.info(f"    Services: {advertisement_data.service_uuids}")
    
    try:
        scanner = BleakScanner(detection_callback=callback)
        await scanner.start()
        await asyncio.sleep(10)
        await scanner.stop()
        
        devices = await scanner.get_discovered_devices()
        logger.info(f"\n✅ Scan complete: Found {len(devices)} total devices")
        
        # Look for Lovense devices
        lovense_devices = [d for d in devices if d.name and 'LVS' in d.name.upper()]
        if lovense_devices:
            logger.info(f"🎯 Found {len(lovense_devices)} Lovense devices:")
            for dev in lovense_devices:
                logger.info(f"  - {dev.name} ({dev.address})")
        else:
            logger.warning("⚠️  No Lovense devices found")
            logger.info("\nTroubleshooting:")
            logger.info("1. Are devices powered ON?")
            logger.info("2. Are devices in pairing mode (light flashing)?")
            logger.info("3. Windows Bluetooth permissions enabled?")
            logger.info("4. Try: Settings > Bluetooth > Turn OFF and back ON")
            
    except Exception as e:
        logger.error(f"❌ Scan failed: {e}")
        logger.error("Windows may need Bluetooth permissions for this app")

if __name__ == "__main__":
    asyncio.run(scan_test())
