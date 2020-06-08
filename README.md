# Logamatic Monitor and Controller

Configures and monitors Buderus Logamatic 4000 heating controller through their ECO-CAN bus interface over MQTT.
This project aims to implement a full remote monitoring and control solution for Logamatic 4000 systems without expensive additional hardware. 
In my setup it takes a NodeMCU board with a CAN controller and a Raspberry Pi.

The main challenge was the CAN bus protocol. 
It's reverse engineering is partly based on public (but hard to find) documents from Buderus, a lot of bus sniffing, and trial-and-error (can_play.py) for the configuration sender.
All already available documents and tools assume a dedicated interface (called "service key", "RS232 gateway", ..)  between the Logamatic and the client. 
Those interfaces translate and buffer several aspects of the original protocol.

This project encodes and the decodes the raw messages on the CAN bus, not the "service key protocol" or the like.

## Modules:

- logamatic4000.py: Main module: Run with python3. Decodes and encodes raw Buderus ECO-CAN bus message (without an interface in between).

- mqtt_can.py: An interface to the ECO-CAN bus. It receives and sends CAN messages over MQTT. 
It requires a custom built hardware (in my case an ESP8266 with CAN) connected to the CAN bus. Bus messages are raw -- not processed, like in a service key.

- mqtt_logamatic.py: Sends out decoded monitor data updates, and config values over MQTT.
Listens for configuration change messages and queues them for the central module.
