import paho.mqtt.client
import traceback
"""
Helpers for Buderus ECO CAN
"""

bitidx = lambda b: "{0:03x} {1:b} {2:x} {3:x}".format(b, b & 0x400 == 0x400, (b >> 5) & 0b11111, b & 0b11111)

def dec_can_id(i):
    m5 = 0b11111 
    mon = int(i & 0x400 > 0)
    d = (i >> 5) & m5
    s = i & m5
    return d, s, mon

def enc_can_id(d, s, mon=0): 
     m5 = 0b11111 
     i = mon << 10 
     i |= (d & m5) << 5 
     i |= s & m5 
     return i 

def stridx(i):
    d, s, mon = dec_can_id(i)
    return "{0:03x} {1:x} {2:02x} {3:02x}".format(i, mon, d, s)

def stridb(i):
    d, s, mon = dec_can_id(i)
    return "{0:03x} {1:b} {2:05b} {3:05b}".format(i, mon, d, s)

def str_msg(l, filt=None):
    m = l.replace("/heizung/burner/can/raw/recv/", "")
    ms = m.split(";")
    rtr = int(ms[0])
    i = int(ms[1], base=16)
    data = bytes.fromhex(ms[2])
    d, s, mon = dec_can_id(i)
    typ = data[0]
    offs = data[1]
    mem = data[2:]
    if filt and not filt(rtr=rtr, mon=mon, d=d, s=s, typ=typ, offs=offs, mem=mem):
        return None
    else:
        return format_msg(rtr, mon, d, s, typ, offs, mem)

def format_msg(rtr, mon, d, s, typ, offs, mem):
    longf = "rtr:{0:x} mon:{1:x} dst:{2:02x} src:{3:02x} typ:{4:02x} off:{5:02x} dat:{6:s}"
    shortf = "r:{0:x} m:{1:x} r:{2:02x} s:{3:02x} t:{4:02x} o:{5:02x} d:{6:s}"

    return shortf.format(rtr, mon, d, s, typ, offs, " ".join(("{0:02x}".format(b) for b in mem))
    )
def dec_file(fn, fo=None):
    if not fo: 
        fo =  fn+".dec"
    with open(fn) as fr: 
        with open(fo, "w") as fw: 
            fw.writelines((str_msg(l)+"\n" for l in fr)) 

# print(splitdumpline("/heizung/burner/can/raw/recv/ 0;38;c3 06 01 ff 19 5a 01 8e"))

def stdio_can_dec(filt=None):
    import sys
    while True:
        l = sys.stdin.readline()
        if not l: break
        if l.strip():
            try:
                f = str_msg(l, filt)
            except Exception as E:
                f = str(E)
            if f: sys.stdout.write(f + "\n")

def sniff_can(filt=None):
    client = paho.mqtt.client.Client()
    def on_connect(client, userdata, flags, rc, properties=None):
        print("Connected ", rc)
        client.subscribe("/heizung/burner/can/raw/recv/")
    def on_message(client, userdata, msg): 
        try:
            f = str_msg(msg.payload.decode(), filt)
            if f:
                print(f)
        except Exception as e:
            traceback.print_exc()

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = lambda client, userdata, rc: print("Disconnected ", rc)
    rc = client.connect("pi3.lan")
    try:
        client.loop_forever()
    except KeyboardInterrupt as K:
        client.disconnect()
    except:
        client.disconnect()
        raise

filt_no_mon = lambda **kwargs: kwargs["mon"] == False
filt_bcast = lambda **kwargs: kwargs["d"] == 0


def enc_can_msg(d, s, typ, offs, mem, mon=0, rtr=0):
    i = enc_can_id(d, s, mon)
    cand = [typ, offs, *mem]
    dstr = " ".join(["{0:x}".format(d) for d in cand])
    mqm = "{rtr:x};{i:x};{d:s}".format(rtr=rtr, i=i, d=dstr)
    return mqm 

def send_can_msg(d, s, typ, offs, mem, mon=0, rtr=0):
    if len(mem) != 6:
        ValueError("mem must be 6 long")
    mqt = "/heizung/burner/can/raw/send"
    mqm = enc_can_msg(d, s, typ, offs, mem, mon, rtr)
    if not client.is_connected():
        connect()

    return client.publish(mqt, mqm).wait_for_publish()

def connect():
    rc = client.connect("pi3.lan")
    client.loop_start() 
def disconnect():
    client.disconnect()
    client.loop_stop()

client = paho.mqtt.client.Client()
if __name__ == "__main__":
    pass
    # mqtt_can_dec(filt_no_mon)
    # stdio_can_dec()