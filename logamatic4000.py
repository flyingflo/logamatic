import mqtt_can
import mqtt_logamatic
import logging
from collections import namedtuple
import queue
import time
import sys

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

timestamp = time.time

class DataTypeBase():
    def __init__(self, name, fullname=""):
        self.name = name 
        self.fullname = fullname if fullname else name
        self.values = {}

    def decode(self, byte):
        """
        Args:
            byte to decode
        Returns:
            dict of decoded values 
        """

class DataSimple(DataTypeBase):
    def decode(self, byte):
        return {self.name: int(byte)}

class DataHex(DataTypeBase):
    def decode(self, byte):
        return {self.name: "0x{0:02X}".format(int(byte))}

class DataTempVorl(DataSimple):
    pass

class DataTempRaum(DataTypeBase):
    def decode(self, byte):
        return {self.name: int(byte)/2}

class DataTempAussen(DataTypeBase):
    def decode(self, byte):
        return {self.name: int.from_bytes(bytes((byte, )), 'little', signed=True)}

class DataHKStat1(DataTypeBase):
    def decode(self, byte):
        if byte == 0x04:
            v = "AUT"
        elif byte == 0:
            v = "MAN0"
        elif byte == 0x80:
            v = "MAN8"
        else:
            v = "0x{0:02X}".format(int(byte))
        return {self.name: v}

class DataHKStat2(DataTypeBase):
    def decode(self, byte):
        if byte == 1:
            v = "Sommer"
        elif byte == 2:
            v = "Tag"
        elif byte == 0:
            v = "Nacht"
        else:
            v = "0x{0:02X}".format(int(byte))
        return {self.name: v}

class MonBase:
    def __init__(self, monid, name, datalen):
        self.monid = monid
        self.name = name
        self.prefix = name
        self.datalen = datalen
        self.mem = [None]*datalen
        self.datatypes = [None]*datalen
        self.values = {}
        self.value_timestamps = {}
        
    def recv(self, databytes):
        blocklen = 6
        now = timestamp()
        i = databytes[0]
        if i+blocklen > self.datalen:
            raise ValueError("Monitor data out of bounds")
        self.mem[i:i+blocklen] = databytes[1:]
        updated = []
        for p in range(i, i+blocklen):
            if not self.datatypes[p]:
                log.debug("Mon recv %d: no datatype", p)
                continue
            log.debug("Mon recv %d: %s", p, self.datatypes[p].name)
            newval = self.datatypes[p].decode(self.mem[p])
            for nk in newval:
                k = "/".join((self.prefix, nk))
                log.debug("Mon recv got %s", k)
                if not k in self.values or self.values[k] != newval[nk]:
                    self.values[k] = newval[nk]
                    self.value_timestamps[k] = now
                    self.update_event(k)
    def get_value(self, k):
        fk = "/".join((self.prefix, k))
        return self.values[fk]

    def update_summary(self):
        pass

    def update_event(self, k):
        publish_update(k, self.values[k])
        self.update_summary()


class MonHeizkreis(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 18)
        self.datatypes[0] = DataHKStat1("Status1", "Betriebswerte 1")
        self.datatypes[1] = DataHKStat2("Status2", "Betriebswerte 2")
        self.datatypes[2] = DataTempVorl("T_Vs", "Vorlaufsolltemperatur")
        self.datatypes[3] = DataTempVorl("T_Vm", "Vorlaufisttemperatur")
        self.datatypes[4] = DataTempRaum("T_Rs", "Raumsolltemperatur")
        self.datatypes[5] = DataTempRaum("T_Rm", "Raumisttemperatur")

    def update_summary(self):
        def vs(k):
            try:
                return self.get_value(k)
            except:
                return "--"
        s = "V: {0}/{1}\nR: {2}/{3}\n{4} {5}".format(vs("T_Vs"), vs("T_Vm"), vs("T_Rs"), vs("T_Rm"), vs("Status1"), vs("Status2"))
        publish_summary(self.name, s)

    
class MonKessel(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 42)
        self.datatypes[0] = DataTempVorl("T_s", "Kesselvorlauf-Solltemperatur")
        self.datatypes[1] = DataTempVorl("T_m", "Kesselvorlauf-Isttemperatur")
        self.datatypes[7] = DataHex("Kesselstatus", "Kessel Betrieb Bits")
        self.datatypes[8] = DataSimple("Brenner_s", "Brenner Ansteuerung")
        self.datatypes[34] = DataHex("Brennerstatus", "Brenner Status Bits")
        
    def update_summary(self):
        def vs(k):
            try:
                return self.get_value(k)
            except:
                return "--"
        s = "V: {0}/{1}\nA: {2}".format(vs("T_s"), vs("T_m"), vs("Brenner_s"))
        publish_summary(self.name, s)

class MonGeneric(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 24)
        self.datatypes[0] = DataTempAussen("T_Aus", "Außentemperatur")

class MonSolar(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 54)
        self.datatypes[10] = DataTempVorl("T_Bufm", "Temperatur Speichermitte")
        self.datatypes[11] = DataTempVorl("T_Rlm", "Anlagenrücklauftemperatur")

    def update_summary(self):
        def vs(k):
            try:
                return self.get_value(k)
            except:
                return "--"
        s = "B: {0}\nR: {1}".format(vs("T_Bufm"), vs("T_Rlm"))
        publish_summary(self.name, s)

CompleteLogamaticType = namedtuple("LogamaticType", "name datalen dataclass shortname")
LogamaticType = lambda name, datalen, dataclass=None, shortname="": CompleteLogamaticType(name, datalen, dataclass, shortname)

monitor_types = {
    # name, overall data length, class
    0x80 : LogamaticType("Heizkreis 1", 18, MonHeizkreis),
    0x81 : LogamaticType("Heizkreis 2", 18, MonHeizkreis),
    0x82 : LogamaticType("Heizkreis 3", 18, MonHeizkreis),
    0x83 : LogamaticType("Heizkreis 4", 18, MonHeizkreis),
    0x84 : LogamaticType("Warmwasser", 12),
    0x85 : LogamaticType("Strategie wandhängend", 12),
    0x87 : LogamaticType("Fehlerprotokoll", 42),
    0x88 : LogamaticType("Kessel bodenstehend", 42, MonKessel, "Kessel"),
    0x89 : LogamaticType("Konfiguration", 24, MonGeneric),
    0x8A : LogamaticType("Heizkreis 5", 18, MonHeizkreis),
    0x8B : LogamaticType("Heizkreis 6", 18, MonHeizkreis),
    0x8C : LogamaticType("Heizkreis 7", 18, MonHeizkreis),
    0x8D : LogamaticType("Heizkreis 8", 18, MonHeizkreis),
    0x8E : LogamaticType("Heizkreis 9", 18, MonHeizkreis),
    0x8F : LogamaticType("Strategie bodenstehend", 30),
    0x90 : LogamaticType("LAP", 18),
    0x92 : LogamaticType("Kessel 1 wandhängend", 60),
    0x93 : LogamaticType("Kessel 2 wandhängend", 60),
    0x94 : LogamaticType("Kessel 3 wandhängend", 60),
    0x95 : LogamaticType("Kessel 4 wandhängend", 60),
    0x96 : LogamaticType("Kessel 5 wandhängend", 60),
    0x97 : LogamaticType("Kessel 6 wandhängend", 60),
    0x98 : LogamaticType("Kessel 7 wandhängend", 60),
    0x99 : LogamaticType("Kessel 8 wandhängend", 60),
    0x9A : LogamaticType("KNX FM446",60),
    0x9B : LogamaticType("Wärmemenge", 36),
    0x9C : LogamaticType("Störmeldemodul", 6),
    0x9D : LogamaticType("Unterstation", 6),
    0x9E : LogamaticType("Solarfunktion", 54, MonSolar, "Speicher"),
    0x9F : LogamaticType("alternativer Wärmeerzeuger", 42),
}
setting_types = {
    0x07 : LogamaticType("Heizkreis 1", 18),
    0x08 : LogamaticType("Heizkreis 2", 18),
    0x09 : LogamaticType("Heizkreis 3", 18),
    0x0A : LogamaticType("Heizkreis 4", 18),
    0x0B : LogamaticType("Außenparameter", 12),
    0x0C : LogamaticType("Warmwasser", 12),
    0x0D : LogamaticType("Konfiguration (Modulauswahl)", 18),
    0x0E : LogamaticType("Strategie wandhängend(UBA)", 18),
    0x10 : LogamaticType("Kessel bodenstehend", 18),
    0x11 : LogamaticType("Schaltuhr pro Woche Kanal 1", 18),
    0x12 : LogamaticType("Schaltuhr pro Woche Kanal 2", 18),
    0x13 : LogamaticType("Schaltuhr pro Woche Kanal 3", 18),
    0x14 : LogamaticType("Schaltuhr pro Woche Kanal 4", 18),
    0x15 : LogamaticType("Schaltuhr pro Woche Kanal 5", 18),
    0x16 : LogamaticType("Heizkreis 5", 18),
    0x17 : LogamaticType("Schaltuhr pro Woche Kanal 6", 18),
    0x18 : LogamaticType("Heizkreis 6", 18),
    0x19 : LogamaticType("Schaltuhr pro Woche Kanal 7", 18),
    0x1A : LogamaticType("Heizkreis 7", 18),
    0x1B : LogamaticType("Schaltuhr pro Woche Kanal 8", 18),
    0x1C : LogamaticType("Heizkreis 8", 18),
    0x1D : LogamaticType("Schaltuhr pro Woche Kanal 9", 18),
    0x1F : LogamaticType("Schaltuhr pro Woche Kanal 10", 18),
    0x20 : LogamaticType("Strategie bodenstehend", 12),
    0x24 : LogamaticType("Solar", 12),
    0x26 : LogamaticType("Strategie (FM458)", 12)
}

mon_objects = {}
can_recv_queue = queue.Queue()

def can_recv_callback(msg):
    can_recv_queue.put(msg)
    log.debug("Incoming CAN id %d data %s", msg.pkid, str(msg.data))

def handle_recv():
    msg = can_recv_queue.get()
    try:
        if msg.pkid & 0x400:
            recv_can_monitor(msg)
        if msg.pkid == 0:
            recv_can_setting(msg)
    except Exception as E:
        log.error(str(E))
        raise
    can_recv_queue.task_done()

def recv_can_setting(msg):
    log.debug("Can setting %d", msg.pkid)

def recv_can_monitor(msg):
    if len(msg.data) != 8:
        raise ValueError("CAN monitor message with len != 8")
    oid = msg.data[0]
    log.debug("Can monitor id=%d oid=0x%x", msg.pkid, oid)

    if not oid in mon_objects:
        if oid in monitor_types:
            if monitor_types[oid].dataclass:
                name = monitor_types[oid].shortname if monitor_types[oid].shortname else monitor_types[oid].name
                mon_objects[oid] = monitor_types[oid].dataclass(oid,name)
                log.info("New can monitor object 0x%x", oid)
            else:
                log.debug("No dataclass implemented for oid 0x%x", oid)
        else:
            log.warning("Unknown monitor oid 0x%x", oid)

    if oid in mon_objects:
        mon_objects[oid].recv(msg.data[1:])
        log.debug("Update for oid 0x%x done", oid)

def publish_update(k, v):
    log.info("Update: %s = %s", str(k), str(v))
    mqtt_logamatic.publish_value(str(k), str(v))
    update_value_dump()
    
def update_value_dump():
    global valuestr
    valuestr = ""
    for ok in sorted(mon_objects):
        o = mon_objects[ok]
        for vk in sorted(o.values):
            valuestr += vk.ljust(30) + "=" + str(o.values[vk]) + "\n"
    log.info("All current values:\n" + valuestr)
    if valuefile:
        with open(valuefile, "w") as f:
            f.write(valuestr)

def publish_summary(name, s):
    mqtt_logamatic.publish_summary(name, s)

def mqtt_command_callback(msg):
    log.info("Receive MQTT command %s : %s", msg.topic, msg.payload)

valuefile = None
valuestr = ""
if __name__ == "__main__":
    logging.basicConfig()
    try:
        valuefile = sys.argv[1]
    except: pass
    mqtt_can.start(can_recv_callback)
    mqtt_logamatic.start(mqtt_command_callback)
    try:
        while True:
            handle_recv()
    except KeyboardInterrupt:
        mqtt_can.stop()
        mqtt_logamatic.stop()
        log.info("Exit")
        sys.exit(0)