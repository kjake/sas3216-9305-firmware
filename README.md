# sas3216-9305-firmware

Retarget stock Broadcom 9305-16i IT firmware (P16.12) so it runs on a **SAS3216
clone**: a "9305-16i" built on cheaper 16-port silicon instead of the SAS3224 the
real card uses.

These clones pair a SAS3216 ROC with a 9305-16i board and internal SFF-8643
connectors, a combination no official firmware package targets. So every stock image
bricks them:

| Firmware | Chip | Connectors | Result on the SAS3216 clone |
|---|---|---|---|
| Stock 9305-16i | SAS3224 | internal | ❌ wrong chip → no POST / drives invisible |
| Stock 9305-16e | SAS3216 | external | ❌ wrong PHY map → ports never enumerate (boot hangs on port-enable) |
| **This tool's output** | **SAS3216** | **internal** | ✅ POSTs, all internal ports enumerate |

What works is **SAS3216 chip identity paired with the 16i internal PHY map**, and
that's exactly what this tool writes into a stock P16.12 image.

**First, [is your card one of these?](docs/identifying-your-card.md)** Photos and the
`lspci`/`sas3flash` checks confirm it before you flash.

> ### ⚠️ This can brick your card if misused.
> - Flashing firmware is inherently risky. **Test on a throwaway machine first.**
> - **Back up your card's current firmware, BIOS, and SAS address** before flashing.
> - This targets **one specific clone**: SAS3216 ROC + internal SFF-8643 wiring.
>   Other clones (external connectors, different PHY routing) need different NVDATA
>   and **will not work** with this image.
> - No warranty. You are responsible for your hardware. See [flashing guide](docs/flash-test.md).

## How it's validated

The firmware format (NVDATA config records, per-record checksums, and the image
balancer) is reverse-engineered in [docs/analysis.md](docs/analysis.md). The build
pipeline is checked two ways:

1. **Oracle (byte-for-byte):** the same transform + checksum logic regenerates a
   *known-good clone P15 backup* from stock 9305-16i P15 firmware, byte-identical.
2. **Real hardware:** the P16.12 output was flashed to a SAS3216 clone (HP Z220,
   unRAID 7.2.3). POST clean, all internal ports enumerate, and an overnight
   ~660 MB/s all-PHY read soak produced **zero** mpt3sas/PHY/CRC errors.

## Requirements

- Python 3 (standard library only, no dependencies)
- To **build** your own: a stock Broadcom **9305-16i P16.12 IT** firmware image
  (`SAS9305_16i_IT_P.bin`), from Broadcom's support site.
- To **skip building**: a prebuilt image is in [`firmware/`](firmware/) (see caveats).

## Usage

```bash
# Build a clone-compatible image from your stock P16.12 download:
python3 build_3216_clone_fw.py --base SAS9305_16i_IT_P.bin --out clone.bin
```

The tool verifies the base is a genuine stock P16.12 9305-16i image and refuses
anything else, so a wrong/renamed input fails loudly instead of bricking a card.

Then flash on a **test box** per the **[flashing & testing guide](docs/flash-test.md)**.
For an IT-mode storage HBA, flash with **no option ROM** (faster POST, avoids the
boot hang some clones show with the BIOS enabled).

### Don't want to build? Use the prebuilt image

[`firmware/`](firmware/) has the hardware-validated P16.12 image plus a known-good P15
rescue image, with checksums and the same warnings. Read
[firmware/README.md](firmware/README.md) first; same rule applies: test on a
disposable machine, back up your card first.

### Optional: prove the pipeline yourself

If you have a known-good clone P15 backup and the stock 9305-16i P15 image, you can
verify the transform is byte-exact before trusting the P16 build:

```bash
python3 build_3216_clone_fw.py --oracle --p15-base 16i_P15.bin --p15-backup clone_P15.fw
# -> [oracle] regenerate known-good clone from P15 base: PASS (byte-identical)
```

## Notes

- **`phys(24)` in dmesg is cosmetic.** The firmware advertises 24 PHY slots
  (inherited from the 16i/3224 base NVDATA); only your 16 wired PHYs enumerate.
- **`--nvdata-build` sets the NVDATA version build byte** (`sas3flash -list` reports
  `NVDATA Version 10.00.00.24` on this build). It's informational, not a checksum, so
  the value is low-risk; the default `0x24` matches the P16 firmware major.
  `--nvdata-build 0x05` (P16 stock) is available as a fallback.
- Validated for the **P16.12** IT base only. Other P-releases would need the
  offsets re-derived; PRs welcome.

## Credits & legal

- This project exists because **[Nialpo](https://forums.truenas.com/u/nialpo)** made
  and shared a firmware + BIOS backup of a working SAS3216 clone. That backup is the
  known-good P15 reference the whole build validates against, byte for byte. No
  backup, no oracle, no project. Thank you. The discussion that started it:
  [TrueNAS forums](https://forums.truenas.com/t/help-finding-updated-firmware-for-avago-sas3216-9305-16i-hba-card/62254).
- "LSI", "Broadcom", and "Avago" and the firmware are property of Broadcom Inc. This
  project is **not affiliated with or endorsed by Broadcom**. The build tool only
  modifies firmware you supply yourself. The prebuilt images in [`firmware/`](firmware/)
  are modified Broadcom firmware, shared for owners of out-of-production clone cards
  that no official firmware supports; if Broadcom objects, they'll be removed and the
  tool stands on its own. See [firmware/README.md](firmware/README.md).
- Tool code (this repo's own scripts and docs): see [LICENSE](LICENSE).
