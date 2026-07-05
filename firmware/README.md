# Prebuilt firmware

For people who want a working image without building one. Read this whole file
before you flash anything.

> **Flashing firmware can permanently brick your card.** Back up your card's current
> firmware, BIOS, and SAS address first. Test on a disposable machine. Have a way to
> recover a no-POST board. These images target **one specific clone**: SAS3216
> silicon with internal SFF-8643 connectors, wired like a 9305-16i. On any other card
> they range from useless to destructive. Full procedure: [docs/flash-test.md](../docs/flash-test.md).

## Files

| File | What it is | Size | SHA-256 |
|---|---|---|---|
| `SAS9305-16i_P16.12_SAS3216clone.bin` | **Recommended.** Stock Broadcom 9305-16i **P16.12** IT firmware, retargeted for the SAS3216 clone. Built by `build_3216_clone_fw.py`, oracle-validated, and soak-tested on real hardware. | 998,280 | `2ddb5ee04a52172c3ceeae9bf75661b21618e7c2de5102ac256b9a7cc8a27314` |
| `original-clone-P15/firmware0.fw` | A known-good **P15** clone image (raw `sas3flash` firmware backup). The reference that made this whole project possible; useful as a rescue image if a build misbehaves. | 959,848 | `e2fc1ee77351399cc8e929da2d07fd6f5c993ab559819efae1b8000b024cfd3a` |
| `original-clone-P15/bios0.rom` | The matching P15 option ROM, for a full firmware+BIOS restore. Not needed for IT-mode storage use. | 445,952 | `c4c9b5b278e477d9cbd967e2edc61f176810686db80fd6b080e2f689acf0f3bf` |

Verify before flashing:

```
shasum -a 256 SAS9305-16i_P16.12_SAS3216clone.bin
```

## Which one

Use **`SAS9305-16i_P16.12_SAS3216clone.bin`**. It's the newer firmware (the stability
and drive-support fixes the community recommends) and it's the image that passed the
overnight hardware soak.

The **P15 files** are here as a reference and a rescue image. If a P16 build ever
misbehaves on your card, the P15 image is a known-good fallback that's been running on
these clones for a while.

The P15 firmware and BIOS backup are the work of
**[Nialpo](https://forums.truenas.com/u/nialpo)**, who captured and shared them on the
[TrueNAS forums](https://forums.truenas.com/t/help-finding-updated-firmware-for-avago-sas3216-9305-16i-hba-card/62254).
They are the known-good reference this whole project is validated against.

## SAS address

Neither firmware image contains a SAS address; it lives in a separate flash region
and stays with your card when you flash. If `sas3flash` ever reports the address as
zeroed after a flash, set your own:

```
sas3flash -o -sasadd 500600XXXXXXXXXX
```

Don't copy someone else's SAS address onto your card if you'll ever share a SAS domain
with them.

## NVDATA version byte

The P16.12 build sets one byte (`--nvdata-build`, default `0x24`) that is the low octet
of the NVDATA version; `sas3flash -list` reports `NVDATA Version 10.00.00.24`
(see [analysis](../docs/analysis.md)). It's informational, not a checksum, so it's
low-risk. If you ever want the P16-stock value instead, rebuild with the fallback:

```
python3 ../build_3216_clone_fw.py --base <your stock P16.12>.bin --out clone_m05.bin --nvdata-build 0x05
```

## Copyright

These are modified Broadcom/LSI firmware images, shared for owners of out-of-production
clone cards that no official firmware supports. "LSI", "Broadcom", and "Avago" and the
underlying firmware are property of Broadcom Inc. This project is not affiliated with
or endorsed by Broadcom. If Broadcom objects, the binaries will be removed; the build
tool doesn't redistribute anything and will remain.
