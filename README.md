# sas3216-9305-firmware

Retarget stock **Broadcom/LSI 9305-16i IT firmware (P16.12)** so it runs on a
**"fake" 9305-16i built on SAS3216 silicon** with internal SFF-8643 connectors.

Some inexpensive "9305-16i" HBAs use a **SAS3216** ROC (16-port) instead of the
genuine **SAS3224** (24-port). Stock firmware bricks them:

| Firmware | Chip | Connectors | Result on the SAS3216 clone |
|---|---|---|---|
| Stock 9305-16i | SAS3224 | internal | ❌ wrong chip → no POST / drives invisible |
| Stock 9305-16e | SAS3216 | external | ❌ wrong PHY map → ports never enumerate (boot hangs on port-enable) |
| **This tool's output** | **SAS3216** | **internal** | ✅ POSTs, all internal ports enumerate |

The clone needs a combination no official package ships: **SAS3216 chip identity +
the 16i internal PHY map.** This tool produces exactly that from a stock P16.12 image.

> ### ⚠️ This can brick your card if misused.
> - Flashing firmware is inherently risky. **Test on a throwaway machine first.**
> - **Back up your card's current firmware, BIOS, and SAS address** before flashing.
> - This targets **one specific clone**: SAS3216 ROC + internal SFF-8643 wiring.
>   Other clones (external connectors, different PHY routing) need different NVDATA
>   and **will not work** with this image.
> - No warranty. You are responsible for your hardware. See [flashing guide](docs/flash-test.md).

## Why it's trustworthy

The firmware format (NVDATA config records, per-record checksums, and the image
balancer) was fully reverse-engineered — see [docs/analysis.md](docs/analysis.md).
The build pipeline is validated two ways:

1. **Oracle (byte-for-byte):** the same transform + checksum logic regenerates a
   *known-good clone P15 backup* from stock 9305-16i P15 firmware, byte-identical.
2. **Real hardware:** the P16.12 output was flashed to a SAS3216 clone (HP Z220,
   unRAID 7.2.3) — POST clean, all internal ports enumerate, and an overnight
   ~660 MB/s all-PHY read soak produced **zero** mpt3sas/PHY/CRC errors.

## Requirements

- Python 3 (standard library only — no dependencies)
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
[firmware/README.md](firmware/README.md) first — same rule applies: test on a
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
- **One vendor byte** (`--mystery`, default `0x24`) could not be oracle-validated
  (no P16 3216-internal reference exists). It is confirmed working on real hardware.
  If your card misbehaves, rebuild with `--mystery 0x05` (P16 stock) and reflash.
- Validated for the **P16.12** IT base only. Other P-releases would need the
  offsets re-derived; PRs welcome.

## Credits & legal

- Made possible by a community-shared known-good clone P15 backup — paying the
  method forward.
- "LSI", "Broadcom", "Avago", and the firmware are property of Broadcom Inc. This
  project is **not affiliated with or endorsed by Broadcom**. It only modifies
  firmware you legally obtain yourself; no firmware is distributed here.
- Tool code: see [LICENSE](LICENSE).
