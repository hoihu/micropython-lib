# This file is part of the MicroPython project, http://micropython.org/
#
# The MIT License (MIT)
#
# Copyright (c) 2025 Martin Fischer <fischer.carlito@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# A simple Wrapper class to encrypt an existing block device
# using AES CBS or AES ESSIV. Implementation should be compatible with Linux
# dcrypt/LUKS

import os
from cryptolib import aes
from hashlib import sha256
import struct

MODE_ECB = 1
MODE_CTR = 6   # AES counter mode
MODE_CBC = 2   # AES CBC mode

# CBC can be used together with "plain". It uses the sector number as IV.
# see also https://gitlab.com/cryptsetup/cryptsetup/-/blob/main/FAQ.md?ref_type=heads chapter 5.13
# for pro/cons
ENCRYPT_AES_CBC = 1
# ESSIV is more secure and uses the hashed master key to obtain
# a new AES instance that can be used to encrypt the IV.
ENCRYPT_AES_ESSIV = 2


class CryptBdev():
    def __init__(self, bdev, key=None, mode=ENCRYPT_AES_ESSIV):
        self.key = key if key else os.urandom(32)
        self.bdev = bdev
        self.mode = mode
        # get block size of block device or default to 512 if none is returned
        self.block_size = self.bdev.ioctl(5, None) or 512
        self.scratch_buffer = bytearray(self.block_size)
        # for ESSIV mode, preallocate the IV AES generation instance
        if mode == ENCRYPT_AES_ESSIV:
            self.aes1 = aes(sha256(self.key).digest(), MODE_ECB)
        print(f'blocksize = {self.block_size} bytes / key = {self.key}')

    def _get_aes_obj(self, block_num):
        iv = struct.pack("<QQ", block_num, 0)
        if self.mode == ENCRYPT_AES_ESSIV:
            iv = self.aes1.encrypt(iv)
        return aes(self.key, MODE_CBC, iv)

    def readblocks(self, block_num, buf, offset=0):
        # get encrypted block, decrypt it and return the required length/offset
        aes_obj = self._get_aes_obj(block_num)
        self.bdev.readblocks(block_num, self.scratch_buffer)
        buf[:] = aes_obj.decrypt(self.scratch_buffer)[offset: offset + len(buf)]

    def writeblocks(self, block_num, buf, offset=0):
        # decrypt block, copy over buf, then encrypt again
        aes_obj = self._get_aes_obj(block_num)
        self.bdev.readblocks(block_num, self.scratch_buffer)
        self.scratch_buffer[offset:offset+len(buf)] = buf
        self.bdev.writeblocks(block_num, aes_obj.encrypt(self.scratch_buffer))

    def ioctl(self, op, arg):
        if op == 6:   # block erase
            # handle page erase separately
            print(f"erasing block {arg}...")
            aes_obj = self._get_aes_obj(arg)
            self.bdev.writeblocks(arg, aes_obj.encrypt(bytearray(self.block_size)))
            return 0
        return self.bdev.ioctl(op, arg)
