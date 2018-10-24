#!/usr/bin/env python3

import usb1
from adepttool.device import get_devices
from adepttool.jtag import Chain

with usb1.USBContext() as ctx:
    devs = get_devices(ctx)
    for i, dev in enumerate(devs):
        print('DEVICE:')
        print('\tPN {dev.product_name}'.format(dev=dev))
        print('\tUN {dev.user_name}'.format(dev=dev))
        print('\tSN {dev.serial_number}'.format(dev=dev))
        print('\tFW {dev.fw_version:04x}'.format(dev=dev))
        print('\tCAPS {dev.caps:016x}'.format(dev=dev))
        print('\tPI {dev.product_id:08x}'.format(dev=dev))
        dev.start()
        print('\tDMGT CAPS: {dev.dmgt.caps:08x}'.format(dev=dev))
        for port in dev.djtg_ports:
            port.enable()
            print('\tDJTG PORT {port.idx}: {port.caps:08x} speed {speed}'.format(port=port, speed=port.get_speed()))
            port.disable()
            chain = Chain(port)
            chain.init()
            for jdev in chain.devices:
                print('\t\tJTAG IDCODE {jdev.idcode:08x} [{jdev.name}]'.format(jdev=jdev))
            chain.close()
        for port in dev.depp_ports:
            port.enable()
            print('\tDEPP PORT {port.idx}: {port.caps:08x}'.format(port=port))
            port.disable()
    if not devs:
        print('No devices found.')
