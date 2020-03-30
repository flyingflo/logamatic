
import paho.mqtt.client
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

topic_prefix = "/heizung/logamatic/"
def on_connect(client, userdata, flags, rc, properties=None):
    log.info("on_connect rc %d", rc);
    client.subscribe(topic_prefix + "set_cnf/#")

def on_message(client, userdata, msg):
    try:
        log.debug("on_message %s", msg.topic)
        callback(msg)
    except Exception as E:
        log.exception("Exception on_message %s : %s", msg.topic, msg.payload)

def on_disconnect(client, userdata, rc):
    log.info("on_disconnect rc %d", rc);

def publish_value(key, value):
    client.publish(topic_prefix + key, value, retain=True)

callback = None

client = paho.mqtt.client.Client(client_id="logamatic_mqtt_monitor_and_control")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

def start(deliver_callback):
    log.info("Start")
    global callback
    callback = deliver_callback
    rc = client.connect("pi3.lan")
    log.info("client.connect %d", rc)
    client.loop_start()

def stop():
    log.info("Stop")
    client.loop_stop()

def test_callback(msg):
    log.info("test_callback")
    log.info("id %d data %s", msg.pkid, msg.data.hex())

if __name__ == "__main__":
    logging.basicConfig()
    start(test_callback)
    