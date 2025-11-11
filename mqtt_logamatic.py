import paho.mqtt.client
import logging
from dotenv import load_dotenv
import os
import json
import hashlib

load_dotenv()

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

topic_prefix = os.getenv("TOPIC_PREFIX", "/heizung/logamatic/")
discovery_prefix = os.getenv("DISCOVERY_PREFIX", "homeassistant/")


def on_connect(client, userdata, flags, rc, properties=None):
    log.info("on_connect rc %d", rc)
    client.subscribe(topic_prefix + "set_cnf/#")


def on_message(client, userdata, msg):
    try:
        log.debug("on_message %s", msg.topic)
        callback(msg)
    except Exception as E:
        log.exception("Exception on_message %s : %s", msg.topic, msg.payload)


def on_disconnect(client, userdata, rc):
    log.info("on_disconnect rc %d", rc)


def get_state_topic(prefix, key):
    t = "/".join([topic_prefix] + prefix + [key])
    t = t.replace("//", "/")
    return t


def get_set_cnf_topic(prefix, key):
    t = "/".join([topic_prefix] + ["set_cnf"] + prefix[1:] + [key])
    t = t.replace("//", "/")
    return t


def publish_update(prefix, key, value, meta, monid, object_name, value_fullname):
    if meta:
        publish_discovery(prefix, key, meta, monid, object_name, value_fullname)
    publish_value(prefix, key, value)


def publish_value(prefix, key, value):
    t = get_state_topic(prefix, key)
    log.debug("Send value %s", t)
    client.publish(t, value, retain=True)

discovery_sent = set()
def publish_discovery(prefix, key, meta, monid, object_name, value_fullname):
    discovery_device = {"identifiers": ["logamatic"], "name": "Logamatic"}
    state_topic = get_state_topic(prefix, key)
    c = dict(meta)
    c["name"] = "/".join(prefix + [value_fullname])
    c["unique_id"] = hashlib.sha1(state_topic.encode()).hexdigest()[:8]
    c["state_topic"] = state_topic
    c["device"] = discovery_device
    if "platform" not in c:
        c["platform"] = "sensor"

    if prefix[0] == "cnf":
        c["command_topic"] = get_set_cnf_topic(prefix, key)

    t = f"{discovery_prefix}/{c['platform']}/{c['unique_id']}/config"
    t = t.replace("//", "/")
    if t in discovery_sent:
        return
    m = json.dumps(c, indent=2)
    log.debug("Send discovery %s", t)
    client.publish(t, m, retain=True)
    discovery_sent.add(t)


callback = None

client = paho.mqtt.client.Client(client_id="logamatic_mqtt_monitor_and_control")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect


def start(deliver_callback):
    log.info("Start")
    global callback
    callback = deliver_callback

    if os.getenv("MQTT_WRITE_USERNAME") and os.getenv("MQTT_WRITE_PASSWORD"):
        client.username_pw_set(
            username=os.getenv("MQTT_WRITE_USERNAME"),
            password=os.getenv("MQTT_WRITE_PASSWORD"),
        )
    rc = client.connect(os.getenv("MQTT_WRITE_HOST", "localhost"))

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
