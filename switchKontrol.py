# switch seviyelerini oku (basılı mı değil mi)
import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
for p, pud in [(19,GPIO.PUD_UP),(20,GPIO.PUD_UP),(16,GPIO.PUD_DOWN)]:
    GPIO.setup(p, GPIO.IN, pull_up_down=pud)
    print(p, GPIO.input(p))