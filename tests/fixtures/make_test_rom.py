"""Writes a minimal NROM test cartridge, generated here so tests need no game file.

Each frame it reads the controller and increments RAM $10 while Right is held. $10 wraps at 255 on purpose: that is the
signed-or-wrapping byte bug the reward lint must catch.
"""
import sys

CODE = bytes([
    0x78, 0xD8, 0xA2, 0xFF, 0x9A,        # SEI, CLD, LDX #$FF, TXS
    0xA9, 0x00, 0x85, 0x10,              # LDA #0, STA $10
    0xA9, 0x01, 0x8D, 0x16, 0x40,        # loop: LDA #1, STA $4016
    0xA9, 0x00, 0x8D, 0x16, 0x40,        # LDA #0, STA $4016
    0xA2, 0x08,                          # LDX #8
    0xAD, 0x16, 0x40, 0x29, 0x01,        # read: LDA $4016, AND #1
    0xCA, 0xD0, 0xF8,                    # DEX, BNE read   (A keeps the 8th bit: Right)
    0x29, 0x01, 0xF0, 0x02, 0xE6, 0x10,  # AND #1 (sets Z from A again), BEQ wait, INC $10
    0x2C, 0x02, 0x20, 0x10, 0xFB,        # wait: BIT $2002, BPL wait
    0x4C, 0x09, 0xC0,                    # JMP loop
])


def rom():
    prg = bytearray(16384)
    prg[:len(CODE)] = CODE
    prg[0x3FFC:0x3FFE] = b'\x00\xC0'     # reset vector $C000
    prg[0x3FFA:0x3FFC] = b'\x00\xC0'
    prg[0x3FFE:0x4000] = b'\x00\xC0'
    return b'NES\x1a\x01\x01\x00\x00' + bytes(8) + bytes(prg) + bytes(8192)


if __name__ == '__main__':
    with open(sys.argv[1], 'wb') as f:
        f.write(rom())
