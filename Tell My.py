import requests
from math import sqrt, radians, sin, cos, atan2
from pprint import pprint
from datetime import datetime
from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException
from time import sleep
import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt5.QtCore import QFile, QTimer
from main_window_ui import Ui_MainWindow
from sign_in_ui import Ui_SignIn
from two_factor_auth_ui import Ui_TwoFactorAuth
import configparser
from appdirs import user_data_dir
from pathlib import Path

INITIAL_COUNTDOWN_TIME = 10
COUNTDOWN_TIME = 120

current_window = None

class SignInWindow(QMainWindow):
    def __init__(self):
        super(SignInWindow, self).__init__()
        self.ui = Ui_SignIn()
        self.ui.setupUi(self)
        username = get_config('username', '')
        password = get_config('passwd', '')
        self.ui.usernameLine.setText(username)
        self.ui.passwordLine.setText(password)
        self.api = None

    def accept(self):
        self.processSignIn()

    def processSignIn(self):
        username = self.ui.usernameLine.text()
        password = self.ui.passwordLine.text()
        set_config('username', username)
        set_config('passwd', password)

        try:
            self.api = PyiCloudService(username, password)
        except PyiCloudFailedLoginException as e:
            show_dialog(e.args[0], "sign in error")
            return

        if self.api.requires_2fa:
            # the modern api
            self.close()
            # we make it a member so the gc doesn't cause problems
            global current_window
            current_window = TwoFactorAuth(self.api)
            current_window.show()
        elif self.api.requires_2sa:
            # the old api that sends a text message
            show_dialog("your account doesn't support 2fa", "error")
            QApplication.quit()
        else:
            print("icloud enabled!")
            self.continue_to_program()

    def continue_to_program(self):
        self.close()
        # we make it a member so the gc doesn't cause problems
        global current_window
        current_window = MainWindow(self.api)
        current_window.show()

    def reject(self):
        QApplication.quit()


class TwoFactorAuth(QMainWindow):
    def __init__(self, api):
        super(TwoFactorAuth, self).__init__()
        self.ui = Ui_TwoFactorAuth()
        self.ui.setupUi(self)
        self.api = api

    def accept(self):
        code = self.ui.lineEdit.text()
        if self.api.validate_2fa_code(code):
            self.continue_to_program()
        else:
            print("Code failed")

    def continue_to_program(self):
        self.close()
        # we make it a member so the gc doesn't cause problems
        global current_window
        current_window = MainWindow(self.api)
        current_window.show()

    def reject(self):
        QApplication.quit()


class MainWindow(QMainWindow):
    def __init__(self, api):
        super(MainWindow, self).__init__()
        self.api = api
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.available_devices = self.api.devices
        self.available_friends = self.api.friends.contact_details
        self.available_devices_names = [f'{x["name"]} ({x["deviceDisplayName"]})' for x in self.available_devices]
        self.available_friends_names = [f'{x["firstName"]} {x["lastName"]}' for x in self.available_friends]
        self.ui.availableDevicesBox.addItems(self.available_friends_names)
        self.ui.availableDevicesBox.addItems(self.available_devices_names)
        self.ui.watch_movement_device_adb.addItems(self.available_devices_names)
        self.ui.proximity_to.addItems(self.available_devices_names)
        self.ui.watch_proximity_device_adb.addItems(self.available_devices_names)

        self.tracked = []

        self.ui.watch_movement.stateChanged.connect(lambda x: self.update_device_config('watch_movement', x))
        self.ui.tolerance.valueChanged.connect(lambda x: self.update_device_config('tolerance', x))
        self.ui.watch_movement_audio.stateChanged.connect(lambda x: self.update_device_config('watch_movement_audio', x))
        self.ui.watch_movement_device_cb.stateChanged.connect(lambda x: self.update_device_config('watch_movement_device_cb', x))
        self.ui.watch_movement_device_adb.currentIndexChanged.connect(lambda x: self.update_device_config('watch_movement_device_adb', x))
        
        self.ui.watch_proximity.stateChanged.connect(lambda x: self.update_device_config('watch_proximity', x))
        self.ui.proximity_to.currentIndexChanged.connect(lambda x: self.update_device_config('proximity_to', x))
        self.ui.distance.valueChanged.connect(lambda x: self.update_device_config('distance', x))
        self.ui.watch_proximity_audio.stateChanged.connect(lambda x: self.update_device_config('watch_proximity_audio', x))
        self.ui.watch_proximity_device_cb.stateChanged.connect(lambda x: self.update_device_config('watch_proximity_device_cb', x))
        self.ui.watch_proximity_device_adb.currentIndexChanged.connect(lambda x: self.update_device_config('watch_proximity_device_adb', x))

        self.countdown = INITIAL_COUNTDOWN_TIME
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.recurring_timer)
        self.timer.start()


    def addButtonClick(self):
        idx = self.ui.availableDevicesBox.currentIndex()
        if idx < len(self.available_friends):
            friend = self.available_friends[idx]
            display_name = self.available_friends_names[idx]
            self.ui.tracked.addItem(display_name)
            self.tracked.append(TrackingConfig("friend", friend, display_name))
        else:
            device = self.available_devices[idx - len(self.available_friends)]
            display_name = self.available_devices_names[idx - len(self.available_friends)]
            self.ui.tracked.addItem(display_name)
            self.tracked.append(TrackingConfig("device", device, display_name))

    def removeButtonClick(self):
        idx = self.ui.tracked.currentRow()
        if idx == -1:
            return
        self.ui.tracked.takeItem(idx)
        del self.tracked[idx]

    def selectedDeviceChanged(self, idx):
        self.update_ui()
    
    def update_ui(self):
        idx = self.ui.tracked.currentRow()
        if idx == -1:
            self.ui.watch_movement.setEnabled(False)
            self.ui.watch_movement.setChecked(False)

            self.ui.tolerance.setEnabled(False)
            self.ui.tolerance_label.setEnabled(False)
            self.ui.tolerance.setValue(500.0)

            self.ui.watch_movement_audio.setEnabled(False)
            self.ui.watch_movement_audio.setChecked(False)

            self.ui.watch_movement_device_cb.setEnabled(False)
            self.ui.watch_movement_device_cb.setChecked(False)

            self.ui.watch_movement_device_adb.setEnabled(False)
            self.ui.watch_movement_device_adb.setCurrentIndex(0)

            self.ui.watch_proximity.setEnabled(False)
            self.ui.watch_proximity.setChecked(False)

            self.ui.proximity_to.setEnabled(False)
            self.ui.proximity_to_label.setEnabled(False)
            self.ui.proximity_to.setCurrentIndex(0)

            self.ui.distance.setEnabled(False)
            self.ui.distance_label.setEnabled(False)
            self.ui.distance.setValue(500.0)

            self.ui.watch_proximity_audio.setEnabled(False)
            self.ui.watch_proximity_audio.setChecked(False)

            self.ui.watch_proximity_device_cb.setEnabled(False)
            self.ui.watch_proximity_device_cb.setChecked(False)

            self.ui.watch_proximity_device_adb.setEnabled(False)
            self.ui.watch_proximity_device_adb.setCurrentIndex(0)

            self.ui.log_box.setPlainText("")
            return
        dev = self.tracked[idx]

        self.ui.watch_movement.setEnabled(True)
        self.ui.watch_movement.setChecked(dev.watch_movement)

        self.ui.tolerance.setEnabled(dev.watch_movement)
        self.ui.tolerance_label.setEnabled(dev.watch_movement)
        self.ui.tolerance.setValue(dev.tolerance)

        self.ui.watch_movement_audio.setEnabled(dev.watch_movement)
        self.ui.watch_movement_audio.setChecked(dev.watch_movement_audio)

        self.ui.watch_movement_device_cb.setEnabled(dev.watch_movement)
        self.ui.watch_movement_device_cb.setChecked(dev.watch_movement_device_cb)

        self.ui.watch_movement_device_adb.setEnabled(dev.watch_movement and dev.watch_movement_device_cb)
        self.ui.watch_movement_device_adb.setCurrentIndex(dev.watch_movement_device_adb)

        self.ui.watch_proximity.setEnabled(True)
        self.ui.watch_proximity.setChecked(dev.watch_proximity)

        self.ui.proximity_to.setEnabled(dev.watch_proximity)
        self.ui.proximity_to_label.setEnabled(dev.watch_proximity)
        self.ui.proximity_to.setCurrentIndex(dev.proximity_to)

        self.ui.distance.setEnabled(dev.watch_proximity)
        self.ui.distance_label.setEnabled(dev.watch_proximity)
        self.ui.distance.setValue(dev.distance)

        self.ui.watch_proximity_audio.setEnabled(dev.watch_proximity)
        self.ui.watch_proximity_audio.setChecked(dev.watch_proximity_audio)

        self.ui.watch_proximity_device_cb.setEnabled(dev.watch_proximity)
        self.ui.watch_proximity_device_cb.setChecked(dev.watch_proximity_device_cb)

        self.ui.watch_proximity_device_adb.setEnabled(dev.watch_proximity and dev.watch_proximity_device_cb)
        self.ui.watch_proximity_device_adb.setCurrentIndex(dev.watch_proximity_device_adb)

        self.ui.log_box.setPlainText(dev.log_box)

    def update_device_config(self, prop, val):
        idx = self.ui.tracked.currentRow()
        self.tracked[idx][prop] = val
        self.update_ui()

    def recurring_timer(self):
        if self.countdown == 0:
            self.locate()
            self.countdown = COUNTDOWN_TIME
        self.ui.statusbar.showMessage(f'Seconds until next locate: {self.countdown}')
        self.countdown -= 1

    def locate(self):
        for trackee in self.tracked:
            handle(trackee, self.api)
        self.update_ui()

def find_distance(location1, location2):
    lat1 = location1['latitude']
    lng1 = location1['longitude']
    lat2 = location2['latitude']
    lng2 = location2['longitude']

    earthRadius = 6371000.0
    dLat = radians(lat2-lat1);
    dLng = radians(lng2-lng1);
    a = sin(dLat/2) * sin(dLat/2) + \
        cos(radians(lat1)) * cos(radians(lat2)) * \
        sin(dLng/2) * sin(dLng/2);
    c = 2 * atan2(sqrt(a), sqrt(1-a));

    return earthRadius * c;

def handle(config, api):
    if config.type == "friend":
        friend_id = config.api_object['id']
        location = next(friend['location'] for friend in api.friends.locations if friend['id'] == friend_id)
    else:
        location = config.api_object.location()

    # couldn't retrieve location
    if not location:
        if (config.watch_movement and config.watch_movement_audio) or \
            (config.watch_proximity and config.watch_proximity_audio):
            say_aloud(f"Error retrieving location")
        config.log(f"Error retrieving location")
        return

    config.log(datetime.now())
    config.log(f"lat {location['latitude']}, lng {location['longitude']}")

    # movement logic
    if config.watch_movement and hasattr(config, 'last_location'):
        # while tracking movement, only update lastlocation 
        # after a detection to prevent creeping
        dist = find_distance(device.last_location, location)
        config.log(f"Delta distance (meters): {dist}")
        if dist >= config.tolerance:
            msg = f"{config.display_name} has moved." 
            notify('Movement Detected', msg)
            if config.watch_movement_audio:
                say_aloud(msg)
            if config.watch_movement_device_cb:
                api.devices[config.watch_movement_device_adb].display_message(subject="this doesnt get shown",message=msg,sounds=True)
            config.log(msg)
            device.last_location = location
    else:
        config.last_location = location

    # proximity logic
    if config.watch_proximity:
        proximity_to_device = available_devices[device.config.proximity_to]
        ptd_name = proximity_to_device["name"]
        dist = find_distance(location, proximity_to_device)
        if dist < config.distance:
            msg = f"{ptd_name} is near {config.display_name}"
            notify('Proximity Detected', msg)
            if config.watch_proximity_audio:
                say_aloud(msg)
            if config.watch_proximity_device_cb:
                available_devices[config.watch_proximity_device_adb].display_message(subject="this doesnt get shown",message=msg,sounds=True)
            config.log(msg)

def say_aloud(text):
    os.system(f'say "{text}"')

def notify(title, text):
    os.system("""
              osascript -e 'display notification "{}" with title "{}"'
              """.format(text, title))
    
class TrackingConfig:
    def __init__(self, type, api_object, display_name):
        # either "device" or "friend"
        self.type = type
        self.api_object = api_object
        self.display_name = display_name

        self.watch_movement = False
        self.tolerance = 500.0
        self.watch_movement_audio = False
        self.watch_movement_device_cb = False
        self.watch_movement_device_adb = 0

        self.watch_proximity = False
        self.proximity_to = 0
        self.distance = 500.0
        self.watch_proximity_audio = False
        self.watch_proximity_device_cb = False
        self.watch_proximity_device_adb = 0

        self.log_box = ""

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, val):
        return setattr(self, key, val)

    def log(self, msg):
        self.log_box += str(msg) + "\n"

def get_config(key, default=None):
    return config.get('data', key, fallback=default)

def set_config(key, value):
    if 'data' not in config.sections():
        config.add_section('data')
    config.set('data', key, value)
    if not os.path.exists(os.path.dirname(config_path)):
        try:
            os.makedirs(os.path.dirname(config_path))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
    with open(config_path, "w") as f:
        config.write(f)

def show_dialog(self, message, title="alert"):
    msgbox = QMessageBox()
    msgbox.setText(message)
    msgbox.setWindowTitle(title)
    msgbox.setStandardButtons(QMessageBox.Ok)

    returnvalue = msgbox.exec()
    if returnvalue == QMessageBox.Ok:
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)

    config = configparser.ConfigParser()
    config_path = Path(user_data_dir('Tell My', 'cw')) / 'data.ini'
    config.read(config_path)

    current_window = SignInWindow()
    current_window.show()

    app.exec_()
