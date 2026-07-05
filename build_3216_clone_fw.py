#!/usr/bin/env python3
"""
build_3216_clone_fw.py
Retarget stock Broadcom/LSI 9305-16i IT firmware (P16.12) so it runs on a
"fake"/clone 9305-16i built on SAS3216 silicon with internal SFF-8643 connectors.

TESTED FIRMWARE VERSIONS (this is the whole supported matrix)
  * BUILD   : 9305-16i **P16.12** IT only. The tool reads the version field and
              REFUSES any other base image, so you cannot accidentally build from
              an untested release.
  * ORACLE  : validates the transform against 9305-16i **P15** IT + a known-good
              P15 clone backup.
  No other P-releases are tested. Adapting to a different one means re-deriving the
  NVDATA offsets in this file (see docs/analysis.md); PRs welcome.

WHAT / WHY
  Some cheap "9305-16i" cards use a SAS3216 ROC (16-port) instead of the genuine
  SAS3224 (24-port). Stock 9305-16i firmware declares SAS3224 + a 24-PHY map and
  bricks the clone (no POST / drives invisible). Stock 9305-16e firmware is the
  right chip (SAS3216) but maps EXTERNAL connectors, so the clone's INTERNAL ports
  never enumerate. The only thing that works is: SAS3216 chip identity + the 16i
  INTERNAL PHY map.

KEY FINDING
  At P16.12 Broadcom already ships the correct internal PHY map in the 16i image
  (the PHY descriptor format changed 8000NN -> 0202NN and now matches the clone).
  So retargeting P16.12-16i needs ONLY the chip-identity change, not PHY surgery.

CHECKSUM MODEL (reverse-engineered; the --oracle mode proves it byte-for-byte
against a known-good clone P15 backup):
  * NVDATA image = [NextImageHeaderLocation .. EOF]; whole image u32-sums to 0.
  * Config records are delimited by `00 00 FF FF FF FF`; the first byte of each
    record is a checksum: cksum = (0xF8 - sum(record[1:])) & 0xFF
  * Image balancer u32 lives in the header as `03 00 00 00 <BAL> 74 34 00 00`
    (located structurally, NOT by fixed offset). Recomputed last so the image
    u32-sums to 0.

SCOPE / SAFETY
  * Validated for the 9305-16i **P16.12** IT firmware base, on the SAS3216 +
    internal-SFF-8643 clone. Other P-releases or clone wirings are NOT covered.
  * The tool verifies expected stock bytes before patching and refuses a base file
    that doesn't match, so a wrong/renamed input fails loudly instead of bricking.
  * ALWAYS back up your card's current firmware+BIOS+SAS address first, test on a
    throwaway box, and keep a known-good image reachable. See docs/flash-test.md.

USAGE
  # Build (you supply your own stock Broadcom P16.12 9305-16i IT image):
  python3 build_3216_clone_fw.py --base SAS9305_16i_IT_P.bin --out clone.bin

  # Prove the pipeline byte-for-byte (needs a known-good clone P15 backup + stock
  # 9305-16i P15 image; most users won't have these — it's for verification):
  python3 build_3216_clone_fw.py --oracle --p15-base 16i_P15.bin --p15-backup clone_P15.fw
"""
import struct, re, sys, hashlib, argparse

SHIFT = 0x9620  # NVDATA content relocation P15 -> P16.12 (used to map P15 offsets to P16)

# (p15_offset, expected_stock_3224_hex, write_clone_3216_hex)
# 'id'  = chip-identity; patched in BOTH the P15 oracle and the P16.12 build.
# 'p15' = already-correct in P16.12 (PHY map, etc.); patched only in the P15 oracle.
IDENTITY = [
    (0x0E6124, "534153393330352d3136690000", "417661676f2053415333323136"),  # board name
    (0x0E6142, "c4", "c9"),                                                    # PCI dev id
    (0x0E6146, "90", "80"),                                                    # PCI subsys
    (0x0E6548, "3234", "3136"),                                                # LSISAS32'24'->'16'
    (0x0E6558, "534153393330352d3136690000", "417661676f2053415333323136"),  # board name 2
    (0x0E6698, "c4", "c9"), (0x0E66B0, "c4", "c9"), (0x0E66B7, "90", "80"),   # PCI
    (0x0E677B, "9a", "a5"),
    (0x0E6C44, "01", "03"),
    (0x0E7764, "08", "18"), (0x0E7767, "0000000300", "8000040305"), (0x0E776E, "0001", "4000"),
    (0x0E844C, "000000", "080506"),
]
# PHY map + one byte that P16.12 already ships correctly. Applied ONLY in oracle.
P15_ONLY = [
    (0x0E6D3C,"0000","0701"),(0x0E6D50,"800008","020213"),(0x0E6D58,"0000","0701"),
    (0x0E6D6C,"800009","020212"),(0x0E6D74,"0000","0701"),(0x0E6D88,"80000b","020210"),
    (0x0E6D90,"0000","0701"),(0x0E6DA4,"80000a","020211"),(0x0E6DAC,"0000","0701"),
    (0x0E6DC0,"80000c","020217"),(0x0E6DC8,"0000","0701"),(0x0E6DDC,"80000d","020216"),
    (0x0E6DE4,"0000","0701"),(0x0E6DF8,"80000f","020214"),(0x0E6E00,"0000","0701"),
    (0x0E6E14,"80000e","020215"),
    (0x0E7178,"00","04"),(0x0E7180,"0001020304050607","0a0b090800000000"),
    (0x0E71A0,"00","04"),(0x0E71A8,"0001020304050607","0e0f0d0c00000000"),
    (0x0E71D0,"08090b0a","12131110"),(0x0E71F8,"0c0d0f0e","16171514"),
    (0x0E8396,"00","08"),
]
MYSTERY_OFF = 0x0E60FC        # vendor/version byte; P15 clone=0x23, P16 stock=0x05
MYSTERY_P16_DEFAULT = 0x24    # linear model (0x04 base +0x01 ver +0x1F chip); hw-validated
REC_CKSUMS = [0x0E6539,0x0E6691,0x0E6C35,0x0E70D9,0x0E7759,0x0E8341,0x0E83DD]

def u32(b,o): return struct.unpack_from("<I",b,o)[0]
def nvdata_start(b): return u32(b,0x30)

def record_starts(b):
    n=nvdata_start(b)
    return [n+m.start()-1 for m in re.finditer(rb"\x00\x00\xff\xff\xff\xff",bytes(b[n:]))]+[len(b)]

def fix_record_cksum(b,starts,rec):
    s=max(x for x in starts if x<=rec); e=min(x for x in starts if x>rec)
    b[s]=(0xF8-(sum(b[s+1:e])&0xFF))&0xFF

def fix_balancer(b):
    n=nvdata_start(b)
    hits=[m.start()+4 for m in re.finditer(rb"\x03\x00\x00\x00(....)\x74\x34\x00\x00",bytes(b),re.S) if m.start()>=n]
    if len(hits)!=1: raise RuntimeError(f"balancer signature hits={len(hits)} (expected 1)")
    w=hits[0]; b[w:w+4]=b"\x00\x00\x00\x00"; tot=0
    for o in range(n,len(b),4): tot=(tot+u32(b,o))&0xFFFFFFFF
    struct.pack_into("<I",b,w,(-tot)&0xFFFFFFFF)

def run_oracle(p15_base, p15_backup):
    o15=bytearray(open(p15_base,'rb').read()); bkp=open(p15_backup,'rb').read()
    img=bytearray(o15)
    img[MYSTERY_OFF]=0x23
    for off,_,new in IDENTITY+P15_ONLY:
        img[off:off+len(new)//2]=bytes.fromhex(new)
    st=record_starts(bytearray(bkp))
    for r in REC_CKSUMS: fix_record_cksum(img,st,r)
    fix_balancer(img)
    ok = bytes(img)==bkp
    print(f"[oracle] regenerate known-good clone from P15 base: {'PASS (byte-identical)' if ok else 'FAIL'}")
    return ok

def build(base_p16, out, mystery):
    b=bytearray(open(base_p16,'rb').read())
    # This tool is tested ONLY on the 9305-16i P16.12 IT base. Refuse anything else.
    if u32(b,0x14)!=0x10000c00:
        sys.exit("ERROR: base is not 9305-16i P16.12 (version field 0x14 != 000c0010).\n"
                 "       This tool only supports the P16.12 IT base. See 'TESTED FIRMWARE\n"
                 "       VERSIONS' at the top of this file for what's supported and why.")
    if b"LSISAS3224" not in bytes(b):
        sys.exit("ERROR: base does not contain 'LSISAS3224' — not a stock 9305-16i IT image.")
    # verify + patch identity fields at P16 offsets
    for off,exp,new in IDENTITY:
        p=off+SHIFT; cur=bytes(b[p:p+len(exp)//2])
        if cur!=bytes.fromhex(exp):
            sys.exit(f"ERROR: base mismatch at 0x{p:06x}: got {cur.hex()} expected {exp}. "
                     f"Base is not the expected stock P16.12 9305-16i IT image.")
        b[p:p+len(new)//2]=bytes.fromhex(new)
    b[MYSTERY_OFF+SHIFT]=mystery
    st=record_starts(b)
    for r in REC_CKSUMS: fix_record_cksum(b,st,r+SHIFT)
    fix_balancer(b)
    open(out,'wb').write(b)
    n=nvdata_start(b); tot=0
    for o in range(n,len(b),4): tot=(tot+u32(b,o))&0xFFFFFFFF
    chips=sorted(set(x.decode() for x in re.findall(rb"LSISAS32\d\d",bytes(b))))
    print(f"[build] wrote {out}  size={len(b)}  md5={hashlib.md5(b).hexdigest()}")
    print(f"[build] chip id: {chips}   NVDATA u32-sum: {tot:#x} (want 0x0)   mystery byte: {mystery:#04x}")
    if chips!=["LSISAS3216"] or tot!=0: sys.exit("ERROR: post-build sanity failed")
    print("[build] OK — flash on a THROWAWAY box first; see docs/flash-test.md")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description="Retarget 9305-16i P16.12 IT firmware for SAS3216 clones")
    ap.add_argument("--base",help="stock Broadcom 9305-16i P16.12 IT image (.bin)")
    ap.add_argument("--out",default="SAS9305-16i_P16.12_SAS3216clone.bin")
    ap.add_argument("--mystery",default=hex(MYSTERY_P16_DEFAULT),
                    help="vendor byte value (default 0x24; fallback 0x05 if the card misbehaves)")
    ap.add_argument("--oracle",action="store_true",help="verify pipeline against P15 reference files")
    ap.add_argument("--p15-base"); ap.add_argument("--p15-backup")
    a=ap.parse_args()
    if a.oracle:
        if not (a.p15_base and a.p15_backup): sys.exit("--oracle needs --p15-base and --p15-backup")
        sys.exit(0 if run_oracle(a.p15_base,a.p15_backup) else 1)
    if not a.base: sys.exit("give --base <stock P16.12 9305-16i IT .bin>  (or --oracle ...)")
    build(a.base,a.out,int(a.mystery,0))
