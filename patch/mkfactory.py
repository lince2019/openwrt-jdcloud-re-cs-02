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


# --- U-Boot 配置名候选 -------------------------------------------------------
# 该机 U-Boot 的 config_select() 并不是用 configurations/default，
# 而是拿自己 DTB 里 /config_name 的字符串去 FIT 里逐个匹配；
# 名字对不上就打印 "Config not available" 并回落 Web 不死界面。
# 我们无法从 U-Boot 二进制里读出那个名字（它不含内嵌 DTB、也没有 cp03 字样），
# 因此把常见候选全部补齐——实测其中能被命中，代价只是几十字节。
EXTRA_CONF = [
    "config@cp03-c2", "config@cp03-c1_1", "config@cp03-c2_1",
    "config@cp03-c1_2", "config@cp03-c2_2", "config@cp03-c3",
    "config@cp03-c4", "config@cp03-c5", "cp03-c2",
]


# --- 极简 FDT 读写（只够克隆 configurations 下的节点）------------------------
_BEGIN_NODE, _END_NODE, _PROP, _NOP, _END = 1, 2, 3, 4, 9


class _Node:
    def __init__(self, name):
        self.name = name
        self.props = []      # [(name, bytes)]
        self.children = []

    def get(self, name):
        for k, v in self.props:
            if k == name:
                return v
        return None

    def set(self, name, val):
        for i, (k, v) in enumerate(self.props):
            if k == name:
                self.props[i] = (k, val)
                return
        self.props.append((name, val))

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None


def _align4(n):
    return (n + 3) & ~3


def _fdt_parse(data):
    magic, totalsize, off_struct, off_strings, off_rsvmap = struct.unpack_from(">5I", data, 0)
    if magic != FIT_MAGIC:
        sys.exit("!! 不是合法 FDT/FIT")
    version, lastcomp, bootcpu, size_strings, size_struct = struct.unpack_from(">5I", data, 20)
    rsv, p = [], off_rsvmap
    while True:
        addr, size = struct.unpack_from(">QQ", data, p)
        p += 16
        if addr == 0 and size == 0:
            break
        rsv.append((addr, size))
    p, root, stack = off_struct, None, []
    while True:
        tok, = struct.unpack_from(">I", data, p); p += 4
        if tok == _BEGIN_NODE:
            e = data.index(b"\0", p)
            n = _Node(data[p:e].decode("utf-8", "surrogateescape"))
            p = _align4(e + 1)
            if root is None:
                root = n
            else:
                stack[-1].children.append(n)
            stack.append(n)
        elif tok == _END_NODE:
            stack.pop()
        elif tok == _PROP:
            ln, nameoff = struct.unpack_from(">II", data, p); p += 8
            s = off_strings + nameoff
            stack[-1].props.append((data[s:data.index(b"\0", s)].decode("utf-8", "surrogateescape"),
                                    data[p:p + ln]))
            p = _align4(p + ln)
        elif tok == _NOP:
            pass
        elif tok == _END:
            break
        else:
            sys.exit("!! FDT 结构解析失败")
    return dict(version=version, lastcomp=lastcomp, bootcpu=bootcpu, rsv=rsv), root


def _fdt_build(hdr, root):
    strings, sindex = bytearray(), {}

    def s_off(name):
        b = name.encode("utf-8")
        if b in sindex:
            return sindex[b]
        off = len(strings)
        strings.extend(b + b"\0")
        sindex[b] = off
        return off

    body = bytearray()

    def emit(n):
        body.extend(struct.pack(">I", _BEGIN_NODE))
        body.extend(n.name.encode("utf-8") + b"\0")
        body.extend(b"\0" * (_align4(len(body)) - len(body)))
        for k, v in n.props:
            body.extend(struct.pack(">III", _PROP, len(v), s_off(k)))
            body.extend(v)
            body.extend(b"\0" * (_align4(len(body)) - len(body)))
        for c in n.children:
            emit(c)
        body.extend(struct.pack(">I", _END_NODE))

    emit(root)
    body.extend(struct.pack(">I", _END))
    rsv = b"".join(struct.pack(">QQ", a, s) for a, s in hdr["rsv"]) + b"\0" * 16
    off_rsvmap = 40
    off_struct = off_rsvmap + len(rsv)
    off_strings = off_struct + len(body)
    out = bytearray()
    out.extend(struct.pack(">10I", FIT_MAGIC, off_strings + len(strings), off_struct,
                           off_strings, off_rsvmap, hdr["version"], hdr["lastcomp"],
                           hdr["bootcpu"], len(strings), len(body)))
    out.extend(rsv)
    out.extend(body)
    out.extend(strings)
    return bytes(out)


def _clone(n, newname):
    c = _Node(newname)
    c.props = list(n.props)
    for ch in n.children:
        c.children.append(_clone(ch, ch.name))
    return c


def add_config_nodes(fit):
    """补齐 U-Boot 可能查找的 config 名字，返回新的 FIT。"""
    hdr, root = _fdt_parse(fit)
    conf = root.child("configurations")
    if conf is None:
        sys.exit("!! FIT 内没有 configurations 节点")
    existing = [c.name for c in conf.children]
    base = conf.children[0]
    added = []
    for name in EXTRA_CONF:
        if name in existing:
            continue
        n = _clone(base, name)
        n.set("description", ("OpenWrt jdcloud_re-ss-01 (%s)" % name).encode() + b"\0")
        conf.children.append(n)
        added.append(name)
    new_fit = _fdt_build(hdr, root)
    print("  config 节点: %d 个 (%s)"
          % (len(conf.children), "新增 " + ",".join(added) if added else "无变化"))
    _verify_hashes(new_fit)
    return new_fit


def _verify_hashes(fit):
    """FIT 内各 image 的 crc32/sha1 必须与 payload 一致（改动结构不能破坏校验）。"""
    import zlib
    hdr, root = _fdt_parse(fit)
    for img in root.child("images").children:
        payload = img.get("data")
        for ch in img.children:
            algo = ch.get("algo")
            if algo is None:
                continue
            algo = algo.rstrip(b"\0").decode()
            if algo == "crc32":
                got = struct.pack(">I", zlib.crc32(payload) & 0xffffffff)
            elif algo == "sha1":
                got = hashlib.sha1(payload).digest()
            elif algo == "sha256":
                got = hashlib.sha256(payload).digest()
            else:
                continue
            if got != ch.get("value"):
                sys.exit("!! %s 的 %s 校验失败" % (img.name, algo))
    print("  FIT 内部校验: OK")


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
    # 中文由 patch/i18n/*.lmo 经 files/ 机制打进根文件系统（config.seed 里的
    # luci-i18n-* 会被 defconfig 丢掉）。注意：这里**不能**用"搜字节"的方式自检——
    # squashfs 的文件名存在压缩过的元数据块里，明文搜索必然搜不到、会误报缺失。
    # 如需确认请解包验证：unsquashfs -ll 或 python 的 PySquashfsImage。

    # --- 内核段 ---
    if len(kernel) < 4 or struct.unpack_from(">I", kernel, 0)[0] != FIT_MAGIC:
        sys.exit("!! kernel 成员不是 FIT 镜像")
    # 补齐 U-Boot 可能查找的 config 名字；只改结构不改 payload，hash 不受影响
    kernel = add_config_nodes(kernel)
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
