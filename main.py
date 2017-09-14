import time
import datetime
import RPi.GPIO as GPIO
import ephem
import requests
import subprocess
import logging

# Logger Configuration
logging.basicConfig(format='[%(asctime)s] %(message)s',
                    level=logging.DEBUG);
logger = logging.getLogger()
formatter = logging.Formatter('[%(asctime)s] %(message)s')
fh = logging.FileHandler('/home/derk/Projects/smartlight/activity.log')
fh.setFormatter(formatter);
logger.addHandler(fh)

class Mode:
    # Take time of day into account
    AUTO=0;
    # Ignore time of day
    FIXED=1;

# Get the difference in seconds between two timestamps
def delta_t(t1, t2):
    return abs(t1 - t2);

class Sunlight:
    def __init__(self):
        sun = ephem.Sun();
        self.loc = ephem.Observer()
        self.loc.lat = '52.3702160'
        self.loc.lon = '4.8951680'
        self.loc.elevation = 9
	self.utc_offset=2	# hours
	self.custom_offset=-45	# minutes
        self.sunrise = (self.loc.next_rising(sun).datetime() + datetime.timedelta(hours=self.utc_offset) + datetime.timedelta(minutes=self.custom_offset)).time()
        self.sunset = (self.loc.next_setting(sun).datetime() + datetime.timedelta(hours=self.utc_offset) + datetime.timedelta(minutes=self.custom_offset)).time()

    # This functions returns whether it is light outside
    def is_light(self):
        now = datetime.datetime.now().time();

        if now > self.sunrise and now < self.sunset:
            return True;
        else:
            return False;

class Smartlight:
    # After what amount of inactivity the lights should go out in seconds
    AUTO_SLEEP = 15 * 60;
    # After what time a detection is called an activity in seconds
    DETECTION_INTERVAL = 5 * 60;

    def __init__(self, pin):
        self.pin = pin;
        self.last_seen = None;
        self.auto_sleep = time.time() + self.AUTO_SLEEP;
        self.sunlight = Sunlight();
        self.mode = Mode.AUTO;
        self.detection = False;
        # flags to prevent duplicate messages
        self.sleep_flag = False;
        self.activity_lost_flag = False;
	self.islight = True	

        GPIO.setmode(GPIO.BCM);
        GPIO.setwarnings(False);
        GPIO.setup(self.pin, GPIO.IN);
	GPIO.setup(21, GPIO.OUT);


    def light_on(self):
        requests.get('http://localhost?lamp=1&state=on');
        logging.info("Light on");

    def light_off(self):
        requests.get('http://localhost?lamp=1&state=off');
        logging.info("Light off");

    def detect(self, input):
        input = GPIO.input(input);
        if(input == 1):
            self.found();
	    GPIO.output(21,1);
        if(input == 0):
            self.lost();
	    GPIO.output(21,0);
        # Register the detection
        self.last_seen = time.time();

    # This function is called when the sensor detects something
    def found(self):
        # Check if the detection counts as a new activity
	if not self.sunlight.is_light() and self.islight:
		self.islight = False
		self.light_on()
		return		

	if self.sunlight.is_light() and not self.islight:
		self.islight = True

		
        if(self.last_seen is None or delta_t(self.last_seen, time.time()) >
            self.DETECTION_INTERVAL and not self.detection):
            logging.info("Activity Detected");
	    self.sunlight = Sunlight();
	    logging.info("Sunset: " + self.sunlight.sunset.isoformat());
	    logging.info("Sunrise: " + self.sunlight.sunrise.isoformat());
            # Check if we are allowed to turn on the lights
            if((self.mode == Mode.AUTO and not self.sunlight.is_light()) or
                self.mode == Mode.FIXED):
                self.light_on();

        # Declare the detection of something
        self.detection = True;
        # Declare that the activity is not lost
        self.activity_lost_flag = False;
        # Declare that the program should not sleep
        self.sleep_flag=False;

    # This function is called when the sensor loses detection of something
    def lost(self):
        # Declare an end to an detection
        self.detection = False
        # Postphone sleep to a later time
        self.auto_sleep = time.time() + self.AUTO_SLEEP

    # Start monitoring
    def start(self):
        # Start detecting signals on the given input pin
        GPIO.add_event_detect(self.pin, GPIO.BOTH, callback=self.detect);
        logging.info("Process Starting");
        while True:
            # Automatically turn of the lights after a period of inactivity
            if (self.auto_sleep < time.time() and not self.detection and not self.sleep_flag):
                logging.info('Automatic sleep timeout reached');
                self.light_off();
                self.auto_sleep = time.time() + self.AUTO_SLEEP;
                self.sleep_flag=True

            # When this is not the first detection and the flag is not yet activated
            if(self.last_seen is not None and not self.activity_lost_flag and
                # When there has not been a detection in a while
                delta_t(self.last_seen, time.time()) > self.DETECTION_INTERVAL
                # When there is no current detection
                and not self.detection):
                # Log the activity as lost
                logging.info("Activity Lost");
                # activate the flag to prevent duplicate messages
                self.activity_lost_flag = True;
            time.sleep(30);

if __name__ == "__main__":
    sm = Smartlight(26);
    sm.start();
