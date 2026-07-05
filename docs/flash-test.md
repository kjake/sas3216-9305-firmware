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

Boot a **Legacy/CSM** environment — a FreeDOS USB with `sas3flash.exe` is the usual
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

Power the machine fully off, then on — not a warm reboot.

## Verify

Go in order. Stop and roll back if any step fails.

**POST.** The system POSTs without hanging on "initializing". A hang here is the
stock-16e failure mode — wrong firmware took, but the PHYs don't map.

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
unRAID without an array, parallel raw reads work well (`iflag=direct` matters — it
bypasses the page cache so the reads actually hit the HBA):

```
for d in sdX sdY sdZ ...; do
  ( while true; do dd if=/dev/$d of=/dev/null bs=4M iflag=direct 2>/dev/null; done ) &
done
watch -n5 'dmesg | grep -iE "mpt3sas|phy|reset|abort|timeout|CRC" | tail -20'
```

A clean run shows **nothing new** in dmesg for hours. Marginal cards throw PHY resets
or command timeouts once they heat-soak — that's what the sustained load is for. When
you're done: `pkill dd`, then check the PHY error counters stayed at zero:

```
for d in sdX sdY sdZ; do smartctl -l sasphy /dev/$d | grep -iE "invalid dword|disparity|loss of|phy reset"; done
```

## If it fails

**Ports don't enumerate, or PHY errors.** Your card may need the fallback value for
the one unproven vendor byte. Rebuild with `--mystery 0x05` and reflash:

```
python3 build_3216_clone_fw.py --base <stock-P16.12>.bin --out clone_m05.bin --mystery 0x05
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
connectors**, wired like a 9305-16i. Other clones — external connectors, different
PHY routing — carry different NVDATA and will not work with it. If your card is a
different variant, the tool and [analysis](analysis.md) show how to derive your own.
