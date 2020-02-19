import paho.mqtt.client
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
logging.basicConfig()

class CanMsg:
    def __init__(self, pkid, data, rtr=0):
        self.rtr = rtr
        self.pkid = pkid
        self.data = data

def on_connect(client, userdata, flags, rc, properties=None):
    log.info("on_connect rc %d", rc);
    client.subscribe("/heizung/burner/can/raw/recv/")

def on_message(client, userdata, msg):
    log.debug("on_message %s", msg.topic)
    m = msg.payload.decode().split(";")
    canmsg = CanMsg(int(m[1], base=16), bytes.fromhex(m[2]), int(m[0]))
    callback(canmsg)

callback = None

client = paho.mqtt.client.Client()
client.on_connect = on_connect
client.on_message = on_message

def start(deliver_callback):
    log.info("Start MQTT CAN receiver")
    global callback
    callback = deliver_callback
    rc = client.connect("pi3.lan")
    log.info("client.connect %d", rc)
    client.loop_start()

def stop():
    log.info("Stop MQTT CAN receiver")
    client.loop_stop()

def test_callback(msg):
    log.info("test_callback")
    log.info("id %d data %s", msg.pkid, msg.data.hex())

if __name__ == "__main__":
    start(test_callback)
    