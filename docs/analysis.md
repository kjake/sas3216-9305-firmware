# How the SAS3216 "9305-16i" clone firmware works

I bought a 9305-16i. It turned out to be a SAS3216 wearing a SAS3224's clothes.
Then I bricked it flashing stock firmware, spent a while getting it back, and
eventually reverse-engineered exactly what makes these clones tick. This is that
writeup — the byte-level differences, the checksum scheme, and why the two obvious
"fixes" both fail.

## The symptom

Flash stock Broadcom 9305-16i firmware onto one of these clones and it dies at POST.
The card either never initializes or comes up with no drives. Flash the 9305-16**e**
firmware instead — which is genuinely SAS3216 silicon — and you get this instead:

```
mpt3sas_cm0: sending port enable !!
... long hang ...
mpt3sas_cm0: port enable: FAILED
```

Two "correct" firmwares, two different failures. That contradiction is the whole
puzzle.

## The card

`lspci` tells the first half of the story:

```
01:00.0 Serial Attached SCSI controller: Broadcom / LSI SAS3216 PCI-Express Fusion-MPT SAS-3 (rev 01)
```

That's a **SAS3216** — a 16-port ROC. The real 9305-16i is a **SAS3224** (24-port,
16 wired). So the board is a clone: 9305-16i layout and internal SFF-8643 connectors,
but cheaper 16-port silicon underneath. No official firmware package targets that
combination, which is why both stock images fail.

## Diffing the images

I had a known-good backup pulled from a working clone (P15, IT mode) — captured and
shared by [Nialpo](https://forums.truenas.com/u/nialpo) on the
[TrueNAS forums](https://forums.truenas.com/t/help-finding-updated-firmware-for-avago-sas3216-9305-16i-hba-card/62254) —
and the stock Broadcom 9305-16i P15 image. Same size to the byte — 959,848 — and
identical headers, down to the firmware version field. The difference is tiny:

```
total differing bytes: 123 / 959848 (0.0128%)
```

All 123 of those bytes live in one region: the NVDATA image at the tail of the file
(everything from `NextImageHeaderLocation` to EOF). The executable firmware — the
first ~900 KB — is **byte-for-byte identical** between the clone and stock. Whatever
makes the clone work isn't code. It's configuration.

Pull the strings out of that 123-byte diff and it names itself:

```
              working clone        stock 9305-16i
chip id       LSISAS3216           LSISAS3224
board name    Avago SAS3216        SAS9305-16i
PCI device    0x00c9               0x00c4
```

Plus a block of PHY-map entries. That's it. Change the chip identity and the PHY
map, and stock firmware becomes clone firmware.

## Why both stock firmwares fail

This is where the two failure modes make sense.

**Stock 9305-16i** declares `LSISAS3224` and a 24-PHY map. On SAS3216 silicon the
chip identity is wrong, PHY init doesn't line up, and the card never comes up.

**Stock 9305-16e** is the right chip (SAS3216) but it's an *external* card. Its PHY
map routes to external SFF-8644 connectors. The clone's ports are internal SFF-8643,
wired like a 16i. So the chip is happy but the PHYs map to connectors that aren't
there — hence `port enable: FAILED` after a long hang.

The clone needs a combination nobody ships: **SAS3216 identity + the 16i internal
PHY map.** The working backup is exactly that — stock 16i NVDATA with the chip
identity swapped to SAS3216 and the PHY map adjusted.

## The checksum scheme

To build a new image I had to change bytes and re-seal it. The NVDATA uses two
checksum layers, both simple once you see them.

**Per-record checksum.** The NVDATA is a series of config records delimited by
`00 00 FF FF FF FF`. The first byte of each record is a checksum. The rule, which
holds across every record in the image:

```
cksum = (0xF8 - sum(rest_of_record)) & 0xFF
```

**Image balancer.** The whole NVDATA image sums to zero as 32-bit little-endian
words. One word in the header absorbs the remainder, sitting in a fixed structure:

```
03 00 00 00  <balancer u32>  74 34 00 00
```

Change any content, fix the affected record checksums, then recompute the balancer
last so the image sums back to zero. One detail that cost me a rebuild: the balancer
has to be located by that `03000000…74340000` signature, not a fixed offset. P16
grew the NVDATA header by 0x70 bytes, and a hardcoded offset put my checksum write
inside the build-date string.

## The P16.12 break

The reason to want newer firmware is code, not config — P16 has the stability and
drive-support fixes the community recommends. So I diffed the P16.12 16i PHY map
against the clone's. They're identical:

```
clone P15:   0202 13  0202 12  0202 10  0202 11  0202 17  0202 16  0202 14  0202 15
16i P16.12:  0202 13  0202 12  0202 10  0202 11  0202 17  0202 16  0202 14  0202 15
16i P15:     8000 08  8000 09  8000 0b  8000 0a  8000 0c  8000 0d  8000 0f  8000 0e
```

Between P15 and P16 Broadcom changed the PHY-descriptor format from `8000NN` to
`0202NN` — and the new values happen to match what the clone needs. So retargeting
P16.12 requires **only the chip-identity change**. The hard part — translating a
16-PHY internal map into a new descriptor format — was already done for me.

## The one byte I couldn't place (until I could)

One byte at `0x0E60FC` changes across both chip and firmware version, and for a while
I couldn't tell what it was:

```
0x04  stock 3224, P15
0x23  clone 3216, P15
0x05  stock 3224, P16
```

No checksum window explained it, and there was no P16 3216-internal reference to copy
from. The deltas are additive — `+0x01` for the version step, `+0x1F` for the chip
step — so the P16 3216 value predicts to `0x24`. I shipped that as a guess with a
`--nvdata-build 0x05` fallback, and it worked on hardware.

Then `sas3flash -list` on the flashed card named it:

```
NVDATA Version (Default)    : 10.00.00.24
```

That `.24` is the byte. `0x0E60FC` is the low octet of the NVDATA version field —
`24 00 00 10`, which the tool reads back as `10.00.00.24`, major `0x10` matching the
P16 firmware. It was never a checksum; it's a version build number. That's why no
checksum math fit it, and why any sane value flashes and runs. The `0x24` guess turned
out to be the internally-consistent version, so it stays the default.

## Proving it before flashing

Two checks stand between the tool and a bricked card.

**The oracle.** Apply the full transform to stock 16i P15, recompute the checksums,
and compare against the known-good clone backup. It has to come out byte-for-byte
identical:

```
[oracle] regenerate known-good clone from P15 base: PASS (byte-identical)
```

That validates the transform and checksum logic against ground truth. Only then does
the same logic get applied to the P16.12 base.

**The hardware.** The P16.12 output flashed clean on a SAS3216 clone (HP Z220,
unRAID 7.2.3): fast POST, all four internal ports enumerating drives across repeated
cold boots, and `port enable: SUCCESS` in dmesg. An overnight soak — four drives,
direct reads, ~660 MB/s aggregate at ~97.5% utilization on every PHY quad — logged
zero PHY resets, zero command timeouts, zero CRC errors. A marginal card throws those
once it heat-soaks. This one stayed silent.

One cosmetic artifact worth knowing: the firmware reports `phys(24)` in dmesg,
inherited from the 16i base NVDATA. Only the 16 wired PHYs enumerate. It's harmless.

## Takeaways

- These clones are SAS3216 silicon on a 16i board. They need SAS3216 identity plus
  the 16i internal PHY map — a combination no stock firmware ships.
- The firmware code is identical across chip variants; only the NVDATA config differs.
- P16.12's 16i image already carries the correct internal PHY map, so retargeting it
  is a chip-identity swap plus a checksum reseal.
- Validate against a known-good backup byte-for-byte before you flash, and test on a
  disposable machine with the original firmware within reach.
