from . import communication
import time
import logging

logging.basicConfig(level=logging.DEBUG)

logger = logging.Logger(__name__)

conn = communication.Connection("/dev/ttyUSB0")
manager = communication.Manager(conn)
manager.launch()
while True:
    for i in range(1, 100):
        logger.debug("Set number to %s" % i)
        message = communication.SevenSegmentDisplay(7, i)
        manager.send(message)
        message = communication.EncoderMotorRun(1, 100)
        manager.send(message)
        message = communication.PirMotionSensorRead(8)
        manager.send(message)
        message = communication.UltrasonicSensorRead(10)
        manager.send(message)
        message = communication.LedMatrixMessage(6, 0, 0, "bye")
        manager.send(message)
        time.sleep(1)
