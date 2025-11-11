import mqtt_can
import mqtt_logamatic
import logging
from collections import namedtuple
import queue
import time
import sys

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
log_send = logging.getLogger("send_conf")
log_send.setLevel(logging.INFO)

timestamp = time.time

class DataTypeBase():
    def __init__(self, name, fullname="", metadata={}):
        self.name = name
        self.fullname = fullname if fullname else name
        self.values = {}
        self.metadata = dict(metadata)

    def decode(self, byte):
        """
        Args:
            byte to decode
        Returns:
            dict of decoded values
        """

class DataUInt8(DataTypeBase):
    def decode(self, byte):
        return {self.name: int(byte)}

class DataUint8Hex(DataTypeBase):
    def decode(self, byte):
        return {self.name: "0x{0:02X}".format(int(byte))}

class DataTempVorl(DataUInt8):
    pass

class DataTempRueckl(DataUInt8):
    pass

class DataTempWW(DataUInt8):
    pass

class DataTempRaum(DataTypeBase):
    def decode(self, byte):
        t = int(byte)/2
        if t == 55:     # --> means invalid value
            return {}
        return {self.name: t}
    def encode(self, value):
        return int(float(value)*2)

class DataTempAussen(DataTypeBase):
    def decode(self, byte):
        return {self.name: int.from_bytes(bytes((byte, )), 'little', signed=True)}
    def encode(self, value):
        return int(value)

class DataUIntMultiByte(DataTypeBase):
    class ByteHook(DataTypeBase):
        def __init__(self, parent, byteindex):
            self.parent = parent
            self.byteindex = byteindex

        @property
        def name(self):
            return self.parent.name + "byte " + str(self.byteindex)

        @property
        def metadata(self):
            return self.parent.metadata

        @property
        def fullname(self):
            return self.parent.fullname

        def decode(self, byte):
            self.parent.bytesvalues[self.byteindex] = byte
            # Update the complete value after all bytes have been received.
            # They use big endian but number them like little, so byte zero will come last.
            if self.byteindex == 0:
                v = int.from_bytes(self.parent.bytesvalues, byteorder='little', signed=False)
                return {self.parent.name: v}
            else:
                return {}

    def __init__(self, bytecount, name, fullname='', metadata={}):
        super().__init__(name, fullname, metadata)
        self.bytesvalues = [0] * bytecount
        self.bytehooks = [self.ByteHook(self, i) for i in range(bytecount)]

    def byte(self, i):
        return self.bytehooks[i]

class DataHKStat1(DataTypeBase):
    """
    Bits:
    Ausschaltoptimierung
    Einschaltoptimierung
    Automatik
    Warmwasservorrang
    Estrichtrocknung
    Ferien
    Frostschutz
    Manuell
    """
    def decode(self, byte):
        if byte == 0x04:
            v = "AUT"
        elif byte == 0:
            v = "MAN Aus"
        elif byte == 0x80:
            v = "MAN Ein"
        else:
            v = "0x{0:02X}".format(int(byte))
        return {self.name: v}

class DataHKStat2(DataTypeBase):
    """
    1. Bit = Sommer
    2. Bit = Tag
    3. Bit = keine Kommunikation mit FB
    4. Bit = FB fehlerhaft
    5. Bit = Fehler Vorlauffühler
    6. Bit = maximaler Vorlauf
    7. Bit = externer Störeingang
    8. Bit = Party / Pause
    """
    def decode(self, byte):
        if byte == 1:
            v = "Nacht Sommer"
        if byte == 3:
            v = "Tag Sommer"
        elif byte == 2:
            v = "Tag"
        elif byte == 0:
            v = "Nacht"
        else:
            v = "0x{0:02X}".format(int(byte))
        return {self.name: v}

class DataWWStat1(DataTypeBase):
    """
    Bits:
    Automatik
    Desinfektion
    Nachladung
    Ferien
    Fehler Desinfektion
    Fehler Fühler
    Fehler WW bleibt kalt
    Fehler Anode
    """
    def decode(self, byte):
        flags = []
        if byte & 0x1:
            flags.append("AUT")
        if byte & 0x4:
            flags.append("NL")
        if byte & 0x8:
            flags.append("HOL")
        if byte & 0x40:
            flags.append("ErrK")
        v = "{1} 0x{0:02X}".format(int(byte), "|".join(flags))
        return {self.name: v}

class DataWWStat2(DataTypeBase):
    """
    Bits:
    Laden
    Manuell
    Nachladen
    Ausschaltoptimierung
    Einschaltoptimierung
    Tag
    Warm
    Vorrang

    """
    def decode(self, byte):
        flags = []
        if byte & 0x1:
            flags.append("LAD")
        if byte & 0x2:
            flags.append("MAN")
        if byte & 0x4:
            flags.append("NL")
        if byte & 0x20:
            flags.append("TAG")
        if byte & 0x40:
            flags.append("WARM")
        v = "{1} 0x{0:02X}".format(int(byte), "|".join(flags))
        return {self.name: v}

class Obase:
    def __init__(self, monid, name, datalen):
        self.monid = monid
        self.name = name
        self.prefix = ["base", name]
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
            log.warning("Monitor 0x%x data out of bounds %d, data %s", self.monid, self.datalen, str(databytes))
            return
        self.mem[i:i+blocklen] = databytes[1:]
        for p in range(i, i+blocklen):
            if not self.datatypes[p]:
                log.debug("Mon recv %d: no datatype", p)
                continue
            log.debug("Mon recv %d: %s", p, self.datatypes[p].name)
            newval = self.datatypes[p].decode(self.mem[p])
            for nk in newval:
                log.debug("Mon recv got %s", "/".join(self.prefix + [nk]))
                if nk not in self.values or self.values[nk] != newval[nk]:
                    self.values[nk] = newval[nk]
                    self.value_timestamps[nk] = now
                    self.update_event(nk, p)

    def get_value(self, k):
        return self.values[k]

    def get_value_str(self, k):
        try:
            return self.get_value(k)
        except:
            return "--"

    def update_event(self, k, p):
        mqtt_logamatic.publish_update(
            self.prefix,
            k,
            self.values[k],
            self.datatypes[p].metadata,
            self.monid,
            self.name,
            self.datatypes[p].fullname
        )


class MonBase(Obase):
    def __init__(self, monid, name, datalen):
        super().__init__(monid, name, datalen)
        self.prefix = ["mon", name]


class MonHeizkreis(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 18)
        self.datatypes[0] = DataHKStat1(
            "Status1", "Betriebswerte 1", {"device_class": "enum"}
        )
        self.datatypes[1] = DataHKStat2(
            "Status2", "Betriebswerte 2", {"device_class": "enum"}
        )
        self.datatypes[2] = DataTempVorl(
            "T_Vs",
            "Vorlaufsolltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[3] = DataTempVorl(
            "T_Vm",
            "Vorlaufisttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[4] = DataTempRaum(
            "T_Rs",
            "Raumsolltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[5] = DataTempRaum(
            "T_Rm",
            "Raumisttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )


class MonKessel(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 42)
        self.datatypes[0] = DataTempVorl(
            "T_s",
            "Kesselvorlauf-Solltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[1] = DataTempVorl(
            "T_m",
            "Kesselvorlauf-Isttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[7] = DataUint8Hex(
            "Kesselstatus", "Kessel Betrieb Bits", {"device_class": "enum"}
        )
        self.datatypes[8] = DataUInt8(
            "Brenner_s", "Brenner Ansteuerung", {"device_class": "enum"}
        )
        self.datatypes[34] = DataUint8Hex(
            "Brennerstatus", "Brenner Status Bits", {"device_class": "enum"}
        )


class MonKesselHaengend(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 60)
        self.datatypes[6] = DataTempVorl(
            "T_s",
            "Kesselvorlauf-Solltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[7] = DataTempVorl(
            "T_m",
            "Kesselvorlauf-Isttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[14] = DataUint8Hex(
            "UBA", "HD-Mode der UBA", {"device_class": "enum"}
        )
        self.datatypes[20] = DataTempRueckl(
            "T_rm",
            "Kesselrücklauf-Isttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )


class MonGeneric(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 24)
        self.datatypes[0] = DataTempAussen(
            "T_Aus",
            "Außentemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[18] = DataTempVorl(
            "T_Vs",
            "Anlagenvorlaufsolltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[19] = DataTempVorl(
            "T_Vm",
            "Anlagenvorlaufisttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[23] = DataTempVorl(
            "T_Vrm",
            "Regelgerätevorlaufisttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )


class MonSolar(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 54)
        self.datatypes[10] = DataTempVorl(
            "T_Bufm",
            "Temperatur Speichermitte",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[11] = DataTempVorl(
            "T_Rlm",
            "Anlagenrücklauftemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )


class MonWaermemenge(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 36)

        overall = DataUIntMultiByte(
            4,
            "W_overall",
            "Wärmemenge gesamt",
            {"device_class": "duration", "unit_of_measurement": "min"},
        )
        self.datatypes[30] = overall.byte(3)
        self.datatypes[31] = overall.byte(2)
        self.datatypes[32] = overall.byte(1)
        self.datatypes[33] = overall.byte(0)

        today = DataUIntMultiByte(2, "W_today", "Wärmemenge heute")
        self.datatypes[6] = today.byte(1)
        self.datatypes[7] = today.byte(0)

        yesterday = DataUIntMultiByte(2, "W_yesterday", "Wärmemenge Vortag")
        self.datatypes[8] = yesterday.byte(1)
        self.datatypes[9] = yesterday.byte(0)


class MonWarmWasser(MonBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 12)
        self.datatypes[0] = DataWWStat1(
            "Status 1", "Betriebswerte 1", {"device_class": "enum"}
        )
        self.datatypes[1] = DataWWStat2(
            "Status 2", "Betriebswerte 2", {"device_class": "enum"}
        )
        self.datatypes[2] = DataTempWW(
            "T_s",
            "Warmwasser Solltemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )
        self.datatypes[3] = DataTempWW(
            "T_m",
            "Warmwasser Isttemperatur",
            {"device_class": "temperature", "unit_of_measurement": "°C"},
        )


class ConfBase(Obase):
    def __init__(self, monid, name, datalen):
        super().__init__(monid, name, datalen)
        self.prefix = ["cnf", self.name]
    def encode(self, name, value):
        dn = None
        for d in self.datatypes:
            if d and d.name == name:
                dn = d
                break
        if not dn:
            raise ValueError("Data object {} contains no {}".format(self.name, name))
        i = self.datatypes.index(dn)

        # Config block offsets are aligned at 7 bytes, however the 7th byte is never received
        # 0x65 means "empty", which means, keep the current value.
        mem = [0x65]*6
        o, mi = divmod(i, 7)
        o *= 7
        mem[mi] = dn.encode(value)
        return o, mem

class DataHKMode(DataTypeBase):
    codes = ["AUS", "EIN", "AUT"]
    def decode(self, byte):
        try:
            v = self.codes[byte]
        except KeyError:
            v = "ERR"
        return {self.name: v}
    def encode(self, value):
        try:
            v = int(value)
        except ValueError:
            v = self.codes.index(value)
        return v


class ConfHeizkreis(ConfBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 62)
        self.datatypes[1] = DataTempAussen(
            "T_Sommer",
            "Sommer-Winter Schwelle",
            {
                "platform": "number",
                "min": 8,
                "max": 18,
                "step": 1,
                "mode": "slider",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        self.datatypes[2] = DataTempRaum(
            "T_Nacht",
            "Solltemperatur Nacht",
            {
                "platform": "number",
                "min": 10,
                "max": 29,
                "step": 0.5,
                "mode": "slider",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        self.datatypes[3] = DataTempRaum(
            "T_Tag",
            "Solltemperatur Tag",
            {
                "platform": "number",
                "min": 11,
                "max": 30,
                "step": 0.5,
                "mode": "slider",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        self.datatypes[4] = DataHKMode(
            "Modus",
            "Betriebsart",
            {"platform": "select", "device_class": "enum", "options": DataHKMode.codes},
        )


class ConfWarmwasser(ConfBase):
    def __init__(self, monid, name):
        super().__init__(monid, name, 41)
        self.datatypes[10] = DataTempWW(
            "T_s",
            "Solltemperatur",
            {
                "platform": "number",
                "min": 10,
                "max": 80,
                "step": 1,
                "mode": "slider",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )
        self.datatypes[14] = DataHKMode(
            "Modus",
            "Betriebsart",
            {"platform": "select", "device_class": "enum", "options": DataHKMode.codes},
        )


class LogamaticType():
    def __init__(self, name, datalen, dataclass=None, shortname=""):
        self.name = name
        self.datalen = datalen
        self.dataclass = dataclass
        self.shortname = shortname

monitor_types = {
# Monitor data
    # name, overall data length, class
    0x80 : LogamaticType("Heizkreis 1", 18, MonHeizkreis),
    0x81 : LogamaticType("Heizkreis 2", 18, MonHeizkreis),
    0x82 : LogamaticType("Heizkreis 3", 18, MonHeizkreis),
    0x83 : LogamaticType("Heizkreis 4", 18, MonHeizkreis),
    0x84 : LogamaticType("Warmwasser", 12, MonWarmWasser),
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
    0x92 : LogamaticType("Kessel 1 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x93 : LogamaticType("Kessel 2 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x94 : LogamaticType("Kessel 3 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x95 : LogamaticType("Kessel 4 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x96 : LogamaticType("Kessel 5 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x97 : LogamaticType("Kessel 6 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x98 : LogamaticType("Kessel 7 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x99 : LogamaticType("Kessel 8 wandhängend", 60, MonKesselHaengend, "Kessel"),
    0x9A : LogamaticType("KNX FM446",60),
    0x9B : LogamaticType("Wärmemenge", 36, MonWaermemenge),
    0x9C : LogamaticType("Störmeldemodul", 6),
    0x9D : LogamaticType("Unterstation", 6),
    0x9E : LogamaticType("Solarfunktion", 54, MonSolar, "Speicher"),
    0x9F : LogamaticType("alternativer Wärmeerzeuger", 42),
}
conf_types = {
# Configuration
    0x07 : LogamaticType("Heizkreis 1", 62, ConfHeizkreis),
    0x08 : LogamaticType("Heizkreis 2", 62, ConfHeizkreis),
    0x09 : LogamaticType("Heizkreis 3", 62), #, ConfHeizkreis),
    0x0A : LogamaticType("Heizkreis 4", 62), #, ConfHeizkreis),
    0x0B : LogamaticType("Außenparameter", 12),
    0x0C : LogamaticType("Warmwasser", 41, ConfWarmwasser),
    0x0D : LogamaticType("Konfiguration (Modulauswahl)", 18),
    0x0E : LogamaticType("Strategie wandhängend(UBA)", 18),
    0x10 : LogamaticType("Kessel bodenstehend", 18),
    0x11 : LogamaticType("Schaltuhr pro Woche Kanal 1", 18),
    0x12 : LogamaticType("Schaltuhr pro Woche Kanal 2", 18),
    0x13 : LogamaticType("Schaltuhr pro Woche Kanal 3", 18),
    0x14 : LogamaticType("Schaltuhr pro Woche Kanal 4", 18),
    0x15 : LogamaticType("Schaltuhr pro Woche Kanal 5", 18),
    0x16 : LogamaticType("Heizkreis 5", 62, ConfHeizkreis),
    0x17 : LogamaticType("Schaltuhr pro Woche Kanal 6", 18),
    0x18 : LogamaticType("Heizkreis 6", 62), #, ConfHeizkreis),
    0x19 : LogamaticType("Schaltuhr pro Woche Kanal 7", 18),
    0x1A : LogamaticType("Heizkreis 7", 62), #, ConfHeizkreis),
    0x1B : LogamaticType("Schaltuhr pro Woche Kanal 8", 18),
    0x1C : LogamaticType("Heizkreis 8", 62), #, ConfHeizkreis),
    0x1D : LogamaticType("Schaltuhr pro Woche Kanal 9", 18),
    0x1F : LogamaticType("Schaltuhr pro Woche Kanal 10", 18),
    0x20 : LogamaticType("Strategie bodenstehend", 12),
    0x24 : LogamaticType("Solar", 12),
    0x26 : LogamaticType("Strategie (FM458)", 12)
}

# reverse map: name -> id
conf_names = { conf_types[k].name: k for k in conf_types }

data_objects = {}

def get_data_object(oid, message_types):
    if not oid in data_objects:
        if oid in message_types:
            if message_types[oid].dataclass:
                name = message_types[oid].shortname if message_types[oid].shortname else message_types[oid].name
                data_objects[oid] = message_types[oid].dataclass(oid,name)
                log.debug("New can data object 0x%x", oid)
            else:
                log.debug("No dataclass implemented for oid 0x%x", oid)
        else:
            pass
            # log.warning("Unknown monitor oid 0x%x", oid)

    if oid in data_objects:
        return data_objects[oid]
    else:
        return None

recv_queue = queue.Queue()
RecvMessage = namedtuple("RecvMessage", ("handler", "msg"))
mon_received = 0
conf_received = 0
conf_requested = False

def can_recv_callback(msg):
    recv_queue.put(RecvMessage(handle_can_recv, msg))
    log.debug("Incoming CAN id %d data %s", msg.pkid, str(msg.data))

def handle_can_recv(msg):
    global mon_received, conf_received, conf_requested

    # Request config, if we are already reading monitor data, but no config.
    # Config is sent fully at startup. Incremental changes are sent on updates.
    if conf_received == 0 and mon_received > 16 and not conf_requested:
        conf_sender.request_settings()
        conf_requested = True

    try:
        if msg.pkid & 0x400:   # monitor data
            mon_received += recv_can_message(msg, monitor_types)
        else:                   # could be conf data
            conf_received += recv_can_message(msg, conf_types)
        recv_can_handshake(msg)
    except Exception as E:
        log.exception(E)
        raise

def recv_can_message(msg, message_types):
    if len(msg.data) != 8:
        log.warning("CAN message with len != 8")
        return
    oid = msg.data[0]
    log.debug("Can id=%d oid=0x%x", msg.pkid, oid)
    o = get_data_object(oid, message_types)
    if o:
        o.recv(msg.data[1:])
        log.debug("Update for mon oid 0x%x done", oid)
        return True
    return False

def enc_can_id(d, s, mon=0):
     m5 = 0b11111
     i = mon << 10
     i |= (d & m5) << 5
     i |= s & m5
     return i

def send_can_msg(d, s, typ, offs, mem, mon=0, rtr=0):
    if len(mem) != 6:
        ValueError("mem must be 6 long")
    cani = enc_can_id(d, s, mon)
    cand = [typ, offs] + mem
    mqtt_can.send_can(cani, cand, rtr)

def mqtt_command_callback(msg):
    recv_queue.put(RecvMessage(handle_cmd, msg))

def handle_cmd(msg):
    try:
        value = msg.payload.decode()
        log.debug("Receive MQTT command %s : %s", msg.topic, value)
        t = msg.topic.split("/")
        oname = t[-2]
        vname = t[-1]
        conf_sender.send_conf(oname, vname, value)
    except Exception:
        log.exception("Handle conf command")

def recv_can_handshake(msg):
    conf_sender.recv_can_handshake(msg)

class ConfSender():
    CLOSED = 0
    OPEN = 1
    WAIT_OPEN = 2

    CAN_ID_SOURCE = 0x11
    CAN_ID_DEST = 1
    def __init__(self):
        self.state = self.CLOSED
        self.queue_pending = queue.Queue()

    def recv_can_handshake(self, msg):
        oid = msg.data[0]
        off = msg.data[1]
        if msg.pkid != enc_can_id(1, 1) or oid != 0xfb or off != 0x04:
            return
        peer = msg.data[2]
        flag = msg.data[3]
        if flag == 0 and peer == self.CAN_ID_SOURCE:
            self.state = self.OPEN
            self.OPEN_since = timestamp()
            log_send.info("Recv CAN handshake OPEN %x %x", peer, flag)
            self.send_pending()

        elif peer == 0xff and flag == 0:
            self.state = self.CLOSED
            log_send.info("Recv CAN handshake CLOSED %x %x", peer, flag)

        else:
            log_send.debug("Recv CAN handshake _other_ %x %x", peer, flag)

    def send_conf(self, oname, vname, value):
        oid = conf_names[oname]
        obj = get_data_object(oid, conf_types)
        off, mem = obj.encode(vname, value)
        log_send.debug("Set config for %x %s/%s to %s", oid, oname, vname, str(value))
        self.queue_pending.put((oid, off, mem))

        # The "channel" closes after about 20 seconds, so reuse it, if in time
        if self.state == self.OPEN and timestamp() - self.OPEN_since < 15:
            log_send.debug("Still OPEN, send now")
            self.send_pending()
        else:
            # wait for open and send
            self.send_handshake_open()

    def send_handshake_open(self):
        log_send.debug("Send handshake OPEN")
        send_can_msg(self.CAN_ID_DEST, self.CAN_ID_SOURCE, 0xfb, 9, [self.CAN_ID_DEST, 1, 0, 0, 0, 0])

    def send_pending(self):
        while True:
            try:
                oid, off, mem = self.queue_pending.get_nowait()
                log_send.info("Sending config for 0x%x at 0x%x %s", oid, off, str(mem))
                send_can_msg(self.CAN_ID_DEST, self.CAN_ID_SOURCE, oid, off, mem)
                self.queue_pending.task_done()
            except queue.Empty:
                break
            except Exception:
                log.exception("Error sending config updates")

    def request_settings(self):
        "This causes the receiver to dump its settings"
        log_send.info("Request all settings")
        send_can_msg(self.CAN_ID_DEST, self.CAN_ID_SOURCE, 0xfb, 1, [0]*6)

valuefile = None
valuestr = ""

conf_sender = ConfSender()

if __name__ == "__main__":
    logging.basicConfig()
    try:
        valuefile = sys.argv[1]
    except: pass
    mqtt_can.start(can_recv_callback)
    mqtt_logamatic.start(mqtt_command_callback)
    try:
        while True:
            m = recv_queue.get()
            m.handler(m.msg)
            recv_queue.task_done()
    except KeyboardInterrupt:
        mqtt_can.stop()
        mqtt_logamatic.stop()
        log.info("Exit")
        sys.exit(0)
