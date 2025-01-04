# crypto-bdev

This library provides a crypto wrapper for any block device
that fullfills the vfs.abstractBlockDev API, e.g. SPI Flash FS
or internal FS.

The design is compatible with Linux' LUKE for the following ciphers
- AES CTR with plain IV
- AES ESSIV 

## Background

External SPI flash are common and often required for many MCU types.

It's often desired that sensitive data is not available in clear text
on those chips, since it's straightforward to read them out. 

A typical example may be Wifi credentials and/or code fragments.

The presented `CryptoBdev` class can be used toghether with a block device
to add encryption.

## Usage

To use this class, you have to wrap an existing blockdevice. 

For a simple test you can use the `RAMBlockDevice` (see https://docs.micropython.org/en/latest/reference/filesystem.html#custom-block-devices)

and wrap it like that

```py
# see https://docs.micropython.org/en/latest/reference/filesystem.html#custom-block-devices
import vfs
from cryptbdev import CryptBdev

bdev = CryptoBlockDev(RAMBlockDev(512, 50))
vfs.VfsLfs2.mkfs(bdev)

vfs.mount(bdev, '/ramdisk')

# use it as usual, it'll end up encrypted in /ramdisk
with open('/ramdisk/hello.txt', 'w') as f:
    f.write('Hello world')
print(open('/ramdisk/hello.txt').read())


```

## Limitations

The following features are unsupported:

