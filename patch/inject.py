#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 jdcloud,re-ss-01 注入 ipq60xx 子目标的板级脚本。

采用「锚点注入」而非整文件替换，好处是：
  1. 上游后续修改的其他机型条目不会被回退；
  2. 锚点一旦变动会立即报错，不会静默生成错误固件。

用法（在 OpenWrt 源码根目录执行）：
    python3 <本脚本路径>
"""

import os
import sys

NET = "target/linux/qualcommax/ipq60xx/base-files/etc/board.d/02_network"
PLAT = "target/linux/qualcommax/ipq60xx/base-files/lib/upgrade/platform.sh"

MARKER = "jdcloud,re-ss-01"


def inject(path, anchor, insertion, before=False):
    """在 anchor 之前(before=True)或之后插入文本。"""
    if not os.path.isfile(path):
        sys.exit("!! 未找到文件: %s（上游目录结构可能已变）" % path)

    s = open(path, encoding="utf-8").read()

    if MARKER in s:
        print("  [skip] 已包含 %s: %s" % (MARKER, path))
        return

    n = s.count(anchor)
    if n != 1:
        sys.exit("!! 锚点在 %s 中命中 %d 次（预期 1 次），上游格式已变更，请更新补丁" % (path, n))

    if before:
        s = s.replace(anchor, insertion + anchor, 1)
    else:
        s = s.replace(anchor, anchor + insertion, 1)

    open(path, "w", encoding="utf-8", newline="\n").write(s)
    print("  [ ok ] 已注入: %s" % path)


def main():
    # 1) 网络：设备树里 dp2/dp3/dp4 = lan1/lan2/lan3，dp5 = wan
    inject(
        NET,
        '\tqihoo,360v6)\n\t\tucidef_set_interfaces_lan_wan "lan1 lan2 lan3" "wan"\n\t\t;;\n',
        "\tjdcloud,re-ss-01)\n"
        '\t\tucidef_set_interfaces_lan_wan "lan1 lan2 lan3" "wan"\n'
        "\t\t;;\n",
        before=False,
    )

    # 2) 升级：eMMC 设备上 nand_do_upgrade / default_do_upgrade 都不适用，
    #    显式拒绝并提示走 U-Boot Web 不死，避免误写坏分区。
    #    注意锚点不要带前导换行，否则 before 插入会把插入内容与上一行的 ";;" 粘在一起。
    inject(
        PLAT,
        '\t*)\n\t\tdefault_do_upgrade "$1"\n\t\t;;\n',
        "\tjdcloud,re-ss-01)\n"
        '\t\tv "jdcloud,re-ss-01 为 eMMC 设备，请通过 U-Boot Web 不死界面刷入 factory 镜像"\n'
        "\t\treturn 1\n"
        "\t\t;;\n",
        before=True,
    )

    # 复核
    for p in (NET, PLAT):
        t = open(p, encoding="utf-8").read()
        if MARKER not in t:
            sys.exit("!! 注入后仍未找到 %s: %s" % (MARKER, p))
    print("  [ ok ] 复核通过")


if __name__ == "__main__":
    main()
