from eco_can_tools import *
import time

def try0():
    s = 0x0b
    a = 1
    send_can_msg(1,s,0xfb, 4, [a, 1, 0, 0, 0, 0])
    send_can_msg(1,s,0x16,0, [0x65,0x65,0x65,0x65,2,0x65])
    send_can_msg(1,s,0xfb, 4, [a, 2, 0, 1, 0, 0])
    send_can_msg(1,s,0xfb, 4, [0xff, 0, 0, 0, 0, 0])

def try1():
    s = 0x19
    a = 1
    r = 0x18
    send_can_msg(r,s,0xfb, 4, [a, 1, 0, 0, 0, 0])
    send_can_msg(r,s,0x16,0, [0x65,0x65,0x65,0x65,2,0x65])
    send_can_msg(r,s,0xfb, 4, [a, 2, 0, 1, 0, 0])
    send_can_msg(r,s,0xfb, 4, [0xff, 0, 0, 0, 0, 0])

def try2():
    s = 0x11
    a = 1
    r = 0x1
    send_can_msg(r,s,0xfb, 9, [a, 1, 0, 0, 0, 0])
    time.sleep(1)
    """
    r:0 m:0 r:01 s:01 t:fb o:04 d:11 00 00 00 00 00
    """
    send_can_msg(r, s, 0x07, 0, [0x65, 0x65, 0x65, 0x65, 0x00, 0x65])
    send_can_msg(r, s, 0x08, 0, [0x65, 0x65, 0x65, 0x65, 0x00, 0x65])
    send_can_msg(r, s, 0x16, 0, [0x65, 0x65, 0x65, 0x65, 0x00, 0x65])
    """
    r:0 m:0 r:01 s:01 t:fb o:04 d:01 01 00 00 00 00
    r:0 m:0 r:01 s:01 t:07 o:00 d:3d 0f 1c 2a 02 14
    r:0 m:0 r:01 s:01 t:fb o:04 d:01 02 00 01 00 00
    r:0 m:0 r:01 s:01 t:fb o:04 d:ff 00 00 00 00 00
    """
    # time.sleep(1)
    # send_can_msg(r,s,0xfb, 4, [a, 2, 0, 1, 0, 0])
"""
r:0 m:0 r:01 s:01 t:fb o:04 d:01 01 00 00 00 00
r:0 m:0 r:01 s:01 t:16 o:00 d:3d 0e 25 2d 00 14
r:0 m:0 r:01 s:01 t:fb o:04 d:01 02 00 01 00 00
r:0 m:0 r:01 s:01 t:fb o:04 d:ff 00 00 00 00 00
"""