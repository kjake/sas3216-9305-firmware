# Flashing and testing

This gets a SAS3216 clone "9305-16i" from bricked-on-stock-firmware to POSTing with
all internal ports live. Do every step on a **disposable machine** first, with the
card's original firmware backed up and within reach.

**Image:** either build your own (`build_3216_clone_fw.py --base <stock P16.12>.bin`)
or use the prebuilt `firmware/SAS9305-16i_P16.12_SAS3216clone.bin`. Read
[firmware/README.md](../firmware/README.md) before using the prebuilt one.

> **Back up your card first.** A firmware backup, a BIOS backup, and the SAS address
> are your only undo button. Have a way to recover a no-POST board (a second machine,
> or IPMI/KVM for a CMOS clear).

## Pre-flight

Boot a **Legacy/CSM** environment; a FreeDOS USB with `sas3flash.exe` is the usual
route. Then capture what's on the card right now:

```
sas3flash -o -ufirmware original_fw.fw
sas3flash -o -ubios     original_bios.rom
sas3flash -listall            # write down the SAS address
```

Keep those three things. If anything goes wrong, they put the card back exactly how
it was.

## Flash

For an IT-mode storage HBA you don't need an option ROM. Skipping it speeds up POST
and avoids the boot hang some clones show with the BIOS enabled.

```
sas3flash -o -f SAS9305-16i_P16.12_SAS3216clone.bin
sas3flash -o -sasadd <SASADDR>     # if sas3flash reports the SAS address as zeroed
sas3flash -o -reset
```

Power the machine fully off, then on, not a warm reboot.

### Option ROM (why `BIOS Version` reads N/A)

We flash firmware only (no `-b`), so `sas3flash -list` shows **`BIOS Version: N/A`**,
and the same for `UEFI BSD Version` and `FCODE Version`. That's expected and correct
for an IT-mode storage HBA. The option ROM is a pre-boot driver you only need if you
**boot the operating system from a drive on this card**. In a NAS (boot from USB, SATA,
or NVMe; the HBA just presents data disks) it does nothing but slow POST, and on some
clones causes the boot hang.

If you *do* need boot-from-HBA, flash an option ROM alongside the firmware. The stock
P16.12 package ships both:

```
sas3flash -o -f SAS9305-16i_P16.12_SAS3216clone.bin -b mpt3x64.rom     # UEFI
sas3flash -o -f SAS9305-16i_P16.12_SAS3216clone.bin -b mptsas3.rom     # legacy/CSM
```

A clean erase clears the option ROM region, and a firmware-only flash won't restore it,
so you'll need to re-add it after any upgrade.

### Erase levels (and the SAS-address trap)

**Upgrading a card that already works?** Use `-e 6` (or just `-f`). What makes the
clone work (chip identity and the PHY map) lives in the firmware image, so replacing
the firmware is all you need. `-e 6` keeps your SAS address and board identity, so
there's no re-set afterward. This is the common case and the safe one.

Reach for `-e 7` only for a first-time conversion, a recovery, or to fix a Board Name
that's stuck on a stale value; know that it costs you the SAS address.

Two erase levels, and the difference bites people:

- **`sas3flash -o -e 6`** clears the firmware regions but **keeps** the manufacturing
  area, so your SAS address and board identity survive. This is the normal pre-flash erase.
- **`sas3flash -o -e 7`** wipes **everything**, including the manufacturing region.
  Use it if the reported **Board Name** is stuck on a stale value from a previous flash
  (a plain `-f` won't change it). But `-e 7` also **erases your SAS address**.

> **Record your SAS address before an `-e 7`.** It's on the sticker on the back of the
> card, and in `sas3flash -list`. After the erase-and-flash, set it back:
> ```
> sas3flash -o -sasadd <SASADDR>
> ```
> A zeroed or duplicated SAS address causes conflicts if the card ever shares a SAS
> domain with another. Don't skip this.

## Verify

Go in order. Stop and roll back if any step fails.

**POST.** The system POSTs without hanging on "initializing". A hang here is the
stock-16e failure mode; wrong firmware took, but the PHYs don't map.

**Controller enumerates.**

```
sas3flash -listall           # firmware reads P16.00.12.00
lspci -nn | grep -i sas      # device id 00c9 (SAS3216)
```

**NVDATA looks sane.**

```
sas3flash -list              # board name "Avago SAS3216", IT mode
```

**Drives enumerate.** Attach drives to the internal ports and confirm they appear:

```
lsblk
dmesg | grep -i mpt3sas      # every disk shows up, no PHY errors
```

Healthy boot log ends with `port enable: SUCCESS`. The `Power-on or device reset
occurred` lines are normal SATA power-on status, not HBA errors.

**Soak it.** Load every port for a few hours before trusting the card. On bare
unRAID without an array, parallel raw reads work well (`iflag=direct` matters; it
bypasses the page cache so the reads actually hit the HBA):

```
for d in sdX sdY sdZ ...; do
  ( while true; do dd if=/dev/$d of=/dev/null bs=4M iflag=direct 2>/dev/null; done ) &
done
watch -n5 'dmesg | grep -iE "mpt3sas|phy|reset|abort|timeout|CRC" | tail -20'
```

A clean run shows **nothing new** in dmesg for hours. Marginal cards throw PHY resets
or command timeouts once they heat-soak; that's what the sustained load is for. When
you're done: `pkill dd`, then check the PHY error counters stayed at zero:

```
for d in sdX sdY sdZ; do smartctl -l sasphy /dev/$d | grep -iE "invalid dword|disparity|loss of|phy reset"; done
```

## If it fails

**Ports don't enumerate, or PHY errors.** Your card may need the fallback value for
the one unproven vendor byte. Rebuild with `--nvdata-build 0x05` and reflash:

```
python3 build_3216_clone_fw.py --base <stock-P16.12>.bin --out clone_m05.bin --nvdata-build 0x05
```

**Won't POST at all.** Restore the backup you took in pre-flight:

```
sas3flash -o -f original_fw.fw -b original_bios.rom
sas3flash -o -sasadd <SASADDR>
sas3flash -o -reset
```

If the board won't POST far enough to run `sas3flash`, move it to another machine or
clear CMOS and try the restore there.

## Scope

This image targets one specific clone: **SAS3216 silicon with internal SFF-8643
connectors**, wired like a 9305-16i. Other clones (external connectors, different
PHY routing) carry different NVDATA and will not work with it. If your card is a
different variant, the tool and [analysis](analysis.md) show how to derive your own.
