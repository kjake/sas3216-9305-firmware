# Is my card one of these?

This project only helps one specific card: a **SAS3216** ROC on a **9305-16i-style
board with internal SFF-8643 connectors**. Before you flash anything, confirm that's
what you have. The software identity is what matters — photos vary between batches.

## What mine looks like

| Front | Back |
|---|---|
| ![front](../images/front@0.5x.jpg) | ![back](../images/back@0.5x.jpg) |

The tell on this batch is the **full-Chinese sticker on the front**. I haven't seen
it on any photo of a genuine 9305-16i. The eBay listing used a more legit-looking
card than what arrived — close, but not the same sticker. Treat the photos as a
"probably" signal, not proof. Confirm in software.

## The definitive check: software identity

**`lspci`** — the chip reports itself. You want SAS3216, not SAS3224 or SAS3008:

```
01:00.0 Serial Attached SCSI controller: Broadcom / LSI SAS3216 PCI-Express Fusion-MPT SAS-3 (rev 01)
```

**`sas3flash -list`** — the firmware's own view (board name, chip, version, SAS
address). Capture this before and after flashing so you can see the change:

```
<!-- paste your `sas3flash -list` output here -->
```

Fields to check:
- **Chip Name / Product ID** — SAS3216
- **Board Name** — on a working clone with this firmware it reads `Avago SAS3216`
- **Firmware Product ID / Version** — after flashing this project's image, P16.00.12.00

**`dmesg`** — after flashing, the driver enumerates cleanly:

```
mpt3sas_cm0: host_add: handle(0x0001), sas_addr(0x5.....), phys(24)
mpt3sas_cm0: port enable: SUCCESS
```

`phys(24)` is expected and cosmetic — the firmware advertises 24 PHY slots from the
16i base NVDATA, but only your 16 wired PHYs enumerate.

## If your card is different

- **SAS3224** reported in `lspci` → you have a genuine 9305-16i (or 16i clone that
  already runs stock firmware). You don't need this.
- **External SFF-8644 connectors** → different PHY wiring. This image will flash but
  the ports won't enumerate. You'd need to derive your own NVDATA — the
  [analysis](analysis.md) and the build tool show how.
- **SAS3008** or anything else → wrong controller entirely; nothing here applies.

If you have a variant that isn't covered, the `sas3flash -list` output and a couple of
clear photos are exactly what a pull request would need to extend support.
