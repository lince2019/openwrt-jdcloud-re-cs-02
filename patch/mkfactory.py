#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 sysupgrade 包合成京东云 RE-SS-01 可直接用 U-Boot Web 不死刷入的 factory 镜像。

布局 -- 必须与 U-Boot 的 check_fw_type() 对齐:
    0x000000   FIT (kernel + fdt)          魔数 d00dfeed
    0x600000   squashfs rootfs             魔数 hsqs
    ...        0x00 填充到 root-pad

为什么要对 root 段做零填充:
    该机没有使用 GPT 里的 rootfs_data 分区, overlay 是 fstools 在 rootfs 分区(p18)
    中、rootfs 镜像之后自动挖出的 loop 设备(实测 loop0 offset == rootfs 镜像长度)。
    U-Boot 刷机只覆盖 p18 的开头部分, 镜像之后的旧 ext4 完好无损,
    于是 /etc/board.json 等旧配置会跨版本残留 -- 这正是之前"改了设置却不生效"的原因。
    把 root 段填充到超过旧 overlay 的起点, 刷入时就会连同旧 ext4 超级块一起抹掉。

用法:
    python3 mkfactory.py --bin openwrt/bin/targets/qualcommax/ipq60xx
"""

import argparse
import glob
import hashlib
import os
import struct
import sys
import tarfile

FIT_MAGIC = 0xD00DFEED
KERNEL_ZONE = 6 * 1024 * 1024           # U-Boot 靠 6MB 处的 hsqs 判定 FW_TYPE_FACTORY_KERNEL6M
ROOT_PAD = 24 * 1024 * 1024             # root 段最小长度, 须大于 rootfs 镜像本身
ROOTFS_PART_BYTES = 60 * 1024 * 1024    # p18 分区大小, 用于上限校验


def pick_member(names, suffix):
    hits = [n for n in names if n.endswith("/" + suffix)]
    if not hits:
        sys.exit("!! sysupgrade 包中找不到成员 " + suffix)
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True, help="bin/targets/<target>/<subtarget> 目录")
    ap.add_argument("--out", default=None, help="输出文件名")
    ap.add_argument("--root-pad", type=int, default=ROOT_PAD)
    args = ap.parse_args()

    tars = sorted(glob.glob(os.path.join(args.bin, "*squashfs-sysupgrade.bin")))
    if not tars:
        sys.exit("!! 未找到 squashfs-sysupgrade 镜像: " + args.bin)
    tar_path = tars[0]
    print("源包: %s" % os.path.basename(tar_path))

    with tarfile.open(tar_path) as tf:
        names = tf.getnames()
        k_name = pick_member(names, "kernel")
        r_name = pick_member(names, "root")
        kernel = tf.extractfile(k_name).read()
        root = tf.extractfile(r_name).read()

    print("  kernel %d 字节 (%s)" % (len(kernel), k_name))
    print("  root   %d 字节 (%s)" % (len(root), r_name))
    # 中文界面是否随镜像下发（config.seed 里的 luci-i18n-* 会被 defconfig 丢掉，
    # 实际上是靠 files/ 机制把 .lmo 打进根文件系统）
    zh = sorted(set(
        n.split("/")[-1] for n in [b"base.zh-cn.lmo", b"firewall.zh-cn.lmo",
                                   b"package-manager.zh-cn.lmo"]
        if n in root
    ))
    print("  中文界面: %s" % ("已内置 " + ",".join(zh) if zh else "缺失，刷机后需另行 apk add"))

    # --- 内核段 ---
    if len(kernel) < 4 or struct.unpack_from(">I", kernel, 0)[0] != FIT_MAGIC:
        sys.exit("!! kernel 成员不是 FIT 镜像")
    if len(kernel) > KERNEL_ZONE:
        sys.exit("!! kernel %d 超过 %d 字节的 kernel 区" % (len(kernel), KERNEL_ZONE))
    kern_zone = kernel + b"\xff" * (KERNEL_ZONE - len(kernel))

    # --- root 段 ---
    if root[:4] != b"hsqs":
        sys.exit("!! root 成员不是 squashfs")
    pad = max(args.root_pad, len(root))
    if pad > ROOTFS_PART_BYTES:
        sys.exit("!! root 段 %d 超过 p18 分区容量 %d" % (pad, ROOTFS_PART_BYTES))
    root_zone = root + b"\x00" * (pad - len(root))

    img = kern_zone + root_zone

    # --- 自检 ---
    assert struct.unpack_from(">I", img, 0)[0] == FIT_MAGIC, "头部不是 FIT"
    assert img[KERNEL_ZONE:KERNEL_ZONE + 4] == b"hsqs", "6MB 处不是 squashfs"
    assert img[KERNEL_ZONE:KERNEL_ZONE + len(root)] == root, "rootfs 内容被破坏"
    assert img[KERNEL_ZONE + len(root):] == b"\x00" * (pad - len(root)), "填充异常"
    assert len(img) == KERNEL_ZONE + pad, "总长度异常"

    out = args.out or "openwrt-25.12-jdcloud-re-ss-01-factory-kernel6M.bin"
    out_path = os.path.join(args.bin, out)
    with open(out_path, "wb") as f:
        f.write(img)

    h = hashlib.sha256(img).hexdigest()
    print("")
    print("输出: %s" % out_path)
    print("大小: %d 字节 (%.2f MiB)" % (len(img), len(img) / 1048576.0))
    print("  [0x000000] FIT   %d -> %d (0xFF 填充)" % (len(kernel), KERNEL_ZONE))
    print("  [0x600000] root  %d -> %d (0x00 填充, 用于抹掉旧 overlay)" % (len(root), pad))
    print("SHA256: %s" % h)
    with open(out_path + ".sha256", "w") as f:
        f.write("%s  %s\n" % (h, out))


if __name__ == "__main__":
    main()
