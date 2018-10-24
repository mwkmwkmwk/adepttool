#!/usr/bin/env python3

import argparse
import usb1
from adepttool.device import get_devices
from adepttool.jtag import Chain, Spartan3
import sys

parser = argparse.ArgumentParser(description='Program the FPGA on Basys 2.')
parser.add_argument('--device', type=int, help='Device index', default=0)
parser.add_argument('bitfile', help='The bitstream file')

args = parser.parse_args()

with open(args.bitfile, 'rb') as f:
    data = f.read()

xlat = bytes(
    sum(1 << bit for bit in range(8) if x & 1 << (7 - bit))
    for x in range(0x100)
)
data = bytes(xlat[x] for x in data)

with usb1.USBContext() as ctx:
    devs = get_devices(ctx)
    if args.device >= len(devs):
        if not devs:
            print('No devices found.')
        else:
            print('Invalid device index (max is {})'.format(len(devs)-1))
        sys.exit(1)
    dev = devs[args.device]
    dev.start()
    port = dev.djtg_ports[0]
    chain = Chain(port)
    chain.init()
    fpga = chain.devices[1]
    if not isinstance(fpga, Spartan3):
        print('Not a Spartan 3 device.')

    def print_status():
        status = fpga.get_status()
        flags = []
        if status & 4:
            flags.append('ISC_DONE')
        if status & 8:
            flags.append('ISC_ENABLED')
        if status & 0x10:
            flags.append('INIT_B')
        if status & 0x20:
            flags.append('DONE')
        flags = ', '.join(flags)
        if not flags:
            flags = '-'
        print('STATUS: {}'.format(flags))


    print('JPROGRAM')
    fpga.jprogram()
    print_status()
    print('CFG_IN')
    fpga.cfg_in(data)
    print_status()
    print('JSTART')
    fpga.jstart()
    print_status()
    print('Wait for DONE')
    fpga.wait_for_done()
    print_status()
    chain.close()
