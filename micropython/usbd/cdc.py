# MicroPython USB CDC module
# MIT license; Copyright (c) 2022 Martin Fischer
from .device import (
    USBInterface,
    get_usbdevice
)
from .utils import (
    endpoint_descriptor,
    EP_IN_FLAG
)
from .midi import RingBuf
from micropython import const
import ustruct
import time

_DEV_CLASS_MISC = const(0xef)
_CS_DESC_TYPE = const(0x24)   # CS Interface type communication descriptor
_ITF_ASSOCIATION_DESC_TYPE = const(0xb)  # Interface Association descriptor

# CDC control interface definitions
_CDC_ITF_CONTROL_CLASS = const(2)
_CDC_ITF_CONTROL_SUBCLASS = const(2)  # Abstract Control Mode
_CDC_ITF_CONTROL_PROT = const(0)   # no protocol

# CDC data interface definitions
_CDC_ITF_DATA_CLASS = const(0xa)
_CDC_ITF_DATA_SUBCLASS = const(0)
_CDC_ITF_DATA_PROT = const(0)   # no protocol


def setup_CDC_device():
    # CDC is a composite device, consisting of multiple interfaces
    # (CDC control and CDC data)
    # therefore we have to make sure that the association descriptor
    # is set and that it associates both interfaces to the logical cdc class
    usb_device = get_usbdevice()
    usb_device.device_class = _DEV_CLASS_MISC
    usb_device.device_subclass = 2
    usb_device.device_protocol = 1   # Itf association descriptor


class CDCControlInterface(USBInterface):
    # Implements the CDC Control Interface

    def __init__(self, interface_str):
        super().__init__(_CDC_ITF_CONTROL_CLASS, _CDC_ITF_CONTROL_SUBCLASS,
                         _CDC_ITF_CONTROL_PROT)
        self.ep_in = None

    def get_itf_descriptor(self, num_eps, itf_idx, str_idx):
        # CDC needs a Interface Association Descriptor (IAD)
        # first interface is zero, two interfaces in total
        desc = ustruct.pack("<BBBBBBBB", 8, _ITF_ASSOCIATION_DESC_TYPE, itf_idx, 2,
                            _CDC_ITF_CONTROL_CLASS, _CDC_ITF_CONTROL_SUBCLASS,
                            _CDC_ITF_CONTROL_PROT, 4)  # "IAD"

        itf, strs = super().get_itf_descriptor(num_eps, itf_idx, str_idx)
        desc += itf
        # Append the CDC class-specific interface descriptor
        # see also USB spec document CDC120-track, p20
        desc += ustruct.pack("<BBBH", 5, _CS_DESC_TYPE, 0, 0x0120)  # "Header"
        desc += ustruct.pack("<BBBBB", 5, _CS_DESC_TYPE, 1, 0, 1)   # "Call Management"
        desc += ustruct.pack("<BBBB", 4, _CS_DESC_TYPE, 2, 2)  # "Abstract Control"
        desc += ustruct.pack("<BBBBB", 5, _CS_DESC_TYPE, 6, itf_idx, itf_idx+1)  # "Union"
        return desc, strs

    def get_endpoint_descriptors(self, ep_addr, str_idx):
        self.ep_in = (ep_addr) | EP_IN_FLAG
        desc = endpoint_descriptor(self.ep_in, "interrupt", 8, 16)
        return (desc, [], (self.ep_in,))


class CDCDataInterface(USBInterface):
    # Implements the CDC Data Interface

    def __init__(self, interface_str, timeout=1):
        super().__init__(_CDC_ITF_DATA_CLASS, _CDC_ITF_DATA_SUBCLASS,
                         _CDC_ITF_DATA_PROT)
        self.rx_buf = bytearray(256)
        # self.mv_buf = memoryview(self.rx_buf)
        # self.rx_done = False
        # self.rx_nbytes = 0
        # self.timeout = timeout
        self.rb = RingBuf(256)
        self.ep_in = None
        self.ep_out = None
        self.read_cd_started = False

    def get_endpoint_descriptors(self, ep_addr, str_idx):
        # XXX OUT = 0x00 but is defined as 0x80?
        self.ep_in = (ep_addr) | EP_IN_FLAG
        self.ep_out = (ep_addr) & ~EP_IN_FLAG
        # one IN / OUT Endpoint
        e_out = endpoint_descriptor(self.ep_out, "bulk", 64, 0)
        e_in = endpoint_descriptor(self.ep_in, "bulk", 64, 0)
        return (e_out + e_in, [], (self.ep_out, self.ep_in))

    def write(self, data):
        self.submit_xfer(self.ep_in, data)

    # read nbytes or until stop char is found
    def read(self, nbytes=1, stop=None):

        if self.read_cd_started == False:
            if self.ep_out == None:
                # ep_out hasn't been set yet, so we can't start recv'ing
                return b'' # TODO: better output then just an empty message?
            self._start_rx_cb()
            self.read_cd_started = True
        res = bytearray()
        for i in range(nbytes):
            nxt = self.rb.get()
            if nxt == None:
                break
            res.append(nxt)
            if nxt == ord(stop):
                break
        return res

    def _start_rx_cb(self):
        self.submit_xfer(self.ep_out, self.rx_buf, self._cb_rx)

    def _cb_rx(self, ep, res, num_bytes):
        for i in range(0, num_bytes):
            self.rb.put(self.rx_buf[i])
        self.submit_xfer(self.ep_out, self.rx_buf, self._cb_rx)
