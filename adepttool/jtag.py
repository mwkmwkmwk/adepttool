class UnknownDeviceError(Exception):
    pass


class Chain:
    def __init__(self, port):
        self.port = port

    def init(self):
        self.port.enable()
        self.port.put_tms_tdi_bits(False, 9, bytes([0xaa, 0x22, 0x00]))
        self.devices = []
        while True:
            res = self.port.get_tdo_bits(False, False, 32)
            res = int.from_bytes(res, 'little')
            if res == 0:
                break
            for idc, idm, cls, nam in DEVICES:
                if (res & idm) == idc:
                    self.devices.append(cls(self, res, nam))
                    break
            else:
                raise UnknownDeviceError('unknown IDCODE {res:08x}'.format(res=res))
        self.port.put_tms_tdi_bits(False, 2, bytes([0xa]))

    def shift_num(self, num, length, last):
        if num >= (1 << length):
            raise ValueError
        if not length:
            raise ValueError
        if not last:
            tdi = num.to_bytes((length + 7) // 8, 'little')
            tdo = self.port.put_tdi_bits(True, False, length, tdi)
            return int.from_bytes(tdo, 'little')
        else:
            if length == 1:
                res = 0
            else:
                res = self.shift_num(num & ~(1 << (length - 1)), length - 1, False)
            hi = self.port.put_tdi_bits(True, True, 1, bytes([num >> (length - 1) & 1]))[0]
            res |= hi << (length - 1)
            return res

    def shift_bytes(self, data, length, last):
        if (length + 7) // 8 != len(data):
            raise ValueError
        if not length:
            raise ValueError
        if not last:
            return self.port.put_tdi_bits(True, False, length, data)
        else:
            if length % 8 == 1:
                if length == 1:
                    res = b''
                else:
                    res = self.shift_bytes(data[:-1], length - 1, False)
                hi = self.port.put_tdi_bits(True, True, 1, data[-1:])
                return res + hi
            else:
                res = self.shift_bytes(data, length - 1, False)
                finbit = data[-1] >> ((length - 1) % 8) & 1
                hi = self.port.put_tdi_bits(True, True, 1, bytes([finbit]))[0]
                finbyte = res[-1] | hi << ((length - 1) % 8)
                return res[:-1] + bytes([finbyte])

    def shift_ir(self, irs):
        if len(irs) != len(self.devices):
            raise ValueError
        self.port.put_tms_tdi_bits(False, 4, bytes([0xa]))
        res = []
        for dev, ir in zip(self.devices, irs):
            res.append(self.shift_num(ir, dev.IR_LEN, dev is self.devices[-1]))
        self.port.put_tms_tdi_bits(False, 1, bytes([0x2]))
        return res

    def prep_cmd(self, cdev, cmd):
        irs = [
            cmd if dev is cdev else (1 << dev.IR_LEN) - 1
            for dev in self.devices
        ]
        self.shift_ir(irs)

    def shift_dr_one_num(self, cdev, num, length):
        self.port.put_tms_tdi_bits(False, 3, bytes([0x2]))
        idx = self.devices.index(cdev)
        if idx:
            self.shift_num(0, idx, False)
        if idx != len(self.devices) - 1:
            res = self.shift_num(num, length, False)
            self.shift_num(0, len(self.devices) - 1 - idx, True)
        else:
            res = self.shift_num(num, length, True)
        self.port.put_tms_tdi_bits(False, 1, bytes([0x2]))
        return res

    def shift_dr_one_bytes(self, cdev, data, length):
        self.port.put_tms_tdi_bits(False, 3, bytes([0x2]))
        idx = self.devices.index(cdev)
        if idx:
            self.shift_num(0, idx, False)
        if idx != len(self.devices) - 1:
            res = self.shift_bytes(data, length, False)
            self.shift_num(0, len(self.devices) - 1 - idx, True)
        else:
            res = self.shift_bytes(data, length, True)
        self.port.put_tms_tdi_bits(False, 1, bytes([0x2]))
        return res

    def clock_rti(self, num):
        self.port.clock_tck(False, False, num+1)

    def close(self):
        self.port.disable()


class JtagDev:
    def __init__(self, chain, idcode, name):
        self.chain = chain
        self.idcode = idcode
        self.name = name

    def prep_cmd(self, cmd):
        self.chain.prep_cmd(self, cmd)

    def shift_dr_num(self, num, length):
        self.chain.shift_dr_one_num(self, num, length)

    def shift_dr_bytes(self, data, length):
        self.chain.shift_dr_one_bytes(self, data, length)

    def get_status(self):
        irs = [
            (1 << dev.IR_LEN) - 1
            for dev in self.chain.devices
        ]
        res = self.chain.shift_ir(irs)
        for i, dev in enumerate(self.chain.devices):
            if self.chain.devices[i] is self:
                return res[i]


class Spartan3(JtagDev):
    IR_LEN = 6

    def jprogram(self):
        self.prep_cmd(0x0b)

    def cfg_in(self, data):
        self.prep_cmd(0x05)
        self.shift_dr_bytes(data, len(data) * 8)

    def jstart(self):
        self.prep_cmd(0x0c)
        self.chain.clock_rti(12)

    def wait_for_done(self):
        while not (self.get_status() & 0x20):
            pass
        self.chain.clock_rti(12)


class PlatformFlashSerial(JtagDev):
    IR_LEN = 8


DEVICES = [
    (0x01c10093, 0x0fffffff, Spartan3, 'xc3s100e'),
    (0x05044093, 0x0fffffff, PlatformFlashSerial, 'xcf01s'),
    (0x05045093, 0x0fffffff, PlatformFlashSerial, 'xcf02s'),
    (0x05046093, 0x0fffffff, PlatformFlashSerial, 'xcf04s'),
]
