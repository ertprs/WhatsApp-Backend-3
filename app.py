"""
******************************************************************

        File name   : webapi.py
        Description : Flask based API to work with webwhatsapi
                      Called from wsgi.py. Can be run as a
                      standalone file to (cmd: python WebAPI.py)

                      The API use chrome as of now, can be changed
                      to use firefox too

                      The API provides a way to run multiple clients
                      by the use of client_id. The api stores drivers
                      and use them in later calls

                      You need to fist call [PUT] /client to create
                      driver for that client and then you can use
                      other calls

        Requirements: Mentioned in Pipfile

# Change Logs
DATE        PROGRAMMER      COMMENT
18/09/18    rbnishant       Initial Version

*****************************************************************/
"""

import json
import logging
import os
import shutil
from datetime import datetime

import requests
import sys
import time
import json
import threading
import random
import werkzeug
import urllib3
import googlemaps
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import Flask, send_file, request, abort, g, jsonify, session
from flask.json import JSONEncoder
from urllib import request as urllibrequest
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from werkzeug.utils import secure_filename
from webwhatsapi import MessageGroup, WhatsAPIDriver, WhatsAPIDriverStatus
from webwhatsapi.objects.whatsapp_object import WhatsappObject
import xmltodict

"""
###########################
##### CLASS DEFINITION ####
###########################
"""


class RepeatedTimer(object):
    """
    A generic class that creates a timer of specified interval and calls the
    given function after that interval
    """

    def __init__(self, interval, function, *args, **kwargs):
        """ Starts a timer of given interval
        @param self:
        @param interval: Wait time between calls
        @param function: Function object that is needed to be called
        @param *args: args to pass to the called functions
        @param *kwargs: args to pass to the called functions
        """
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        """Creates a timer and start it"""

        if not self.is_running:
            self._timer = threading.Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        """Stop the timer"""
        self._timer.cancel()
        self.is_running = False


class WhatsAPIJSONEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, WhatsappObject):
            return obj.get_js_obj()
        if isinstance(obj, MessageGroup):
            return obj.chat
        return super(WhatsAPIJSONEncoder, self).default(obj)


class NewMessageObserver:
    def __init__(self, appId):
        self.appId = appId

    def on_message_received(self, new_messages):
        for message in new_messages:
            logger.info("New Message event" + message)
            if message.chat_id.endswith("@c.us"):
                if message.type == "chat" or message.type == "location":
                    body = reformat_message_r2mp(message, self.appId)
                    forward_message_to_r2mp(body)
                    print(
                        "New {} message '{}' received from number {}".format(self.appId,
                                                                             message.content, message.sender.id
                                                                             )
                    )
                else:
                    print(
                        "New message of type '{}' received from number {}".format(
                            message.type, message.sender.id
                        )
                    )


"""
###########################
##### GLOBAL VARIABLES ####
###########################
"""

GOOGLE_API_KEY = 'AIzaSyBAPz88HCjuOjq7nHNdm1X-HPRwYqFE4oc'



# Flask Application
app = Flask(__name__)
app.json_encoder = WhatsAPIJSONEncoder
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s  %(levelname)s : %(message)s', )
http = urllib3.PoolManager(num_pools=50)

logger = logging.getLogger("WhatsApp Backend")
handler = logging.FileHandler('whatsapp_development.log')
formatter = logging.Formatter('%(asctime)s  %(levelname)s : %(message)s')
handler.setFormatter(formatter)
# handler.setLevel(logging.INFO)
logger.addHandler(handler)

app.debug = True

gmaps = googlemaps.Client(key=GOOGLE_API_KEY)


# Logger

# Driver store all the instances of webdriver for each of the client user
drivers = dict()
# Store all timer objects for each client user
timers = dict()
# Store list of semaphores
semaphores = dict()

# store quick replies payload
payload = dict()
payload2 = dict()

emojis_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
faces = ['😎', '😋', '😉', '😌', '😇', '😊', '😀', '😃', '🤤', '🤠', '👻', '😺', '🕺']
hands = ['💪', '🤞', '🤞', '👍', '👊', '✊', '🤛', '🤜', '🤞', '✌', '🤟', '🤘', '👌', '👈', '🖖']
numbers = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
food_ordering = ['60801469fb0e7e25432c5b7c']


SANDBOX_URL = "http://r2mp-sandbox.rancardmobility.com"
PRODUCTION_URL = "http://r2mp.rancard.com"
LOCAL = "http://localhost:8080"
PRODUCTION_URL2 = "https://r2mp2.rancard.com"

SERVER = SANDBOX_URL
WEBHOOK = SANDBOX_URL

# API key needed for auth with this API, change as per usage
API_KEY = "5ohsRCA8os7xW7arVagm3O861lMZwFfl"
# File type allowed to be sent or received
ALLOWED_EXTENSIONS = (
    "avi",
    "mp4",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "mp3",
    "doc",
    "docx",
    "pdf",
)
# Path to temporarily store static files like images
STATIC_FILES_PATH = "static/"

# Seleneium Webdriver configuration
CHROME_IS_HEADLESS = True
CHROME_CACHE_PATH = BASE_DIR + "/chrome_cache/"
CHROME_DISABLE_GPU = True
CHROME_WINDOW_SIZE = "910,512"

"""
##############################
##### FUNCTION DEFINITION ####
##############################
"""


def get_connected_companies():
    logger.info("Finding connected whatsApp Companies")
    directory = os.fsencode(CHROME_CACHE_PATH)
    connected_companies = os.listdir(directory)
    logger.info(str(len(connected_companies)) + " Connected WhatsApp Companies retrieved "+ str(connected_companies))
    for company in connected_companies:
        company = company.decode("utf-8")
        thread = threading.Thread(target=restore_sessions, args=(company,))
        thread.start()


def restore_sessions(client_id):
    # assign global variable
    logger.info("Session Restoration for client "+ str(client_id) + " commencing")

    logger.info("About getting driver status")
    # check if client driver exist otherwise create new driver and global variable
    if client_id not in drivers:
        drivers[client_id] = init_client(client_id)
        logger.info("Driver initialised Successfully")

    driver = drivers[client_id]
    driver_status = WhatsAPIDriverStatus.Unknown

    if driver is not None:
        driver_status = driver.get_status()
        logger.info("Driver Status retrieved successfully  "+ driver_status)

    if drivers[client_id].is_logged_in():
        acquire_semaphore(client_id)
        init_timer(client_id)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.driver_status != WhatsAPIDriverStatus.LoggedIn:
            return jsonify({"error": "client is not logged in"})
        return f(*args, **kwargs)

    return decorated_function


def create_logger():
    """Initial the global logger variable"""
    global logger

    # formatter = logging.Formatter("%(asctime)s|%(levelname)s|%(message)s")
    # handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1)
    # handler.setFormatter(formatter)
    # handler.setLevel(log_level)
    # handler.suffix = "%Y-%m-%d"
    # logger = logging.getLogger("sacplus")
    # logger.setLevel(log_level)
    # logger.addHandler(handler)


def init_driver(client_id):
    """Initialises a new driver via webwhatsapi module

    @param client_id: ID of user client
    @return webwhatsapi object
    """

    # Create profile directory if it does not exist
    profile_path = CHROME_CACHE_PATH + str(client_id)
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)

    # Options to customize chrome window
    chrome_options = [
        "window-size=" + CHROME_WINDOW_SIZE,
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/60.0.3112.78 Chrome/60.0.3112.78 Safari/537.36",
    ]
    if CHROME_IS_HEADLESS:
        chrome_options.append("--headless")
    if CHROME_DISABLE_GPU:
        chrome_options.append("--disable-gpu")

    # Create a whatsapidriver object
    d = WhatsAPIDriver(
        username=client_id,
        profile=profile_path,
        client="chrome",
        chrome_options=chrome_options,
    )
    return d


def init_client(client_id):
    """Initialse a driver for client and store for future reference

    @param client_id: ID of client user
    @return whebwhatsapi object
    """
    if client_id not in drivers:
        drivers[client_id] = init_driver(client_id)
    return drivers[client_id]


def delete_client(client_id, preserve_cache):
    """Delete all objects related to client

    @param client_id: ID of client user
    @param preserve_cache: Boolean, whether to delete the chrome profile folder or not
    """
    if client_id in drivers:
        drivers.pop(client_id).quit()
        try:
            timers[client_id].stop()
            timers[client_id] = None
            release_semaphore(client_id)
            semaphores[client_id] = None
        except:
            pass

    if not preserve_cache:
        logger.info("Deleting the profile folder for app Id")
        pth = CHROME_CACHE_PATH + g.client_id
        shutil.rmtree(pth)


def init_timer(client_id):
    """Create a timer for the client driver to watch for events

    @param client_id: ID of clinet user
    """
    if client_id in timers and timers[client_id]:
        timers[client_id].start()
        logger.info("Previous driver timer initialised")
        return
    # Create a timer to call check_new_message function after every 2 seconds.
    # client_id param is needed to be passed to check_new_message
    timers[client_id] = RepeatedTimer(2, check_new_messages, client_id)


def init_login_timer(client_id):
    """Create a timer for the client driver to watch for events

    @param client_id: ID of clinet user
    """
    timer_id = client_id + "login"
    if timer_id in timers and timers[timer_id]:
        timers[timer_id].start()
        return
    # Create a timer to call check_new_message function after every 2 seconds.
    # client_id param is needed to be passed to check_new_message
    timers[timer_id] = RepeatedTimer(5, send_qr, client_id)


def serve_user_login(client_id):
    """Check if user is logged in and send them to the custom api

    @param client_id: ID of client user
    """

    try:
        """ Get qr as base64 string"""

        qr = drivers[client_id].get_qr_base64()
        body = {
            'success': True,
            'appId': client_id,
            'isLoggedIn': False,
            'qr': qr
        }
        logger.info("Sending QR to server")
        # encoded_data = json.dumps(body).encode('utf-8')
        # url = SERVER + '/api/v1/whatsapp/webhook'
        # response = http.request('POST', url, body=encoded_data, headers={'Content-Type': 'application/json'})
        response = requests.post(SERVER + '/api/v1/whatsapp/webhook', json=body)
    except NoSuchElementException:
        phone = drivers[client_id].get_id().replace("\"", "").replace("@c.us", "")
        drivers[client_id].save_sessions()
        body = {
            'success': True,
            'isLoggedIn': True,
            'appId': client_id,
            "msisdn": phone,
            "qr": None
        }
        try:
            timer_id = client_id + "login"
            timers[timer_id].stop()
            timers[timer_id] = None

            init_timer(client_id)

            logger.info("Timer killed successfully")
        except:
            logger.error("Error occurred trying to kill timer")
            pass
        response = requests.post(SERVER + '/api/v1/whatsapp/webhook', json=body)


def serve_user_login_v2(client_id):
    driver = drivers[client_id]

    # User is logged In
    if driver.is_logged_in():
        logger.info("Driver Logged In")
        phone = drivers[client_id].get_id().replace("\"", "").replace("@c.us", "")
        body = {
            'success': True,
            'isLoggedIn': True,
            'appId': client_id,
            "msisdn": phone,
            "qr": None
        }
        drivers[client_id].save_sessions()

        try:
            timer_id = client_id + "login"
            timers[timer_id].stop()
            timers[timer_id] = None

            init_timer(client_id)

            logger.info("Timer killed successfully")
        except:
            logger.error("Error occurred trying to kill Login timer")
            pass

        response = requests.post(WEBHOOK + '/api/v1/whatsapp/webhook', json=body)
        logger.info("User logged In "+ str(WEBHOOK)+ " " + str(response))
    else:
        try:
            logger.info("Not Logged In (Status) - Trying to get QR")
            qr = driver.get_qr_base64()
            body = {
                'success': True,
                'appId': client_id,
                'isLoggedIn': False,
                'qr': qr
            }
            response = requests.post(WEBHOOK + '/api/v1/whatsapp/webhook', json=body)
            logger.info("Sending QR to server " + str(WEBHOOK) + " " + str(response))
        except Exception as e:
            logger.error("Disconnected (Status) - Failed to get QR . Sending notice")
            body = {
                'success': True,
                'isLoggedIn': False,
                'appId': client_id,
                "message": "WhatsApp Web is not connected",
                "qr": None
            }
            response = requests.post(WEBHOOK + '/api/v1/whatsapp/webhook', json=body)
            logger.info("Sending Error to server " + str(WEBHOOK) + " " + str(response))


def send_qr(client_id):
    driver = drivers[client_id]

    if not driver.is_logged_in():
        qr_code = driver.get_qr_base64()
        body = {
            'success': True,
            'appId': client_id,
            'isLoggedIn': False,
            'qr': qr_code
        }
        response = requests.post(WEBHOOK + '/api/v1/whatsapp/webhook', json=body)
        logger.info("Sending QR to server " + str(WEBHOOK) + " " + str(response))


def send_data(client_id):
    logger.info("Driver Logged In")

    # get phone number from local storage
    phone = drivers[client_id].get_id().replace("\"", "").replace("@c.us", "")
    body = {
        'success': True,
        'isLoggedIn': True,
        'appId': client_id,
        "msisdn": phone,
        "qr": None
    }
    drivers[client_id].save_sessions()
    # Stop Login timer
    stop_login_timer(client_id)

    # Send post requests to r2mp
    response = requests.post(WEBHOOK + '/api/v1/whatsapp/webhook', json=body)
    logger.info("User logged In " + str(WEBHOOK) + " " + str(response))


def stop_login_timer(client_id):
    try:
        timer_id = client_id + "login"
        timers[timer_id].stop()
        timers[timer_id] = None

        init_timer(client_id)

        logger.info("Timer killed successfully")
    except:
        logger.error("Error occurred trying to kill Login timer")
        pass


def check_new_messages(client_id):

    """Check for new unread messages and send them to the custom api

    @param client_id: ID of client user
    """
    # Return if driver is not defined or if whatsapp is not logged in.
    # Stop the timer as well
    if (
            client_id not in drivers
            or not drivers[client_id]
            or not drivers[client_id].is_logged_in()
    ):
        return

    # Acquire a lock on thread
    # logger.info("Acquiring a lock on thread {0}".format(client_id))
    # if not acquire_semaphore(client_id, True):
    #     return

    try:
        body = {}
        # Get all unread messages
        res = drivers[client_id].get_unread()
        # Mark all of them as seen
        for message_group in res:
            message_group.chat.send_seen()
        # Release thread lock
        release_semaphore(client_id)
        # If we have new messages, do something with it
        if res:
            logger.info(res)
            for message_group in res:
                # message_group = res[0]
                if not message_group.chat._js_obj["isGroup"]:
                    if client_id in food_ordering:
                        forwarder = threading.Thread(target=process_message_to_randy, args=(message_group, client_id))
                        forwarder.start()
                    else:
                        forwarder = threading.Thread(target=send_message_to_client, args=(message_group, client_id))
                        forwarder.start()
    except Exception as e:
        print(str(e))
        pass
    finally:
        # Release lock anyway, safekeeping
        release_semaphore(client_id)


def reformat_message_r2mp(message, appId):
    body = {"recipientMsisdn": message._js_obj["to"].replace("@c.us", ""),
            "content": message.content if message.type == "chat" else "https://www.latlong.net/c/?lat=" + str(
                message.latitude) + "&long=" + str(message.longitude)}
    # body['recipientMsisdn'] = recipient_msisdn
    if message.type == "location":
        location_url = "https://www.latlong.net/c/?lat=" + str(message.latitude) + "&long=" + str(message.longitude)
        body["location"] = '<a href="' + location_url + '" target="_blank"> Click to view location </a>'
    body['content'] = message.content
    body["type"] = "text"
    body["timeSent"] = message.timestamp.isoformat()
    body["senderMsisdn"] = message.chat_id.replace("@c.us", "")
    body["messageId"] = message.id
    body["companyId"] = appId
    body["appId"] = appId
    return body


def number_emoji(text):
    return text.replace(".1.", "1️⃣", 1).replace(".2.", "2️⃣", 1).replace(".3.", "3️⃣", 1).replace(".4.", "4️⃣",
                                                                                                   1).replace(".5.",
                                                                                                              "5️⃣",
                                                                                                              1).replace(
        ".6.", "6️⃣", 1) \
        .replace(".7.", "7️⃣", 1).replace(".8.", "8️⃣", 1).replace(".9.", "9️⃣", 1).replace(".10.", " 🔟", 1).replace(
        ".11.", '1️⃣1️⃣', 1).replace(".12.", "1️⃣2️⃣", 1) \
 \
 \
# Process the incoming message and forward to whoever wants it


def send_message_to_client(message_group, appId):
    logger.info("About to process incoming message")
    message = message_group.messages[0]
    chat = message_group.chat

    body = dict()
    body["recipientMsisdn"] = message._js_obj["to"].replace("@c.us", "")
    body["timeSent"] = message.timestamp.isoformat()
    body["senderMsisdn"] = message.chat_id.replace("@c.us", "")
    body['senderUsername'] = message._js_obj['sender']['pushname']
    body["messageId"] = message.id
    body["companyId"] = appId
    body["appId"] = appId

    # check if chat has payload else create
    if message.chat_id not in payload and message.chat_id not in payload2:
        payload[message.chat_id] = dict()
        payload2[message.chat_id] = dict()

    # check if message is a chat
    if message.type == "chat":
        body["content"] = message.content
        body["type"] = "text"

        # message is a reply to a quick reply
        if message.content in payload[message.chat_id]:
            logger.info("User swiped to reply option")
            body["content"] = message.content
            body['postback'] = {"payload": payload[message.chat_id][message.content]}
            body['quick_reply'] = payload[message.chat_id][message.content]
        else:
            # User typed in the choice of order
            if len(message.content) < 3 and message.content.isdigit():
                logger.info("User choice out of range")
                chat.send_message("‼ 🖐 Choice out of range 😬 . 🤗 Please send any number from 1 to " + str(
                    len(payload[message.chat_id])) + " to make a 🤝 selection")
                return

        if message.content.lower().replace(" ", "") in payload2[message.chat_id]:
            # User type in full the preferred choice
            msg = message.content.lower().replace(" ", "")
            body["content"] = message.content
            body['postback'] = {"payload": payload2[message.chat_id][msg]}
            body['quick_reply'] = payload2[message.chat_id][msg]

        # if its a reply
        if message._js_obj["quotedMsg"] is not None:
            if message._js_obj["quotedMsg"]["type"] == "chat":
                text = message._js_obj['quotedMsg']['body']
                body['content'] = text
                body['postback'] = {"payload": payload[message.chat_id][text]}
                body['quick_reply'] = payload[message.chat_id][text]
            else:
                text = message._js_obj['quotedMsg']['caption']
                body['content'] = text
                body['postback'] = {"payload": payload[message.chat_id][text]}
                body['quick_reply'] = payload[message.chat_id][text]
        forward_message_to_r2mp(body, message.chat_id)
    elif message.type == "location":

        address = gmaps.reverse_geocode((message.latitude, message.longitude))
        place_id = address[0]['place_id']
        formatted_address = address[0]['formatted_address']
        location_intent = "intent.useLocation.{0}".format(place_id)

        body['postback'] = {"payload": location_intent}
        body['quick_reply'] = location_intent
        body['content'] = formatted_address
        body['text'] = 'text'

        delivery_info = "Your ongoing order will be delivered at {0} after confirmation".format(formatted_address)
        chat.send_message(delivery_info)
        forward_message_to_r2mp(body, message.chat_id)

    else:
        logger.info("Media Message incoming")


def forward_message_to_r2mp(message_data, chat_id):
    headers = {'Content-Type': 'application/json; charset=utf-8', 'x-r2-wp-screen-name': message_data["companyId"],
               'msisdn': message_data["recipientMsisdn"]}

    response = requests.post(SERVER + "/api/v1/bot?channelType=WHATSAPP",
                             headers=headers,
                             json=message_data)
    # url = SERVER + '/api/v1/bot?channelType=WHATSAPP'
    # encoded_data = json.dumps(message_data).encode('utf-8')
    # response = http.request('POST', url, body=encoded_data, headers=headers)
    # payload[chat_id] = dict()
    # payload2[chat_id] = dict()
    logger.info(
        "Message " + message_data['content'] + " sent to " + SERVER + "/api/v1/bot?channelType=WHATSAPP ---- " + str(
            response))


def get_client_info(client_id):
    """Get the status of a perticular client, as to he/she is connected or not

    @param client_id: ID of client user
    @return JSON object {
        "driver_status": webdriver status
        "is_alive": if driver is active or not
        "is_logged_in": if user is logged in or not
        "is_timer": if timer is running or not
    }
    """
    if client_id not in drivers:
        return None

    driver_status = drivers[client_id].get_status()
    is_alive = False
    is_logged_in = False
    if (
            driver_status == WhatsAPIDriverStatus.NotLoggedIn
            or driver_status == WhatsAPIDriverStatus.LoggedIn
    ):
        is_alive = True
    if driver_status == WhatsAPIDriverStatus.LoggedIn:
        is_logged_in = True

    return {
        "is_alive": is_alive,
        "is_logged_in": is_logged_in,
        "is_timer": bool(timers[client_id]) and timers[client_id].is_running,
    }


def allowed_file(filename):
    """Check if file as allowed type or not

    @param filename: Name of the file to be checked
    @return boolean True or False based o#!/bin/sh

pwdn file name check
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def send_media(chat_id, requestObj):
    files = requestObj.files
    if not files:
        return jsonify({"Status": False})

    # create user folder if not exists
    profile_path = create_static_profile_path(g.client_id)

    file_paths = []
    for file in files:
        file = files.get(file)
        if file.filename == "":
            return {"Status": False}

        if not file or not allowed_file(file.filename):
            return {"Status": False}

        filename = secure_filename(file.filename)

        # save file
        file_path = os.path.join(profile_path, filename)
        file.save(file_path)
        file_path = os.path.join(os.getcwd(), file_path)

        file_paths.append(file_path)

    caption = requestObj.form.get("message")

    res = None
    for file_path in file_paths:
        res = g.driver.send_media(file_path, chat_id, caption)
    return res


def get_file_name(url):
    name = uuid.uuid5(uuid.NAMESPACE_URL, str(url))

    # parts = url.split('-')
    # return parts[len(parts) - 1] + ".jpg"
    return str(name) + ".jpg"


def download_file(url):
    file_name = get_file_name(url)
    file_path = os.path.join(STATIC_FILES_PATH, file_name)
    if not os.path.isfile(file_path):
        print("About to download image")
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            r.raw.decode_content = True
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
                f.close()
                return file_path
    else:
        return file_path


def download_file2(url):
    file_name = get_file_name(url)
    file_path = os.path.join(STATIC_FILES_PATH, file_name)

    if not os.path.isfile(file_path):
        try:
            logger.info("About to downloading files : " + url)
            save_path = urllibrequest.urlretrieve(url, filename=file_path)[0]
            save_path = urllibrequest.urlretrieve(url, filename=file_path)[0]
            logging.info("Dowloading files")
            return save_path
        except Exception:
            logger.exception("Error in downloading file " + url)
            return False
    else:
        return file_path


def create_static_profile_path(client_id):
    """Create a profile path folder if not exist

    @param client_id: ID of client user
    @return string profile path
    """
    profile_path = os.path.join(STATIC_FILES_PATH, str(client_id))
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)
    return profile_path


def acquire_semaphore(client_id, cancel_if_locked=False):
    if not client_id:
        return False

    if client_id not in semaphores:
        semaphores[client_id] = threading.Semaphore()

    timeout = 10
    if cancel_if_locked:
        timeout = 0

    val = semaphores[client_id].acquire(blocking=True, timeout=timeout)

    return val


def release_semaphore(client_id):
    if not client_id:
        return False

    if client_id in semaphores:
        semaphores[client_id].release()


def process_message_to_randy(message_group, client_id):
    logger.info('About to send the message to Randy')
    message = message_group.messages[0]
    chat = message_group.chat

    # url = 'https://twilio.rancardmobility.com'
    url = 'http://sandbox.rancardmobility.com:5958'
    # url = 'https://3775bf328917.ngrok.io'
    payload_to_randy = {'SmsMessageSid': 'SM0{0}'.format(message.id),
               'NumMedia': '0',
               'ProfileName': message._js_obj['sender']['pushname'],
               'SmsSid': 'SM0{0}'.format(message.id),
               'WaId': message._js_obj["to"].replace("@c.us", ""),
               'SmsStatus': 'received',
               'Body': message.content,
               'To': 'whatsapp:+{0}'.format(message._js_obj['to'].replace('@c.us', '')),
               'NumSegments': '1',
               'MessageSid': 'SM0{0}'.format(message.id),
               'AccountSid': 'AC7787685627e3c6ddc5ea5eb1003aaeb1',
               'From': 'whatsapp:+{0}'.format(message.chat_id.replace("@c.us", "")),
               'ApiVersion': '2010-04-01'
               }
    if message.type == 'location':
        payload_to_randy['latitude'] = message.latitude
        payload_to_randy['longitude'] = message.longitude

    response = requests.post(url, data=payload_to_randy)

    logger.info('Sending ' + message.content + ' to ' + url + str(response))

    json_response = xmltodict.parse(response.text)

    texts = json_response['Response']['Message']
    final_text = ''

    if len(texts) == 1:
        final_text = texts['Body']
        chat.send_message(final_text)
    else:
        for text in texts:
            final_text = final_text + text['Body']
            chat.send_message(text['Body'])
        logger.info('Replying ' + final_text)


@app.before_request
def before_request():
    logger.info("New Request")
    """This runs before every API request. The function take cares of creating
    driver object is not already created. Also it checks for few prerequisits
    parameters and set global variables for other functions to use

    Required paramters for an API hit are:
    auth-key: key string to identify valid request
    client_id: to identify for which client the request is to be run
    """

    if not request.url_rule:
        abort(404)

    logger.info("API call " + request.method + " " + request.url)

    auth_key = request.headers.get("auth-key")
    g.client_id = request.headers.get("client_id")
    rule_parent = request.url_rule.rule.split("/")[1]

    if rule_parent == "test":
        return


    if API_KEY and auth_key != API_KEY:
        abort(401, "you must send valid auth-key")
        logger.error("You must send a valid auth key")
        raise Exception()

    if not g.client_id and rule_parent != "admin":
        abort(400, "client ID is mandatory")
        logger.error("you must send a valid auth ey")

    logger.info("About acquiring semaphore for client" + g.client_id)
    acquire_semaphore(g.client_id)

    # Create a driver object if not exist for client requests.

    if rule_parent != "admin":
        if g.client_id not in drivers:
            logger.info("About to initialise new driver ")
            drivers[g.client_id] = init_client(g.client_id)

        g.driver = drivers[g.client_id]
        g.driver_status = WhatsAPIDriverStatus.Unknown

        if g.driver is not None:
            logger.info("About getting driver status")
            # g.driver_status = WhatsAPIDriverStatus.Unknown
            g.driver_status = g.driver.get_status()
            logger.info("Driver Status - " + g.driver_status)

        # If driver status is unkown, means driver has closed somehow, reopen it
        logger.info("Checking if driver is unknown")
        if (
                g.driver_status != WhatsAPIDriverStatus.NotLoggedIn
                and g.driver_status != WhatsAPIDriverStatus.LoggedIn
        ):
            logger.info("Re-initiaising driver")
            drivers[g.client_id] = init_client(g.client_id)
            g.driver_status = g.driver.get_status()

        init_timer(g.client_id)
        logger.info("subscribing to new messages")
        # g.driver.subscribe_new_messages(NewMessageObserver(g.client_id))


@app.after_request
def after_request(r):
    """This runs after every request end. Purpose is to release the lock acquired
    during staring of API request"""
    if "client_id" in g and g.client_id:
        release_semaphore(g.client_id)
    return r


# -------------------------- ERROR HANDLER -----------------------------------


@app.errorhandler(werkzeug.exceptions.InternalServerError)
def on_bad_internal_server_error(e):
    if "client_id" in g and g.client_id:
        release_semaphore(g.client_id)
    if type(e) is WebDriverException and "chrome not reachable" in e.msg:
        drivers[g.client_id] = init_driver(g.client_id)
        return jsonify(
            {
                "success": False,
                "message": "For some reason, browser for client "
                           + g.client_id
                           + " has closed. Please, try get QrCode again",
            }
        )
    else:
        raise e


"""
#####################
##### API ROUTES ####
#####################
"""


# ---------------------------- Client -----------------------------------------


@app.route("/client", methods=["PUT"])
def create_client():
    """Create a new client driver. The driver is automatically created in
    before_request function."""
    result = False
    if g.client_id in drivers:
        result = True
    return jsonify({"Success": result})


@app.route("/client", methods=["DELETE"])
def remove_client():
    """Delete all objects related to client"""
    preserve_cache = request.args.get("preserve_cache", False)
    delete_client(g.client_id, preserve_cache)
    return jsonify({"Success": True})


# ---------------------------- WhatsApp ----------------------------------------


@app.route("/screen", methods=["GET"])
def get_screen():
    """Capture chrome screen image and send it back. If the screen is currently
    at qr scanning phase, return the image of qr only, else return image of full
    screen"""
    img_title = "screen_" + g.client_id + ".png"
    image_path = STATIC_FILES_PATH + img_title
    if g.driver_status != WhatsAPIDriverStatus.LoggedIn:
        try:
            g.driver.get_qr(image_path)
            return send_file(image_path, mimetype="image/png")
        except Exception as err:
            pass
    g.driver.screenshot(image_path)
    return send_file(image_path, mimetype="image/png")


@app.route("/screen/qr", methods=["GET"])
def get_qr():
    """Get qr as a json string"""
    qr = g.driver.get_qr_plain()
    return jsonify({"qr": qr})


def process_request(client_id):
    state = drivers[client_id].alert_user_login()

    if state:
        send_data(client_id)
    else:
        stop_login_timer(client_id)


@app.route("/screen/qr/request", methods=["POST"])
def initialise_authentication():
    logger.info("QR requested")
    init_login_timer(g.client_id)
    client_id = g.client_id
    forwarder = threading.Thread(target=process_request, args=(client_id,))
    forwarder.start()
    return jsonify({
        "success": True
    })


# @app.route("/screen/qr/request", methods=["POST"])
# def begin_login_timer():
#     logger.info("QR requested")
#     """ Initialise login timer """
#     try:
#         init_login_timer(g.client_id)
#         logger.info("Timer initialised")
#         return jsonify({
#             "success": True
#         })
#     except Exception:
#         logger.error("Timer initialisation failed")
#         return jsonify({
#             "success": False
#         })


@app.route("/screen/qr/base64", methods=["GET"])
def get_qr_base64():
    logger.info("QR code in base64 requested")
    """ Get qr as base64 string"""
    try:
        qr = g.driver.get_qr_base64()
        logger.info("Successfully returning QR code as base 64 string")
        return jsonify({
            "success": True,
            "isLoggedIn": False,
            "qr": qr
        })
    except NoSuchElementException:
        phone = g.driver.get_id().replace("\"", "").replace("@c.us", "")
        logger.info("User is logged In, Successfully returning phone number")
        return jsonify({
            "success": True,
            "msisdn": phone,
            "isLoggedIn": True,
            "qr": None
        })


@app.route("/messages/unread", methods=["GET"])
@login_required
def get_unread_messages():
    """Get all unread messages"""
    mark_seen = request.args.get("mark_seen", True)
    unread_msg = g.driver.get_unread()

    if mark_seen:
        for msg in unread_msg:
            msg.chat.send_seen()

    return jsonify(unread_msg)


@app.route("/contacts", methods=["GET"])
@login_required
def get_contacts():
    """Get contact list as json"""
    return jsonify(g.driver.get_contacts())


@app.route("/open/receive/<appId>", methods=["POST"])
def receive_message(appId):
    data = request.json
    logger.info("Twilio Message "+ str(data)+" Received for Company "+ str(appId))

    request_dict = request.form.to_dict()
    sender_msisdn = request_dict.get("From").split(":+")[1]
    chat_id = sender_msisdn + "@c.us"
    profile_name = str(request_dict.get("ProfileName"))
    content = str(request_dict.get("Body"))
    recipient_msisdn = request_dict.get("To").split(":+")[1]
    message_id = request_dict.get("MessageSid")

    body = dict()
    body["recipientMsisdn"] = recipient_msisdn
    body["timeSent"] = datetime.datetime.utcnow().isoformat()
    body["senderMsisdn"] = sender_msisdn
    body["senderUsername"] = profile_name
    body["messageId"] = message_id
    body["appId"] = appId
    body["companyId"] = appId

    # check if chat has payload else create
    if chat_id not in payload and chat_id not in payload2:
        payload[chat_id] = dict()
        payload2[chat_id] = dict()

    try:
        num_media = int(request.values.get("NumMedia"))
    except (ValueError, TypeError):
        return "Invalid request: invalid or missing NumMedia parameter", 400

    # Message is a chat
    # There is no media in the message payload
    if not num_media:
        if "Address" and "Longitude" in request_dict:
            lng = str(request_dict.get("Longitude"))
            lat = str(request_dict.get("Latitude"))
            formatted_address = str(request_dict.get("Address"))

            logger.info("Twilio Message - Location incoming")
            address = gmaps.reverse_geocode((lat, lng))
            place_id = address[0]['place_id']
            location_intent = "intent.useLocation.{0}".format(place_id)

            body['postback'] = {"payload": location_intent}
            body['quick_reply'] = location_intent
            body['content'] = formatted_address
            body['text'] = 'text'

            delivery_info = "Your ongoing order will be delivered at {0} after confirmation".format(formatted_address)
            forward_message_to_r2mp(body, chat_id)

        else:
            # Incoming message is a chat
            logger.info("Twilio Message - Chat incoming")
            body["content"] = content
            body["type"] = "text"

            if content in payload[chat_id]:
                logger.info("User swiped to reply option")
                body["content"] = content
                body['postback'] = {"payload": payload[chat_id][content]}
                body['quick_reply'] = payload[chat_id][content]
            else:
                # User typed in the choice of order
                if len(content) < 3 and content.isdigit():
                    logger.info("User choice out of range")
                    response = MessagingResponse()
                    msg = response.message("‼ 🖐 Choice out of range 😬 . 🤗 Please send any number from 1 to " + str(
                        len(payload[chat_id])) + " to make a 🤝 selection")
                    return str(response)

            if content.lower().replace(" ", "") in payload2[chat_id]:
                # User type in full the preferred choice
                msg = content.lower().replace(" ", "")
                body["content"] = content
                body['postback'] = {"payload": payload2[chat_id][msg]}
                body['quick_reply'] = payload2[chat_id][msg]

            forward_message_to_r2mp(body, chat_id)
    else:
        logger.info("Media Message, will process later")
        media_type = request_dict.get("MediaContentType0")
        media_url = request_dict.get("MediaUrl0")

        body["content"] = content
        body["type"] = "image"

        if "image" in media_type:
            body["type"] = "image"
        elif "audio" in media_type:
            body["type"] = "audio"
        elif "video" in media_type:
            body["type"] = "video"

        forward_message_to_r2mp(body, chat_id)

    return Response("Received", status=200, mimetype='application/json')

# ------------------------------- Chats ---------------------------------------


@app.route("/chats", methods=["GET"])
@login_required
def get_chats():
    """Return all the chats"""
    result = g.driver.get_all_chats()
    return jsonify(result)


@app.route("/chats/<chat_id>/messages", methods=["GET"])
@login_required
def get_messages(chat_id):
    """Return all of the chat messages"""

    mark_seen = request.args.get("mark_seen", True)

    chat = g.driver.get_chat_from_id(chat_id)
    msgs = list(g.driver.get_all_messages_in_chat(chat))

    for msg in msgs:
        print(msg.id)

    if mark_seen:
        for msg in msgs:
            try:
                msg.chat.send_seen()
            except:
                pass

    return jsonify(msgs)


@app.route("/chats/<chat_id>/messages", methods=["POST"])
@login_required
def send_message(chat_id):
    """Send a message to a chat
    If a media file is found, send_media is called, else a simple text message
    is sent
    """

    # global res
    res = {
        'status': 'Message Received'
    }
    data = request.json
    contents = data.get("contents")
    message = data.get("message")
    instruction = data.get("instruction")
    card = data.get("card")
    selection = str()

    chat = g.driver.get_chat_from_id(chat_id)
    payload[chat_id] = dict()
    payload2[chat_id] = dict()

    if card is not None:
        caption = card.get('caption')
        image_url = card.get('imageUrl').replace("https", "http")

        file_path = download_file(image_url)
        res = chat.send_media(file_path, caption)

    time.sleep(2)
    if message is not None:
        msg = message
        chat.send_message(msg)

    for content in contents:
        number = contents.index(content) + 1
        option = content.get('title')
        title = "." + str(number) + ". " + option
        intent = content.get('payload')
        image_url = content.get('imageUrl')

        if intent is not None:
            # payload[title] = intent
            # payload[str(number)] = intent
            payload[chat_id][str(number)] = intent

            # remove whitespaces and put in the second payload
            payload2[chat_id][option.lower().replace(" ", "")] = intent
        if image_url is None:
            selection = selection + number_emoji(title) + " \n"
            # chat.send_message(number_emoji(title))
        else:
            file_path = download_file(image_url)
            res = chat.send_media(file_path, number_emoji(title))
            time.sleep(2)

    if instruction is not None:
        text = "\n\n\n Do type {0} to select an option".format(', '.join(numbers[0:len(contents)]))
        selection = selection + text

    if selection is not "":
        res = chat.send_message(selection)
    if res:
        return jsonify(res)
    else:
        return False

    # files = request.files
    #
    # if files:
    #     res = send_media(chat_id, request)
    # else:
    #     message = request.form.get("message")
    #     logger.info("Sending :" +message + "to " + chat_id)
    #     res = g.driver.chat_send_message(chat_id, message)
    #
    #     if request.form.get("payload") is not None:
    #         payload[message] = request.form.get("payload")
    # if res:
    #     return jsonify(res)
    # else:
    #     return False


@app.route("/blast/<chat_id>/messages", methods=["POST"])
@login_required
def send_blast(chat_id):
    res = {
        'status': 'Message Received'
    }
    data = request.json
    message = data.get('message')
    media_url = data.get('image')

    if media_url is None:
        g.driver.send_message_to_id(chat_id, message)
    else:
        file_path = download_file(media_url)
        g.driver.send_media(file_path, chat_id, message)
    return jsonify(res)


@app.route("/messages/<msg_id>/download", methods=["GET"])
@login_required
def download_message_media(msg_id):
    """Download a media file"""
    message = g.driver.get_message_by_id(msg_id)

    if not message or not message.mime:
        abort(404)

    profile_path = create_static_profile_path(g.client_id)
    filename = message.save_media(profile_path, True)

    if os.path.exists(filename):
        return send_file(filename, mimetype=message.mime)

    abort(404)


# --------------------------- Admin methods ----------------------------------


@app.route("/admin/clients", methods=["GET"])
def get_active_clients():
    """Get a list of all active clients and their status"""
    global drivers

    if not drivers:
        return jsonify([])

    result = {client: get_client_info(client) for client in drivers}
    return jsonify(result)


@app.route("/admin/clients", methods=["PUT"])
def run_clients():
    """Force create driver for client """
    clients = request.form.get("clients")
    if not clients:
        return jsonify({"Error": "no clients provided"})

    result = {}
    for client_id in clients.split(","):
        if client_id not in drivers:
            init_client(client_id)
            init_timer(client_id)

        result[client_id] = get_client_info(client_id)

    return jsonify(result)


@app.route("/admin/client", methods=["DELETE"])
def erase_client():
    data = request.json
    client = data.get("clients")[0]

    if client in drivers:
        drivers.pop(client).quit()
        try:
            logger.info("Releasing Semaphore and Message time")
            timers[client].stop()
            timers[client] = None
            # release_semaphore(client)
            # semaphores[client] = None

            logger.info("Deleting profile for client")
            pth = CHROME_CACHE_PATH + g.client_id
            shutil.rmtree(pth)
            return jsonify({"Success": True})
        except:
            pass
    return jsonify({"Error": "Failed to delete profile"})


@app.route("/admin/clients", methods=["DELETE"])
def kill_clients():
    """Force kill driver and other objects for a perticular clien"""
    clients = request.json
    kill_dead = request.args.get("kill_dead", default=True)
    kill_dead = kill_dead and kill_dead in ["true", "1"]

    if not kill_dead and not clients:
        return jsonify({"Error": "no clients provided"})

    for client in list(drivers.keys()):
        if kill_dead and not drivers[client].is_logged_in() or client in clients:
            logger.info("About to delete client")
            drivers.pop(client).quit()
            try:
                timers[client].stop()
                timers[client] = None
                release_semaphore(client)
                semaphores[client] = None
                logger.info("Deleted Driver Successfully")
            except:
                pass

    return get_active_clients()


@app.route("/admin/exception", methods=["GET"])
def get_last_exception():
    """Get last exception"""
    return jsonify(sys.exc_info())


@app.route("/")
def hello():
    return "API is running"

@app.route("/test/ping")
def ping():
    return "Application is running"



get_connected_companies()

if __name__ == "__main__":
    # todo: load presaved active client ids
    app.run(port=8888, host='0.0.0.0')
