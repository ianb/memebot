import serial
import logging
import struct
import time
import threading

logger = logging.getLogger(__name__)

start_time = int(time.time())

def short2bytes(sval):
    val = struct.pack("h", sval)
    return [val[0], val[1]]

def long2bytes(lval):
    val = struct.pack("=l", lval)
    return [val[0], val[1], val[2], val[3]]

def float2bytes(fval):
    val = struct.pack("f", fval)
    return [val[0], val[1], val[2], val[3]]

def char2byte(cval):
    val = struct.pack("b", cval)
    return val[0]

def bytes2string(v):
    return "".join(chr(b) for b in v)

class Connection:

    def __init__(self, port, baudrate=115200, timeout=10):
        self.s = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        self.buffer = []
        self.manager = Manager(self)

    def write(self, v):
        logger.debug("  Sending bytes %r" % v)
        self.s.write(v)

    def on_byte(self, byte):
        # The message starts with 0xff 0x55 ("U"), and ends with
        # 0x0d ("\r") 0x0a ("\n") - if that's found then then buffer is cleared and
        # the message sent
        self.buffer.append(byte)
        state = "look 0xff"
        start = end = None
        for i, c in enumerate(self.buffer):
            if state == "look 0xff" and c == b"\xff":
                state = "look 0x55"
            elif state == "look 0x55":
                if c == b"\x55":
                    state = "look 0x0d"
                    start = i + 1
                else:
                    state = "look 0xff"
            elif state == "look 0x0d" and c == b"\x0d":
                end = i
                state = "look 0x0a"
            elif state == "look 0x0a":
                if c == b"\x0a":
                    # We found it!
                    buffer = self.buffer[start:end]
                    if self.buffer[:start-2]:
                        # This is leading text
                        logging.info("Leading incoming text: %s" % b"".join(self.buffer[:start-2]).decode("UTF-8", "replace"))
                    if not buffer:
                        # It pings with empty message regularly
                        self.buffer = []
                        return
                    ext_id, value = self.parse_message(self.buffer[start:end])
                    logger.info("Received incoming message (%r): ext_id=%r; value=%r" % (self.buffer[start:end], ext_id, value))
                    self.manager.dispatch_message(ext_id, value)
                    self.buffer = []
                    return
                else:
                    state = "look 0x0d"
                    end = None
        # logger.info("Failed to parse buffer: %r" % self.buffer)

    def parse_message(self, message):
        ## FIXME: test if there's any extra data
        logger.info("Parsing message: %r" % message)
        if not message:
            return None, None
        ext_id = ord(message[0])
        type = ord(message[1])
        value = None
        rest = b"".join(message[2:])
        print("incoming", type, rest)
        if type == 1:
            # byte
            value = rest[0]
        elif type == 2:
            # float
            value = struct.unpack("<f", rest[:4])[0]
        # Truncation? Weird bit of code...
        if value and (value < -512 or value > 1023):
            value = 0
        if type == 3:
            # short
            value = struct.unpack("<h", rest[:2])[0]
        elif type == 4:
            # length + string
            length = rest[0]
            value = rest[1:1 + length]
        elif type == 5:
            # double (same as float?)
            value = struct.unpack("<f", rest[:4])[0]
        elif type == 6:
            # long
            value = struct.unpack("<l", rest[:4])[0]
        return ext_id, value

    def poll(self):
        logger.info("Waiting for incoming messages...")
        while True:
            if not self.s.isOpen():
                time.sleep(0.05)
                continue
            c = self.s.read(1)
            # logger.info("Received incoming: %r" % c)
            self.on_byte(c)


class Manager:

    def __init__(self, conn):
        self.conn = conn
        self.handlers = {}
        self.thread = None

    def launch(self):
        self.thread = threading.Thread(target=self.conn.poll)
        self.thread.start()

    def send(self, handler):
        self.add_handler(handler)
        logger.debug("Added handler for %r" % handler.ext_id)
        handler.time_sent = time.time()
        logger.info("Sending message: %r" % handler)
        handler.send(self.conn)

    def add_handler(self, handler):
        self.handlers.setdefault(handler.ext_id, []).append(handler)

    def dispatch_message(self, ext_id, value):
        handlers = self.handlers.get(ext_id, [])
        if not handlers:
            logger.info("No handlers for ext_id=%s -> %r" % (ext_id, value))
        if len(handlers) > 1:
            logger.info("Multiple handlers for ext_id=%s -> %r..." % (ext_id, value))
            logger.info("  Handlers: %r" % handlers)
        for handler in handlers:
            handler.value = value


class Message:

    device_id = None
    _event = None

    def __init__(self, port):
        self.port = port
        self.time_sent = None
        self.time_returned = None

    def __repr__(self):
        sent = returned = value = ""
        if self.time_sent:
            sent = " sent %s" % self._format_time(self.time_sent)
        if self.time_returned:
            returned = " returned %s" % self._format_time(self.time_returned)
        if hasattr(self, "_value"):
            value = " value=%r" % value
        return "<%s port=%r%s%s%s>" % (
            self.__class__.__name__,
            self.port,
            sent,
            returned,
            value,
        )

    def wait(self):
        if hasattr(self, "_value"):
            logger.debug("Waiting/no-need on %r" % self)
            return
        if self._event is None:
            self._event = threading.Event()
        self._event.wait()
        logger.debug("Waiting on %r" % self)

    def _format_time(self, t):
        minute = 60
        hour = 60 * minute
        diff = t - start_time
        if diff > 24 * hour:
            return str(t)
        hours = int(diff / hour)
        minutes = int((diff % hour) / minute)
        result = "%0.2fs" % (diff % minute)
        if minutes or hours:
            result = "%im%s" % (minutes, result)
        if hours:
            result = "%ih%s" % (hours, result)
        return result

    @property
    def ext_id(self):
        if not self.device_id:
            ## FIXME: should have a different identifier, I guess
            return self.port & 0xff
        if not self.port:
            return self.device_id & 0xff
        return ((self.port << 4) + self.device_id) & 0xff

    @property
    def value(self):
        if hasattr(self, "_value"):
            return self._value
        raise Exception("Value on %r has not returned" % self)

    @value.setter
    def value_set(self, value):
        self.time_returned = time.time()
        if self._event:
            self._event.set()
        self._value = value
        logger.debug("Received value: %r" % self)

class Request(Message):

    extra_params = ()

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x04,
            self.ext_id, 0x01, self.device_id, self.port,
            *self.extra_params
        ]))

class LightSensorRead(Request):

    device_id = 4

class UltrasonicSensorRead(Request):

    device_id = 1

class LineFollowerRead(Request):

    device_id = 17

class SoundSensorRead(Request):

    device_id = 7

class PirMotionSensorRead(Request):

    device_id = 15

class PotentiometerRead(Request):

    device_id = 4

class LimitSwitchRead(Request):

    device_id = 21

class TemperatureRead(Request):

    device_id = 2

class TouchSensorRead(Request):

    device_id = 15

class HumitureSensorRead(Request):

    device_id = 23

    def __init__(self, port, type):
        super().__init__(port)
        self.extra_params = (type,)

class JoystickRead(Request):

    device_id = 5

    def __init__(self, port, axis):
        super().__init__(port)
        self.extra_params = (axis,)

class GasSensorRead(Request):

    device_id = 25

class FlameSensorRead(Request):

    device_id = 24

class CompassRead(Request):

    device_id = 26

class AngularSensorRead(Request):

    device_id = 28

class ButtonRead(Request):

    device_id = 22

class GyroRead(Request):

    device_id = 6

    def __init__(self, port, axis):
        super().__init__(port)
        self.extra_params = (axis,)

class PressureSensorBegin(Message):

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x03, 0x00, 0x02, 29,
        ]))

class PressureSensorRead(Request):

    device_id = 29

## TODO: digitalWrite
## TODO: pwmWrite

class MotorRun(Message):

    def __init__(self, port, speed):
        super().__init__(port)
        self.speed = speed

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x06, 0x00, 0x02, 0x0a,
            port, *short2bytes(self.speed),
        ]))

class MotorMove(Message):

    def __init__(self, left_speed, right_speed):
        super().__init__(None)
        self.left_speed = left_speed
        self.right_speed = right_speed

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x07, 0x00, 0x02, 0x05,
            *short2bytes(-self.left_speed),
            *short2bytes(self.right_speed),
        ]))

class ServoRun(Message):

    def __init__(self, port, slot, angle):
        super().__init__(port)
        self.slot = slot
        self.angle = angle

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x06, 0x00, 0x02, 0x0b,
            self.port, self.slot, self.angle,
        ]))

class EncoderMotorRun(Message):

    device_id = 62

    def __init__(self, slot, speed):
        super().__init__(None)
        self.slot = slot
        self.speed = speed

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x07, 0x00, 0x02,
            self.device_id, 0x02, self.slot,
            *short2bytes(self.speed),
        ]))

class EncoderMotorMove(Message):

    device_id = 62

    def __init__(self, slot, speed, distance):
        self.slot = slot
        self.speed = speed
        self.distance = distance

    def send(self, conn):
        ## TODO: has response
        conn.write(bytearray([
            0xff, 0x55, 0x0b, self.ext_id,
            0x02, self.device_id, 0x01, slot,
            *long2bytes(self.distance),
            *short2bytes(self.speed),
        ]))

class EncoderMotorMoveTo(Message):

    device_id = 62

    def __init__(self, slot, speed, distance):
        ## TODO: has response
        super().__init__(None)
        self.slot = slot
        self.speed = speed
        self.distance = distance

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x0b,
            self.ext_id, 0x02,
            self.device_id, 0x06,
            self.slot,
            *long2bytes(self.distance),
            *short2bytes(self.speed),
        ]))

class EncoderMotorSetCurPosZero(Message):

    device_id = 62

    def __init__(self, slot):
        super().__init__(None)
        self.slot = slot

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x02,
            self.device_id, 0x04, self.slot,
        ]))

class EncoderMotorPosition(Message):

    device_id = 61

    def __init__(self, slot):
        super().__init__()
        self.slot = slot

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x02,
            self.device_id, 0x04, self.slot
        ]))

class EncoderMotorPosition(Message):

    device_id = 61

    def __init__(self, slot):
        super().__init__(None)
        self.slot = slot

    def send(self, conn):
        ## TODO: has response
        conn.write(bytearray([
            0xff, 0x55, 0x06,
            self.ext_id, 0x01,
            self.device_id, 0x00,
            self.slot, 0x02,
        ]))

class StepperMotorRun(Message):

    device_id = 76

    def __init__(self, slot, speed):
        super().__init__(None)
        self.slot = slot
        self.speed = speed

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x07, 0x00, 0x02,
            self.device_id, 0x02, self.slot,
            *short2bytes(self.speed()),
        ]))

class StepperMotorMove(Message):

    device_id = 76

    def __init__(self, port, speed, distance):
        super().__init__(port)
        self.speed = speed
        self.distance = distance

    def send(self, conn):
        ## TODO: response
        conn.write(bytearray([
            0xff, 0x55, 0x0b,
            self.ext_id, 0x02,
            self.device_id, 0x01,
            self.port,
            *long2bytes(self.distance),
            *short2bytes(self.speed),
        ]))

class StepperMotorMoveTo(Message):

    device_id = 76

    def __init__(self, port, speed, distance):
        super().__init__(port)
        self.speed = speed
        self.distance = distance

    def send(self, conn):
        ## TODO: response
        conn.write(bytearray([
            0xff, 0x55, 0x0b,
            self.ext_id, 0x02,
            self.device_id, 0x06,
            self.port,
            *long2bytes(self.distance),
            *short2bytes(self.speed),
        ]))

class StepperMotorSetCurPosZero(Message):

    device_id = 76

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x02,
            self.device_id, 0x04,
            self.port,
        ]))

class RgbLedDisplay(Message):

    def __init__(self, port, slot, index, red, green, blue):
        super().__init__(port)
        self.slot = slot
        self.index = index
        self.red, self.green, self.blue = red, green, blue

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x09, 0x00, 0x02,
            18,
            self.port,
            self.slot,
            self.index,
            int(self.red),
            int(self.green),
            int(self.blue),
        ]))

class RgbLedShow(Message):

    def __init__(self, port, slot):
        super().__init__(port)
        self.slot = slot

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x02,
            19,
            self.port,
            self.slot,
        ]))

class SevenSegmentDisplay(Message):

    def __init__(self, port, number):
        super().__init__(port)
        self.number = number

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x08, 0x00, 0x02,
            9,
            self.port,
            *float2bytes(self.number)
        ]))

class LedMatrixMessage(Message):

    def __init__(self, port, x, y, message):
        super().__init__(port)
        self.x, self.y = x, y
        self.message = message

    def send(self, conn):
        numbers = [ord(c) for c in self.message]
        conn.write(bytearray([
            0xff, 0x55,
            8 + len(numbers),
            0x00, 0x02,
            41,
            self.port,
            1,
            char2byte(self.x),
            char2byte(7 - self.y),
            len(numbers),
            *numbers,
        ]))

class LedMatrixDisplay(Message):

    def __init__(self, port, x, y, buffer):
        super().__init__(port)
        self.x, self.y = x, y
        self.buffer = buffer

    def send(self, conn):
        ## FIXME: check and adapt buffer size
        conn.write(bytearray([
            0xff, 0x55,
            7 + len(self.buffer),
            0x00, 0x02,
            41,
            self.port,
            2,
            x,
            7 - y,
            *buffer,
        ]))

class SetShutter(Message):

    def __init__(self, port, shutter_on):
        super().__init__(port)
        self.shutter_on = shutter_on

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x03,
            20, self.port,
            1 if self.shutter_on else 2
        ]))

class SetFocus(Message):

    def __init__(self, port, focus_on):
        super().__init__(port)
        self.focus_on = focus_on

    def send(self, conn):
        conn.write(bytearray([
            0xff, 0x55, 0x05, 0x00, 0x03,
            20, self.port,
            3 if self.focus_on else 4
        ]))
