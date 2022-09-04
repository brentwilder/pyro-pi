import RPi.GPIO as GPIO
import datetime
import time
import Adafruit_DHT
import os
import pickle
import logging
import re
import subprocess
import signal
#import urllib2 needed for checking internet is on (not working)
import sys
from serial import Serial
import struct

# This code was heavily borrwed from work done by Thomas Van Der Weide's MS Thesis

# --------------------------------------------------------------------
# Strings for pyranometer
GET_VOLT = str.encode('55 21')
READ_CALIBRATION = str.encode('83 21')
SET_CALIBRATION = str.encode('84 XX XX XX XX YY YY YY YY 21')
READ_SERIAL_NUM = str.encode('87 21')
GET_LOGGING_COUNT = str.encode('f3 21')
GET_LOGGED_ENTRY = str.encode('f2 XX XX XX XX 21')
SET_LOGGING_INTERVAL = str.encode('f1 21')
ERASE_LOGGED_DATA = str.encode('f4 21')
# --------------------------------------------------------------------

class Pyranometer(object):
    def __init__(self):
        """Initializes class variables, and attempts to connect to device"""
        self.pyranometer = None
        self.offset = 0.0
        self.multiplier = 0.0
        self.connect_to_device()

    def connect_to_device(self):
        """This function creates a Serial connection with the defined COM port
        and attempts to read the calibration (offset and multiplier) values"""

        """you'll have to check your device manager and put the actual
        COM port here"""
        # port = 'COM4'
        port = '/dev/ttyACM0'
        self.pyranometer = Serial(port, 115200, timeout=0.5)
        try:
            self.pyranometer.write(READ_CALIBRATION)
            multiplier = self.pyranometer.read(5)[1:]
            offset = self.pyranometer.read(4)
            self.multiplier = struct.unpack('<f', multiplier)[0]
            self.offset = struct.unpack('<f', offset)[0]
        except (IOError):
            self.pyranometer = None

    def read_calibration(self):
        """This function returns offset value of the pyranometer."""
        if self.pyranometer is None:
            try:
                self.connect_to_device()
            except IOError:
                # you can raise some sort of exception here if you need to
                return
        try:
            self.pyranometer.write(READ_CALIBRATION)
            multiplier = self.pyranometer.read(5)[1:]
            offset = self.pyranometer.read(4)
            multiplier = struct.unpack('<f', multiplier)[0]
            offset = struct.unpack('<f', offset)[0]
            print(multiplier)
        except (IOError, struct.Error):
            self.pyranometer = None
        return offset, multiplier

    def read_serial(self):
        """This function returns the serial number of the pyranometer."""

        if self.pyranometer is None:
            try:
                self.connect_to_device()
            except IOError:
                # you can raise some sort of exception here if you need to
                return

        try:
            self.pyranometer.write(READ_SERIAL_NUM)
            serial = self.pyranometer.read(5)[1:]
        except IOError:
            # dummy value to know something went wrong. could raise an
            # exception here alternatively
            return 9999
        else:
            # if not serial:
            #     continue
            # if the response is not 4 bytes long, this line will raise
            # an exception
            sn = int(struct.unpack('<f', serial)[0])
        return sn

    def read_voltage(self):
        """This function reads the voltage of the pyranometer."""

        if self.pyranometer is None:
            try:
                self.connect_to_device()
            except IOError:
                # you can raise some sort of exception here if you need to
                return

        try:
            self.pyranometer.write(GET_VOLT)
            response = self.pyranometer.read(5)[1:]
        except IOError:
            # dummy value to know something went wrong. could raise an
            # exception here alternatively
            return 9999
        else:
            voltage = struct.unpack('<f', response)[0]

        return voltage

    def get_micromoles(self):
        """This function converts the voltage to micromoles"""

        voltage = self.read_voltage()
        if voltage == 9999:
            # you could raise some sort of Exception here if you wanted to
            return 9999
        # this next line converts volts to micromoles
        micromoles = (voltage - self.offset) * self.multiplier * 1000
        if micromoles < 0:
            micromoles = 0

        return micromoles


# --------------------------------------------------------------------


class StreamToLogger(object):
   """
   Fake file-like stream object that redirects writes to a logger instance.
   """
   def __init__(self, logger, log_level=logging.INFO):
      self.logger = logger
      self.log_level = log_level
      self.linebuf = ''

   def write(self, buf):
      for line in buf.rstrip().splitlines():
         self.logger.log(self.log_level, line.rstrip())
# --------------------------------------------------------------------


def getserial():
    '''
    Extract the PI serial number from the 'cpuinfo' file
    '''
    cpuserial = None
    try:
        f = open('/proc/cpuinfo', 'r')
        for line in f:
            if line[0:6] == 'Serial':
                cpuserial = line[10:26]
        f.close()
        logging.info('Determined CPU serial number: %s', cpuserial)
    except:
        logging.error('Could not determine CPU serial number')
    return cpuserial
# --------------------------------------------------------------------


def getSensorData():
    '''
    This function reads a single relative humidity and temperature pair
    '''
    RH = None
    T = None
    count = 0

    while RH is None or T is None and count < 100:
        RH, T = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, 27)
        # Keep reading until both data are logged at the same time
        # still need to add limit
        count += 1
    # If still bad data after 100 attempts, set to -9999
    if RH is None:
        RH = int(-9999)
        logging.info('Logged a bad RH value: -9999')
    if T is None:
        T = int(-9999)
        logging.info('Logged a bad T value: -9999')
    return (RH, T)
# --------------------------------------------------------------------


def handler(signum, frame):
    '''
    https://stackoverflow.com/questions/492519/timeout-on-a-function-call
    '''
    logging.warning('Stopping because of timeout!')
    raise Exception("Data logging request timed out.")
    return
# --------------------------------------------------------------------


def logSensorData(n_average, sleep_time):
    '''
    This function logs the sensor for a give amount of time and 
    sample interval.
    Returns vectors of the logged temp and humidity data.
    '''
    RH_out = []  # allocate list variable
    T_out = []  # allocate list variable
    i_point = 0
    while i_point < n_average:
        # Register the signal function handler
        signal.signal(signal.SIGALRM, handler)
        # Define the timeout for the getSensorData() function
        signal.alarm(n_points*2)  # Make sure that one log attempt does not
        # take more than 10 seconds. This can happen if the PIN is
        # not correct in the getSensorData() call.
        try:
            RH, T = getSensorData()
            RH_out.append(RH)
            T_out.append(T)

            # Wait before logging next data point
            time.sleep(sleep_time)
            i_point += 1
        except:
            logging.warning('Did not log sensor data: exiting.')
            break
        # Cancel the timer if the function returned before timeout
        signal.alarm(0)
    return (RH_out, T_out)
# --------------------------------------------------------------------


def log_humid_temp_data(sleep_time, n_points, data_dir, filename):
    '''
    Write humidity and temp data to file
    '''
    # Log the sensor data 
    logging.info('Starting to log temp and humidity...')
    RH, T = logSensorData(n_points, sleep_time)
    # Merge the data into single variable
    logging.info('Combined humidity and temperature data')
    data = zip(RH, T)
    
    try:
        filename = os.path.join(data_dir, filename + '_ht.pkl')  # this gives same name as image file
        f = open(filename, 'wb')
        pickle.dump(data, f)
        f.close()
        logging.info('Wrote data file: %s', filename)
    except IOError:
        logging.error('Could not write file %s', filename)
    return filename, data_dir
# --------------------------------------------------------------------


def log_pyranometer_data(sleep_time, n_points, data_dir, filename):
    '''
    Write pyranometer data to file
    '''
    logging.info('Starting to log pyranometer...')
    # instantiate pyranometer object
    my_pyranometer = Pyranometer() 
    serial = my_pyranometer.read_serial()
    offset,multiplier = my_pyranometer.read_calibration()
    
    p_out = []  # allocate blank list for data vector
    i_point = 0
    while i_point < n_points:
        p_out.append(my_pyranometer.get_micromoles())
        time.sleep(sleep_time)
        i_point += 1
        
        data = [serial, offset, multiplier, p_out]
        
    try:
        filename = os.path.join(data_dir, filename + '_pyr.pkl')  # this gives same name as image file
        f = open(filename, 'wb')
        pickle.dump(data, f)
        f.close()
        logging.info('Wrote data file: %s', filename)
    except IOError:
        logging.error('Could not write file %s', filename)
    return filename, data_dir
# --------------------------------------------------------------------


def make_serial_directory():
    ''' 
    Output data file has date/time stamp in filename.
    Need to make sure we write to the folder for this RPi.
    '''
    
    cpuserial = getserial()
    if cpuserial is not None:
        # make sure there is not a / after last folder
        data_dir = '/home/pi/DATA_' + cpuserial  
        # check that directory exists and make if needed
        checkOutputDirectory(data_dir)
        logging.info('Saving local data to %s', data_dir)
    else:
        logging.warning('Could not determine CPU information.')
        logging.warning('Not logging data.')
        exit()
    return data_dir
# --------------------------------------------------------------------


def checkOutputDirectory(data_dir):
    '''
    Check the output directory exists and if not, create it.
    '''
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        logging.info('Created new directory %s', data_dir)
    else:
        logging.info('Found directory %s', data_dir)
# --------------------------------------------------------------------

def start_log():
    '''
    open the log file and start tracking events, if opened in main() 
    it can be called anywhere
    '''
    # Make the log file name
    log_file = '%s.log' % time.strftime("%Y_%m_%d")
    # Open the log file and set parameters
    logging.basicConfig(filename=log_file, filemode='a', \
                        level=logging.DEBUG, \
                        format='%(asctime)s: %(levelname)s: %(name)s: %(message)s', \
                        datefmt='%Y-%m-%d %H:%M:%S', \
                        stream=sys.stdout )
    logging.info('====================================')
    logging.info('Starting to log temp, humidity, and SW radiation...')
    
    return log_file
# --------------------------------------------------------------------


def connect_sakis():
    '''
    Connect the 3G modem to the network.
    Return a True if the connection is setup, otherwise False.
    '''
    
    internet_flag = False
    i_count = 0
    while internet_flag is False and i_count < 60:
        try:
            #subprocess.call("sudo /usr/bin/modem3g/umtskeeper/umtskeeper --devicename 'Huawei' --nat 'no' &", shell=True)
            time.sleep(10)
            internet_flag = internet_on()
            i_count += 1
            logging.info("Turning on SAKIS: attempt %s", i_count)
            time.sleep(1)
        except:
            time.sleep(1)
    if internet_flag:
        logging.info('Connnected to internet')
    else:
        logging.warning('Could not connect to internet')
    return internet_flag
# --------------------------------------------------------------------


def disconnect_sakis():
    '''
    Disconnect 3G modem from the netowrk.
    '''
    #subprocess.call("sudo /usr/bin/modem3g/umtskeeper/umtskeeper stop", shell=True)
    #logging.info('Disconnnected from internet')
    pass
    return
# --------------------------------------------------------------------


def internet_on():
    '''
    Ping google.com to determine if the network connection is up.
    '''
    try:
        urllib2.urlopen('http://216.58.192.142', timeout=5)  # google.com
        internet_flag = True
    except urllib2.URLError as exc:
        internet_flag = False
    return internet_flag
# --------------------------------------------------------------------


def send_ht_data(ht_data_dir, ht_file, server):
    '''
    Transfer humidity and temperature (HT) data to the remote server.
    Transfer is done using rsync command.
    '''
    success = False
    try:
        # sync data directory
        line = "rsync -vahz --partial --inplace " + ht_file + " " + server
        logging.info('%s',line)
        subprocess.call(line, shell=True)
        logging.info('Transferred %s to remote server', ht_file)
        success = True
    except:
        logging.error('Could not transfer %s to remote server', ht_file)
    return success
# --------------------------------------------------------------------


def send_log_data(log_file, server):
    # transfer log data to server
    try:
        # sync log file
        line = "rsync -vahz --partial --inplace " + log_file + " " + server
        logging.info('%s',line)
        subprocess.call(line, shell=True)
        logging.info('Transferred %s to remote server', log_file)
    except:
        logging.error('Could not transfer %s to remote server', log_file)
    return
# --------------------------------------------------------------------

def send_all_logs(server):  # rsync all logs
    fn = '/home/pi/2018*'
    logging.info("Attempting to rsync all log files.")
    transfer = "rsync -vahz --partial --inplace --append-verify " + fn + " " + server
    logging.info('%s', transfer)
    connected = connect_sakis()
    try:
        if connected:
            process = subprocess.call(transfer, shell=True)
            logging.info('Log file transfer complete')
        else:
            logging.error('Could not connect to internet to send log files.')
            pass
    except:
        logging.error('Something wrong with the log transfer.')
        pass

# --------------------------------------------------------------------


def main(n_points, sleep_time, server=None, sensor_name=None):  # Log humid & temp & rad and send via cellular connection
	'''
	RPI turns on 1300 to 1305 each day
	takes 60 measurements (1 per second)
	after which it will send the data.. then shut down
	'''
	# Make/check for data directory for this particular Pi
	data_dir = make_serial_directory()
	
	# filename is doy
	filename = str(datetime.datetime.now().timetuple().tm_yday)
	
	# Log the temperature and humidity data -- give same name as RAW file
	ht_file, ht_data_dir = log_humid_temp_data(sleep_time, n_points, data_dir, filename) 
		
	# Log the Pyranometer data right after taking picture
	pyr_file, pyr_data_dir = log_pyranometer_data(sleep_time, n_points, data_dir, filename)
  
	# Now begin file transfer 	
	#connected = connect_sakis()
	
	# Send pyra data to my server
	#try:
	#	success = send_ht_data(pyr_data_dir, pyr_file, server)
	#		except:
	#			logging.error("Could not send pyranometer data.")
	#			pass
				
	# Send Temp/RH data to my server
	#try:
	#	success = send_ht_data(ht_data_dir, ht_file, server)
	#		except:
	#			logging.error("Could not send Temp/RH data.")
	#			pass
	# Send log data to my server
	#try:
	#	success = send_log_data(log_file, server)
	#		except:
	#			logging.error("Could not send log file.")
	#			pass
			
	# shutdown the pi
	#os.system('sudo shutdown -h now')
	print('pretend shutdown')
	
# --------------------------------------------------------------------
# call main() function to run program
if __name__ == '__main__':
    '''
    This program will collect temperature/humidity/SW RAD..
    Data are collected between 1300-1302 and then sent to server.
    '''
    # temperature and humidity logging parameters
    sleep_time = 0.1  # [s] record data every sleep_time seconds
    n_points = 5  # [points] number of points to record

    # server name and directory location on remote server
    #server = "thomasvanderweide@tomservo.boisestate.edu:/data/2018/"
    #line = "cat sensor_name.txt"
    #directory = subprocess.check_output(line, shell=True)  # get the filename
    #directory = os.linesep.join([s for s in directory.splitlines() if s])  # remove extra lines
    #server = server + directory + "/"

    # run the main program
    main(n_points, sleep_time)
