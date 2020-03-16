import time
from eco_can_tools import *

client = paho.mqtt.client.Client()
def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected ", rc)
    client.subscribe("/heizung/burner/can/raw/recv/")
def on_message(client, userdata, msg): 
    try:
        f = play(msg.payload.decode())
        if f:
            print(f)
    except Exception as e:
        traceback.print_exc()
def play(l):
    global playing
    rtr, mon, d, s, typ, offs, mem = dec_can_msg(l)
    f = str_msg(l, filt=filt_something_new)
    if f:
        print(f)
        playing = False
        print("Stop playing")
    #filt(rtr=rtr, mon=mon, d=d, s=s, typ=typ, offs=offs, mem=mem)
    thisid = 0x11 
    #answer poll
    if rtr == 0 and mon == 0 and d == 1 and s == 1 and typ == 0xc0:
        send_can_msg(1, thisid, 0xc0, 0, [0]*6)
        if playing:
            try:
                msgs = send_tryout()
                sent.append(msgs)
            except StopIteration:
                playing = False
                print("Done playing")
                

def send_tryout():
    msgs = next(tryer)
    for d, s, t, o, m in msgs:
        send_can_msg(d, s, t, o, m)
        time.sleep(0.1)
    return msgs

def typeTryer():
    s = 0x11
    a = 1
    r = 0x1
    o = 4
    t = 0xfb
    for t in range(0xfb, 0xff):
        print("{:x}".format(t))
        msgs = ((r,s,t, o, [a, 1, 0, 0, 0, 0]),
            (r,s,0x16,0, [0x3d,0x0e,0x25,0x2d,0,0x14]), 
            (r,s,t, o, [a, 2, 0, 1, 0, 0]),
            (r,s,t, o, [0xff, 0, 0, 0, 0, 0]))
        yield msgs
    
def offTryer():
    s = 0x11
    a = 1
    r = 0x1
    t = 0xfb
    for o in range(2, 33):
        print("{:x}".format(o))
        msgs = ((r,s,t, o, [a, 1, 0, 0, 0, 0]),
            (r,s,0x16,0, [0x3d,0x0e,0x25,0x2d,0,0x14]), 
            (r,s,t, o, [a, 2, 0, 1, 0, 0]),
            #(r,s,t, o, [0xff, 0, 0, 0, 0, 0])
            )
        yield msgs


tryer = offTryer()
sent = []
playing = True

client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = lambda client, userdata, rc: print("Disconnected ", rc)

def start():
    rc = client.connect("pi3.lan")
    try:
        client.loop_forever()
    except KeyboardInterrupt as K:
        client.disconnect()
    except:
        client.disconnect()
        raise
