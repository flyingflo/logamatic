# Logamatic Monitor and Controller

Configures and monitors Buderus Logamatic 4000 heating controller through their ECO-CAN bus interface over MQTT.
This project aims to implement a full remote monitoring and control solution for Logamatic 4000 systems without expensive additional hardware. 
In my setup it takes a NodeMCU board with a CAN controller and a Raspberry Pi.

The main challenge was the CAN bus protocol. 
It's reverse engineering is partly based on public (but hard to find) documents from Buderus, a lot of bus sniffing, and trial-and-error (can_play.py) for the configuration sender.
All already available documents and tools assume a dedicated interface (called "service key", "RS232 gateway", ..)  between the Logamatic and the client. 
Those interfaces translate and buffer several aspects of the original protocol.

This project encodes and the decodes the raw messages on the CAN bus, not the "service key protocol" or the like.

## Requirements

You need a MQTT broker. For example mosquitto:

`sudo apt install mosquitto mosquitto-clients`



## Modules:

This program has only MQTT interfaces. 
It receives and sends CAN messages on the one side and it broadcasts decoded monitor data and receives control commands over MQTT on the other side.

- logamatic4000.py: Main module: Run with python3. Decodes and encodes raw Buderus ECO-CAN bus message (without an interface in between).

- mqtt_can.py: An interface to the ECO-CAN bus. It receives and sends CAN messages over MQTT. 
It requires a custom built hardware (in my case an ESP8266 with CAN) connected to the CAN bus. Bus messages are raw -- not processed, like in a service key.
Example input:
```
/heizung/burner/can/raw/recv/ 0;421;88 00 0c 19 05 13 00 00 
/heizung/burner/can/raw/recv/ 0;421;88 06 00 20 00 ff 00 00 
/heizung/burner/can/raw/recv/ 0;421;88 0c 01 56 3c ff ff ff 
/heizung/burner/can/raw/recv/ 0;421;88 12 00 2d 69 ff ff ff 
/heizung/burner/can/raw/recv/ 0;421;88 18 1e 64 9c 00 19 6e 
/heizung/burner/can/raw/recv/ 0;421;88 1e 5f 19 00 00 82 00 
/heizung/burner/can/raw/recv/ 0;421;88 24 00 00 6e 6e 6e 00 
/heizung/burner/can/raw/recv/ 0;421;89 00 14 11 04 11 00 00 
```

- mqtt_logamatic.py: Sends out decoded monitor data updates, and config values over MQTT.
Listens for configuration change messages and queues them for the central module.
Example output:
```
/heizung/logamatic/mon/Heizkreis 1/T_Rm 22.5
/heizung/logamatic/mon/Heizkreis 1/T_Rs 0.0
/heizung/logamatic/mon/Heizkreis 1/T_Vm 23
/heizung/logamatic/mon/Heizkreis 1/T_Vs 5
/heizung/logamatic/mon/Heizkreis 1/Status1 MAN Aus
/heizung/logamatic/mon/Heizkreis 1/Status2 Nacht
```

## Usage:
Check the mqtt_*.py files and replace "pi3.lan" with the hostname of your MQTT broker.
```
python3 logamatic4000.py
```
