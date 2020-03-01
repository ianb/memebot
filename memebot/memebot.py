from . import communication
import sys
import time

def configure(s):
    lines = s.strip().splitlines()
    connection = None
    bot = Bot()
    for line in lines:
        port = slot = None
        if not line.strip() or line.strip().startswith("#"):
            continue
        parts = line.split()
        t = parts[0]
        if parts[2:]:
            name = parts[2]
        else:
            name = t
        if t == "connection":
            connection = parts[1]
            continue
        if "+" in parts[1]:
            port, slot = parts[1].split("+", 1)
            port = int(port)
            slot = int(slot)
        else:
            port = int(parts[1])
        bot.add_device(name, t, port, slot)
    bot.start(connection)
    return bot

class Bot(object):

    def __init__(self):
        self.m = MegaPi()
        self.devices = {}

    def __str__(self):
        props = [v for n, v in sorted(self.devices.items())]
        return 'Bot:%s' % "\n".join("  %s" % prop for prop in props)

    def start(self, connection):
        self.m.start(connection)

    def add_device(self, name, type, port, slot):
        device = factories[type](self, name, port, slot)
        self.devices[name] = device
        setattr(self, name, device)

class Device(object):

    def __init__(self, bot, name, port, slot=None):
        self.bot = bot
        self.name = name
        self.port = port
        self.slot = slot

    def __repr__(self):
        name = self.type
        if self.name != name:
            name = "%s (%s)" % (name, self.name)
        pos = ""
        if self.port:
            pos = " %s" % self.port
            if self.slot:
                pos = "%s+%s" % (pos, self.slot)
        return '<%s %s%s>' % (name, pos, self._extra_repr())

    def _extra_repr(self):
        return ""


class Sensor(Device):

    def __init__(self, *args, **kw):
        Device.__init__(self, *args, **kw)
        self.last_value = None
        self.last_value_time = None

    def update(self):
        self.bot.m[self.megapi_name](self.port, self.on_update)

    def on_update(self, value):
        self.last_value = value
        self.last_value_time = time.time()
        print("Received %r" % self)

    def _extra_repr(self):
        if not self.last_value_time:
            return " (not updated)"
        diff = int(time.time() - self.last_value_time)
        if diff < 60:
            diff = "%ss" % diff
        else:
            diff = "%sm" % (diff / 60)
        return " %s (%s)" % (self.last_value, diff)


class LightSensor(Sensor):
    type = "light_sensor"
    Message = communication.lightSensorRead
    megapi_name = "lightSensorRead"

class UltraSonic(Sensor):
    type = "ultrasound"
    Message = communication.UltrasonicSensorRead
    megapi_name = "ultrasonicSensorRead"

## FIXME: should do on-board sound, etc

class Motion(Sensor):
    type = "motion"
    Message = communication.PirMotionSensorRead
    megapi_name = "pirMotionSensorRead"

class Contact(Sensor):
    type = "contact"
    megapi_name = "??"

class NumberDisplay(Device):
    type = "number_display"
    Message = communication.SevenSegmentDisplay

    def set(self, value):
        print("Setting", self.type, value, self.bot, self.bot.m, self.bot.m.sevenSegmentDisplay, self.port)
        self.bot.m.sevenSegmentDisplay(self.port, value)

class LED(Device):
    type = "led"
    Message = communication.LedMatrixMessage

    def set(self, value, x=0, y=0):
        if isinstance(value, (unicode, str)):
            self.bot.m.ledMatrixMessage(self.port, x, y, value)
        else:
            ## FIXME: convert array to appropriate buffer
            self.bot.m.ledMatrixDisplay(self.port, x, y, value)

factories = {}
for _name in dir():
    _a_class = eval(_name)
    if isinstance(_a_class, type) and issubclass(_a_class, Device) and getattr(_a_class, "type", None):
        factories[_a_class.type] = _a_class
