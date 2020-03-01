from .memebot import configure
from time import sleep

my_bot = configure("""
connection /dev/ttyUSB0
led 6
number_display 7
motion 8
contact 9+1 left_contact
contact 9+2 right_contact
ultrasound 10
""")

print(my_bot)

print("update ultrasound")
#my_bot.ultrasound.update()
print("update number")
my_bot.number_display.set(50)
sleep(0.5)
print("update number")
my_bot.number_display.set(10)
print(my_bot)
sleep(0.5)
my_bot.number_display.set(0)
