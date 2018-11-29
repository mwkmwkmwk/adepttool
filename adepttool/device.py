import usb1

CTRL_GET_PRODUCT_NAME = 0xe1
CTRL_GET_USER_NAME = 0xe2
CTRL_GET_SERIAL_NUMBER = 0xe4
CTRL_GET_FW_VERSION = 0xe6
CTRL_GET_CAPS = 0xe7
CTRL_GET_PRODUCT_ID = 0xe9

APP_SYS = 0
APP_DMGT = 1
APP_DJTG = 2
APP_DEPP = 4

CAPS_DJTG = 0x00000001
CAPS_DEPP = 0x00000004

CMD_SYS_RESET = 3

CMD_DMGT_GET_CAPS = 2
CMD_DMGT_CONFIG_RESET = 6
CMD_DMGT_QUERY_DONE = 8

DMGT_CAPS_POWER_ON_OFF = 0x00000001
DMGT_CAPS_CONFIG_RESET = 0x00000002
DMGT_CAPS_USER_RESET = 0x00000004
DMGT_CAPS_QUERY_DONE = 0x00000008
DMGT_CAPS_QUERY_POWER = 0x00000020
DMGT_CAPS_MONITOR_POWER = 0x00000040

CMD_APP_ENABLE = 0
CMD_APP_DISABLE = 1
CMD_APP_GET_PORTS = 2

CMD_DJTG_SET_SPEED = 3
CMD_DJTG_GET_SPEED = 4
CMD_DJTG_SET_TMS_TDI_TCK = 5
CMD_DJTG_GET_TMS_TDI_TDO_TCK = 6
CMD_DJTG_CLOCK_TCK = 7
CMD_DJTG_PUT_TDI_BITS = 8
CMD_DJTG_GET_TDO_BITS = 9
CMD_DJTG_PUT_TMS_TDI_BITS = 10
CMD_DJTG_PUT_TMS_BITS = 11

DJTG_CAPS_SET_SPEED = 0x00000001

CMD_DEPP_SET_TIMEOUT = 3
CMD_DEPP_PUT_REG = 4
CMD_DEPP_GET_REG = 5
CMD_DEPP_PUT_REG_SET = 6
CMD_DEPP_GET_REG_SET = 7


class DeviceInterfaceError(Exception):
    """The device did not behave according to our expectations.  Please report this."""


class CommandError(Exception):
    pass

class PortInUseError(CommandError):
    pass

class PortDisabledError(CommandError):
    pass

class EppAddrTimeoutError(CommandError):
    pass

class EppDataTimeoutError(CommandError):
    pass

class UnknownAppError(CommandError):
    pass

class UnknownCmdError(CommandError):
    pass


class Device:
    def __init__(self, ctx, dev):
        self.ctx = ctx
        self.dev = dev.open()
        self.product_name = self.get_product_name()
        self.user_name = self.get_user_name()
        self.serial_number = self.get_serial_number()
        self.fw_version = self.get_fw_version()
        self.caps = self.get_caps()
        self.product_id = self.get_product_id()
        self.djtg_ports = []

    def close(self):
        self.dev.close()

    def start(self):
        self.sys_reset(0)
        self.dmgt = Dmgt(self)
        self.djtg_ports = self.make_apps(APP_DJTG, Djtg, CAPS_DJTG)
        self.depp_ports = self.make_apps(APP_DEPP, Depp, CAPS_DEPP)

    def get_product_name(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_PRODUCT_NAME, 0, 0, 28))
        if len(res) != 28:
            raise DeviceInterfaceError
        return res

    def get_user_name(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_USER_NAME, 0, 0, 16))
        if len(res) != 16:
            raise DeviceInterfaceError
        return res

    def get_serial_number(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_SERIAL_NUMBER, 0, 0, 12))
        if len(res) != 12:
            raise DeviceInterfaceError
        return res

    def get_fw_version(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_FW_VERSION, 0, 0, 2))
        if len(res) != 2:
            raise DeviceInterfaceError
        return int.from_bytes(res, 'little')

    def get_caps(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_CAPS, 0, 0, 8))
        if len(res) != 8:
            raise DeviceInterfaceError
        return int.from_bytes(res, 'little')

    def get_product_id(self):
        res = bytes(self.dev.controlRead(0xc0, CTRL_GET_PRODUCT_ID, 0, 0, 4))
        if len(res) != 4:
            raise DeviceInterfaceError
        return int.from_bytes(res, 'little')

    def sys_reset(self, data):
        res = self.cmd(APP_SYS, CMD_SYS_RESET, 0, data.to_bytes(4, 'little'), 4)
        return int.from_bytes(res, 'little')

    def get_app_ports(self, app):
        res = self.cmd(app, CMD_APP_GET_PORTS, 0, bytes([1]), 1)
        num = res[0]
        res = self.cmd(app, CMD_APP_GET_PORTS, 0, bytes([num * 4 + 1]), num * 4 + 1)
        if res[0] != num:
            raise DeviceInterfaceError
        return [
            int.from_bytes(res[1+i*4:5+i*4], 'little')
            for i in range(num)
        ]

    def make_apps(self, appid, appcls, caps):
        if not (self.caps & caps):
            return []
        return [
            appcls(self, appid, port, caps)
            for port, caps in enumerate(self.get_app_ports(appid))
        ]

    def cmd(self, app, cmd, port, payload=b'', reply_len=0, get_stats=False):
        data = bytes([len(payload) + 3, app, cmd, port]) + payload
        self.dev.bulkWrite(0x01, data)
        while True:
            reply = bytes(self.dev.bulkRead(0x82, reply_len + 10))
            if reply:
                break
        if len(reply) < 2:
            raise DeviceInterfaceError(reply)
        if reply[0] != len(reply) - 1:
            raise DeviceInterfaceError
        status = reply[1] & 0x3f
        if status:
            if status == 3 and len(reply) == 2:
                raise PortInUseError
            if status == 4 and len(reply) == 2:
                raise PortDisabledError
            if status == 5 and len(reply) == 2:
                raise EppAddrTimeoutError
            if status == 6 and len(reply) == 6:
                raise EppDataTimeoutError(int.from_bytes(reply[2:6], 'little'))
            if status == 49 and len(reply) == 2:
                raise UnknownAppError
            if status == 50 and len(reply) == 2:
                raise UnknownCmdError
            raise CommandError(status, reply[2:])
        if status & 0xc0 and not get_stats:
            raise DeviceInterfaceError
        rest = reply[2:]
        if get_stats:
            if reply[1] & 0x80:
                if len(rest) < 4:
                    raise DeviceInterfaceError
                sent = int.from_bytes(rest[:4], 'little')
                rest = rest[4:]
            else:
                sent = None
            if reply[1] & 0x40:
                if len(rest) < 4:
                    raise DeviceInterfaceError
                recvd = int.from_bytes(rest[:4], 'little')
                rest = rest[4:]
            else:
                recvd = None
            if reply_len is not None:
                if len(rest) != reply_len:
                    raise DeviceInterfaceError
            return rest, sent, recvd
        else:
            if reply_len is not None:
                if len(rest) != reply_len:
                    raise DeviceInterfaceError
            return rest

    def cmd_long(self, app, cmd, port, payload, data_send, data_recv_len):
        self.cmd(app, cmd, port, payload, 0)
        bad = False
        def finish_send(xfer):
            nonlocal send_done, bad
            if xfer.getStatus() != usb1.TRANSFER_COMPLETED:
                bad = xfer
            send_done = True
            if len(data_send) != xfer.getActualLength():
                bad = xfer
        def finish_recv(xfer):
            nonlocal recv_done, data_recv, bad
            if xfer.getStatus() != usb1.TRANSFER_COMPLETED:
                bad = xfer
            recv_done = True
            if data_recv_len != xfer.getActualLength():
                bad = xfer
            data_recv = xfer.getBuffer()[:]
        if data_send:
            xfer_send = self.dev.getTransfer()
            xfer_send.setBulk(0x03, data_send, callback=finish_send)
            xfer_send.submit()
            send_done = False
        else:
            send_done = True
        if data_recv_len:
            xfer_recv = self.dev.getTransfer()
            xfer_recv.setBulk(0x84, data_recv_len, callback=finish_recv)
            xfer_recv.submit()
            recv_done = False
        else:
            recv_done = True
            data_recv = b''
        while (not recv_done or not send_done) and not bad:
            self.ctx.handleEvents()
        reply, sent, recvd = self.cmd(app, cmd | 0x80, port, b'', 0, True)
        if bad:
            raise DeviceInterfaceError(bad)
        return reply, sent, recvd, data_recv


def get_devices(ctx):
    return [
        Device(ctx, udev)
        for udev in ctx.getDeviceList()
        if udev.getVendorID() == 0x1443 and udev.getProductID() == 0x0007
    ]


class Dmgt:
    def __init__(self, dev):
        self.dev = dev
        self.caps = self.get_caps()

    def get_caps(self):
        res = self.dev.cmd(APP_DMGT, CMD_DMGT_GET_CAPS, 0, b'', 4)
        return int.from_bytes(res, 'little')

    def config_reset(self, state):
        res = self.dev.cmd(APP_DMGT, CMD_DMGT_CONFIG_RESET, 0, bytes([state]))

    def query_done(self):
        res = self.dev.cmd(APP_DMGT, CMD_DMGT_QUERY_DONE, 0, b'', 1)
        return res[0]


class App:
    def __init__(self, dev, appid, idx, caps):
        self.dev = dev
        self.appid = appid
        self.idx = idx
        self.caps = caps

    def cmd(self, cmd, payload=b'', reply_len=0):
        return self.dev.cmd(self.appid, cmd, self.idx, payload, reply_len)

    def cmd_long(self, cmd, payload, data_send, data_recv_len):
        return self.dev.cmd_long(self.appid, cmd, self.idx, payload, data_send, data_recv_len)

    def enable(self):
        return self.cmd(CMD_APP_ENABLE)

    def disable(self):
        return self.cmd(CMD_APP_DISABLE)


class Djtg(App):
    def set_speed(self, speed):
        res = self.cmd(CMD_DJTG_SET_SPEED, speed.to_bytes(4, 'little'), 4)
        return int.from_bytes(res, 'little')

    def get_speed(self):
        res = self.cmd(CMD_DJTG_GET_SPEED, b'', 4)
        return int.from_bytes(res, 'little')

    def set_tms_tdi_tck(self, tms, tdi, tck):
        self.cmd(CMD_DJTG_SET_TMS_TDI_TCK, bytes([tms, tdi, tck]))

    def get_tms_tdi_tdo_tck(self):
        return self.cmd(CMD_DJTG_GET_TMS_TDI_TDO_TCK, b'', 4)

    def clock_tck(self, tms, tdi, bits):
        req = bytes([tms, tdi]) + bits.to_bytes(4, 'little')
        _, sent, recvd, res = self.cmd_long(CMD_DJTG_CLOCK_TCK, req, b'', 0)
        if recvd is not None or sent is not None:
            raise DeviceInterfaceError

    def put_tdi_bits(self, oe, tms, bits, data):
        req = bytes([oe, tms]) + bits.to_bytes(4, 'little')
        nb = (bits + 7) // 8
        if nb != len(data):
            raise ValueError
        _, sent, recvd, res = self.cmd_long(CMD_DJTG_PUT_TDI_BITS, req, data, nb if oe else 0)
        if sent != bits:
            raise DeviceInterfaceError
        if oe:
            if recvd != bits:
                raise DeviceInterfaceError
            return res
        else:
            if recvd is not None:
                raise DeviceInterfaceError

    def get_tdo_bits(self, tms, tdi, bits):
        req = bytes([tms, tdi]) + bits.to_bytes(4, 'little')
        nb = (bits + 7) // 8
        _, sent, recvd, res = self.cmd_long(CMD_DJTG_GET_TDO_BITS, req, b'', nb)
        if recvd != bits or sent is not None:
            raise DeviceInterfaceError
        return res

    def put_tms_tdi_bits(self, oe, bits, data):
        req = bytes([oe]) + bits.to_bytes(4, 'little')
        nb2 = (bits + 3) // 4
        nb = (bits + 7) // 8
        if nb2 != len(data):
            raise ValueError
        _, sent, recvd, res = self.cmd_long(CMD_DJTG_PUT_TMS_TDI_BITS, req, data, nb if oe else 0)
        if sent != bits:
            raise DeviceInterfaceError
        if oe:
            if recvd != bits:
                raise DeviceInterfaceError
            return res
        else:
            if recvd is not None:
                raise DeviceInterfaceError

    def put_tms_bits(self, oe, tdi, bits, data):
        req = bytes([oe, tdi]) + bits.to_bytes(4, 'little')
        nb = (bits + 7) // 8
        if nb != len(data):
            raise ValueError
        _, sent, recvd, res = self.cmd_long(CMD_DJTG_PUT_TMS_BITS, req, data, nb if oe else 0)
        if sent != bits:
            raise DeviceInterfaceError
        if oe:
            if recvd != bits:
                raise DeviceInterfaceError
            return res
        else:
            if recvd is not None:
                raise DeviceInterfaceError


class Depp(App):
    def set_timeout(self, timeout):
        res = self.cmd(CMD_DEPP_SET_TIMEOUT, timeout.to_bytes(4, 'little'), 4)
        return int.from_bytes(res, 'little')

    def put_reg(self, addr, data):
        req = bytes([addr]) + len(data).to_bytes(4, 'little')
        _, sent, recvd, res = self.cmd_long(CMD_DEPP_PUT_REG, req, data, 0)

    def get_reg(self, addr, num):
        req = bytes([addr]) + num.to_bytes(4, 'little')
        _, sent, recvd, res = self.cmd_long(CMD_DEPP_GET_REG, req, b'', num)
        return res

    def get_regs(self, addrs):
        req = len(addrs).to_bytes(4, 'little')
        _, sent, recvd, res = self.cmd_long(CMD_DEPP_GET_REG_SET, req, addrs, len(addrs))
        return res

    def put_regs(self, addrs, data):
        if len(addrs) != len(data):
            raise ValueError('mismatched address and data lengths')
        req = len(addrs).to_bytes(4, 'little')
        payload = b''.join(bytes([a, d]) for a, d in zip(addrs, data))
        _, sent, recvd, res = self.cmd_long(CMD_DEPP_PUT_REG_SET, req, payload, 0)
